# -*- coding: utf-8 -*-
"""#3089 归置：同一笔钱不再被「持仓市值」与「账外类现金」各算一遍。

反向验证口径：四处类现金出口（账户级汇总 / 账户级明细 / 家庭级明细 /
`get_cash_like_stats`）任一处漏掉 `covered_position_id IS NULL`，下面的断言都会转红。
另覆盖总资产变化、撤销归置、每日货基收益基线、逆回购在途本金与自动挂回候选集。
"""

from app.domains.ledgers.models import Ledger
from app.services.cash_like_settle import outstanding_cents
from app.services.ledger_service import LedgerService
from app.services.money_fund_income import _collect_orphan_flows
from app.services.position_orphan_flows import find_orphan_cash_flows
from app.services.position_valuation import market_value_cents
from app.services.summary_service import (
    get_summary_data,
    orphan_cash_like_breakdown,
    orphan_cash_like_breakdown_all,
    orphan_money_fund_totals_by_ledger,
)


def _ledger(db, name='银河证券'):
    lg = Ledger(name=name, ledger_type='fund', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _orphan(make_transaction, ledger_id, txn_type, amount_yuan, *, covered_position_id=None, **kwargs):
    return make_transaction(
        None,
        ledger_id,
        txn_type=txn_type,
        amount=amount_yuan,
        asset_type=kwargs.pop('asset_type', 'money_fund'),
        entry_status='orphan',
        covered_position_id=covered_position_id,
        **kwargs,
    )


def _scene(db, make_transaction, make_position, *, covered_now=True):
    """持仓（市值 1000 元）+ 3 笔未归置 + 2 笔已归置流水。

    `covered_now=False` 时先让 5 笔都未归置，供「归置前后总资产变化」用例用。
    """
    ledger = _ledger(db)
    pos = make_position(
        symbol='MF001',
        name='覆盖用货基',
        ledger_id=ledger.id,
        quantity=1000,
        avg_price=1.0,
        current_price=1.0,
        asset_type='fund',
    )
    pid = pos.id if covered_now else None
    rows = [
        _orphan(make_transaction, ledger.id, 'buy', 100),
        _orphan(make_transaction, ledger.id, 'buy', 50),
        _orphan(make_transaction, ledger.id, 'dividend', 10),
        _orphan(make_transaction, ledger.id, 'buy', 200, covered_position_id=pid),
        _orphan(make_transaction, ledger.id, 'dividend_tax', 5, covered_position_id=pid),
    ]
    db.flush()
    return ledger, pos, rows


def _assert_four_calibers(db, ledger, *, net_cents, income_cents, txn_count):
    """四处口径对同一批数据必须给出同一个结论。"""
    net_map, income_map = orphan_money_fund_totals_by_ledger(db, 1)
    assert net_map.get(ledger.id, 0) == net_cents
    assert income_map.get(ledger.id, 0) == income_cents

    items, net, income = orphan_cash_like_breakdown(db, 1, ledger.id)
    assert (net, income) == (net_cents, income_cents)
    assert sum(it['txn_count'] for it in items) == txn_count

    items_all, net_all, income_all = orphan_cash_like_breakdown_all(db, 1)
    assert (net_all, income_all) == (net_cents, income_cents)
    assert sum(it['txn_count'] for it in items_all) == txn_count

    stats = LedgerService.get_cash_like_stats(db, ledger.id, 1)
    assert round(stats['orphan_amount'] * 100) == net_cents
    assert round(stats['orphan_income_amount'] * 100) == income_cents
    assert sum(it['txn_count'] for it in stats['cash_like_breakdown']) == txn_count


def test_four_calibers_exclude_covered_rows(db, make_transaction, make_position):
    """归置后四处口径都只看到 3 笔未归置流水（本金 150 / 收益 10）。"""
    ledger, _pos, _rows = _scene(db, make_transaction, make_position)
    _assert_four_calibers(db, ledger, net_cents=15000, income_cents=1000, txn_count=3)


def test_cover_lowers_total_assets_but_not_position_value(db, make_transaction, make_position):
    """归置让总资产少掉被排除的 195 元（200 本金 − 5 代扣税），持仓市值一分不动。"""
    ledger, pos, rows = _scene(db, make_transaction, make_position, covered_now=False)
    _assert_four_calibers(db, ledger, net_cents=35000, income_cents=500, txn_count=5)
    before = get_summary_data(db, 1)
    mv_before = market_value_cents(pos)

    for t in rows[-2:]:
        t.covered_position_id = pos.id
    db.flush()  # SessionLocal autoflush=False，写后必须显式 flush 才能被后续 query 看见

    after = get_summary_data(db, 1)
    assert round(before['total_assets_cny'] - after['total_assets_cny'], 2) == 195.0
    assert after['net_assets_cny'] == after['total_assets_cny']
    assert market_value_cents(pos) == mv_before
    assert all(t.position_id is None for t in rows[-2:]), '归置绝不改 position_id'
    _assert_four_calibers(db, ledger, net_cents=15000, income_cents=1000, txn_count=3)


def test_undo_cover_restores_calibers(db, make_transaction, make_position):
    """清空 covered_position_id 即回到原状，不需要删流水。"""
    ledger, _pos, rows = _scene(db, make_transaction, make_position)
    for t in rows[-2:]:
        t.covered_position_id = None
    db.flush()
    _assert_four_calibers(db, ledger, net_cents=35000, income_cents=500, txn_count=5)


def test_other_amount_calibers_skip_covered_rows(db, make_transaction, make_position):
    """货基每日收益基线 / 逆回购在途本金同样不看已归置流水。"""
    ledger, pos, _rows = _scene(db, make_transaction, make_position)
    _orphan(make_transaction, ledger.id, 'buy', 300, covered_position_id=pos.id, symbol='MF002')
    _orphan(make_transaction, ledger.id, 'buy', 700, asset_type='reverse_repo', symbol='204001')
    _orphan(
        make_transaction, ledger.id, 'buy', 900, asset_type='reverse_repo', symbol='204001', covered_position_id=pos.id
    )
    db.flush()

    flows = _collect_orphan_flows(db, 1, None)
    # 未归置且属于本金方向：100 + 50（000001）+ 700（204001）= 850 元 = 85000 分；
    # 分红、代扣税与三笔已归置流水都不进持有基线。
    assert sum(sum(day.values()) for day in flows.values()) == 85000
    assert outstanding_cents(db, 1, ledger.id, '204001') == 70000


def test_auto_reattach_candidate_set_excludes_covered_rows(db, make_transaction, make_position):
    """建仓自动挂回不得把已归置流水再挂到持仓上（会双计成本）。"""
    ledger = _ledger(db)
    pos = make_position(symbol='MF001', name='覆盖用货基', ledger_id=ledger.id, quantity=1, avg_price=1.0)
    covered = _orphan(make_transaction, ledger.id, 'buy', 100, symbol='MF001', covered_position_id=pos.id)
    uncovered = _orphan(make_transaction, ledger.id, 'buy', 200, symbol='MF001')
    db.flush()

    matched = find_orphan_cash_flows(db, ledger.id, 'MF001', 1)
    assert [t.id for t in matched] == [uncovered.id], '只应捞到未归置的那笔'
    assert covered.covered_position_id == pos.id
    assert covered.position_id is None


def test_transaction_list_and_detail_expose_readonly_marker(client, db, make_transaction, make_position):
    """流水不隐藏：列表/详情都给只读标记，详情额外给持仓名。"""
    _ledger_obj, pos, rows = _scene(db, make_transaction, make_position)
    db.commit()  # 请求会话是独立 Session：写入须提交后才对端点可见
    txn_id = rows[-1].id
    listed = client.get('/api/transactions/').get_json()['data']
    row = next(r for r in listed if r['id'] == txn_id)
    assert row['covered_position_id'] == pos.id
    detail = client.get(f'/api/transactions/{txn_id}/').get_json()['data']
    assert detail['covered_position_id'] == pos.id
    assert detail['covered_position_name'] == '覆盖用货基'
