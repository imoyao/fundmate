# -*- coding: utf-8 -*-
"""账户级 XIRR / Modified Dietz（#3287 B0）.

单独立成模块而不是塞进 `calculators.py`：`calculate_xirr_by_scope` 补账户档会顶破
`guard_service_size.py` 的只减不增基线（585 行 / max_func 70 均已顶满），按仓规正解
是**下沉新模块**，不是改基线。

为什么账户级不需要新算法：XIRR 是定义在**任意现金流集合**上的统计，单账户就是
「只有一个成员的集合」——流水与市值同口径收窄，分子分母不会错配。`#3246` 已经给
`calculate_portfolio_xirr` 建好 `visible_ids`，本模块只是把「一个 id 的集合」喂进去。

为什么必须显式校验归属：`restrict_visible` 对 `ledger_id IS NULL` 的明细是**放行**的
（无主行按家庭共有处理，见 `domains/ledgers/visibility.py` 第 67-72 行）。若直接用
外家庭的 id，查询不会报错，而是返回「无主行 + 空集」的半截数据——静默错数比报错更坏。
"""

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.services.scope import family_ledger_ids


def ledger_scope_xirr(
    db: Session,
    ledger_id: int | None,
    family_id: int = 1,
    include_cash_equivalents: bool = False,
    method: str = 'xirr',
) -> Dict[str, Any]:
    """单账户年化收益率（`scope=ledger`）。

    两类失败都显式抛错，不靠「查不到就空集」兜底：

    - 缺 `ledger_id` ⇒ ``XirrScopeParameterError``（视图映射 **400**，客户端参数错）；
    - id 不属于本家庭 ⇒ ``ValueError``（视图映射 **404**，与组合档
      `calculate_portfolio_xirr_by_id` 同款，不区分「不存在」与「不是你的」）。

    顶部不 import `calculators`、改用函数内导入：`calculators.calculate_xirr_by_scope`
    要反向 import 本模块，顶部互导会成环。
    """
    from app.services.performance.calculators import XirrScopeParameterError, calculate_portfolio_xirr

    if ledger_id is None:
        raise XirrScopeParameterError('缺少 ledger_id 参数')
    if ledger_id not in family_ledger_ids(db, family_id):
        raise ValueError('账户不存在')
    return calculate_portfolio_xirr(
        db,
        family_id=family_id,
        include_cash_equivalents=include_cash_equivalents,
        method=method,
        visible_ids={ledger_id},
    )
