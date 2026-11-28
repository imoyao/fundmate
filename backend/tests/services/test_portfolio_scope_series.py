# -*- coding: utf-8 -*-
"""组合档（portfolio scope）在「时间维度」三处端点的落地测试（三期 D）。

覆盖四个后端空洞里的三个（净值曲线仍需 `asset_snapshots` 加组合维度，见 D134）：

1. `/api/positions/?portfolio_id=` —— 浮亏回本块的数据源；
2. `cleared-cycles?portfolio_id=` —— 清仓复盘（含浮亏计数）；
3. `pnl-calendar?portfolio_id=` —— 收益日历（不读写物化行）。

三条判据的共同前提：**组合归属按持仓判定，不按流水/账户的 `ledger_id` 判定**。
故每个夹具都刻意造出「显式指派覆盖账户继承」的持仓（D20 语义），并用它做反向断言——
只按成员账本过滤会把改派走的持仓算回来（真库 257→164 那次同款错法）。
"""

import datetime as dt

import pytest

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.summary.models import PnlDailySnapshot
from app.domains.transactions.models import Transaction
from app.services.analytics.cleared_cycles import build_cleared_cycles
from app.services.pnl_calendar import build_pnl_series
from app.services.transaction_scope import filter_transactions_by_scope


def _ledger(db, name, portfolio_id=None):
    row = Ledger(name=name, ledger_type='bank', family_id=1, portfolio_id=portfolio_id)
    db.add(row)
    db.commit()
    return row


def _nav(db, code, day, unit_nav):
    db.add(DailyWorth(fund_code=code, date=day, unit_nav=unit_nav))
    db.commit()


def _seed_scope(db, make_position, make_transaction):
    """三笔持仓 × 三种归属：继承 / 改派到别处 / 外部显式指派到本组合。"""
    p1 = Portfolio(name='组合一', family_id=1)
    p2 = Portfolio(name='组合二', family_id=1)
    db.add_all([p1, p2])
    db.commit()
    l1 = _ledger(db, '继承账本', portfolio_id=p1.id)
    l2 = _ledger(db, '外部账本')
    day = dt.date(2026, 1, 5)
    rows = {
        'inherited': make_position(
            symbol='000001', name='继承', quantity=100, avg_price=1.0, asset_type='fund', ledger_id=l1.id
        ),
        'overridden': make_position(
            symbol='000002',
            name='改派',
            quantity=100,
            avg_price=1.0,
            asset_type='fund',
            ledger_id=l1.id,
            portfolio_id=p2.id,
        ),
        'explicit': make_position(
            symbol='000003',
            name='外部显式',
            quantity=100,
            avg_price=1.0,
            asset_type='fund',
            ledger_id=l2.id,
            portfolio_id=p1.id,
        ),
    }
    txns = {}
    for idx, (key, pos) in enumerate(rows.items()):
        txns[key] = make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=100,
            price=1.0,
            confirm_date=day,
            symbol=pos.symbol,
            asset_type='fund',
        )
        _nav(db, pos.symbol, day, 1.0 + idx * 0.1)
        _nav(db, pos.symbol, day + dt.timedelta(days=1), 1.1 + idx * 0.1)
    # 无持仓的入金流水：只能按流水自己的 ledger_id 归属（fixture 强制要有 position_id，
    # 而这类流水正是「没有持仓」的形态，故直接建模型）
    cash = Transaction(
        position_id=None,
        ledger_id=l1.id,
        family_id=1,
        txn_type='deposit',
        symbol='CASH',
        position_name='入金',
        account_name='继承账本',
        quantity=0,
        price=0,
        amount=Money.yuan_to_cents(1000),
        confirm_date=day,
        status='success',
        asset_type='cash',
    )
    db.add(cash)
    db.commit()
    txns['cash_in'] = cash
    return {'p1': p1, 'p2': p2, 'l1': l1, 'l2': l2, 'pos': rows, 'txn': txns}


# -------------------- 流水级归属（唯一出口） --------------------


def test_流水归属_按持仓判定且显式覆盖继承(db, make_position, make_transaction):
    s = _seed_scope(db, make_position, make_transaction)
    all_txns = list(s['txn'].values())

    p1 = {t.id for t in filter_transactions_by_scope(db, 1, all_txns, portfolio_id=s['p1'].id)}
    p2 = {t.id for t in filter_transactions_by_scope(db, 1, all_txns, portfolio_id=s['p2'].id)}

    # p1：继承（账本默认组合）+ 外部账本的显式指派 + 该账本的入金；**不含**改派走的那笔
    assert p1 == {s['txn']['inherited'].id, s['txn']['explicit'].id, s['txn']['cash_in'].id}
    # p2：只有显式改派过来的那笔（它记在 p1 的成员账本里——按 ledger 过滤就会算进 p1）
    assert p2 == {s['txn']['overridden'].id}


def test_流水归属_账户档与家庭档不受影响(db, make_position, make_transaction):
    s = _seed_scope(db, make_position, make_transaction)
    all_txns = list(s['txn'].values())

    l1 = {t.id for t in filter_transactions_by_scope(db, 1, all_txns, ledger_id=s['l1'].id)}
    assert l1 == {s['txn']['inherited'].id, s['txn']['overridden'].id, s['txn']['cash_in'].id}
    assert len(filter_transactions_by_scope(db, 1, all_txns)) == len(all_txns)


def test_流水归属_互斥与非法组合抛错(db, make_position, make_transaction):
    s = _seed_scope(db, make_position, make_transaction)
    all_txns = list(s['txn'].values())

    with pytest.raises(ValueError, match='互斥'):
        filter_transactions_by_scope(db, 1, all_txns, ledger_id=s['l1'].id, portfolio_id=s['p1'].id)
    with pytest.raises(ValueError, match='投资组合不存在'):
        filter_transactions_by_scope(db, 1, all_txns, portfolio_id=999999)


# -------------------- 收益日历（组合档） --------------------


def _series(db, **kwargs):
    return build_pnl_series(db, 1, '2026-01-05', '2026-01-07', **kwargs)


def test_日历组合档_只算本组合持仓且不读写物化(db, make_position, make_transaction):
    s = _seed_scope(db, make_position, make_transaction)

    data = _series(db, portfolio_id=s['p1'].id)
    assert data['scope'] == 'portfolio'
    assert data['first_txn_date'] == '2026-01-05'

    # 组合一含「继承 000001」与「外部显式 000003」两只；改派到 p2 的 000002 不进本组合。
    # 1/6 净值各 +0.1 ⇒ 市值 110 + 130；若把 000002 算进来会多出 100×1.3。
    by_date = {d['date']: d for d in data['days']}
    assert by_date['2026-01-06']['net_worth'] == pytest.approx(110 + 130)
    assert by_date['2026-01-06']['daily_pnl'] == pytest.approx(10 + 10)

    # 组合档旁路物化：一次组合档调用之后表里仍是一行都没有
    assert db.query(PnlDailySnapshot).count() == 0


def test_日历组合档_与账户档逐位一致(db, make_position, make_transaction):
    """组合成员与账户完全重合时，两档必须同数（同持仓、同决策集、同一引擎）。"""
    pf = Portfolio(name='单账本组合', family_id=1)
    db.add(pf)
    db.commit()
    lg = _ledger(db, '单独账本', portfolio_id=pf.id)
    pos = make_position(ledger_id=lg.id, symbol='000900', name='单只', quantity=100, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=lg.id,
        txn_type='buy',
        quantity=100,
        price=1.0,
        confirm_date=dt.date(2026, 1, 5),
        symbol='000900',
        asset_type='fund',
    )
    _nav(db, '000900', dt.date(2026, 1, 5), 1.0)
    _nav(db, '000900', dt.date(2026, 1, 6), 1.08)

    ledger_series = _series(db, ledger_id=lg.id)
    portfolio_series = _series(db, portfolio_id=pf.id)

    assert portfolio_series['days'] == ledger_series['days']
    assert portfolio_series['month_total'] == ledger_series['month_total']


def test_日历组合档_读写互斥(db, make_position, make_transaction):
    s = _seed_scope(db, make_position, make_transaction)
    with pytest.raises(ValueError, match='互斥'):
        _series(db, ledger_id=s['l1'].id, portfolio_id=s['p1'].id)


# -------------------- 清仓复盘（组合档） --------------------


def _closed_cycle(db, make_position, make_transaction, ledger_id, symbol, name):
    pos = make_position(ledger_id=ledger_id, symbol=symbol, name=name, quantity=0, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2026, 1, 5),
        symbol=symbol,
        asset_type='fund',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=ledger_id,
        txn_type='sell',
        quantity=1000,
        price=1.2,
        confirm_date=dt.date(2026, 1, 9),
        symbol=symbol,
        asset_type='fund',
    )
    return pos


def test_清仓复盘组合档_只回本组合的周期(db, make_position, make_transaction):
    s = _seed_scope(db, make_position, make_transaction)
    _closed_cycle(db, make_position, make_transaction, s['l1'].id, '000011', '一账本周期')
    _closed_cycle(db, make_position, make_transaction, s['l2'].id, '000022', '二账本周期')

    data = build_cleared_cycles(db, 1, portfolio_id=s['p1'].id)

    symbols = {c['symbol'] for c in data['cycles']}
    # 000011 在 p1 的成员账本上 ⇒ 进；000022 在非成员账本、且未显式指派 ⇒ 不进
    assert symbols == {'000011'}


def test_清仓复盘组合档_改派持仓不进原账本默认组合(db, make_position, make_transaction):
    """显式指派优先：改派走的持仓，其周期不得再出现在账户默认组合里（D20 语义）。"""
    s = _seed_scope(db, make_position, make_transaction)
    pos = _closed_cycle(db, make_position, make_transaction, s['l1'].id, '000033', '改派周期')
    pos.portfolio_id = s['p2'].id
    db.commit()

    p1 = build_cleared_cycles(db, 1, portfolio_id=s['p1'].id)
    p2 = build_cleared_cycles(db, 1, portfolio_id=s['p2'].id)

    assert '000033' not in {c['symbol'] for c in p1['cycles']}
    assert '000033' in {c['symbol'] for c in p2['cycles']}


# -------------------- 持仓列表（组合档，浮亏回本的数据源） --------------------


def test_持仓列表组合档_显式覆盖继承(client, db, make_position, make_transaction):
    s = _seed_scope(db, make_position, make_transaction)

    data = client.get(f'/api/positions/?portfolio_id={s["p1"].id}&per_page=50').get_json()['data']
    ids = {row['id'] for row in data}

    assert ids == {s['pos']['inherited'].id, s['pos']['explicit'].id}
    assert s['pos']['overridden'].id not in ids


def test_持仓列表组合档_非法组合返回400(client, db):
    resp = client.get('/api/positions/?portfolio_id=999999')
    assert resp.status_code == 400


# -------------------- 端点互斥（视图层错误映射） --------------------


@pytest.mark.parametrize('path', ['/api/summary/pnl-calendar/', '/api/summary/cleared-cycles/'])
def test_两个端点都拒绝同传两档(client, db, make_position, make_transaction, path):
    s = _seed_scope(db, make_position, make_transaction)
    resp = client.get(f'{path}?ledger_id={s["l1"].id}&portfolio_id={s["p1"].id}')
    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001
