"""家庭级资金流动（2026-11-27）：三级作用域的第三种口径。

钉的是「家庭 ≡ Σ 账户」这条可加性在资金流上的四条边界：

- 家庭级 = **全家账本集合**（不是「下游不过滤」——`collect_flows` 拿到空集合会返回空，
  页面会显示「这个家庭从没有过资金进出」）；
- 家庭内账户互转在家庭集合里配对抵消（净额 0），账户级各记 ∓1 万、相加仍为 0；
- 家庭级只能**显式** `scope=family` 请求：两个 id 都不传仍是 400（不设隐式默认，
  漏传参数静默变成全家数据比报错更坏），且 `scope` 与 id 互斥；
- 别家的账本不能混进来（`family_ledger_ids` 少写一次 family 过滤就是跨家庭取数）。
"""

import datetime as dt

import pytest

from app.domains.ledgers.models import Ledger
from app.services.cash_flow_service import build_cash_flow

DAY = dt.date(2026, 3, 2)
DAY2 = dt.date(2026, 4, 1)


def _ledger(db, name, family_id=1):
    ledger = Ledger(name=name, ledger_type='fund', family_id=family_id)
    db.add(ledger)
    db.flush()
    return ledger


def _seed(db, make_position, make_transaction, ledger, rows):
    """在指定账本下落一串流水（`rows` = [(txn_type, 金额元, 日期)]）。"""
    pos = make_position(
        symbol='AAA', name='测试标的', ledger_id=ledger.id, asset_type='bond', quantity=0, current_price=1.0
    )
    for txn_type, amount, day in rows:
        make_transaction(
            pos.id, ledger.id, txn_type=txn_type, asset_type='bond', amount=amount, confirm_date=day, symbol='AAA'
        )
    db.commit()
    return pos


def test_family_scope_aggregates_all_accounts(db, make_position, make_transaction):
    """两个账户各自入金 → 家庭级入金 = 两账户之和，且 scope 回 'family'。"""
    a = _ledger(db, '家庭A')
    b = _ledger(db, '家庭B')
    _seed(db, make_position, make_transaction, a, [('deposit', 100000, DAY), ('withdraw', 20000, DAY2)])
    _seed(db, make_position, make_transaction, b, [('deposit', 50000, DAY)])

    data = build_cash_flow(db, 1, scope='family', start_date='2026-03-01', end_date='2026-04-30')

    assert data['scope'] == 'family'
    # 家庭级没有单个账户 / 组合的身份，两个键都必须是 null（前端靠它决定文案）
    assert data['ledger_id'] is None
    assert data['portfolio_id'] is None
    assert data['totals']['deposit'] == 150000.0
    assert data['totals']['withdraw'] == 20000.0
    assert data['totals']['net_invested'] == 130000.0
    # 「投资以来」起点取全家最早一笔资金流水
    assert data['first_txn_date'] == DAY.isoformat()


def test_family_net_matches_sum_of_account_net(db, make_position, make_transaction):
    """家庭内互转：账户级各记 ∓1 万，家庭级配对抵消 ⇒ 净额与「Σ 账户」一致。

    ⚠️ 相等的是**净额**，不是每个字段：Σ 账户的 withdraw 是 1 万、deposit 是 1 万，
    家庭级两个都是 0（这笔钱没跨出家庭）。这正是 `pair_internal_transfers` 的意义。
    """
    a = _ledger(db, '家庭A')
    b = _ledger(db, '家庭B')
    _seed(db, make_position, make_transaction, a, [('deposit', 100000, DAY), ('withdraw', 10000, DAY2)])
    _seed(db, make_position, make_transaction, b, [('deposit', 10000, DAY2)])

    family = build_cash_flow(db, 1, scope='family', start_date='2026-03-01', end_date='2026-04-30')
    account_a = build_cash_flow(db, 1, ledger_id=a.id, start_date='2026-03-01', end_date='2026-04-30')
    account_b = build_cash_flow(db, 1, ledger_id=b.id, start_date='2026-03-01', end_date='2026-04-30')

    assert family['totals']['deposit'] == 100000.0
    assert family['totals']['withdraw'] == 0.0
    assert family['totals']['net_invested'] == 100000.0
    assert family['totals']['net_invested'] == pytest.approx(
        account_a['totals']['net_invested'] + account_b['totals']['net_invested']
    )
    # 逐笔列表同样剔除互转（否则出现「列表 2 笔、总额只算 0 笔」的对不上，同 #2681）
    assert [flow['direction'] for flow in family['external_flows']] == ['in']


def test_family_scope_excludes_other_family(db, make_position, make_transaction):
    """别家账本的入金不能出现在本家庭响应里（少一次 family 过滤就是跨家庭取数）。"""
    mine = _ledger(db, '我的账户')
    other = _ledger(db, '别人家账户', family_id=2)
    _seed(db, make_position, make_transaction, mine, [('deposit', 7000, DAY)])
    _seed(db, make_position, make_transaction, other, [('deposit', 900000, DAY)])

    data = build_cash_flow(db, 1, scope='family', start_date='2026-03-01', end_date='2026-04-30')

    assert data['totals']['deposit'] == 7000.0


def test_family_scope_must_be_explicit(db):
    """两个 id 都不传且没给 scope ⇒ 400（不设隐式默认）。"""
    with pytest.raises(ValueError, match='scope=family'):
        build_cash_flow(db, 1)


def test_scope_family_conflicts_with_ids(db, make_position, make_transaction):
    """`scope=family` 与任何 id 互斥：容忍矛盾参数会让「想看账户、实际给了全家」静默生效。"""
    ledger = _ledger(db, '家庭A')
    with pytest.raises(ValueError, match='scope=family'):
        build_cash_flow(db, 1, ledger_id=ledger.id, scope='family')


def test_invalid_scope_rejected(db):
    with pytest.raises(ValueError, match='scope 参数非法'):
        build_cash_flow(db, 1, scope='household')


def test_explicit_ledger_scope_needs_ledger_id(db):
    with pytest.raises(ValueError, match='scope=ledger'):
        build_cash_flow(db, 1, scope='ledger')


def test_family_scope_keeps_market_value_but_skips_residual(db, make_position, make_transaction):
    """家庭级不推导现金残差 ⇒ 期末资产 / 累计收益为 null，持仓市值照常给。

    依据：现金残差的前提是「集合里每个账户的入金都记全了」。账户级还能靠余额自证，
    家庭合并后缺一笔入金就是大额负数（真库实测 −34 万 ⇒ 期末资产 −8 万）。
    与其给一个负资产，不如让页面拿可靠的持仓市值报数。
    """
    a = _ledger(db, '家庭A')
    _seed(db, make_position, make_transaction, a, [('deposit', 10000, DAY)])

    data = build_cash_flow(db, 1, scope='family', start_date='2026-03-01', end_date='2026-04-30')

    assert data['totals']['cash_residual'] is None
    assert data['totals']['end_asset'] is None
    assert data['totals']['total_return'] is None
    assert data['totals']['market_value'] is not None
    assert data['coverage']['cash_residual_is_derived'] is False


def test_account_scope_still_derives_residual(db, make_position, make_transaction):
    """账户级行为不变：期末资产 = 持仓市值 + 现金残差，累计收益 = 期末资产 − 净投入。"""
    a = _ledger(db, '家庭A')
    _seed(db, make_position, make_transaction, a, [('deposit', 10000, DAY)])

    data = build_cash_flow(db, 1, ledger_id=a.id, start_date='2026-03-01', end_date='2026-04-30')

    totals = data['totals']
    assert totals['cash_residual'] == pytest.approx(10000.0)
    assert totals['end_asset'] == pytest.approx(totals['market_value'] + totals['cash_residual'])
    assert totals['total_return'] == pytest.approx(totals['end_asset'] - totals['net_invested'])


def test_cash_asset_type_deposits_are_counted(db, make_position, make_transaction):
    """入金记在「现金 / 货基」账户上也必须算 L1（`include_cash_equivalents` 回归）。

    之前 `build_layers` 用默认 `include_cash_equivalents=False`，把
    `asset_type ∈ {cash, money_fund, reverse_repo}` 的流水整条丢掉——真库实测微众银行
    25.8 万入金、14.4 万出金全部消失，面板显示「还没有入金记录，净投入按 0」。
    L1 是外部资金流，与「算不算主动投资」无关。
    """
    bank = _ledger(db, '银行现金账户')
    pos = make_position(symbol='CASH', name='现金', ledger_id=bank.id, asset_type='cash', quantity=0, current_price=1.0)
    make_transaction(pos.id, bank.id, txn_type='deposit', asset_type='cash', amount=258529, confirm_date=DAY)
    make_transaction(pos.id, bank.id, txn_type='withdraw', asset_type='cash', amount=144780, confirm_date=DAY2)
    db.commit()

    data = build_cash_flow(db, 1, ledger_id=bank.id, start_date='2026-03-01', end_date='2026-04-30')

    assert data['totals']['deposit'] == 258529.0
    assert data['totals']['withdraw'] == 144780.0
    assert data['totals']['net_invested'] == 113749.0
    assert data['totals']['has_deposit_record'] is True


def test_接口_家庭级作用域(client, db, make_position, make_transaction):
    """`?scope=family` 走通接口层；与 id 同传回 400 而不是静默取其中一边。"""
    a = _ledger(db, '接口家庭A')
    b = _ledger(db, '接口家庭B')
    _seed(db, make_position, make_transaction, a, [('deposit', 30000, DAY)])
    _seed(db, make_position, make_transaction, b, [('deposit', 20000, DAY)])

    r = client.get('/api/summary/cash-flow/?scope=family')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['scope'] == 'family'
    assert data['totals']['net_invested'] == pytest.approx(50000.0)

    for url in (
        f'/api/summary/cash-flow/?scope=family&ledger_id={a.id}',
        '/api/summary/cash-flow/?scope=household',
    ):
        r = client.get(url)
        assert r.status_code == 400, url
        assert r.get_json()['error_code'] == 1001, url
