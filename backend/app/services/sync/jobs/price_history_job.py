# -*- coding: utf-8 -*-
"""证券历史行情同步任务（场内日线：股票 / ETF / 可转债）。

## 增量口径 = 缺口回补（#1104）

增量模式的起点是**每个 symbol 库内最新交易日的次日**，而不是固定的「昨天→今天」。
原写法（写死昨天→今天）没有任何自愈能力：任何一天没跑成功，那天就永久缺失且
再也不会被补。实测后果是各标的最后日期散落成满天星——SH601899 停在 8/14、
SZ000568 停在 7/20、SZ000001 停在 7/03、SZ000008 停在 5/29。本机调度不含本 job
（只靠 CI 每天 17:00 UTC 跑一次）时，这种断档尤其常见。

## 覆盖范围

目标池由 Orchestrator 传入（持仓 + 自选，`resolve_targets()` 的 stock 池）。
取数与复权口径见 `AkshareAdapter.fetch_stock_price`：`close` 未复权（展示 / 盈亏）、
`adj_close` 前复权（区间收益 / 回撤）。

## 注意

- ETF 两个数据源（东财 / 新浪）的**当日** K 线都要到次日才齐，故当天盘后跑往往
  只拿到 T-1；缺口回补会在下一次运行时把缺的那天补上，这正是本口径的价值。
- 依赖 securities 表存在对应 symbol（`_get_security_map`），查不到即静默跳过——
  名录缺失是历史坑，见 StockListSyncJob.fetch_security_catalog。
"""

from datetime import date, datetime, timedelta
from typing import List, Optional

from loguru import logger
from sqlalchemy import func

from app.core.time_utils import today_shanghai
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.job_base import IN_CHUNK_SIZE, SyncJob

# 库内无任何历史时的首次回补窗口（天）。更长的历史走全量同步（full_sync=True）
DEFAULT_BACKFILL_DAYS = 365


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
        """全量：拉取所有历史；增量：按各 symbol 的库内最新交易日做缺口回补。"""
        sec_map = self._get_security_map(targets)
        if not sec_map:
            return []

        today = today_shanghai()
        last_map = {} if full_sync else self._load_last_trade_dates(list(sec_map.keys()))

        records = list()
        for symbol in targets:
            sec = sec_map.get(symbol)
            if not sec:
                continue

            start_date, end_date = self._resolve_window(symbol, last_map, today, full_sync)
            if start_date is not None and start_date > end_date:
                # 已是最新：多见于「当日 K 线尚未发布」，留给下一次运行补
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

    @staticmethod
    def _resolve_window(symbol: str, last_map: dict, today: date, full_sync: bool):
        """本次抓取窗口 (start, end)：全量不限；增量从「库内最新交易日的次日」起。

        `start > end` 表示无需抓取（库内已到最新），由调用方跳过。
        """
        if full_sync:
            return None, None
        last = PriceHistorySyncJob._as_date(last_map.get(symbol))
        if last is None:
            # 首次同步该标的：回补近一年，更长的历史走 full_sync
            return today - timedelta(days=DEFAULT_BACKFILL_DAYS), today
        return last + timedelta(days=1), today

    def _load_last_trade_dates(self, symbols: List[str]) -> dict:
        """批量取 {symbol: 库内最新交易日}；分批 in_ 防 SQLite 变量上限。"""
        out: dict = {}
        for i in range(0, len(symbols), IN_CHUNK_SIZE):
            chunk = symbols[i : i + IN_CHUNK_SIZE]
            rows = (
                self.db.query(PriceHistory.symbol, func.max(PriceHistory.trade_date))
                .filter(PriceHistory.symbol.in_(chunk))
                .group_by(PriceHistory.symbol)
                .all()
            )
            for symbol, last in rows:
                if last is not None:
                    out[symbol] = last
        return out

    @staticmethod
    def _as_date(value) -> Optional[date]:
        """宽松转 date：SQLite 的 max() 在个别驱动下会回传字符串而非 date。"""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

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
