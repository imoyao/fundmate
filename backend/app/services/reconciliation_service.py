# -*- coding: utf-8 -*-
"""统一对账域 B（持仓快照一致性）计算服务（#1232 §6.1 / P1）。

域 B 算法（设计文档 §6.1）：
    理论持仓 = 期初余额（快照份额）+ 期后流水净变化（confirm_date > snapshot_date）
    差异     = 实际持仓（positions.quantity）− 理论持仓

口径落地（P1，数量差异 + 孤儿检测）：
- 检测范围（§6.1 边界）：该 `(ledger_id, symbol)` 在 transactions 存在至少 1 条记录才纳入；
  纯快照/E账户（无流水）skip，不检测、不告警（避免误报）。
- 期初快照份额：当前数据模型 `position_import_meta` 无份额列（仅 market_value 市值），
  故 P1 用「流水重建净份额」作为理论持仓（`recompute_position_from_transactions` 口径），
  检测「流水推演 vs 实际持仓」的数量不一致。严格快照锚定需补充快照份额字段（技术债，后续）。
- 孤儿检测（§6.1）：流水推演净份额 > 0 但系统无对应持仓 → 报 orphan。
- 数量差异：理论（流水净额）与实际（positions.quantity）最小单位不一致 → 报 quantity。

差异结果按业务键 upsert 到 `discrepancies`（§8.1），并记录 `reconciliation_runs`。
"""

import json
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.domains.reconciliation.models import ReconciliationDiscrepancy, ReconciliationRun
from app.domains.transactions.models import Transaction

# 参与数量轧差的流水类型（与 recompute_position_from_transactions 一致）
_BUY_TYPES = ('buy', 'deposit')
_SELL_TYPES = ('sell', 'withdraw')
_ADD_TYPES = ('buy', 'deposit', 'split')

DOMAIN_B = 'B'


def _txn_type(t) -> str:
    """兼容 Transaction 对象与 dict 两种流水表示。"""
    return t.txn_type if not isinstance(t, dict) else t['txn_type']


def _txn_quantity(t) -> int:
    """兼容 Transaction 对象与 dict 两种流水表示。"""
    return t.quantity if not isinstance(t, dict) else t['quantity']


def _txn_net_quantity(txns) -> int:
    """从流水计算净份额（最小单位）：Σ买入/存入/送股 − Σ卖出/取出。"""
    buy_qty = sum(_txn_quantity(t) for t in txns if _txn_type(t) in _ADD_TYPES)
    sell_qty = sum(_txn_quantity(t) for t in txns if _txn_type(t) in _SELL_TYPES)
    return buy_qty - sell_qty


def _find_holding(txns):
    """从流水推断理论持仓是否存在：净份额 > 0 即存在（对齐孤儿检测）。"""
    return _txn_net_quantity(txns) > 0


def run_domain_b_reconciliation(db: Session, family_id: int) -> tuple[ReconciliationRun, bool]:
    """执行一次域 B 对账，返回 (run, 是否新建)。

    - 遍历该 family 有流水的持仓（positions.quantity vs 流水重建净额）。
    - 差异按业务键 upsert 到 discrepancies；无差异的旧差异置 cleared。
    - 孤儿：流水推演净额 > 0 但无持仓行。
    """
    run = ReconciliationRun(
        family_id=family_id,
        domain=DOMAIN_B,
        data_date=date.today(),
        started_at=datetime.utcnow(),
        triggered_by='manual',
    )
    db.add(run)
    db.flush()

    # 1) 该 family 有流水的 (ledger_id, symbol) 集合（检测范围，§6.1 边界）
    rows = (
        db.query(Transaction.ledger_id, Transaction.symbol, Transaction.txn_type, Transaction.quantity)
        .filter(Transaction.family_id == family_id)
        .all()
    )
    # 按业务键聚合流水
    txn_by_key: dict[tuple, list] = {}
    for ledger_id, symbol, txn_type, quantity in rows:
        if not symbol:
            continue
        key = (ledger_id, symbol)
        txn_by_key.setdefault(key, []).append({'txn_type': txn_type, 'quantity': quantity or 0})

    # 2) 当前持仓 map：业务键 → quantity
    positions = db.query(Position).filter(Position.family_id == family_id, Position.ownership_status == 'active').all()
    pos_by_key: dict[tuple, Position] = {}
    for p in positions:
        pos_by_key[(p.ledger_id, p.symbol)] = p

    summary = {'pending': 0, 'cleared': 0, 'ignored': 0, 'orphan': 0}
    seen_keys: set[tuple] = set()

    # 3) 对每个「有流水」的业务键做数量比对
    for key, txns in txn_by_key.items():
        if not _find_holding(txns):
            # 流水净额 <= 0（已清仓）且无持仓 → 不算孤儿
            if key not in pos_by_key:
                continue
        seen_keys.add(key)
        ledger_id, symbol = key
        actual_qty = pos_by_key[key].quantity if key in pos_by_key else 0
        theoretical_qty = _txn_net_quantity(txns)

        if key not in pos_by_key:
            # 孤儿：流水推演净额 > 0 但系统无该持仓（§6.1 边界）
            _upsert_discrepancy(db, family_id, run.id, ledger_id, symbol, 'orphan', theoretical_qty, 0, theoretical_qty)
            summary['orphan'] += 1
            continue

        diff = actual_qty - theoretical_qty
        if diff != 0:
            # 数量差异
            _upsert_discrepancy(db, family_id, run.id, ledger_id, symbol, 'quantity', theoretical_qty, actual_qty, diff)
            summary['pending'] += 1

    # 4) 本 run 未检测到的既有 pending 差异 → cleared（差异消失）
    _clear_stale_discrepancies(db, family_id, run.id, seen_keys)

    summary_json = json.dumps(summary)
    run.summary_json = summary_json
    run.finished_at = datetime.utcnow()
    return run, True


def _upsert_discrepancy(
    db: Session,
    family_id: int,
    run_id: int,
    ledger_id: int | None,
    symbol: str,
    disc_type: str,
    expected: int,
    actual: int,
    diff: int,
) -> ReconciliationDiscrepancy:
    """按业务键 upsert 一条差异；已永久忽略的保持 ignored。"""
    existing = (
        db.query(ReconciliationDiscrepancy)
        .filter(
            ReconciliationDiscrepancy.family_id == family_id,
            ReconciliationDiscrepancy.domain == DOMAIN_B,
            ReconciliationDiscrepancy.ledger_id == ledger_id,
            ReconciliationDiscrepancy.symbol == symbol,
            ReconciliationDiscrepancy.discrepancy_type == disc_type,
        )
        .first()
    )
    if existing:
        if existing.is_permanent:
            # 永久忽略：不覆盖，保持静默（§6.5 状态流转）
            existing.last_run_id = run_id
            return existing
        existing.expected_value = expected
        existing.actual_value = actual
        existing.diff = diff
        existing.status = 'pending'
        existing.last_run_id = run_id
        db.flush()
        return existing
    d = ReconciliationDiscrepancy(
        family_id=family_id,
        domain=DOMAIN_B,
        ledger_id=ledger_id,
        symbol=symbol,
        discrepancy_type=disc_type,
        expected_value=expected,
        actual_value=actual,
        diff=diff,
        status='pending',
        last_run_id=run_id,
        first_detected_at=datetime.utcnow(),
    )
    db.add(d)
    db.flush()
    return d


def _clear_stale_discrepancies(db: Session, family_id: int, run_id: int, seen_keys: set[tuple]) -> None:
    """本 run 未检测到的 pending 差异 → 差异消失置 cleared（§6.5 状态流转）。

    注意：这是系统自动行为，**不写 adjustment_logs**（§5.5）。
    """
    discrepancies = (
        db.query(ReconciliationDiscrepancy)
        .filter(
            ReconciliationDiscrepancy.family_id == family_id,
            ReconciliationDiscrepancy.domain == DOMAIN_B,
            ReconciliationDiscrepancy.status == 'pending',
        )
        .all()
    )
    for d in discrepancies:
        key = (d.ledger_id, d.symbol)
        if key not in seen_keys:
            d.status = 'cleared'
            d.last_run_id = run_id
    db.flush()
