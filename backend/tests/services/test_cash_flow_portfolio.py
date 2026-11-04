# -*- coding: utf-8 -*-
"""组合级资金流动（#2681）回归：互转抵消、Σ 可加性、作用域契约。

钉三件事：

1. **组合内 A→B 划转抵消为 0**：不得记成「一笔入金 + 一笔出金」共 2 万流水。
   这是本卡最容易写错的地方——账户级单传一个 ledger 时 `pair_internal_transfers`
   天然配不上对，只有组合级一次传入全集才配得上。
2. **Σ 账户 ≡ 组合**：账户级各记 −1 万 / +1 万（净额为 0 的「各记各的」），
   相加正好等于组合级的抵消结果，同一套口径两种视图。
3. 作用域契约：`ledger_id` / `portfolio_id` 二选一，同传与都不传都回 400（`error_code=1001`），
   组合不存在也回 400——不设隐式默认，避免「传错了还能拿到数」。
"""

import datetime as dt

import pytest

from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.cash_flow_service import build_cash_flow

# 外部入金日 / 组合内互转日（同日同额反向才会被配对剔除）
DAY = dt.date(2026, 3, 2)
DAY2 = dt.date(2026, 3, 5)
RANGE = ('2026-03-01', '2026-03-31')


def _portfolio(db, name='资金流动组合'):
    pf = Portfolio(family_id=1, name=name, is_deleted=False)
    db.add(pf)
    db.commit()
    return pf


def _ledger(db, name, portfolio_id=None, family_id=1):
    ledger = Ledger(name=name, ledger_type='fund', family_id=family_id, portfolio_id=portfolio_id)
    db.add(ledger)
    db.flush()
    return ledger


def _seed_account(db, make_position, make_transaction, ledger, rows, symbol='AAA'):
    """一个账户一张持仓 + 若干流水（amount 传元，夹具内部转分）。"""
    pos = make_position(
        symbol=symbol, name='测试标的', ledger_id=ledger.id, asset_type='bond', quantity=0, current_price=1.0
    )
    for txn_type, amount, day in rows:
        make_transaction(
            pos.id, ledger.id, txn_type=txn_type, asset_type='bond', amount=amount, confirm_date=day, symbol=symbol
        )
    db.commit()
    return pos


def test_组合内互转抵消为0且等于Σ账户(db, make_position, make_transaction):
    """A 外部入金 5 万；A→B 划转 1 万（同额反向同一天）。"""
    pf = _portfolio(db)
    a = _ledger(db, '组合账户A', portfolio_id=pf.id)
    b = _ledger(db, '组合账户B', portfolio_id=pf.id)

    _seed_account(
        db,
        make_position,
        make_transaction,
        a,
        [('deposit', 50000, DAY), ('withdraw', 10000, DAY2)],
    )
    _seed_account(
        db,
        make_position,
        make_transaction,
        b,
        [('deposit', 10000, DAY2)],
        symbol='BBB',
    )

    combo = build_cash_flow(db, 1, portfolio_id=pf.id, start_date=RANGE[0], end_date=RANGE[1])

    assert combo['scope'] == 'portfolio'
    assert combo['ledger_id'] is None
    assert combo['portfolio_id'] == pf.id
    # 1 万互转被配对剔除：入金只剩外部那 5 万，出金 0（不是 6 万 / 1 万）
    assert combo['totals']['deposit'] == pytest.approx(50000.0)
    assert combo['totals']['withdraw'] == pytest.approx(0.0)
    assert combo['totals']['net_invested'] == pytest.approx(50000.0)
    # 逐笔流水里也不该出现被抵消的那两笔
    assert len(combo['external_flows']) == 1

    # Σ 账户 ≡ 组合：账户级各记各的（−1 万 / +1 万），相加正好抵消
    a_net = build_cash_flow(db, 1, ledger_id=a.id)['totals']['net_invested']
    b_net = build_cash_flow(db, 1, ledger_id=b.id)['totals']['net_invested']
    assert a_net == pytest.approx(40000.0)
    assert b_net == pytest.approx(10000.0)
    assert a_net + b_net == pytest.approx(combo['totals']['net_invested'])


def test_空组合_返回零值不抛错(db):
    """组合存在但没有成员账本：出 0 与空曲线，不报错、也不回退家庭级。"""
    pf = _portfolio(db, '空组合')
    _ledger(db, '组合外账户')  # 家庭里有钱，但不在本组合

    data = build_cash_flow(db, 1, portfolio_id=pf.id)

    assert data['scope'] == 'portfolio'
    assert data['totals']['deposit'] == 0.0
    assert data['totals']['net_invested'] == 0.0
    assert data['totals']['has_deposit_record'] is False
    assert data['net_worth_series'] == []
    assert data['external_flows'] == []


def test_服务层_互斥与必填(db):
    with pytest.raises(ValueError, match='互斥'):
        build_cash_flow(db, 1, ledger_id=1, portfolio_id=1)
    with pytest.raises(ValueError, match='必填'):
        build_cash_flow(db, 1)
    with pytest.raises(ValueError, match='投资组合不存在'):
        build_cash_flow(db, 1, portfolio_id=999999)


def test_接口_作用域契约(client, db, make_position, make_transaction):
    pf = _portfolio(db, '接口组合')
    a = _ledger(db, '接口账户A', portfolio_id=pf.id)
    _seed_account(db, make_position, make_transaction, a, [('deposit', 30000, DAY)])

    # 组合级生效
    r = client.get(f'/api/summary/cash-flow/?portfolio_id={pf.id}')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['scope'] == 'portfolio'
    assert data['totals']['net_invested'] == pytest.approx(30000.0)

    # 账户级行为不变（含作用域回显）
    r = client.get(f'/api/summary/cash-flow/?ledger_id={a.id}')
    assert r.status_code == 200
    assert r.get_json()['data']['scope'] == 'ledger'

    # 同传 / 都不传 / 组合不存在 → 400 + error_code=1001
    for url in (
        '/api/summary/cash-flow/?ledger_id=%d&portfolio_id=%d' % (a.id, pf.id),
        '/api/summary/cash-flow/',
        '/api/summary/cash-flow/?portfolio_id=999999',
    ):
        r = client.get(url)
        assert r.status_code == 400, url
        assert r.get_json()['error_code'] == 1001, url
