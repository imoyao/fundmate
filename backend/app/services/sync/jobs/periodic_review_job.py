# -*- coding: utf-8 -*-
# app/services/sync/jobs/periodic_review_job.py
"""定期复盘报告（周/月/季/年）生成落账任务（#875 页面形态第一期）。

把「最近一个数据就绪的自然周期」的复盘结果算好落库（``periodic_review_reports``），
供消息提醒与复盘页读快照。纯本地计算、零外部请求，用 NullAdapter 占位
（与 asset_snapshot_job / orphan_backfill 同范式）。

触发时机语义（owner 拍板，见方案文档 §4）
----------------------------------------
报告**不能按时钟生成，要按数据就绪生成**——只有该周期最后一个交易日的净值已落库，
统计出来的数字才是完整的。故本 job 排在本机每日调度的净值落库（fund_nav 21:30）
**之后**（cron 见 daily_scheduler）。job 内部按「最后交易日净值是否已到」判定：

- 「今天所属的自然周期」最后交易日 ``end_trading_day``（从自然周期终点向前回退）；
- 仅当 ``today >= end_trading_day``（该周期最后一个交易日已到 / 已过）**且**
  ``daily_worth`` 存在 ``date == end_trading_day`` 的净值 ⇒ 就绪，生成该期报告；
- 否则跳过（下一天再判），**不误报完整**（QDII 延迟 / 源延迟诚实降级）。

这样「周五汇总」落地为：周五 21:30 净值落库 → 21:45 本 job 判定周五是本周最后交易日
且净值已到 → 生成**本周**周报；周六/周日/次周一重复跑时幂等跳过。月末/季末/年末同理。

幂等：生成按 ``(family_id, ledger_id, period_kind, period_key)`` upsert，
重复跑只覆盖不新增；「是否已生成」由服务层查表判断，job 不另记状态。
"""

import datetime as dt
import json
from typing import Any, Dict, List, Optional

from app.core.time_utils import today_shanghai
from app.core.trading_calendar import is_trading_day
from app.services.adapters.null_adapter import NullAdapter
from app.services.analytics.period_key import (
    PERIOD_KINDS,
    period_bounds,
    period_key_of,
    resolve_last_trading_day,
)
from app.services.job_base import JobStatus, SyncJob
from app.services.periodic_review_notify import emit_periodic_report_notice
from app.services.periodic_review_service import generate_and_store


def _due_period_key(today: dt.date, kind: str) -> Optional[str]:
    """今天所属自然周期是否「已到最后一个交易日」——是则返回该周期键，否则 None。

    判据：``today >= 该自然周期最后一个交易日``。周末/月末/季末/年末恰逢休市时，
    最后交易日 = 向前回退到最近的交易日；``today`` 一旦到了/过了那一天，即可生成。
    """
    key = period_key_of(today, kind)
    _, end = period_bounds(key, kind)
    end_trading_day = resolve_last_trading_day(end, is_trading_day)
    if end_trading_day is None or today < end_trading_day:
        return None
    return key


class PeriodicReviewJob(SyncJob):
    """定期复盘报告生成落账（家庭/账户两级，四粒度）"""

    def __init__(self, db):
        # 纯本地计算，无外部数据源，NullAdapter 占位
        super().__init__(NullAdapter(), db)

    def get_name(self) -> str:
        return 'periodic_review'

    # run() 已重写，以下抽象方法仅满足 ABC 要求、运行期不被调用
    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return raw_data

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    def _family_ids(self) -> List[int]:
        """枚举全部 family_id（从 user 域 Ledger 表去重）。"""
        from app.domains.ledgers.models import Ledger

        rows = self.db.query(Ledger.family_id).distinct().all()
        return sorted({r[0] for r in rows if r[0] is not None})

    def _nav_ready(self, end_trading_day) -> bool:
        """该交易日净值是否已落库（``daily_worth`` 有该日任何一条净值即可）。"""
        from app.domains.funds.models import DailyWorth

        return self.db.query(DailyWorth.id).filter(DailyWorth.date == end_trading_day).first() is not None

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        self._full_sync_flag = full_sync
        self.logger.info('开始定期复盘报告生成落账')
        family_ids = self._family_ids()
        if not family_ids:
            self.status = JobStatus.SUCCESS
            self.stats = {'total': 0, 'success': 0, 'skipped': 0, 'failed': 0, 'errors': []}
            return self._build_result()

        today = today_shanghai()
        generated = 0
        failed = 0
        errors: List[str] = []
        for fid in family_ids:
            for kind in PERIOD_KINDS:
                period_key = _due_period_key(today, kind)
                if period_key is None:
                    continue  # 该周期最后一个交易日还没到，跳过
                try:
                    self._generate_one(fid, kind, period_key)
                    generated += 1
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    errors.append(f'family_id={fid} kind={kind} key={period_key}: {e}')
                    self.logger.exception(f'报告生成失败（family_id={fid} {kind} {period_key}）: {e}')
                    self.db.rollback()
        self.status = JobStatus.SUCCESS if failed == 0 else JobStatus.FAILED
        self.stats = {
            'total': len(family_ids) * len(PERIOD_KINDS),
            'success': generated,
            'skipped': 0,
            'failed': failed,
            'errors': errors,
        }
        self.logger.info(f'定期复盘报告生成完成，成功 {generated}，失败 {failed}')
        return self._build_result()

    def _generate_one(self, family_id: int, kind: str, period_key: str) -> None:
        """生成某一家庭某一粒度某周期的报告（最后交易日净值已就绪才落库）。"""
        start, end = period_bounds(period_key, kind)
        # 周期最后交易日：从自然周期终点向前回退到最近的交易日
        end_trading_day = resolve_last_trading_day(end, is_trading_day)
        if end_trading_day is None:
            self.logger.warning(f'周期 {kind} {period_key} 找不到最后交易日，跳过（日历未覆盖？）')
            return
        if not self._nav_ready(end_trading_day):
            self.logger.info(f'周期 {kind} {period_key} 最后交易日 {end_trading_day} 净值未落库，跳过（下一天再判）')
            return
        # 家庭级报告（ledger_id=None）
        row = generate_and_store(self.db, family_id, kind, period_key, ledger_id=None)
        # 生成成功后落一条 category=report 的站内通知（同期间幂等去重）。
        payload = json.loads(row.payload) if row.payload else None
        emit_periodic_report_notice(self.db, family_id, kind, period_key, payload=payload)
        self.db.commit()
