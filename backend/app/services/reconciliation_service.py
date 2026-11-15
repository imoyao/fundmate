# -*- coding: utf-8 -*-
"""统一对账域 B（持仓快照一致性）计算服务（#1232 §6.1 / P1）。

域 B 算法（设计文档 §6.1）：
    理论持仓 = 期初余额（快照份额）+ 期后流水净变化（confirm_date > snapshot_date）
    差异     = 实际持仓（positions.quantity）− 理论持仓

口径落地（P1，数量差异 + 孤儿检测）：
- 检测范围（§6.1 边界）：该 `(ledger_id, symbol)` 在 transactions 存在至少 1 条记录才纳入；
  纯快照/E账户（无流水）skip，不检测、不告警（避免误报）。
- 期初快照份额：`positions.snapshot_quantity`（锚点）已在 2026-10 落地，有锚点时按
  「快照 + 快照日之后流水」推演；**无锚点**（迁移产物只回填了日期、份额已丢失）退回
  全量流水净额 —— 两种口径见 `reconciliation_theory` 模块 docstring。
- 孤儿检测（§6.1）：流水推演净份额 > 0 但系统无对应持仓 → 报 orphan。
- 数量差异：理论值与实际（positions.quantity）不一致 → 报 quantity；无锚点、**active**
  且流水净额 > 0（流水没反证份额）时报 no_anchor（#3125：缺基准不是数据错，补录解决
  不了，卡片给「以此为准」写锚点）。净额 ≤ 0 却仍有份额是 #3127 的幽灵持仓/超卖，
  份额本身可能有误，保持 quantity 交人工；判据与写锚点动作共用
  `reconciliation_theory.is_missing_baseline` / `flow_disproves_position`。

差异结果按业务键 upsert 到 `discrepancies`（§8.1），并记录 `reconciliation_runs`。
"""

import json
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.domains.reconciliation.models import ReconciliationDiscrepancy, ReconciliationRun
from app.domains.transactions.models import Transaction
from app.services.position_write_support import _find_existing_position
from app.services.reconciliation_integrity import refresh_domain_c_orphans
from app.services.reconciliation_theory import find_holding as _find_holding
from app.services.reconciliation_theory import group_by_business_key, is_missing_baseline
from app.services.reconciliation_theory import theoretical_qty as _theoretical_qty

# 参与数量轧差的流水类型（与 recompute_position_from_transactions 一致：buy/deposit/split 增、sell/withdraw 减；
# 分红/税费等现金事件 quantity=0 不影响份额，未知非零份额类型在快照一致性计算中会告警，避免静默漏算）
DOMAIN_B = 'B'
DOMAIN_C = 'C'


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
        db.query(
            Transaction.ledger_id,
            Transaction.symbol,
            Transaction.txn_type,
            Transaction.quantity,
            Transaction.confirm_date,
        )
        .filter(Transaction.family_id == family_id)
        .yield_per(1000)
        .all()
    )  # yield_per 分批拉取，避免家庭流水量大时一次性 .all() 撑爆内存（AI review #5）
    # 按业务键聚合流水（confirm_date 供锚点口径过滤「快照日之前」的流水）
    txn_by_key = group_by_business_key(rows)

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

    summary = {'pending': 0, 'cleared': 0, 'ignored': 0, 'orphan': 0, 'no_anchor': 0}
    seen_keys: set[tuple] = set()
    orphan_qty: dict[tuple, int] = {}  # (ledger_id, symbol, disc_type)：与 upsert 身份键对齐

    # 3) 对每个「有流水」的业务键做比对
    for key, txns in txn_by_key.items():
        if not _find_holding(txns) and key not in pos_by_key:
            # 流水净额 <= 0（已清仓）且无持仓 → 不算孤儿
            continue
        ledger_id, symbol = key
        # 字面量查不到就退回写入层的同一判据（#1662：同一基金两种写法并存，#3097）
        pos = pos_by_key.get(key) or _find_existing_position(db, ledger_id, family_id, symbol, '')
        # 锚点口径：快照基线 + 快照日之后的流水；无锚点份额时退回全量流水（见 _theoretical_qty）
        theoretical_qty = _theoretical_qty(txns, pos)

        if pos is None:
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
                summary,
            )
            seen_keys.add((*key, 'orphan'))
            orphan_qty[key] = theoretical_qty
            continue

        # 域 C：只做孤儿检测，不做数量比对（§6.2；补录差异留 P2 工作台）
        if domain == DOMAIN_C:
            continue

        diff = pos.quantity - theoretical_qty
        if diff != 0:
            # 「缺基准」不等于「流水与持仓对不上」：净额 ≤ 0 却仍有份额是 #3127
            # 的幽灵持仓 / 超卖（真错），判成 no_anchor 会被「以此为准」固化。
            # 判据与写锚点动作共用一个函数，见 reconciliation_theory（含时点差说明）。
            disc_type = 'no_anchor' if is_missing_baseline(txns, pos) else 'quantity'
            _upsert_discrepancy(
                db,
                family_id,
                run.id,
                domain,
                ledger_id,
                symbol,
                disc_type,
                theoretical_qty,
                pos.quantity,
                diff,
                summary,
            )
            seen_keys.add((*key, disc_type))

    return _finalize_run(db, family_id, run, domain, seen_keys, orphan_qty, summary)


def _finalize_run(
    db: Session,
    family_id: int,
    run: ReconciliationRun,
    domain: str,
    seen_keys: set[tuple],
    orphan_qty: dict[tuple, int],
    summary: dict,
) -> tuple[ReconciliationRun, bool]:
    """收尾：清掉本轮不再成立的差异 → 刷新域 C 孤儿卡 → 落 run 统计。

    清理**必须按本次 run 的域**：否则域 C（导入后自动触发）会把域 B 的待裁决差异
    误置 cleared，同时域 C 自身的陈旧差异永远清不掉。

    域 C 的孤儿卡只在导入时重算（见 `reconciliation_integrity` 模块 docstring），
    数据修好之后卡片会一直停在导入那一刻 —— 域 B 的覆盖范围是它的超集，同源刷新。
    """
    _clear_stale_discrepancies(db, family_id, run.id, seen_keys, domain, summary)
    if domain == DOMAIN_B:
        refresh_domain_c_orphans(db, family_id, run.id, orphan_qty, summary)
    run.summary_json = json.dumps(summary)
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
    summary: dict,
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
            summary['ignored'] += 1
            return existing
        existing.expected_value = expected
        existing.actual_value = actual
        existing.diff = diff
        existing.status = 'pending'
        existing.last_run_id = run_id
        db.flush()
        summary['pending'] += 1
        _count_by_type(summary, disc_type)
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
    summary['pending'] += 1
    _count_by_type(summary, disc_type)
    return d


def _count_by_type(summary: dict, disc_type: str) -> None:
    """按类型累计本次 run 的计数（orphan / no_anchor）。

    只有 `_upsert_discrepancy` 知道 disc_type，调用处各加一遍必然漂移；
    `is_permanent` 提前 return 的分支不计入（与 pending 口径一致）。
    """
    if disc_type in ('orphan', 'no_anchor'):
        summary[disc_type] += 1


def _clear_stale_discrepancies(
    db: Session, family_id: int, run_id: int, seen_keys: set[tuple], domain: str, summary: dict
) -> None:
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
    cleared_count = 0
    for d in discrepancies:
        key = (d.ledger_id, d.symbol, d.discrepancy_type)
        if key not in seen_keys:
            d.status = 'cleared'
            d.last_run_id = run_id
            cleared_count += 1
    db.flush()
    summary['cleared'] += cleared_count


def apply_decision(db: Session, family_id: int, payload: dict) -> dict:
    """就地补充/调整裁决的 facade：实现已下沉到 `reconciliation_decision`（#3125）。

    下沉原因：本模块体积基线顶格，且「写库裁决」与「只读比对」是两件职责。
    签名与行为逐字不变，views 层调用点无需改动。
    """
    from app.services.reconciliation_decision import apply_decision as _impl  # noqa: PLC0415

    return _impl(db, family_id, payload)
