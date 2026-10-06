# -*- coding: utf-8 -*-
"""#1812 收益日历接口契约测试。

锁定三件事：
1. 路由与响应信封符合 `AGENTS.md` 接口契约（`{data, message, error_code}`）；
2. 四态经HTTP 出口后仍然可区分（序列化不能把 None 变成 0）；
3. `ledger_id` 透传生效（家庭级 / 账户级）。
"""

import datetime as dt

from app.domains.funds.models import DailyWorth


def _seed(db, make_position, make_transaction, ledger_id=None):
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)
    kwargs = {
        'symbol': '000031',
        'name': '接口测试基金',
        'quantity': 1000,
        'avg_price': 1.0,
        'asset_type': 'fund',
        # 必须给account_name：make_position 靠它调 _ensure_ledger 建账户，
        # 否则 pos.ledger_id 为 None，账户级用例就退化成家庭级（测不到透传）。
        'account_name': '证券测试账户',
    }
    if ledger_id is not None:
        kwargs['ledger_id'] = ledger_id
    pos = make_position(**kwargs)
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000031',
    )
    db.add(DailyWorth(fund_code='000031', date=d1, unit_nav=1.0))
    db.add(DailyWorth(fund_code='000031', date=d2, unit_nav=1.1))
    db.commit()
    return pos


def test_收益日历接口返回契约信封(client, db, make_position, make_transaction):
    _seed(db, make_position, make_transaction)
    resp = client.get('/api/summary/pnl-calendar/?start_date=2026-01-05&end_date=2026-01-07')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert 'data' in payload and 'message' in payload
    data = payload['data']
    assert data['scope'] == 'family'
    assert data['ledger_id'] is None
    assert len(data['days']) == 3
    # 首日无前一日基准 ⇒ daily_pnl 必须是 None（不是 0）
    assert data['days'][0]['daily_pnl'] is None
    # 次日净值 1.0→1.1，1000 份 ⇒ +100
    assert data['days'][1]['daily_pnl'] == 100.0
    assert data['days'][1]['state'] == 'updown'


def test_收益日历接口_缺数据不被序列化成零(client, db, make_position):
    """balance 模式无价格序列 ⇒ state=no_price 且 daily_pnl 为 null。"""
    from app.core.money import Money

    make_position(
        symbol='ZH9999',
        name='无价理财',
        quantity=0,
        avg_price=0,
        asset_type='portfolio',
        valuation_mode='balance',
        market_value_override=Money.yuan_to_cents(30000),
    )
    resp = client.get('/api/summary/pnl-calendar/?start_date=2026-01-05&end_date=2026-01-06')
    data = resp.get_json()['data']
    assert data['has_any_price'] is False
    assert all(d['state'] == 'no_price' for d in data['days'])
    # 关键：JSON 里必须是 null，若被转成 0.0 前端就会把缺数据画成「零收益」
    assert all(d['daily_pnl'] is None for d in data['days'])
    assert b'"daily_pnl":null' in resp.data


def test_收益日历接口_ledger_id透传(client, db, make_position, make_transaction):
    pos = _seed(db, make_position, make_transaction)
    resp = client.get(f'/api/summary/pnl-calendar/?start_date=2026-01-05&end_date=2026-01-07&ledger_id={pos.ledger_id}')
    data = resp.get_json()['data']
    assert data['scope'] == 'ledger'
    assert data['ledger_id'] == pos.ledger_id


def test_收益日历接口_非法日期返回400(client):
    resp = client.get('/api/summary/pnl-calendar/?start_date=not-a-date')
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload['error_code'] == 1001
    assert payload['data'] is None
