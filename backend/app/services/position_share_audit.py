# -*- coding: utf-8 -*-
"""常驻巡检：份额被流水「反证」却仍挂在账上的持仓（#3135）。

## 为什么需要常驻，而不是又一次一次性脚本

#3127 把 ``reattach_transactions`` 的契约定成「只改 ``position_id``、绝不自动重算份额」
（份额变更不可逆，``undo_reattach`` 依赖这一点），并在返回体里加了 ``share_check``
只读提示。但提示只在**当次请求**里出现一次：用户没看见、或者卖腿是后来才挂回的，
就再没有任何人回答「这条持仓的份额还和流水自洽吗」。#3127 的
``fix_phantom_position_shares.py`` 是一次性扫描，判据是「此刻派生份额恰好为 0」——
真库 ``SZ159981``（positions#944）那次扫的时候净额还是 +3000 份，没进名单；
当晚补录一笔卖出后净额归零、账上仍 1000 份，而脚本不会回头再跑。

本模块把判据做成**每次对账收尾都会执行**的常驻检查，并且每条命中都带 ``remedy``
（指向「核对流水 / 按账单填份额」），不新建重复差异卡：域 B 已经会为这类持仓生成
``quantity`` 卡（见 ``is_missing_baseline``），由那张卡承载用户裁决。

## 判据口径（与重算动作同源）

- 检测单位 = **持仓名下的流水**（``transactions.position_id``），不是域 B 的
  ``(ledger, symbol)`` 业务键。理由：``recompute_from_transactions`` 也是按
  ``position_id`` 取流水，检测与修复动作必须看同一批数据，否则会「检出但重算后仍不平」；
- 复用 ``reconciliation_theory.flow_disproves_position``（#3125 定的「流水反证份额」
  唯一判据）：无锚点 + 账上仍有正份额 + 名下流水净额 ≤ 0；
- 外层再加两条边界：``ownership_status == 'active'``（清仓行没有份额可修）、
  **至少一条份额级流水**（货币基金按金额记账、``quantity`` 恒 0，净额天然为 0，
  不是「卖完了」；完全无流水的是空壳行，重算会删行。两者都不属本形态，
  与 #3127 存量脚本的两条排除同源）。

有锚点的持仓不适用：锚点前流水本就不计入份额，全量净额 ≤ 0 是正常现象
（``flow_disproves_position`` 内部已判 ``has_anchor``）。

## 只报数、更不按流水清仓

超卖（派生份额 < 0）多半缺买入腿，#3127 明确「不敢批量清仓、只报数交人工」。
2026-11-16 用户进一步定调：**份额的真相是账单，不是流水**——净额归零同样可能是
流水缺腿（或补录多记了一笔卖出），按流水重算会把一条正确持仓清零。
故本模块**只读业务表**（巡检只落自己的 ``sync_logs`` 审计行），``remedy`` 统一是
``verify_flows``（去核对流水 / 按账单填 0），不再给一键重算入口。

## 「成因」也要报（2026-11-16，#3135 收尾）

只报「账上 1000 / 流水 0」不解释这 1000 从哪来，用户唯一想得到的动作就是「补录一笔卖出」
——而那恰好是制造这批脏数据的动作（补录同时改流水与份额，差额恒定）。所以命中项额外带
``adjustment_txns``：这条持仓名下所有 ``source=reconciliation_adjustment`` 的流水。
有它时 ``remedy`` 改成「先核对/回滚补录再重算」，不再诱导一键清仓。
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.constants import PositionSource
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.models.sync_log import insert_audit_row
from app.services.reconciliation_theory import flow_disproves_position, net_quantity

SUMMARY_KEY = 'share_integrity'
SUMMARY_IDS_KEY = 'share_integrity_positions'
SUMMARY_IDS_LIMIT = 20
#: 命中项的统一动作：**只核对、不代改**（2026-11-16 用户定调，见 scan_disproved_shares）。
VERIFY_FLOWS = 'verify_flows'
REMEDY_HINT = (
    '账上还有 {now:g} 份，交易记录里这只卖出的已经不少于买入的：'
    '可能是漏记了一笔买入，也可能确实已经清仓。'
    '系统不会照着流水替你清仓——先到「交易记录」逐笔核对：漏了就补上；'
    '若账单确认已经没有这只，用「改成账单份额」把份额填 0。'
)
OVERSOLD_HINT = (
    '交易记录里这只卖出的比买入还多，多半漏记了买入。'
    '系统不会照着流水替你清仓——先到「交易记录」核对，漏记的买入补上；'
    '若账单确认已经没有这只，用「改成账单份额」填 0。'
)
ADJUSTED_HINT = (
    '该持仓名下有 {count} 笔「对账补录」流水（#{ids}）：补录会同时改流水与份额，'
    '差额因此恒定。请先到「交易记录」核对这几笔补录是否成立（不成立就删掉，'
    '删除会自动重算份额），再回来按账单确认份额。'
)

# 巡检落库用（`local_checks` 的每日通道；status 与 `due_checks` 的判据同源）
JOB_NAME = 'share_integrity_guard'
STATUS_OK = 'ok'
STATUS_FLAGGED = 'flagged'
ADJUSTMENT_SOURCE = PositionSource.RECONCILIATION_ADJUSTMENT.value


def _flows_by_position(db: Session, family_id: int) -> dict[int, list[dict]]:
    """一次取全家庭的份额流水并按持仓分组（避免逐持仓 N+1 查询）。

    只取判据用得到的三列；``confirm_date`` 不参与 ``net_quantity``，锚点口径由
    ``compute_anchored_state`` 自己按库重算（命中数少，逐条查可接受）。
    """
    rows = (
        db.query(Transaction.position_id, Transaction.txn_type, Transaction.quantity)
        .filter(Transaction.family_id == family_id, Transaction.position_id.isnot(None))
        .yield_per(1000)
        .all()
    )
    grouped: dict[int, list[dict]] = defaultdict(list)
    for pid, txn_type, quantity in rows:
        grouped[pid].append({'txn_type': txn_type, 'quantity': quantity or 0})
    return grouped


def scan_disproved_shares(db: Session, family_id: int) -> list[dict]:
    """只读扫描，返回「份额被流水反证」的持仓清单（每条带可执行的重算入口）。

    返回单位：份额 / 份（库内最小单位在边界换算，内部计算一律整数）。
    ``quantity_if_recomputed`` 取自 ``compute_anchored_state``（份额派生唯一入口），
    只是**告知**重算结果，不代替用户决定是否重算。
    """
    positions = (
        db.query(Position)
        .filter(
            Position.family_id == family_id,
            Position.ownership_status == 'active',
            Position.quantity > 0,
        )
        .yield_per(500)
        .all()
    )
    flows = _flows_by_position(db, family_id)
    found: list[dict] = []
    for pos in positions:
        txns = flows.get(pos.id, [])
        if not txns or not any(t['quantity'] for t in txns):
            continue  # 无流水 / 只有金额流水：重算会删行或本就不按份额记账
        if not flow_disproves_position(txns, pos):
            continue

        # 函数内导入：position_service 服务多条写路径，模块级导入会成环。
        from app.services.position_service import compute_anchored_state  # noqa: PLC0415

        expected_units, _ = compute_anchored_state(db, pos)
        now = Money.min_unit_to_shares(pos.quantity)
        expected = Money.min_unit_to_shares(expected_units)
        net_units = net_quantity(txns)
        oversold = net_units < 0  # #3127：超卖不敢批量清仓，只报数交人工
        found.append(
            {
                'position_id': pos.id,
                'symbol': pos.symbol,
                'name': pos.name,
                'ledger_id': pos.ledger_id,
                'quantity_now': now,
                'quantity_if_recomputed': expected,
                'diff': round(expected - now, 4),
                'flow_net': Money.min_unit_to_shares(net_units),
                'flow_state': 'oversold' if oversold else 'netted_out',
                'remedy': {
                    'action': VERIFY_FLOWS,
                    'blocked': True,
                    'hint': (OVERSOLD_HINT if oversold else REMEDY_HINT).format(now=now),
                },
            }
        )
    _attach_adjustment_evidence(db, family_id, found)
    return found


def _attach_adjustment_evidence(db: Session, family_id: int, found: list[dict]) -> None:
    """给命中项补上「对账补录」流水，并把 remedy 改成先核对再重算。

    ``found`` 可能被测试整体替成只带 ``position_id`` 的假数据（见
    ``test_report_to_summary_truncates_ids``），所以逐条 `get`，缺 ``remedy`` 就跳过。
    """
    position_ids = [row.get('position_id') for row in found if row.get('position_id')]
    grouped = _adjustment_txns(db, family_id, position_ids)
    for row in found:
        txns = grouped.get(row.get('position_id'), [])
        row['adjustment_txns'] = txns
        remedy = row.get('remedy')
        if not remedy or not txns:
            continue
        remedy['action'] = 'review_adjustment'
        remedy['blocked'] = True
        remedy['hint'] = ADJUSTED_HINT.format(
            count=len(txns),
            ids=', '.join(str(t['id']) for t in txns),
        )


def _adjustment_txns(db: Session, family_id: int, position_ids: list[int]) -> dict[int, list[dict]]:
    """这些持仓名下由「对账补录」写出来的流水（份额级），按持仓分组。

    只查命中项（通常个位数），不放进 ``_flows_by_position`` 的全量扫描里：
    补录只是解释成因用的旁证，不该让每次对账都多读几列。
    """
    if not position_ids:
        return {}
    rows = (
        db.query(
            Transaction.id,
            Transaction.position_id,
            Transaction.txn_type,
            Transaction.quantity,
            Transaction.price,
            Transaction.trade_date,
            Transaction.confirm_date,
            Transaction.source,
        )
        .filter(
            Transaction.family_id == family_id,
            Transaction.position_id.in_(position_ids),
            Transaction.source == ADJUSTMENT_SOURCE,
            Transaction.quantity > 0,
        )
        .order_by(Transaction.id)
        .all()
    )
    grouped: dict[int, list[dict]] = defaultdict(list)
    for txn_id, position_id, txn_type, quantity, price, trade_date, confirm_date, _src in rows:
        when = trade_date or confirm_date
        grouped[position_id].append(
            {
                'id': txn_id,
                'txn_type': txn_type,
                'quantity': Money.min_unit_to_shares(quantity or 0),
                'price': Money.price_units_to_yuan(price or 0),
                # `trade_date` 是 DateTime、`confirm_date` 是 Date：两者都有 isoformat，
                # 取前 10 位即可，不用 `.date()`（date 对象没有这个方法）。
                'trade_date': when.isoformat()[:10] if when else None,
                'source': ADJUSTMENT_SOURCE,
            }
        )
    return dict(grouped)


def scan_all_families(db: Session) -> list[dict]:
    """跨家庭扫描（巡检没有请求上下文，拿不到 ``get_family_id()``）。"""
    family_ids = sorted({row[0] for row in db.query(Position.family_id).distinct().all() if row[0] is not None})
    found: list[dict] = []
    for family_id in family_ids:
        found.extend(scan_disproved_shares(db, family_id))
    return found


def run_and_record(db: Session, *, commit: bool = True) -> dict:
    """巡检一次并把结论落进 ``sync_logs``（唯一的写，与 ``cold_set_guard.record`` 同口径）。

    命中即 ``flagged``：`local_checks` 会按「非 success」打 warning，让它出现在日志与
    ``--status`` 里，而不是只在某个用户恰好点开对账时才被看见。
    写入统一走 ``sync_log.insert_audit_row``（时间参数由它格式化，见 #3182）。
    """
    found = scan_all_families(db)
    status = STATUS_FLAGGED if found else STATUS_OK
    stats = {
        'hits': len(found),
        'position_ids': [row['position_id'] for row in found[:SUMMARY_IDS_LIMIT]],
    }
    insert_audit_row(db, job_name=JOB_NAME, status=status, stats=stats)
    if commit:
        db.commit()
    return {'status': status, 'stats': stats}


def report_to_summary(db: Session, family_id: int, summary: dict) -> list[dict]:
    """对账收尾的常驻报数：把命中数与持仓 id 写进 ``reconciliation_runs.summary_json``。

    只报数、不建卡、不写持仓。命中 id 截断到前 20 条（完整清单用巡检脚本取），
    避免大批量脏数据把 run 记录撑大。调用点在 ``reconciliation_service._finalize_run``，
    由 ``test_reconciliation_share_integrity.py`` 的收尾用例钉住——删掉接线会转红。
    """
    found = scan_disproved_shares(db, family_id)
    summary[SUMMARY_KEY] = len(found)
    summary[SUMMARY_IDS_KEY] = [row['position_id'] for row in found[:SUMMARY_IDS_LIMIT]]
    return found
