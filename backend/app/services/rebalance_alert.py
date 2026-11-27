# -*- coding: utf-8 -*-
"""调仓聚合提醒（#3258 ·「调仓解读付费功能」L1 监控提醒链路）。

## 定位

用户关注（自选 `asset_type=portfolio`）的投顾组合发生调仓后，主动聚合提醒「你关注的
产品调仓了」。这是「调仓解读」付费功能的第一环——没有它，L4 解读做得再好也没人触发。

本模块只负责**「检测 + 聚合 + 落通知」**，不碰调仓数据抓取（那是
`sync/jobs/advisor_portfolio_job.py` 的事）、不做深度解读（那是 L4）、不做自动跟调
（代客理财红线）。

## 职责边界（与抓取 job 的分工）

- 抓取 job（`advisor_portfolio_job`）落库时**就地 diff** 出「本轮新增了调仓的组合」，
  把 ``{组合 code → 新增调仓日期列表}`` 传进来；
- 本模块把这些「新调仓」收口成**一条聚合提醒**（多组合同期调仓合并，不逐组合刷屏），
  走 `notification_service.emit_many` 落 `notifications`，`category=调仓`。

为什么「检测」放 job、「聚合+落库」放这里：检测依赖落库前后的 diff，逻辑天然属于
落库方；聚合与通知是独立业务，且未来可能有其它触发源（手动补录），收口成独立服务
便于复用与单测。

## 聚合口径（2026-11-25 拍板，勿自行改）

1. **关注组合口径** = 自选里 `asset_type=portfolio` 的**全部**投顾组合（不做 favorite 过滤）；
2. **一条聚合**：同一天关注到的所有组合调仓合并为**一条**通知，标题客观陈述
   「N 个组合调仓」，正文列出组合名 + 调仓日期，**不含**投资建议措辞；
3. **dedup 一天一条**：`dedup_key` 含日期（`rebalance:<family_id>:<date>`），
   同一天重复触发只留一条——由 `notification_service.emit_many` 的先查后插 + 唯一约束保证。

## 合规（design §2）

title / body 只陈述「某组合于某日调仓」这一客观事实，禁止「建议买入/卖出/替换」。
措辞由本模块产出，`output_filter` 不在此链路上（通知不是 LLM 产出，是代码拼的客观陈述）。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from app.core.notification_categories import (
    NotificationCategory,
    NotificationSourceType,
)
from app.services import notification_service

#: 通知 category：消息箱第 4 个 Tab「调仓」（前端 lay-notice 的 noticeTabs 与之对齐）。
#: 真相源：app/core/notification_categories.py（category 收敛，#875）。
CATEGORY_REBALANCE = NotificationCategory.REBALANCE.value

#: 通知 source_type：调仓提醒（区别于已有的 allocation_deviation）。
SOURCE_TYPE_REBALANCE = NotificationSourceType.ADVISOR_REBALANCE.value

#: 通知级别：P1（消息盒，不抢首页横栏）。
LEVEL_REBALANCE = 'P1'

#: 聚合标题里最多列出的组合数；超出用「等 N 个」收口，避免超长。
_MAX_NAMED = 3

#: 单条 body 里列出的组合上限（超出折叠为计数）。
_MAX_BODY_NAMED = 8


def _build_dedup_key(family_id: int, day: Optional[date] = None) -> str:
    """去重键：`rebalance:<family_id>:<date>`。

    家庭级聚合去重——同一天同一家庭只产生一条「调仓」提醒，而不是每个组合一条。
    日期是节流粒度（同一天至多一条），跨天是新的提醒。
    """
    return f'rebalance:{family_id}:{(day or date.today()).isoformat()}'


def _portfolio_display_names(db, codes: Iterable[str]) -> Dict[str, str]:
    """组合 code → 组合名（缺名时回退 code 本身）。

    只查一次、O(1) 回表，避免在聚合里逐个组合发查询。
    """
    from app.domains.funds.models import AdvisorPortfolio

    uniq = list(dict.fromkeys(c for c in codes if c))
    if not uniq:
        return {}
    rows = db.query(AdvisorPortfolio.code, AdvisorPortfolio.name).filter(AdvisorPortfolio.code.in_(uniq)).all()
    return {code: (name or code) for code, name in rows}


def _aggregate_title(count: int, names: List[str]) -> str:
    """客观陈述标题：「N 个你关注的组合于 D 日调仓」。

    不含指令性措辞（不写「速看」「赶紧」），只陈述事实。
    """
    if count <= 0:
        return '你关注的组合有调仓'
    if count == 1:
        return f'你关注的组合「{names[0]}」有调仓'
    head = '、'.join(names[:_MAX_NAMED])
    tail = f'等 {count} 个' if count > _MAX_NAMED else f'{count} 个'
    return f'你关注的 {tail}组合（{head}）有调仓'


def _aggregate_body(adjustments: List[Dict[str, Any]], names: Dict[str, str]) -> str:
    """正文：逐组合列出「名称 + 调仓日期」，超长折叠为计数。

    每条形如「远足 · 2026-11-24 调仓」，客观罗列，不评价方向。
    """
    lines: List[str] = []
    for item in adjustments[:_MAX_BODY_NAMED]:
        code = item.get('code', '')
        day = item.get('adjust_date') or ''
        lines.append(f'{names.get(code, code)} · {day} 调仓')
    if len(adjustments) > _MAX_BODY_NAMED:
        lines.append(f'…等 {len(adjustments)} 个组合')
    return '\n'.join(lines)


def emit_rebalance_alerts(
    db,
    family_id: int,
    adjustments: List[Dict[str, Any]],
) -> int:
    """把「本轮新调仓」聚合为通知落库，返回新建条数（0 表示无新调仓或已存在）。

    Args:
        db: 路由会话（job 落库的同一会话）。
        family_id: 家庭 ID。
        adjustments: ``[{'code': 组合代码, 'adjust_date': 'YYYY-MM-DD'}, ...]``，
            由抓取 job 落库时 diff 产出；空列表表示本轮无新调仓。

    Returns:
        `notification_service.emit_many` 的新建条数（0 或 1）。

    空集契约（验收标准）：无新调仓时**不产生空通知**——adjustments 为空直接返回 0。
    """
    if not adjustments:
        return 0

    # 去重保序：同组合同一天只算一次（job 可能同组合多笔调仓行共用同一 adjust_date）。
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for item in adjustments:
        key = (item.get('code'), item.get('adjust_date'))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    if not deduped:
        return 0

    names = _portfolio_display_names(db, (item.get('code', '') for item in deduped))
    ordered_names = [names.get(item.get('code', ''), item.get('code', '')) for item in deduped]

    title = _aggregate_title(len(deduped), ordered_names)
    body = _aggregate_body(deduped, names)

    candidate = {
        'level': LEVEL_REBALANCE,
        'category': CATEGORY_REBALANCE,
        'title': title[:120],
        'body': body[:500],
        'dedup_key': _build_dedup_key(family_id),
        'source_type': SOURCE_TYPE_REBALANCE,
        # 多组合聚合，source_key 不指向单一组合；放「本次调仓组合数」便于前端深链兜底。
        'source_key': ','.join(item.get('code', '') for item in deduped)[:80],
    }

    created = notification_service.emit_many(db, family_id, [candidate])
    if created:
        logger.info(
            f'[rebalance_alert] family={family_id} 生成调仓聚合提醒：{len(deduped)} 个组合 （{ordered_names[:3]}）'
        )
    return created


def emit_for_watched_families(db, new_adjusts: List[Dict[str, Any]]) -> int:
    """把抓取 job 落库 diff 出的新调仓，按「关注了该组合的家庭」分发聚合提醒。

    这是 L1 挂钩的**唯一入口**：抓取 job 落库后 diff 出 ``[{code, adjust_date}]``，
    传进来即可。本函数负责：

    1. 查自选 ``asset_type=portfolio`` 命中本轮调仓组合的家庭（按 family 分组）；
    2. 逐家庭调用 :func:`emit_rebalance_alerts` 生成一条聚合提醒；
    3. 提交通知写入（``notification_service.emit_many`` 只 flush 不 commit，
       请求路径由外层事务收口，这里 job 无后续提交点，须显式 commit）。

    Returns:
        实际新建的通知条数（0 = 无人关注或本轮无新调仓）。
    """
    if not new_adjusts:
        return 0

    from app.domains.watchlist.models import WatchlistItem

    codes = list({a['code'] for a in new_adjusts})
    rows = (
        db.query(WatchlistItem.family_id, WatchlistItem.symbol)
        .filter(WatchlistItem.asset_type == 'portfolio', WatchlistItem.symbol.in_(codes))
        .all()
    )
    by_family: Dict[int, set] = {}
    for family_id, symbol in rows:
        by_family.setdefault(int(family_id), set()).add(symbol)
    if not by_family:
        return 0

    by_code = {a['code']: a['adjust_date'] for a in new_adjusts}
    emitted = 0
    for family_id, watched in by_family.items():
        adjustments = [
            {'code': code, 'adjust_date': by_code[code].isoformat()}
            for code in watched
            if code in by_code and by_code[code] is not None
        ]
        if adjustments:
            emitted += emit_rebalance_alerts(db, family_id, adjustments)
    if emitted:
        db.commit()
    return emitted


def adjust_dates(db, portfolio_id: int) -> set:
    """某投顾组合现有调仓日期集合（``advisor_adjust_histories.adjust_date``）。

    供抓取 job 在落库前后各取一次、diff 出「本轮新增调仓」用。放在本模块而非 job，
    是为了让 job 文件不因这个 helper 顶破 ``guard_service_size`` 的冻结基线。
    """
    from app.domains.funds.models import AdvisorAdjustHistory

    rows = db.query(AdvisorAdjustHistory.adjust_date).filter(AdvisorAdjustHistory.portfolio_id == portfolio_id).all()
    return {d for (d,) in rows if d is not None}


__all__ = [
    'CATEGORY_REBALANCE',
    'SOURCE_TYPE_REBALANCE',
    'LEVEL_REBALANCE',
    'emit_rebalance_alerts',
    'emit_for_watched_families',
    'adjust_dates',
]
