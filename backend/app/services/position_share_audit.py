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
（#3128 的「按流水重算份额」入口），不新建重复差异卡：域 B 已经会为这类持仓生成
``quantity`` 卡（见 ``is_missing_baseline``），#3134 负责把那张卡的动作接成重算。

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

## 只报数、不自动修

超卖（派生份额 < 0）多半缺买入腿，#3127 明确「不敢批量清仓、只报数交人工」。
故本模块**只读**，是否重算由用户点入口决定；巡检脚本同样不写库。
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.reconciliation_theory import flow_disproves_position, net_quantity

RECOMPUTE_ENDPOINT = '/api/positions/{position_id}/recompute/'
SUMMARY_KEY = 'share_integrity'
SUMMARY_IDS_KEY = 'share_integrity_positions'
SUMMARY_IDS_LIMIT = 20
REMEDY_HINT = '到持仓详情点「按流水重算份额」，或调用 POST {endpoint}（需带登录态）'
OVERSOLD_HINT = (
    '超卖（流水净额为负）多半缺买入腿，重算会直接清仓：请先核对流水是否齐全，'
    '确认后再到持仓详情点「按流水重算份额」或调用 POST {endpoint}（需带登录态）'
)


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
        endpoint = RECOMPUTE_ENDPOINT.format(position_id=pos.id)
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
                    'action': 'position_recompute',
                    'method': 'POST',
                    'endpoint': endpoint,
                    'hint': (OVERSOLD_HINT if oversold else REMEDY_HINT).format(endpoint=endpoint),
                },
            }
        )
    return found


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
