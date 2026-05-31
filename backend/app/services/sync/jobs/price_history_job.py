# -*- coding: utf-8 -*-
"""证券历史行情同步（全量分批写入，增量走基类）"""

import time
from datetime import date, timedelta
from typing import Any, Dict, List

from loguru import logger

from app.core.time_utils import now_shanghai
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.domains.watchlist.models import WatchlistItem
from app.services.sync.jobs.base import JobStatus, SyncJob


class PriceHistorySyncJob(SyncJob):
    def get_name(self) -> str:
        return 'price_history'

    @property
    def _allow_empty_data(self) -> bool:
        """增量同步在非交易日或未添加标时返回空数据是正常的"""
        return True

    def _get_target_codes(self) -> List[str]:
        """获取本次应同步的股票代码（持仓 + 自选 + 系统指数）"""
        # 如果有 target_file_codes 属性，则使用文件中非纯6位数字的代码
        if hasattr(self, 'target_file_codes') and self.target_file_codes:
            return [c for c in self.target_file_codes if not (c.isdigit() and len(c) == 6)]

        codes = set()

        # 1. 持仓中的股票/ETF/可转债
        position_rows = (
            self.db.query(Position.symbol).filter(Position.asset_type.in_(['stock', 'etf', 'bond'])).distinct().all()
        )
        codes.update(row[0] for row in position_rows if row[0])

        # 2. 自选中的股票/ETF（排除纯6位数字）
        watchlist_rows = self.db.query(WatchlistItem.symbol).distinct().all()
        for row in watchlist_rows:
            code = row[0]
            if code and not (code.isdigit() and len(code) == 6):
                codes.add(code)

        # 3. 系统强制同步列表：主要基准指数 TODO: 指数接口暂时不可用，待后续实现指数专用 Job
        # system_codes = ["SH000001", "SZ399001", "SH000300", "SH000905"]
        system_codes = []
        codes.update(system_codes)

        return list(codes)

    def _get_securities(self) -> List[Security]:
        """获取需要同步行情的证券（股票、ETF、可转债）"""
        return self.db.query(Security).filter(Security.type.in_(['stock', 'etf', 'bond'])).all()

    # ---------- 增量同步（沿用基类标准流程） ----------

    def _fetch_data(self, full_sync: bool) -> List[dict]:
        if full_sync:
            # 全量：返回空，由自定义 run 处理
            logger.info('无持仓/自选股票，跳过行情同步')
            return []
        # 增量：使用目标代码列表
        target_codes = self._get_target_codes()
        if not target_codes:
            return []
        sec_map = {s.symbol: s.id for s in self.db.query(Security).filter(Security.symbol.in_(target_codes)).all()}
        records = []
        start_date = date.today() - timedelta(days=1)  # 昨天到今天
        for symbol in target_codes:
            try:
                items = self.adapter.fetch_stock_price(symbol, start_date=start_date, end_date=date.today())
                for item in items:
                    item['security_id'] = sec_map.get(symbol)
                records.extend(items)
            except Exception as e:
                self.logger.warning(f'增量获取 {symbol} 行情失败: {e}')
        return records

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """数据清洗与默认值填充"""
        validated = []
        for item in raw_data:
            if not item.get('security_id') or not item.get('trade_date') or item.get('close') is None:
                continue
            if isinstance(item['trade_date'], str):
                try:
                    item['trade_date'] = date.fromisoformat(item['trade_date'])
                except ValueError:
                    continue
            item.setdefault('open', None)
            item.setdefault('high', None)
            item.setdefault('low', None)
            item.setdefault('volume', None)
            item.setdefault('adj_close', item['close'])
            item.setdefault('source', self.adapter.get_name())
            validated.append(item)
        return validated

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """复合键去重 (security_id, trade_date)"""
        if not data:
            return []
        security_ids = list({item['security_id'] for item in data})
        existing = set(
            (row.security_id, row.trade_date)
            for row in self.db.query(PriceHistory.security_id, PriceHistory.trade_date)
            .filter(PriceHistory.security_id.in_(security_ids))
            .all()
        )
        return [item for item in data if (item['security_id'], item['trade_date']) not in existing]

    def _save_data(self, new_data: List[dict]) -> None:
        """批量写入并提交（每批一个事务）"""
        if new_data:
            self.db.bulk_insert_mappings(PriceHistory, new_data)
            self.db.commit()

    # ---------- 全量同步（自定义分批流程） ----------

    def run(self, full_sync: bool = False) -> Dict[str, Any]:
        batch_size = getattr(self, 'batch_size', 50)
        if not full_sync:
            # 增量：走基类标准四步流程
            return super().run(full_sync)

        # 全量：分批抓取、即时写入
        self._full_sync_flag = True
        self.snapshot_time = now_shanghai()
        self.status = JobStatus.RUNNING
        self._pre_run()
        self.logger.info('开始全量同步历史行情（分批模式）')

        securities = self._get_securities()
        total = len(securities)
        failed_stocks = []

        for i in range(0, total, batch_size):
            batch = securities[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size
            self.logger.info(f'全量进度: 批次 {batch_num}/{total_batches}')

            # 1. 抓取本批次数据
            batch_data = []
            for sec in batch:
                try:
                    records = self.adapter.fetch_stock_price(sec.symbol)
                    for rec in records:
                        rec['security_id'] = sec.id
                    batch_data.extend(records)
                except Exception as e:
                    self.logger.warning(f'获取 {sec.symbol} 行情失败: {e}')
                    failed_stocks.append(sec.symbol)
                    self.stats.setdefault('errors', []).append({'symbol': sec.symbol, 'error': str(e)})

            # 2. 校验、去重
            validated = self._validate_data(batch_data)
            new_data = self._deduplicate(validated)

            # 3. 写入（天然续传：已存在的记录会被 _deduplicate 跳过）
            if new_data:
                self._save_data(new_data)
                self.stats['success'] = self.stats.get('success', 0) + len(new_data)
            self.stats['total'] = self.stats.get('total', 0) + len(batch_data)
            self.stats['skipped'] = self.stats.get('skipped', 0) + len(validated) - len(new_data)
            self.stats['failed'] = len(failed_stocks)

            self.logger.info(
                f"批次 {batch_num} 完成: 新增 {len(new_data) if new_data else 0} 条，"
                f"累计新增 {self.stats['success']} 条"
            )

            # >>> 在这里加延迟，避免对数据源请求过密 <<<
            time.sleep(1.0)  # 批次间休息 1 秒

        if failed_stocks:
            self.logger.warning(f"以下股票获取失败: {', '.join(failed_stocks[:20])}...（共 {len(failed_stocks)} 只）")

        self._validate_integrity()
        self._post_run()
        self.status = JobStatus.SUCCESS
        self.logger.info(f"历史行情全量同步完成，总计新增 {self.stats['success']} 条记录")
        return self._build_result()
