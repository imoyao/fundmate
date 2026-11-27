# -*- coding: utf-8 -*-
"""定期复盘报告（周/月/季/年）的生成与落库服务（#875 页面形态第一期）。

「定时生成」的语义 = 把**那一刻的账定格**成快照：生成时把区间收益 / 基准超额 /
逐品种归因 / 逐日曲线算好，落 ``periodic_review_reports``。消息提醒与复盘页读的都是
这份快照（缺则现算兜底），而不是每次打开都重算——否则「生成时提醒你的那一期」
会随其后改持仓而变化，消息就失去了意义。

口径唯一（复用既有地基，**本模块不另起炉灶算账**）：

- 「这段赚了多少 + 和基准比 + 逐日曲线」→ ``analytics.benchmark_excess.build_scope_excess``
  （``range_rate`` / ``range_pnl`` / ``excess_return`` / ``series``，唯一口径 #2134）；
- 「谁拖后腿」→ ``pnl_calendar.compute_range_attribution``（``positions`` 按 |pnl| 降序、
  ``categories`` 大类归因，``Σ positions[].pnl ≡ 区间合计``，唯一口径 #2135）；
- 期间键 / 起止日 → ``analytics.period_key``（自然周/月/季/年，唯一真相源）。

对齐 :class:`PnlDailySnapshot` 的范式：``CALIBER_VERSION`` 一改旧快照即作废重算、
幂等 upsert（同家庭同账户同粒度同期间键唯一）。
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.domains.summary.models import PeriodicReviewReport
from app.services.analytics.benchmark_excess import build_scope_excess
from app.services.analytics.period_key import PERIOD_KINDS, period_bounds
from app.services.pnl_calendar import compute_range_attribution

# 报告口径版本号：归因/超额算法一改，这里 +1，旧快照全部作废重算。
# 与 PeriodicReviewReport.caliber_version 对照，不符即读侧现算覆盖。
CALIBER_VERSION = 1


def resolve_period(period_kind: str, period_key: str) -> tuple[dt.date, dt.date]:
    """期间键 → 起止日 ``(start, end)``；非法类型/键抛 ``ValueError``。"""
    if period_kind not in PERIOD_KINDS:
        raise ValueError(f'非法期间类型：{period_kind!r}（合法值 {PERIOD_KINDS}）')
    return period_bounds(period_key, period_kind)


def _build_payload(
    db: Session,
    family_id: int,
    start: dt.date,
    end: dt.date,
    ledger_id: Optional[int],
) -> Dict[str, Any]:
    """组装一份报告 payload：区间绩效 + 基准超额 + 品种归因。

    不落库、不 commit——纯计算，供生成与「缺则现算兜底」两条路径共用。
    """
    excess = build_scope_excess(db, family_id, start.isoformat(), end.isoformat(), ledger_id=ledger_id)
    attribution = compute_range_attribution(
        db,
        family_id,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        ledger_id=ledger_id,
    )
    return {
        # 区间绩效（赚多少 + 和基准比 + 逐日曲线）
        'excess': excess,
        # 谁拖后腿（逐品种 + 大类归因）
        'attribution': attribution,
    }


def _serialize(payload: Dict[str, Any]) -> str:
    """payload → 单列 JSON 文本（ensure_ascii=False 保中文可读）。"""
    return json.dumps(payload, ensure_ascii=False)


def _deserialize(raw: str) -> Dict[str, Any]:
    return json.loads(raw)


def write_report(
    db: Session,
    family_id: int,
    period_kind: str,
    period_key: str,
    start: dt.date,
    end: dt.date,
    payload: Dict[str, Any],
    ledger_id: Optional[int] = None,
) -> PeriodicReviewReport:
    """幂等 upsert 一份报告快照，返回该行（不 commit，由调用方提交）。"""
    row = (
        db.query(PeriodicReviewReport)
        .filter(
            PeriodicReviewReport.family_id == family_id,
            PeriodicReviewReport.ledger_id == ledger_id,
            PeriodicReviewReport.period_kind == period_kind,
            PeriodicReviewReport.period_key == period_key,
        )
        .first()
    )
    serialized = _serialize(payload)
    if row is None:
        row = PeriodicReviewReport(
            family_id=family_id,
            ledger_id=ledger_id,
            period_kind=period_kind,
            period_key=period_key,
            start_date=start,
            end_date=end,
            payload=serialized,
            caliber_version=CALIBER_VERSION,
        )
        db.add(row)
    else:
        row.start_date = start
        row.end_date = end
        row.payload = serialized
        row.caliber_version = CALIBER_VERSION
    db.flush()
    return row


def generate_and_store(
    db: Session,
    family_id: int,
    period_kind: str,
    period_key: str,
    ledger_id: Optional[int] = None,
) -> PeriodicReviewReport:
    """生成并落库一份报告（`ledger_id=None` 为家庭级）。

    幂等：同作用域同期间重复调用只覆盖不新增。不 commit（由调用方控制事务边界）。
    """
    start, end = resolve_period(period_kind, period_key)
    payload = _build_payload(db, family_id, start, end, ledger_id)
    return write_report(db, family_id, period_kind, period_key, start, end, payload, ledger_id=ledger_id)


def read_report(
    db: Session,
    family_id: int,
    period_kind: str,
    period_key: str,
    ledger_id: Optional[int] = None,
) -> Dict[str, Any]:
    """读一份报告快照；缺行或口径版本不符则**现算兜底**（#1926 验收 3 同源）。

    返回 ``(payload_dict, source)`` 语义——这里简化为返回 payload，并额外在
    payload 里不带落库元信息；调用方（读端点）自行决定是否要透出「来自快照/现算」。
    本函数保证：口径不符 / 缺行时，现算结果会覆盖落库（保证下次命中快照）。
    """
    row = (
        db.query(PeriodicReviewReport)
        .filter(
            PeriodicReviewReport.family_id == family_id,
            PeriodicReviewReport.ledger_id == ledger_id,
            PeriodicReviewReport.period_kind == period_kind,
            PeriodicReviewReport.period_key == period_key,
        )
        .first()
    )
    if row is not None and row.caliber_version == CALIBER_VERSION:
        return _deserialize(row.payload)

    # 缺行 / 口径不符：现算并回写（读路径不空白，#1926 验收 3）。
    logger.info(
        '定期复盘报告缺快照或口径不符，现算兜底：family={} kind={} key={} ledger={}',
        family_id,
        period_kind,
        period_key,
        ledger_id,
    )
    start, end = resolve_period(period_kind, period_key)
    payload = _build_payload(db, family_id, start, end, ledger_id)
    write_report(db, family_id, period_kind, period_key, start, end, payload, ledger_id=ledger_id)
    return payload
