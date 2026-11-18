# -*- coding: utf-8 -*-
"""补录后的差异重算（从 `reconciliation_service.py` 下沉）。

`reconciliation_service.py` 已被 `guard_service_size.py` 冻结基线（只减不增），
「补录完算不算平」这段判定继续堆在那里会把 lines / max_func / max_cc 一起顶穿。

为什么复用 `run_reconciliation` 而不另写一份判定：锚点 / 流水净额 / 孤儿的差额
口径只有那一处，复制一份必然与全量对账分叉——旧实现无条件 `cleared` 正是这么
来的，导致「账上 1000 股只补 200 股」这条差异处理一次后就从待办队列消失。
"""

from loguru import logger
from sqlalchemy.orm import Session

from app.domains.reconciliation.models import ReconciliationDiscrepancy


def recompute_linked_discrepancy(db: Session, family_id: int, disc: ReconciliationDiscrepancy) -> dict:
    """按域重算关联差异，返回前端需要的状态与当前差额。

    真正轧平 → `cleared`；差额仍在 → `pending`，队列里可继续补第二笔。
    重算异常不吞掉已成功的补录，也不误标「已平」：保守保持 pending。
    """
    # 局部导入：`reconciliation_service` 顶层会 import 本模块，模块级导入会成环。
    from app.services.reconciliation_service import run_reconciliation  # noqa: PLC0415

    try:
        run_reconciliation(db, family_id, domain=disc.domain, triggered_by='manual')
    except Exception:
        logger.exception('补录后重算对账失败，差异保持待处理: discrepancy_id={}', disc.id)
        if not disc.is_permanent:
            disc.status = 'pending'
    return {
        'id': disc.id,
        'status': disc.status,
        'diff': disc.diff,
        'expected_value': disc.expected_value,
        'actual_value': disc.actual_value,
    }
