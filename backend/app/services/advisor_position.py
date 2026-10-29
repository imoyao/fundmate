# -*- coding: utf-8 -*-
"""投顾组合持仓 ↔ 主理人调仓的只读关联（D70 / #2740）。

## 为什么单独一层

投顾组合**持仓**在 user 域（`positions`），组合元信息与调仓明细在 market 域
（`advisor_portfolios` / `advisor_adjust_histories`）。两域是独立引擎，不能 SQL join
（AGENTS.md「跨域零外键、零 SQL join」），只能按业务键 `symbol` 走「应用层两步法」：
先按持仓拿到 `code`，再用 `code` 查 market 域。

`get_db()` 拿到的是 `_RoutingSession`，同一请求内会**按表所属域**逐句路由，所以这两步
可以共用同一个 session；但仍是两次独立查询，绝不拼成 join。

## 为什么不重写查询

调仓口径已定稿（`decisions.md`：#1622 / 0.5pp 阈值、不写持平行、且慢按持仓快照序列
推导、天天来自官方接口）。`FundService.build_advisor_adjusts` 就是那套口径的唯一实现，
这里只做「持仓 → 组合码 → 调仓」的取数编排，避免长出第二套判定。
"""

from __future__ import annotations

from loguru import logger

from app.services.fund_service import FundService

# 持仓视角默认只取最近 3 个调仓日：这是**提示位**不是明细页，多了会把持仓本身挤下去。
# 与 `/api/funds/advisors/<code>/adjusts/` 的缺省 10 故意不同（那个接口就是明细页）。
DEFAULT_ADJUST_LIMIT = 3
MAX_ADJUST_LIMIT = 50


def parse_adjust_limit(raw: str | None) -> int:
    """把请求里的 ``limit`` 夹取到 ``[1, MAX_ADJUST_LIMIT]``，非法值回落默认。

    夹取留在服务层而不是视图：这是**口径**（提示位最多看几个调仓日），不是 HTTP 解析。
    非法 / 负 / 超上限一律按「用户没传好」处理并回落默认，而不是 400——
    调仓提示是可选信息，参数写得不对不该让整个持仓详情页报错。
    """
    try:
        return max(1, min(MAX_ADJUST_LIMIT, int(raw if raw is not None else DEFAULT_ADJUST_LIMIT)))
    except (TypeError, ValueError):
        return DEFAULT_ADJUST_LIMIT


def build_advisor_context(db, position, limit: int = DEFAULT_ADJUST_LIMIT) -> dict | None:
    """组装某投顾组合持仓的主理人上下文；组合不在 market 域时返回 ``None``。

    **返回 None 而不是抛错**是刻意选择：组合主数据是否已同步是**市场域的数据完整性**
    问题，与「这笔记账对不对」无关。缺了它，持仓金额、市值、成本、盈亏全部照常
    （数据策略：参考展示类按需取 + 可降级）。把它判成 500 会让用户以为自己的账坏了。

    Args:
        db: 请求级 session（`_RoutingSession`，按表路由两域）。
        position: `Position` 实例；调用方须先确认 `asset_type == 'portfolio'`
            （本函数也做一次防御，写错调用点时不至于静默查出别人的组合）。
        limit: 最近 N 个调仓日（视图层已 clamp 到 [1, MAX_ADJUST_LIMIT]）。

    Returns:
        ``{position_id, code, name, platform, adjusts}``；组合查不到时 ``None``。

    Raises:
        ValueError: 传入的不是投顾组合持仓（调用点写错，属编程错误而非数据缺失）。
    """
    if getattr(position, 'asset_type', None) != 'portfolio':
        raise ValueError('仅投顾组合持仓有主理人调仓上下文')

    code = (getattr(position, 'symbol', '') or '').strip()
    if not code:
        # 没有业务键就无从关联；不猜（同理 symbol_identity 对空 symbol 返回空串）。
        return None

    try:
        payload = FundService.build_advisor_adjusts(db, code, limit, None)
    except ValueError:
        # `advisor_portfolios` 里没有这个 code：本地从未同步该组合（或平台已下线）。
        logger.debug(
            '投顾组合不在 market 域，跳过调仓提示: position={} code={}',
            getattr(position, 'id', None),
            code,
        )
        return None

    return {
        'position_id': getattr(position, 'id', None),
        'code': payload.get('code') or code,
        'name': payload.get('name'),
        'platform': payload.get('platform'),
        'adjusts': payload.get('adjusts') or [],
    }
