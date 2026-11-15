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

from app.core.constants import AnchorKind, PositionSource
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy, ReconciliationRun
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService
from app.services.position_write_support import _find_existing_position
from app.services.reconciliation_adjustment import recompute_linked_discrepancy
from app.services.reconciliation_integrity import assert_supplement_is_new, refresh_domain_c_orphans
from app.services.reconciliation_theory import find_holding as _find_holding
from app.services.reconciliation_theory import group_by_business_key
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

    summary = {'pending': 0, 'cleared': 0, 'ignored': 0, 'orphan': 0}
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
            summary['orphan'] += 1
            seen_keys.add((*key, 'orphan'))
            orphan_qty[key] = theoretical_qty
            continue

        # 域 C：只做孤儿检测，不做数量比对（§6.2；补录差异留 P2 工作台）
        if domain == DOMAIN_C:
            continue

        diff = pos.quantity - theoretical_qty
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
                pos.quantity,
                diff,
                summary,
            )
            seen_keys.add((*key, 'quantity'))

    # 4) 本 run 未检测到的既有 pending 差异 → cleared（差异消失）
    #    必须按本次 run 的域清理：否则域 C（导入后自动触发）会把域 B 的待裁决差异误置 cleared，
    #    同时域 C 自身的陈旧差异永远清不掉。
    _clear_stale_discrepancies(db, family_id, run.id, seen_keys, domain, summary)
    if domain == DOMAIN_B:
        # 域 C 的孤儿卡只在导入时重算（见 reconciliation_integrity 模块 docstring），
        # 数据修好之后卡片会一直停在导入那一刻 —— 域 B 的覆盖范围是它的超集，同源刷新。
        refresh_domain_c_orphans(db, family_id, run.id, orphan_qty, summary)

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
    return d


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


def _resolve_sell_position_id(db: Session, family_id: int, data: dict) -> dict:
    """卖出/取出补录缺 `position_id` 时按统一身份键定位持仓并回填，原样返回 data。

    为什么这里要自己定位：对账补录的 payload 只有 `(symbol, ledger_id)`，没有
    「完整记账」UI 的持仓下拉，而卖出汇点 `prepare_sell` 第一行就是
    `data['position_id']` —— 用户实测补一笔卖出直接 500（KeyError: 'position_id'）。
    买入侧无此问题（`position_buy_command` 自己按身份键查/建持仓）。`venue=''`：
    payload 通常不带 asset_type/market，强判场所会把 asset_type 为 NULL 的存量行
    漏掉；`ledger_id` 允许 None（positions.ledger_id 可为 NULL，差异本就由持仓派生）。
    显式传了 `position_id` 时透传不覆盖；找不到时 ValueError → views 层转 400。
    """
    if data.get('position_id') is not None:
        return data
    pos = _find_existing_position(db, data.get('ledger_id'), family_id, data.get('symbol', ''), '')
    if pos is None:
        raise ValueError('找不到这笔持仓：可能已清仓、换了账本，或持仓记录已被删除。若已删除，去「修正数据」按流水重建')
    data['position_id'] = pos.id
    return data


def apply_decision(
    db: Session,
    family_id: int,
    payload: dict,
) -> dict:
    """就地补充/调整裁决（#1232 §5.4 / P2）：生成调整凭证 + 审计日志。

    不新建调整表：increment → 买卖汇点（Transaction + Position）；
    set → `upsert_from_holding`（SET 语义、不建流水）。审计写 `adjustment_logs`。
    携带 `discrepancy_id` 时，完成后由 `recompute_linked_discrepancy` 重算差异：
    真正轧平才 cleared，差额仍在则保持 pending，用户可继续补第二笔。
    payload：kind / op_type / discrepancy_id / reason / operator + 汇点字段。
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
        # 设定型：写**人工锚点**（不是普通快照导入）。
        # - anchor_kind='manual'：同日外部快照不得覆盖它（见 _assert_anchor_accepts）；
        # - allow_anchor_rewind=True：用户显式要求设定持仓，不属于「导入旧快照」，
        #   不受「更旧日期拒绝」约束——这是唯一的合法回退入口；
        # - snapshot_date 缺省取今天：用户是「以此刻的事实」校准，而非补历史快照。
        data.setdefault('anchor_kind', AnchorKind.MANUAL.value)
        data.setdefault('snapshot_date', date.today())
        position = PositionService.upsert_from_holding(db, data, allow_anchor_rewind=True)
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
        # 补录是「修差异」，不是「记账」：既有的同笔流水、同标的缺归属流水都必须先处置，
        # 否则差异会被重复录入「轧平」成假修复（reconciliation_integrity 模块 docstring）。
        assert_supplement_is_new(db, family_id, data)
        if op_type in ('sell', 'withdraw'):
            position = PositionService.process_sell_or_withdraw(db, _resolve_sell_position_id(db, family_id, data))
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
    # 先落审计日志拿到 log.id，也让本次补录对重算可见（autoflush=False）
    db.flush()
    result = {'action': action, 'before': before, 'after': after, 'log_id': log.id}
    if disc:
        result['discrepancy'] = recompute_linked_discrepancy(db, family_id, disc)
    db.flush()
    return result
