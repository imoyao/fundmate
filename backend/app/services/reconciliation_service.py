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

from app.core.constants import PositionSource
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy, ReconciliationRun
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService

# 参与数量轧差的流水类型（与 recompute_position_from_transactions 一致）
_BUY_TYPES = ('buy', 'deposit')
_SELL_TYPES = ('sell', 'withdraw')
_ADD_TYPES = ('buy', 'deposit', 'split')

DOMAIN_B = 'B'
DOMAIN_C = 'C'


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
    """兼容别名：域 B 对账（旧引用）。"""
    return run_reconciliation(db, family_id, DOMAIN_B)


def run_reconciliation(
    db: Session, family_id: int, domain: str = DOMAIN_B, triggered_by: str | None = None
) -> tuple[ReconciliationRun, bool]:
    """执行一次对账，返回 (run, 是否新建)。

    - 域 B：遍历该 family 有流水的持仓（positions.quantity vs 流水重建净额），
      数量差异 + 孤儿（流水推演净额 > 0 但无持仓行）。
    - 域 C（对账单导入，§6.2）：导入 commit 后自动触发，只做孤儿检测
      （孤儿流水 → orphan 差异），不做数量比对（导入对账单 vs 系统持仓的
      补录差异在 P2 工作台补录环节处理）。
    - 差异按业务键 upsert 到 discrepancies；无差异的旧差异置 cleared。
    - triggered_by 未显式传入时按域推断：域 C 为 import（导入后自动触发），其余 manual。
    """
    run = ReconciliationRun(
        family_id=family_id,
        domain=domain,
        data_date=date.today(),
        started_at=datetime.utcnow(),
        triggered_by=triggered_by or ('import' if domain == DOMAIN_C else 'manual'),
    )
    db.add(run)
    db.flush()

    # 1) 该 family 有流水的 (ledger_id, symbol) 集合（检测范围，§6.1 边界）
    rows = (
        db.query(Transaction.ledger_id, Transaction.symbol, Transaction.txn_type, Transaction.quantity)
        .filter(Transaction.family_id == family_id)
        .yield_per(1000)
        .all()
    )  # yield_per 分批拉取，避免家庭流水量大时一次性 .all() 撑爆内存（AI review #5）
    # 按业务键聚合流水
    txn_by_key: dict[tuple, list] = {}
    for ledger_id, symbol, txn_type, quantity in rows:
        if ledger_id is None or not symbol:
            continue
        key = (ledger_id, symbol)
        txn_by_key.setdefault(key, []).append({'txn_type': txn_type, 'quantity': quantity or 0})

    # 2) 当前持仓 map：业务键 → quantity
    positions = (
        db.query(Position)
        .filter(Position.family_id == family_id, Position.ownership_status == 'active')
        .yield_per(1000)
        .all()
    )  # 分批拉取，缓解内存压力（AI review #4）
    pos_by_key: dict[tuple, Position] = {}
    for p in positions:
        pos_by_key[(p.ledger_id, p.symbol)] = p

    summary = {'pending': 0, 'cleared': 0, 'ignored': 0, 'orphan': 0}
    seen_keys: set[tuple] = set()

    # 3) 对每个「有流水」的业务键做比对
    for key, txns in txn_by_key.items():
        if not _find_holding(txns):
            # 流水净额 <= 0（已清仓）且无持仓 → 不算孤儿
            if key not in pos_by_key:
                continue
        ledger_id, symbol = key
        actual_qty = pos_by_key[key].quantity if key in pos_by_key else 0
        theoretical_qty = _txn_net_quantity(txns)

        if key not in pos_by_key:
            # 孤儿：流水推演净额 > 0 但系统无该持仓（§6.1 边界；域 B/C 均检测）
            _upsert_discrepancy(
                db,
                family_id,
                run.id,
                domain,
                ledger_id,
                symbol,
                'orphan',
                theoretical_qty,
                0,
                theoretical_qty,
            )
            summary['orphan'] += 1
            seen_keys.add(key)
            continue

        # 域 C：只做孤儿检测，不做数量比对（§6.2；补录差异留 P2 工作台）
        if domain == DOMAIN_C:
            continue

        diff = actual_qty - theoretical_qty
        if diff != 0:
            # 数量差异（域 B）
            _upsert_discrepancy(
                db,
                family_id,
                run.id,
                domain,
                ledger_id,
                symbol,
                'quantity',
                theoretical_qty,
                actual_qty,
                diff,
            )
            summary['pending'] += 1
            seen_keys.add(key)

    # 4) 本 run 未检测到的既有 pending 差异 → cleared（差异消失）
    #    必须按本次 run 的域清理：否则域 C（导入后自动触发）会把域 B 的待裁决差异误置 cleared，
    #    同时域 C 自身的陈旧差异永远清不掉。
    _clear_stale_discrepancies(db, family_id, run.id, seen_keys, domain)

    summary_json = json.dumps(summary)
    run.summary_json = summary_json
    run.finished_at = datetime.utcnow()
    return run, True


def _upsert_discrepancy(
    db: Session,
    family_id: int,
    run_id: int,
    domain: str,
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
            ReconciliationDiscrepancy.domain == domain,
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
        domain=domain,
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


def _clear_stale_discrepancies(db: Session, family_id: int, run_id: int, seen_keys: set[tuple], domain: str) -> None:
    """本 run 未检测到的 pending 差异 → 差异消失置 cleared（§6.5 状态流转）。

    domain 为必填：清理范围必须与本次 run 的域一致，否则会跨域误清他域的待裁决差异。

    注意：这是系统自动行为，**不写 adjustment_logs**（§5.5）。
    """
    discrepancies = (
        db.query(ReconciliationDiscrepancy)
        .filter(
            ReconciliationDiscrepancy.family_id == family_id,
            ReconciliationDiscrepancy.domain == domain,
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


def apply_decision(
    db: Session,
    family_id: int,
    payload: dict,
) -> dict:
    """就地补充/调整裁决（#1232 §5.4 / P2）——生成调整凭证 + 审计日志。

    **不新建调整表**：按语义分派到既有汇点，聚合层天然可见（§5.4）：
    - 增量型（补一笔缺失买卖，`op_type` in buy/sell/deposit/withdraw）
      → `process_buy_or_deposit` / `process_sell_or_withdraw`（写 Transaction + Position）
    - 设定型（期初建仓 / 直接改数量成本，`kind='set'`）
      → `upsert_from_holding`（SET 语义，不建流水；硬约束）

    审计：写 `adjustment_logs`（before_json/after_json），action=supplement|adjust。
    若携带 `discrepancy_id`，处理成功后该差异置 `cleared`。

    payload 关键字段：
        kind:        'increment'（默认）| 'set'
        op_type:     buy|sell|deposit|withdraw（increment 必填）
        discrepancy_id: 可选，关联差异
        reason:      可选，操作原因
        operator:    可选，操作用户 ID
        其余字段透传给汇点（symbol/ledger_id/quantity/avg_price/confirm_date/...）
    """
    kind = payload.get('kind', 'increment')
    disc_id = payload.get('discrepancy_id')
    reason = payload.get('reason')
    operator = payload.get('operator')

    disc = None
    if disc_id:
        disc = (
            db.query(ReconciliationDiscrepancy)
            .filter(ReconciliationDiscrepancy.id == disc_id, ReconciliationDiscrepancy.family_id == family_id)
            .first()
        )
        if not disc:
            raise ValueError('差异不存在或无权访问')

    data = {k: v for k, v in payload.items() if k not in ('kind', 'discrepancy_id', 'reason', 'operator')}
    data['family_id'] = family_id
    # 日期归一化：API 传入的是 ISO 字符串，而汇点/模型要求 Python date 对象
    # （绕过 PositionCreate schema 的类型转换，需在此显式处理，否则 SQLite 报
    # "Date type only accepts Python date objects"）。
    for key in ('confirm_date', 'snapshot_date', 'trade_date'):
        raw = data.get(key)
        if isinstance(raw, str) and raw:
            try:
                data[key] = (
                    datetime.strptime(raw[:10], '%Y-%m-%d').date()
                    if key != 'trade_date'
                    else datetime.strptime(raw[:10], '%Y-%m-%d')
                )
            except ValueError:
                raise ValueError(f'日期格式错误: {key}={raw!r}，应为 YYYY-MM-DD')
    # 对账补录来源标记（决策 11）。RECONCILIATION_ADJUSTMENT 由 #1238 引入；
    # 当前分支若未合入 #1238 则回退 manual，保证 P2 代码在合入前后均可运行。
    recon_source = getattr(PositionSource, 'RECONCILIATION_ADJUSTMENT', PositionSource.MANUAL).value
    data.setdefault('source', recon_source)

    # 操作前快照（审计）
    before = {
        'discrepancy_id': disc_id,
        'symbol': data.get('symbol'),
        'ledger_id': data.get('ledger_id'),
        'kind': kind,
    }

    if kind == 'set':
        # 设定型：SET 语义整条替换（期初建仓 / 直接改数量成本），不建流水
        position = PositionService.upsert_from_holding(db, data)
        after = {
            'position_id': position.id,
            'symbol': position.symbol,
            'quantity': position.quantity,
            'avg_price': position.avg_price,
        }
        action = 'adjust' if disc else 'supplement'
    else:
        # 增量型：走交易处理汇点（写 Transaction + 更新 Position）
        op_type = data.get('op_type', 'buy')
        if op_type in ('sell', 'withdraw'):
            position = PositionService.process_sell_or_withdraw(db, data)
        else:
            position = PositionService.process_buy_or_deposit(db, data)
        after = {
            'position_id': position.id if position else None,
            'symbol': data.get('symbol'),
            'op_type': op_type,
            'quantity': data.get('quantity'),
            'avg_price': data.get('avg_price'),
        }
        action = 'supplement'

    db.flush()

    # 审计日志（用户主动操作，§5.5）
    log = AdjustmentLog(
        family_id=family_id,
        discrepancy_id=disc_id,
        action=action,
        before_json=json.dumps(before, default=str),
        after_json=json.dumps(after, default=str),
        reason=reason,
        operator=operator,
    )
    db.add(log)

    # 处理成功后：关联差异置 cleared（该差异已被裁决）
    if disc:
        disc.status = 'cleared'
        disc.last_run_id = None

    db.flush()
    return {'action': action, 'before': before, 'after': after, 'log_id': log.id}
