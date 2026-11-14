# -*- coding: utf-8 -*-
# Author : imoyao
"""请求内复用：把「只依赖 family_id 的家庭级派生结果」在一次请求里只算一遍。

WHY（2026-11-14 真库实测：组合 1 / 6 个成员 / 5 年窗口 9.4s）
------------------------------------------------------------
组合级超额必须**逐成员**调 `pnl_calendar.build_daily_pnl_series`（口径可加性要求
Σ成员盈亏 ÷ Σ成员基线，见 `analytics/benchmark_excess`），但引擎里有一批派生结果
**与成员无关**：

- 状态判定集恒为家庭级全量（#1916：各作用域必须丢同一批天，否则差分基准错位）；
- `_price_presence` 的最新价组查（`MAX(trade_date) GROUP BY symbol/code`）；
- `_as_of_shares` 的全量流水。

三者逐成员重算 ⇒ 同一份 O(全量) 查询跑 N 遍。实测 6 成员 5 年窗口里约 2.5s 花在
重复的 `MAX()` 组查上（SQLite 对 `GROUP BY + MAX` 不做 min/max 优化，成本 O(行数)
而非 O(组数)，5 年窗口 ≈ 0.22s/次 × 10 次）。

为什么默认关闭、只在上下文里生效
--------------------------------
`Session.info` 活到**会话**结束，比一次请求长。写库后复用旧值会让「先算一遍 →
改数据 → 再算一遍」的测试与批跑拿到过期结果，而这类回归最难查。故缓存只在
`request_memo()` 里存在，退出即清空；其余调用方（单作用域端点、既有单测）走
`memoized()` 的空实现，行为逐位不变。
"""

from contextlib import contextmanager
from typing import Any, Callable

_MEMO_KEY = '_family_request_memo'


def memoized(db, key: Any, fn: Callable[[], Any]) -> Any:
    """`key` 命中即复用，否则调用 `fn()` 并存下结果。

    **未进入 `request_memo()` 时直接 `fn()`** —— 默认路径零行为变化，缓存是否
    生效不构成第二套口径。
    """
    cache = db.info.get(_MEMO_KEY)
    if cache is None:
        return fn()
    if key not in cache:
        cache[key] = fn()
    return cache[key]


@contextmanager
def request_memo(db):
    """上下文内启用家庭级复用；嵌套调用只由最外层负责建桶与清空。"""
    if db.info.get(_MEMO_KEY) is not None:  # 已在外层上下文里：不接管、不清空
        yield
        return
    db.info[_MEMO_KEY] = {}
    try:
        yield
    finally:
        db.info.pop(_MEMO_KEY, None)
