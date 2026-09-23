# -*- coding: utf-8 -*-
"""探市大类资产日频快照同步任务（#1460 P1）。

把「大类资产观察」20 个品种 + 债券 10Y 收益率轨的**每日快照**落库，
使 /api/market/overview 由「每次请求实时拉全量历史现算」改为「读库组装」。

设计要点：
- 取数复用 MarketOverviewService.get_overview(force_refresh=True)：指标口径
  （当日涨跌 / 相对位置分位 / ⚡ 异动双线）与接口完全一致，不在此重算，
  避免「库里的值」与「实时算的值」两套口径。
- 落库复用 market_snapshot_store.save_overview_to_db：写入语义（upsert、软占位
  处理）只有一处实现，接口兜底回写走同一条路径。
- 长历史日线序列**不落库**：仅在取数过程中临时使用、算完即弃（#1460 第 2 步待定）。
"""

from typing import Any, Dict, List

from loguru import logger

from app.services.job_base import SyncJob
from app.services.market_service import MarketOverviewService
from app.services.market_snapshot_store import save_overview_to_db


def _filter_overview(overview: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    """按资产 key 过滤 overview（外部传入 targets 时只落指定品种）。"""
    filtered = dict(overview)
    groups = []
    for group in overview.get('groups') or []:
        assets = [a for a in (group.get('assets') or []) if a.get('key') in keys]
        if assets:
            groups.append({**group, 'assets': assets})
    filtered['groups'] = groups
    return filtered


class MarketAssetDailySyncJob(SyncJob):
    """每日快照落库：20 个大类资产 + 债券收益率轨。"""

    batch_size = 20

    @property
    def _allow_empty_data(self) -> bool:
        # 非交易日 / 源端整体不可用时静默跳过，不阻断整体同步
        return True

    def get_name(self) -> str:
        return 'market_asset_daily'

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[Dict[str, Any]]:
        keys = [t for t in (targets or []) if t and t != '__full__'] or None

        # force_refresh=True：本 job 是「当日权威写入者」，必须取实时值而非进程缓存
        overview = MarketOverviewService.get_overview(force_refresh=True)
        if keys:
            overview = _filter_overview(overview, keys)
        return [overview]

    # ── 校验 / 去重 ──

    def _validate_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [o for o in raw_data if o.get('groups')]

    def _deduplicate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 单次取数即一份完整 overview，天然无重复
        return data[:1]

    # ── 落库 ──

    def _save_data(self, new_data: List[Dict[str, Any]]) -> None:
        for overview in new_data:
            save_overview_to_db(self.db, overview)
        # 非请求上下文：store 只 flush，此处由 job 显式提交
        self.db.commit()
        logger.info('大类资产日频快照已落库')
