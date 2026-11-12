# -*- coding: utf-8 -*-
"""账户持仓快照一致性（只读报告，#1133 §4 温柔提醒数据源）。

从 `reconciliation_service.py` 下沉（2026-11-12），**为什么必须下沉**：当时要给
`apply_decision` 的卖出分支补 `_resolve_sell_position_id` helper（~18 行），而该文件
540 行正顶在 `guard_service_size.py` 的冻结基线（**只减不增**，上调会被脚本拒绝）、
`run_reconciliation` 又恰好顶在 max_func=122——helper 在 services 层无处可放
（全层 284 个文件的基线余量实测全为 0）。本函数是自包含的只读报告（不写
discrepancies），下沉它是**唯一不需要删注释、也不需要动基线**的合法解，不是顺手
重构——下一个人不要因为「看起来能搬回去」就搬，搬回去 helper 就没地方放了。
与 `reconciliation_query.py` 同一范式。函数拆成三个小函数是为满足新增文件
max_cc ≤ 20 的新文件上限，口径不变。
"""

from datetime import date

from loguru import logger
from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.positions.models import Position, PositionImportMeta
from app.domains.transactions.models import Transaction

# 与 reconciliation_service 域 B 轧差共用同一份流水类型口径
from app.services.reconciliation_service import _ADD_TYPES, _SELL_TYPES  # noqa: PLC2701


def _group_txns_by_key(db: Session, family_id: int, ledger_id: int | None) -> dict[tuple, list]:
    """该 family（可再限定账本）的全部流水按 (ledger_id, symbol) 聚合。

    一次性拉取，避免逐持仓查库放大 N+1。
    """
    txn_q = db.query(
        Transaction.ledger_id,
        Transaction.symbol,
        Transaction.txn_type,
        Transaction.quantity,
        Transaction.confirm_date,
    ).filter(Transaction.family_id == family_id)
    if ledger_id is not None:
        txn_q = txn_q.filter(Transaction.ledger_id == ledger_id)
    grouped: dict[tuple, list] = {}
    for ledger_id, symbol, txn_type, quantity, confirm_date in txn_q.all():
        if ledger_id is None or not symbol:
            continue
        grouped.setdefault((ledger_id, symbol), []).append((txn_type, quantity or 0, confirm_date))
    return grouped


def _report_theoretical_qty(txns: list, snapshot_qty: int, anchor_date: date) -> tuple[int, date | None]:
    """快照基线 + 快照日之后流水净额 → (theoretical, 最近流水日)。

    为什么不是复用 `reconciliation_service._theoretical_qty`：两者**输入前提不同**。
    域 B 那份对无锚点份额的持仓**回退全量流水净额**；本报告只处理有锚点份额的行
    （无基线份额直接跳过，见 `get_ledger_snapshot_consistency`），没有回退路径。
    强行复用会把这里的「跳过」变成「蒙一个数字」——那正是 #1133 §4 要避免的假红。

    - 只看**快照日之后**的流水：之前的已被快照包含，再加一遍就是重复计数；
    - 未知/非增减类型：现金事件（分红、税费等）通常 quantity=0 不影响份额，静默跳过；
      若带非零份额却未分类，告警以免静默漏算 theoretical（#ai-review 次要建议 1）。
    """
    theoretical = int(snapshot_qty)
    last_txn_date = None
    for txn_type, quantity, confirm_date in txns:
        if confirm_date is None:
            continue
        # 记录最新交易日期（用于温柔提醒文案：快照后是否还有交易活动）
        if last_txn_date is None or confirm_date > last_txn_date:
            last_txn_date = confirm_date
        if confirm_date <= anchor_date:
            continue
        if txn_type in _ADD_TYPES:
            theoretical += quantity
        elif txn_type in _SELL_TYPES:
            theoretical -= quantity
        elif quantity:
            logger.warning(
                '快照一致性忽略未分类交易类型 {}(quantity={})，可能影响 theoretical 计算',
                txn_type,
                quantity,
            )
    return theoretical, last_txn_date


def get_ledger_snapshot_consistency(db: Session, family_id: int, ledger_id: int | None = None) -> list[dict]:
    """只读：计算各账户持仓快照一致性（#1133 §4 温柔提醒数据源）。

    不写 discrepancies 表（那是工作台域 B 对账的落点），本函数提供按需、轻量的检查视图，
    供前端在账户列表 / 账本详情页以「温柔、非阻断」方式提示快照可能滞后。

    口径（#1133 §4，2026-10-18 按锚点模型修正）：
    - 取 active 持仓 + `anchor_date`（positions.snapshot_date，缺失回退
      position_import_meta.snapshot_date）。
    - **theoretical = snapshot_quantity + Σ(confirm_date > snapshot_date 的流水净额)**。
      快照是独立绝对值，不是流水的推导结果——旧口径「只算 <= snapshot_date 的流水」
      把快照当成流水的结果，与锚点模型正好相反，会对正确数据误报。
    - `snapshot_quantity IS NULL`（迁移后待修复的存量行）→ **跳过**：没有基线份额
      就算不出理论值，宁可沉默也不要编造差异。
    - diff = positions.quantity − theoretical。
    - 边界：该 (ledger_id, symbol) 无任何流水 → 纯快照模式（如 E账户持仓导入不建流水），
      跳过，禁止误报。
    - diff != 0 → 标记「可能对不上」，返回明细（份额换算为可读单位）。
    """
    rows_q = (
        db.query(Position, PositionImportMeta.snapshot_date)
        .join(PositionImportMeta, PositionImportMeta.position_id == Position.id)
        .filter(
            Position.family_id == family_id,
            Position.ownership_status == 'active',
            PositionImportMeta.snapshot_date.isnot(None),
        )
    )
    if ledger_id is not None:
        rows_q = rows_q.filter(Position.ledger_id == ledger_id)
    rows = rows_q.all()
    if not rows:
        return []

    txn_by_key = _group_txns_by_key(db, family_id, ledger_id)

    items: list[dict] = []
    for pos, meta_snapshot_date in rows:
        # 锚点日以 positions 层为准，缺失才回退 meta（迁移只回填了日期，份额仍是 NULL）
        anchor_date = pos.snapshot_date or meta_snapshot_date
        # 没有基线份额 → 算不出理论值。禁止回退「全量流水」蒙一个数字：
        # 那正是旧口径误报的来源，且会让用户以为持仓真的错了。
        if pos.snapshot_quantity is None or anchor_date is None:
            continue
        # 纯快照模式（无流水）：跳过，禁止误报（#1133 §4 边界）
        txns = txn_by_key.get((pos.ledger_id, pos.symbol))
        if not txns:
            continue
        theoretical, last_txn_date = _report_theoretical_qty(txns, pos.snapshot_quantity, anchor_date)
        diff = pos.quantity - theoretical
        if diff != 0:
            items.append(
                {
                    'ledger_id': pos.ledger_id,
                    'symbol': pos.symbol,
                    'name': pos.name,
                    'snapshot_date': anchor_date.isoformat(),
                    'last_txn_date': last_txn_date.isoformat() if last_txn_date else None,
                    'expected_qty': Money.min_unit_to_shares(theoretical),
                    'actual_qty': Money.min_unit_to_shares(pos.quantity),
                    'diff_qty': Money.min_unit_to_shares(diff),
                }
            )
    return items
