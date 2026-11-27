# -*- coding: utf-8 -*-
"""定期复盘报告的站内通知发射（#875 页面形态第一期）。

生成服务（``periodic_review_service``）只负责「算 + 落快照」，通知发射另起本模块：
一是让生成链路保持纯计算、可脱离提醒独立复用；二是通知措辞（客观陈述、不含投资
建议）自成一条合规边界，收口在这里便于单测与审查。

对齐 ``rebalance_alert`` 范式：通过 ``notification_service.emit_many`` 落
``notifications``，``category=report`` / ``source_type=periodic_report``。

去重口径：``dedup_key`` 含 ``<kind>:<period_key>``（周期级，不含日期）——一周/月/季/年
只生成一次，同一期间重复触发只留一条；跨周期是新提醒。幂等由 ``emit_many`` 的
先查后插 + 唯一约束保证。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.notification_categories import (
    NotificationCategory,
    NotificationSourceType,
)
from app.services import notification_service
from app.services.analytics.period_key import period_bounds

#: 通知 category：消息盒第 5 个 Tab「报告」（前端 lay-notice 的 noticeTabs 与之对齐）。
#: 真相源：app/core/notification_categories.py（category 收敛，#875）。
CATEGORY_REPORT = NotificationCategory.REPORT.value

#: 通知 source_type：周期报告已生成（区别于 allocation_deviation / advisor_rebalance）。
SOURCE_TYPE_PERIODIC_REPORT = NotificationSourceType.PERIODIC_REPORT.value

#: 通知级别：P1（消息盒，不抢首页横栏——报告非紧急告警）。
LEVEL_REPORT = 'P1'

#: 期间类型 → 中文名（标题 / 正文用）。
_PERIOD_LABEL = {'week': '周报', 'month': '月报', 'quarter': '季报', 'year': '年报'}


def _period_display_name(period_kind: str, period_key: str) -> str:
    """期间键 → 人类可读中文名（含粒度词），如 ``2026-11`` → ``2026年11月月报``。

    粒度词（周报/月报/季报/年报）拼进名字里，标题一眼可辨「这是哪种报告」。
    """
    label = _PERIOD_LABEL.get(period_kind, period_kind)
    if period_kind == 'week':
        year, _, week = period_key.partition('-W')
        return f'{year}年第{int(week)}周{label}'
    if period_kind == 'month':
        year, month = period_key.split('-')
        return f'{year}年{int(month)}月{label}'
    if period_kind == 'quarter':
        year, _, q = period_key.partition('-Q')
        return f'{year}年第{int(q)}季度{label}'
    if period_kind == 'year':
        return f'{period_key}年{label}'
    return f'{period_key}{label}'


def _build_dedup_key(family_id: int, period_kind: str, period_key: str) -> str:
    """去重键：``periodic_report:<family_id>:<kind>:<period_key>``（周期级，不含日期）。"""
    return f'periodic_report:{family_id}:{period_kind}:{period_key}'


def _format_rate(rate: Optional[float]) -> Optional[str]:
    """区间收益率 → 带符号百分比文案（``None`` 表示不可算）。"""
    if rate is None:
        return None
    sign = '+' if rate >= 0 else ''
    return f'{sign}{rate:.2f}%'


def emit_periodic_report_notice(
    db: Session,
    family_id: int,
    period_kind: str,
    period_key: str,
    payload: Optional[Dict[str, Any]] = None,
) -> int:
    """报告生成成功后，落一条 ``category=report`` 的站内通知，返回新建条数（0 或 1）。

    Args:
        db: 路由会话（与生成落库同一会话）。
        family_id: 家庭 ID。
        period_kind: 期间类型（week/month/quarter/year）。
        period_key: 期间键（``2026-W48`` / ``2026-11`` / ``2026-Q4`` / ``2026``）。
        payload: 已生成的报告 payload（用于取区间收益率拼正文）；缺省时正文只陈述「已生成」。

    Returns:
        ``notification_service.emit_many`` 的新建条数（0 = 该期已发过）。

    措辞合规：标题/正文只陈述「某期报告已生成 + 客观收益数字」，禁止「建议加仓/减仓/
    赎回」等指令性措辞。
    """
    display = _period_display_name(period_kind, period_key)
    title = f'你的{display}已生成'

    # 正文客观陈述区间收益；收益率不可算（无持仓 / 无基准）时只陈述「已生成」。
    rate = None
    if payload:
        excess = payload.get('excess') or {}
        rate = excess.get('range_rate')
    rate_text = _format_rate(rate)
    if rate_text is not None:
        start, end = period_bounds(period_key, period_kind)
        body = f'{start.isoformat()} ~ {end.isoformat()} 区间收益 {rate_text}。点击查看复盘详情。'
    else:
        body = f'你的{display}已生成，点击查看复盘详情。'

    candidate = {
        'level': LEVEL_REPORT,
        'category': CATEGORY_REPORT,
        'title': title[:120],
        'body': body[:500],
        'dedup_key': _build_dedup_key(family_id, period_kind, period_key),
        'source_type': SOURCE_TYPE_PERIODIC_REPORT,
        # source_key 放期间键，便于前端深链到对应期间。
        'source_key': period_key[:80],
    }

    created = notification_service.emit_many(db, family_id, [candidate])
    if created:
        logger.info(
            '[periodic_review_notify] family={} 生成 {}{} 通知：{}',
            family_id,
            period_kind,
            period_key,
            title,
        )
    return created


__all__ = [
    'CATEGORY_REPORT',
    'SOURCE_TYPE_PERIODIC_REPORT',
    'LEVEL_REPORT',
    'emit_periodic_report_notice',
]
