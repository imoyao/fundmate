# -*- coding: utf-8 -*-
"""清仓周期的「涉及账户」回填（#经验：复盘页看不到账户）。

WHY
    周期聚合（`cleared_cycles.compute_cleared_cycles`）按标的身份分组，同一只产品
    在多个账户买入会被合并成**一轮**——这是产品级口径，与账户管理页一致，不能改。
    但用户看这一行时第一个问题就是「这笔到底在哪个账户买的」：表格里没有账户列，
    只能去账户详情页逐个对流水。

    账户真相在流水上（`transactions.ledger_id`）。聚合时顺手收集周期涉及的 id 集合
    （去重），名称在这里**一次查表**回填——不按周期各查一次（334 个周期就是 334 次
    查询），也不改任何周期口径与汇总数字。

口径
    - **周期不按账户拆分**：同一标的多账户买入仍是一轮。拆分会与账户管理页的口径
      打架（同一产品在两个页面显示成不同「产品数」，胜率分母也跟着变）。
    - `ledger_names` 为空 = 该周期流水没有 `ledger_id`（存量迁移 / 未归档持仓）。
      前端显示 `--`，**不写「未知」**——「未知」是在断言「查了但查不到」，与
      「本来就没记」是两件事。
    - 同名账户去重：两个都叫「华泰证券」的账户不该显示成「+1」。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from loguru import logger


def attach_ledger_names(db, cycles: Sequence[Dict[str, Any]], family_id: int = 1) -> None:
    """就地把周期的 `ledger_ids` 换成 `ledger_names`（保序去重），无 id 时为空列表。

    调用点在 `build_cleared_cycles` 的**末卖日裁剪之后**：窗口外的周期不查账户名，
    与 `include_post_clear` 的懒查同一条理由（不为不展示的行付查询成本）。

    Args:
        db: 会话（ledgers / transactions 同库）。
        cycles: `compute_cleared_cycles` 的出参（含中间字段 `ledger_ids`）。
        family_id: 家庭作用域；名称查询也限定家庭，避免跨家庭串号。
    """
    from app.domains.ledgers.models import Ledger

    wanted = {lid for c in cycles for lid in (c.get('ledger_ids') or [])}
    names: Dict[int, str] = {}
    if wanted:
        rows = db.query(Ledger.id, Ledger.name).filter(Ledger.id.in_(wanted), Ledger.family_id == family_id).all()
        names = {row[0]: row[1] for row in rows}
    for c in cycles:
        # 中间字段不进 API 出参：前端只消费账户名（排序也按名），不下发内部 id
        c['ledger_names'] = _distinct(names.get(lid) for lid in (c.pop('ledger_ids', None) or []))
    logger.debug(f'清仓周期账户回填：{len(wanted)} 个账户 / {len(cycles)} 个周期')


def _distinct(names: Sequence[Any]) -> List[str]:
    """同名去重并保持原顺序（首个出现的位置决定排序）。"""
    out: List[str] = []
    for name in names:
        if name and name not in out:
            out.append(name)
    return out
