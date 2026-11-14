# -*- coding: utf-8 -*-
"""#3107 基准超额曲线的区间左界（`start_date=inception` 哨兵）。

锁定三件事：

1. **有流水** ⇒ 起点 = 作用域最早一笔资金流水的生效日，**含出入金**
   （组合的第一笔入金就是它的起点；等第一笔买入会把最开始那段砍掉）；
2. **无流水** ⇒ 回落到近 90 天，且响应里的 `start_date` 就是**实际起点**
   ——不能把 90 天窗口当「成立来」报出去；
3. **非哨兵原样透传** —— 日期格式与区间倒挂仍由口径层统一拒绝，
   两处各写一遍校验必然演化成「一个接受、一个拒绝」的漂移。

变异探针：把 `resolve_scope_start` 改成直接 `return start_date`（不解析），
`test_端点_inception起点回写为最早流水日` 会拿到 400（口径层 `fromisoformat('inception')`
抛 ValueError），即「没解析」立刻可见。
"""

import datetime as dt

import pytest

from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.analytics.excess_range import DEFAULT_RANGE_DAYS, resolve_scope_start

D_EARLY = dt.date(2024, 3, 1)  # 成员甲第一笔买入
D_DEPOSIT = dt.date(2024, 1, 15)  # 更早的一笔入金（全周期真正的起点）
D_END = dt.date(2026, 11, 14)


def _seed_portfolio(db, make_position, make_transaction, *, with_deposit=False):
    """组合「成员甲」：2024-03-01 买入 1000 份；可选更早的一笔入金。"""
    pf = Portfolio(name='区间解析组合', family_id=1)
    db.add(pf)
    db.flush()
    ledger = Ledger(name='区间解析成员', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add(ledger)
    db.flush()
    pos = make_position(
        symbol='000031',
        name='区间解析基金',
        quantity=1000,
        avg_price=1.0,
        asset_type='fund',
        ledger_id=ledger.id,
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=ledger.id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=D_EARLY,
        symbol='000031',
    )
    if with_deposit:
        # 入金流水通常没有 position_id（#1916 的错配形态之一），但它们决定全周期起点
        make_transaction(
            position_id=None,
            ledger_id=ledger.id,
            txn_type='deposit',
            quantity=0,
            price=0,
            amount=10000.0,
            confirm_date=D_DEPOSIT,
            symbol='CASH',
        )
    db.commit()
    return pf


def test_inception_取组合成员最早买入日(db, make_position, make_transaction):
    pf = _seed_portfolio(db, make_position, make_transaction)

    start = resolve_scope_start(db, 1, 'inception', D_END.isoformat(), portfolio_id=pf.id)

    assert start == D_EARLY.isoformat()


def test_inception_含出入金_起点早于第一笔买入(db, make_position, make_transaction):
    """「成立来」是账户开始有钱那天，不是第一次买基金那天。"""
    pf = _seed_portfolio(db, make_position, make_transaction, with_deposit=True)

    start = resolve_scope_start(db, 1, 'inception', D_END.isoformat(), portfolio_id=pf.id)

    assert start == D_DEPOSIT.isoformat()


def test_inception_无流水回落90天窗口(db, make_position, make_transaction):
    """组合已建、成员账户在、但一笔流水都没有 ⇒ 起点回落到近 90 天，不报错。"""
    pf = Portfolio(name='空流水组合', family_id=1)
    db.add(pf)
    db.flush()
    db.add(Ledger(name='空流水成员', ledger_type='fund', family_id=1, portfolio_id=pf.id))
    db.commit()
    expected = (D_END - dt.timedelta(days=DEFAULT_RANGE_DAYS)).isoformat()

    start = resolve_scope_start(db, 1, 'inception', D_END.isoformat(), portfolio_id=pf.id)

    assert start == expected


def test_非哨兵原样透传_校验归口径层(db):
    # 合法日期原样返回
    assert resolve_scope_start(db, 1, '2026-01-01', '2026-01-07') == '2026-01-01'
    # 非法日期也原样返回：由 build_scope_excess 统一 400，不在本层抢先报另一种错
    assert resolve_scope_start(db, 1, 'not-a-date', '2026-01-07') == 'not-a-date'


def test_inception_终点非法_抛ValueError(db):
    with pytest.raises(ValueError):
        resolve_scope_start(db, 1, 'inception', 'not-a-date')


def test_端点_inception起点回写为最早流水日(client, db, make_position, make_transaction):
    """端点收到的哨兵必须变成具体日期再进口径层，且响应如实回写该起点。

    变异探针：`resolve_scope_start` 若不解析，口径层 `fromisoformat('inception')`
    抛 ValueError ⇒ 端点返回 400，本用例红。
    """
    pf = _seed_portfolio(db, make_position, make_transaction, with_deposit=True)

    resp = client.get(
        f'/api/summary/benchmark-excess/?start_date=inception&end_date={D_END.isoformat()}&portfolio_id={pf.id}'
    )

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['start_date'] == D_DEPOSIT.isoformat()
    assert data['end_date'] == D_END.isoformat()
