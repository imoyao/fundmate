# -*- coding: utf-8 -*-
"""#3135 常驻判据：份额被流水反证的持仓必须被检出，且带可执行的重算入口。

真库现场（2026-11-15，positions#944 / SZ159981）：11-13 按买入腿重建 3000 份、
买腿与卖腿先后经 ``dangling_ref_reattach`` 挂回（``recompute:false``）；14:14 的
#3127 一次性扫描时净额仍为 +3000，没进名单；当晚补录一笔卖出后净额归零、账上仍
1000 份，而没有任何机制回头再扫一遍。本文件把这条时间轴钉成回归网。

验收覆盖两态：「reattach 后份额未重算 → 被检出」与「重算后不再检出」，
另加「对账收尾常驻报数」与四类不得误报的边界。
"""

import json
from datetime import date, datetime

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services import dangling_ref_service as svc
from app.services.position_recompute_entry import recompute_with_audit
from app.services.position_share_audit import report_to_summary, scan_disproved_shares
from app.services.reconciliation_service import DOMAIN_B, run_reconciliation

_FAMILY = 1
_OTHER_FAMILY = 2
_DANGLING_PID = 990001  # 不存在的持仓 id（position_id 无外键，可安全写入）
_BASE = datetime(2026, 1, 1, 9, 0, 0)


@pytest.fixture
def ledger(db):
    lg = Ledger(name='3135-测试账户', ledger_type='bank', family_id=_FAMILY)
    db.add(lg)
    db.flush()
    return lg


def _mk_pos(db, ledger_id, symbol, shares, *, family_id=_FAMILY, status='active', anchor=False):
    p = Position(
        family_id=family_id,
        ledger_id=ledger_id,
        symbol=symbol,
        name='能源化工',
        market='CN_A',
        currency='CNY',
        quantity=Money.shares_to_min_unit(0 if status == 'cleared' else shares),
        avg_price=Money.yuan_to_price_units(1.0),
        current_price=Money.yuan_to_price_units(1.0),
        ownership_status=status,
    )
    if anchor:
        p.snapshot_quantity = Money.shares_to_min_unit(shares)
        p.snapshot_avg_price = Money.yuan_to_price_units(1.0)
        p.snapshot_date = date(2026, 6, 30)
    db.add(p)
    db.flush()
    return p


def _mk_txn(
    db,
    ledger_id,
    *,
    position_id=_DANGLING_PID,
    symbol='SZ159981',
    txn_type='buy',
    shares=1.0,
    family_id=_FAMILY,
    confirm_date=None,
    source=None,
):
    t = Transaction(
        family_id=family_id,
        position_id=position_id,
        ledger_id=ledger_id,
        symbol=symbol,
        position_name='能源化工',
        txn_type=txn_type,
        quantity=Money.shares_to_min_unit(shares),
        price=Money.yuan_to_price_units(1.0),
        amount=10000,
        realized_pnl=0,
        status='success',
        trade_date=_BASE,
        confirm_date=confirm_date,
        source=source,
        created_at=_BASE,
        updated_at=_BASE,
    )
    db.add(t)
    db.flush()
    return t


def _ghost_after_reattach(db, ledger, *, shares=4.0):
    """回放 #3135：建 4 份持仓 → 买 3 / 买 1 / 卖 1 → 卖 3 经 reattach 挂回。

    挂回前净额 +3（#3127 批量扫描的时点），挂回后净额 0、份额仍 4（漏网时点）。
    """
    pos = _mk_pos(db, ledger.id, 'SZ159981', shares)
    for kind, qty in (('buy', 3.0), ('buy', 1.0), ('sell', 1.0)):
        _mk_txn(db, ledger.id, position_id=pos.id, txn_type=kind, shares=qty)
    assert scan_disproved_shares(db, _FAMILY) == []  # 净额 > 0：判据不适用
    sell = _mk_txn(db, ledger.id, txn_type='sell', shares=3.0)
    data = svc.reattach_transactions(db, _FAMILY, [sell.id], pos.id)
    assert data['recompute'] is False  # 契约不变：挂回只改归属
    assert data['quantity_after'] == pytest.approx(shares)
    return pos


def test_scan_detects_unrecomputed_shares_after_reattach(db, ledger):
    """核心两态：reattach 后份额未重算 ⇒ 检出且带可执行入口；重算后 ⇒ 不再检出。"""
    pos = _ghost_after_reattach(db, ledger)

    found = scan_disproved_shares(db, _FAMILY)
    assert len(found) == 1
    row = found[0]
    assert row['position_id'] == pos.id
    assert row['symbol'] == 'SZ159981'
    assert row['quantity_now'] == pytest.approx(4.0)
    assert row['flow_net'] == pytest.approx(0.0)
    assert row['flow_state'] == 'netted_out'
    assert row['quantity_if_recomputed'] == pytest.approx(0.0)
    assert row['diff'] == pytest.approx(-4.0)
    assert row['remedy']['action'] == 'position_recompute'
    assert row['remedy']['method'] == 'POST'
    assert row['remedy']['endpoint'] == f'/api/positions/{pos.id}/recompute/'
    assert '重算' in row['remedy']['hint']

    result = recompute_with_audit(db, _FAMILY, pos.id)
    assert result['quantity_after'] == pytest.approx(0.0)
    assert result['ownership_status_after'] == 'cleared'
    assert scan_disproved_shares(db, _FAMILY) == []


def test_reconciliation_run_reports_share_integrity_every_time(db, ledger):
    """常驻接线：每次域 B 收尾都报数，数据修好后下一次 run 必须归零。"""
    pos = _ghost_after_reattach(db, ledger)

    run, _ = run_reconciliation(db, _FAMILY, DOMAIN_B)
    summary = json.loads(run.summary_json)
    assert summary['share_integrity'] == 1
    assert summary['share_integrity_positions'] == [pos.id]

    recompute_with_audit(db, _FAMILY, pos.id)
    run2, _ = run_reconciliation(db, _FAMILY, DOMAIN_B)
    assert json.loads(run2.summary_json)['share_integrity'] == 0


def test_scan_marks_oversold_as_manual_only(db, ledger):
    """超卖（净额<0）单独标注：#3127 明确只报数交人工，不能给无脑重算提示。"""
    pos = _mk_pos(db, ledger.id, 'SZ127094', 40.0)
    _mk_txn(db, ledger.id, position_id=pos.id, symbol='SZ127094', txn_type='buy', shares=10.0)
    _mk_txn(db, ledger.id, position_id=pos.id, symbol='SZ127094', txn_type='sell', shares=20.0)

    found = scan_disproved_shares(db, _FAMILY)
    assert len(found) == 1
    assert found[0]['position_id'] == pos.id
    assert found[0]['flow_state'] == 'oversold'
    assert '先核对' in found[0]['remedy']['hint']


def test_scan_skips_anchored_positions(db, ledger):
    """锚点前的流水本就不计入份额，净额 0 是常态，不能误报（#3125 同源判据）。"""
    pos = _mk_pos(db, ledger.id, 'SZ159981', 5.0, anchor=True)
    _mk_txn(db, ledger.id, position_id=pos.id, txn_type='buy', shares=2.0)
    _mk_txn(db, ledger.id, position_id=pos.id, txn_type='sell', shares=2.0)

    assert scan_disproved_shares(db, _FAMILY) == []


def test_scan_skips_amount_only_and_flowless_positions(db, ledger):
    """货币基金按金额记账 / 无流水空壳行：派生份额恒 0，但都不是「卖完了」。"""
    money_fund = _mk_pos(db, ledger.id, '000198', 500.0)
    _mk_txn(db, ledger.id, position_id=money_fund.id, symbol='000198', txn_type='buy', shares=0.0)
    _mk_pos(db, ledger.id, '000199', 3.0)  # 完全无流水，重算会删行

    assert scan_disproved_shares(db, _FAMILY) == []


def test_scan_skips_cleared_rows_and_other_families(db, ledger):
    """清仓行没有份额可修；跨家庭的幽灵持仓不能被别家扫到。"""
    cleared = _mk_pos(db, ledger.id, 'SZ159981', 0.0, status='cleared')
    _mk_txn(db, ledger.id, position_id=cleared.id, txn_type='buy', shares=1.0)
    _mk_txn(db, ledger.id, position_id=cleared.id, txn_type='sell', shares=1.0)
    other = _mk_pos(db, ledger.id, 'SZ159982', 2.0, family_id=_OTHER_FAMILY)
    _mk_txn(db, ledger.id, position_id=other.id, symbol='SZ159982', txn_type='buy', shares=1.0, family_id=_OTHER_FAMILY)
    _mk_txn(
        db, ledger.id, position_id=other.id, symbol='SZ159982', txn_type='sell', shares=1.0, family_id=_OTHER_FAMILY
    )

    assert scan_disproved_shares(db, _FAMILY) == []
    assert [r['symbol'] for r in scan_disproved_shares(db, _OTHER_FAMILY)] == ['SZ159982']


def test_adjustment_txns_explain_the_gap_and_block_one_click_recompute(db, ledger):
    """真库 #944 的成因必须随命中一起报出来，且不再诱导一键重算。

    用户看到的只有「账上 1000 / 流水 0」，唯一想得到的动作是「补录一笔卖出」——
    而那正是 11-15 18:49 制造这批脏数据的动作（补录同时改流水与份额，差额恒定）。
    所以有补录流水时必须把 remedy 改成「先核对/回滚补录」。
    """
    from app.core.constants import PositionSource  # noqa: PLC0415

    pos = _ghost_after_reattach(db, ledger)
    adj = _mk_txn(
        db,
        ledger.id,
        position_id=pos.id,
        txn_type='sell',
        shares=3.0,
        source=PositionSource.RECONCILIATION_ADJUSTMENT.value,
    )

    found = scan_disproved_shares(db, _FAMILY)
    assert len(found) == 1
    row = found[0]
    assert [t['id'] for t in row['adjustment_txns']] == [adj.id]
    assert row['adjustment_txns'][0]['txn_type'] == 'sell'
    assert row['adjustment_txns'][0]['quantity'] == pytest.approx(3.0)
    assert row['adjustment_txns'][0]['source'] == 'reconciliation_adjustment'
    assert row['remedy']['action'] == 'review_adjustment'
    assert row['remedy']['blocked'] is True
    assert '补录' in row['remedy']['hint']


def test_plain_flows_are_not_marked_as_adjustment(db, ledger):
    """没有补录流水时 remedy 保持原样：不能把每一条命中都当成「被补录污染」。"""
    pos = _ghost_after_reattach(db, ledger)

    found = scan_disproved_shares(db, _FAMILY)
    assert found[0]['position_id'] == pos.id
    assert found[0]['adjustment_txns'] == []
    assert found[0]['remedy']['action'] == 'position_recompute'


def test_endpoint_lists_hits_with_envelope(client, db, ledger):
    """GET /share-integrity/ 是工作台「打开就能看见」的那条线索，信封与既有端点一致。"""
    from app.core.constants import PositionSource  # noqa: PLC0415

    pos = _ghost_after_reattach(db, ledger)
    _mk_txn(
        db,
        ledger.id,
        position_id=pos.id,
        txn_type='sell',
        shares=3.0,
        source=PositionSource.RECONCILIATION_ADJUSTMENT.value,
    )
    db.commit()

    body = client.get('/api/reconciliation/share-integrity/').get_json()
    assert body['message'] == 'ok'
    assert body['data']['total'] == 1
    item = body['data']['items'][0]
    assert item['position_id'] == pos.id
    assert item['quantity_now'] == pytest.approx(4.0)
    assert item['remedy']['action'] == 'review_adjustment'
    assert len(item['adjustment_txns']) == 1


def test_run_and_record_flags_hits_for_the_daily_check(db, ledger):
    """巡检落库：命中即 flagged（`local_checks` 会打 warning），清干净后回到 ok。"""
    from app.models.sync_log import SyncLog  # noqa: PLC0415
    from app.services import position_share_audit as audit  # noqa: PLC0415
    from app.services.position_recompute_entry import recompute_with_audit as recompute  # noqa: PLC0415

    pos = _ghost_after_reattach(db, ledger)
    first = audit.run_and_record(db)
    assert first['status'] == audit.STATUS_FLAGGED
    assert first['stats']['hits'] == 1
    assert first['stats']['position_ids'] == [pos.id]
    logged = db.query(SyncLog).filter(SyncLog.job_name == audit.JOB_NAME).order_by(SyncLog.id.desc()).first()
    assert logged is not None and logged.status == 'flagged'

    recompute(db, _FAMILY, pos.id)
    second = audit.run_and_record(db)
    assert second['status'] == audit.STATUS_OK
    assert second['stats']['hits'] == 0


def test_scan_all_families_covers_every_family(db, ledger):
    """巡检没有请求上下文：两个家庭的命中都要被扫到，不能只看 family 1。"""
    from app.services.position_share_audit import scan_all_families  # noqa: PLC0415

    _ghost_after_reattach(db, ledger)
    other = _mk_pos(db, ledger.id, 'SZ159982', 2.0, family_id=_OTHER_FAMILY)
    _mk_txn(db, ledger.id, position_id=other.id, symbol='SZ159982', txn_type='buy', shares=1.0, family_id=_OTHER_FAMILY)
    _mk_txn(
        db, ledger.id, position_id=other.id, symbol='SZ159982', txn_type='sell', shares=1.0, family_id=_OTHER_FAMILY
    )

    assert {row['symbol'] for row in scan_all_families(db)} == {'SZ159981', 'SZ159982'}


def test_report_to_summary_truncates_ids(db, ledger, monkeypatch):
    """大批量脏数据不能把 run.summary_json 撑大：只留前 20 个 id，计数仍为全量。"""
    from app.services import position_share_audit as audit  # noqa: PLC0415

    fake = [{'position_id': i} for i in range(25)]
    monkeypatch.setattr(audit, 'scan_disproved_shares', lambda db, family_id: fake)
    summary = {}

    assert len(report_to_summary(db, _FAMILY, summary)) == 25
    assert summary['share_integrity'] == 25
    assert summary['share_integrity_positions'] == list(range(20))
