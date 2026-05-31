# -*- coding: utf-8 -*-
"""
证券历史行情同步任务。
增量模式接收 Orchestrator 传入的 targets 列表。
全量模式拉取所有证券的全部历史（分批写入）。
"""

from datetime import date, timedelta
from typing import List

from loguru import logger

from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.sync.jobs.base import SyncJob


class PriceHistorySyncJob(SyncJob):
    def get_name(self) -> str:
        return 'price_history'

    @property
    def _allow_empty_data(self) -> bool:
        # 增量同步在非交易日或无目标时返回空是正常的
        return True

    # ── 目标代码获取 ──

    def _get_security_map(self, targets: List[str]) -> dict:
        """
        根据代码列表查询 securities 表，返回 {symbol: Security} 映射。
        用于将 symbol 转换为 security_id。
        """
        securities = self.db.query(Security).filter(Security.symbol.in_(targets)).all()
        return {s.symbol: s for s in securities}

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """
        全量同步：遍历所有目标证券，拉取全部历史行情。
        增量同步：只拉取最近一天的行情。
        """
        sec_map = self._get_security_map(targets)
        if not sec_map:
            return []

        if full_sync:
            # 全量：不限日期，拉取所有历史
            start_date = None
            end_date = None
        else:
            # 增量：只拉取昨天到今天的数据
            today = date.today()
            start_date = today - timedelta(days=1)
            end_date = today

        records = list()
        for symbol in targets:
            sec = sec_map.get(symbol)
            if not sec:
                continue

            try:
                price_list = self.adapter.fetch_stock_price(symbol, start_date=start_date, end_date=end_date)
            except Exception as e:
                logger.warning(f'获取 {symbol} 行情失败: {e}')
                continue

            if not isinstance(price_list, list):
                continue

            # 关联 security_id
            for item in price_list:
                item['security_id'] = sec.id
            records.extend(price_list)

        return records

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """清洗数据：必填字段检查、日期转换、默认值填充"""
        validated = list()
        for item in raw_data:
            if not item.get('security_id') or not item.get('trade_date') or item.get('close') is None:
                continue

            # 日期字符串转 date 对象
            if isinstance(item['trade_date'], str):
                try:
                    item['trade_date'] = date.fromisoformat(item['trade_date'])
                except ValueError:
                    continue

            # 可选字段默认值
            item.setdefault('open', None)
            item.setdefault('high', None)
            item.setdefault('low', None)
            item.setdefault('volume', None)
            item.setdefault('adj_close', item['close'])
            item.setdefault('source', self.adapter.get_name())
            validated.append(item)

        return validated

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """复合键去重: (security_id, trade_date)"""
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

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        if new_data:
            self.db.bulk_insert_mappings(PriceHistory, new_data)
            self.db.commit()
