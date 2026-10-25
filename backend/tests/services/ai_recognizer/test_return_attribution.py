# -*- coding: utf-8 -*-
"""#2618 收益贡献归因工具测试。

锁定五件事：
1. **占比可加**——正负贡献混合时 Σ 各行 `contribution_pct` ≈ 100；
2. **明细 ≠ 归因**——收益额与 `compute_range_attribution`（#2135）逐位同源，
   本工具不另算一套账；
3. **合计为 0 时占比 None**（不是 0%），与 #2135 同纪律；
4. **区间可切分**——分段贡献之和等于整段贡献；
5. **account 维度按 ledger 聚合、多账户不串账**，且 user 隔离。
"""

import datetime as dt

import pytest

from app.domains.funds.models import DailyWorth
from app.services.ai_recognizer.tools import ToolExecutor


def _add_nav(db, fund_code, date, unit_nav):
    db.add(DailyWorth(fund_code=fund_code, date=date, unit_nav=unit_nav))
    db.commit()


def _seed_one(db, make_position, make_transaction, *, symbol, name, navs, quantity=1000, account_name='测试账户'):
    """建一只持仓 + 买入流水 + 净值序列（d1 为建仓日）。"""
    pos = make_position(
        symbol=symbol,
        name=name,
        quantity=quantity,
        avg_price=navs[0][1],
        asset_type='fund',
        account_name=account_name,
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=quantity,
        price=navs[0][1],
        confirm_date=navs[0][0],
        symbol=symbol,
    )
    for date, nav in navs:
        _add_nav(db, symbol, date, nav)
    return pos


def test_正负贡献混合_占比相加为100(db, make_position, make_transaction):
    """A +300 / B −100 ⇒ 合计 200，占比 150% / −50%（合计 100）。"""
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)
    _seed_one(db, make_position, make_transaction, symbol='000201', name='上涨基金', navs=[(d1, 1.0), (d2, 1.3)])
    _seed_one(db, make_position, make_transaction, symbol='000202', name='下跌基金', navs=[(d1, 1.0), (d2, 0.9)])

    r = ToolExecutor.run('get_return_attribution', {'start_date': '2026-01-05', 'end_date': '2026-01-06'})
    assert r['status'] == 'success', r.get('msg')
    data = r['data']

    assert data['dimension'] == 'instrument'
    assert data['total_pnl'] == pytest.approx(200.0, abs=0.001)
    by_symbol = {it['symbol']: it for it in data['items']}
    assert by_symbol['000201']['pnl'] == pytest.approx(300.0, abs=0.001)
    assert by_symbol['000202']['pnl'] == pytest.approx(-100.0, abs=0.001)
    assert by_symbol['000201']['contribution_pct'] == pytest.approx(150.0, abs=0.01)
    assert by_symbol['000202']['contribution_pct'] == pytest.approx(-50.0, abs=0.01)
    # 各行占比相加 ≈ 100（舍入误差内）
    assert sum(it['contribution_pct'] for it in data['items']) == pytest.approx(100.0, abs=0.05)
    # 按贡献绝对值降序
    assert data['items'][0]['symbol'] == '000201'


def test_合计为零时占比为None而非0(db, make_position, make_transaction):
    """一涨一跌打平：total=0 ⇒ 占比 None（「没赚没赔」的占比无意义）。"""
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)
    _seed_one(db, make_position, make_transaction, symbol='000203', name='涨', navs=[(d1, 1.0), (d2, 1.2)])
    _seed_one(db, make_position, make_transaction, symbol='000204', name='跌', navs=[(d1, 1.0), (d2, 0.8)])

    r = ToolExecutor.run('get_return_attribution', {'start_date': '2026-01-05', 'end_date': '2026-01-06'})
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['total_pnl'] == pytest.approx(0.0, abs=0.001)
    assert all(it['contribution_pct'] is None for it in r['data']['items'])


def test_单持仓占比为100(db, make_position, make_transaction):
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)
    _seed_one(db, make_position, make_transaction, symbol='000205', name='唯一持仓', navs=[(d1, 1.0), (d2, 1.2)])

    r = ToolExecutor.run('get_return_attribution', {'start_date': '2026-01-05', 'end_date': '2026-01-06'})
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['count'] == 1
    assert r['data']['items'][0]['pnl'] == pytest.approx(200.0, abs=0.001)
    assert r['data']['items'][0]['contribution_pct'] == pytest.approx(100.0, abs=0.01)


def test_空持仓诚实回空(db):
    r = ToolExecutor.run('get_return_attribution', {'start_date': '2026-01-05', 'end_date': '2026-01-06'})
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['items'] == []
    assert r['data']['count'] == 0
    assert r['data']['total_pnl'] is None  # 算不了 ≠ 没赚没赔
    assert r['data']['has_any_computable'] is False


def test_区间可切分_不重叠分段之和等于整段(db, make_position, make_transaction):
    """净值 1.0→1.2→1.5：d2 当日 +200 / d3 当日 +300，整段 +500。

    口径固化：区间**含起点当日**（收益日历同源），故 `[d2,d3]` 会把 d2 的
    +200 再算一次 = 500 —— 重叠边界不可加。分段求和必须切在不重叠的日边界上
    （`[d1,d2]` + `[d3,d3]`），这是消费方最容易踩的一处。
    """
    d1, d2, d3 = dt.date(2026, 1, 5), dt.date(2026, 1, 6), dt.date(2026, 1, 7)
    _seed_one(
        db, make_position, make_transaction, symbol='000206', name='分段基金', navs=[(d1, 1.0), (d2, 1.2), (d3, 1.5)]
    )

    def _total(start, end):
        r = ToolExecutor.run('get_return_attribution', {'start_date': start, 'end_date': end})
        assert r['status'] == 'success', r.get('msg')
        return r['data']['total_pnl']

    seg1 = _total('2026-01-05', '2026-01-06')  # d1 建仓日剔除 + d2 的 200
    seg2 = _total('2026-01-07', '2026-01-07')  # 仅 d3 的 300
    whole = _total('2026-01-05', '2026-01-07')
    assert seg1 == pytest.approx(200.0, abs=0.001)
    assert seg2 == pytest.approx(300.0, abs=0.001)
    assert whole == pytest.approx(seg1 + seg2, abs=0.001)
    # 反向钉住：重叠边界会重复计（d2 的 200 被算两次）
    assert _total('2026-01-06', '2026-01-07') == pytest.approx(500.0, abs=0.001)


def test_account维度按账户聚合(db, make_position, make_transaction):
    """两账户各一只：按 ledger 聚合后各成一行，占比仍相加 100。"""
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)
    _seed_one(
        db,
        make_position,
        make_transaction,
        symbol='000207',
        name='甲账户基金',
        navs=[(d1, 1.0), (d2, 1.3)],
        account_name='账户甲',
    )
    _seed_one(
        db,
        make_position,
        make_transaction,
        symbol='000208',
        name='乙账户基金',
        navs=[(d1, 1.0), (d2, 0.9)],
        account_name='账户乙',
    )

    r = ToolExecutor.run(
        'get_return_attribution',
        {'start_date': '2026-01-05', 'end_date': '2026-01-06', 'dimension': 'account'},
    )
    assert r['status'] == 'success', r.get('msg')
    data = r['data']
    assert data['dimension'] == 'account'
    assert data['count'] == 2
    assert [it['account_name'] for it in data['items']] == ['账户甲', '账户乙']
    assert data['items'][0]['pnl'] == pytest.approx(300.0, abs=0.001)
    assert data['items'][0]['contribution_pct'] == pytest.approx(150.0, abs=0.01)
    assert data['items'][1]['contribution_pct'] == pytest.approx(-50.0, abs=0.01)


def test_user隔离(db, make_position):
    make_position(symbol='000209', name='别人家的', family_id=2, quantity=100, avg_price=1.0, current_price=2.0)
    r = ToolExecutor.run(
        'get_return_attribution',
        {'start_date': '2026-01-05', 'end_date': '2026-01-06'},
        server_ctx={'family_id': 1},
    )
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['items'] == []


def test_dimension非法值被schema拒绝():
    r = ToolExecutor.run('get_return_attribution', {'dimension': 'sector'})
    assert r['status'] == 'error'
    assert '不在允许值' in r['msg']


def test_日期格式非法被schema拒绝():
    r = ToolExecutor.run('get_return_attribution', {'start_date': '2026/01/05'})
    assert r['status'] == 'error'
    assert '不匹配格式' in r['msg']
