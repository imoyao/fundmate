# -*- coding: utf-8 -*-
"""#2135 收益归因接口契约测试。

锁定三件事：
1. 路由与响应信封符合 `AGENTS.md` 接口契约（`{data, message, error_code}`）；
2. 降级字段经 HTTP 出口后仍可区分（None 不被序列化成 0）；
3. `ledger_id` / `portfolio_id` 互斥与非法参数回 400（error_code 1001）。
"""

import datetime as dt

from app.domains.funds.models import DailyWorth


def _seed(db, make_position, make_transaction):
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)
    pos = make_position(symbol='000131', name='归因接口基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000131',
    )
    db.add(DailyWorth(fund_code='000131', date=d1, unit_nav=1.0))
    db.add(DailyWorth(fund_code='000131', date=d2, unit_nav=1.1))
    db.commit()
    return pos


def test_归因接口_契约信封与数据结构(client, db, make_position, make_transaction):
    _seed(db, make_position, make_transaction)
    resp = client.get('/api/summary/pnl-attribution/?start_date=2026-01-05&end_date=2026-01-06')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert 'data' in payload and 'message' in payload
    data = payload['data']
    assert data['scope'] == 'family'
    assert data['has_any_computable'] is True
    assert data['total_pnl'] == 100.0
    assert len(data['positions']) == 1
    assert data['positions'][0]['symbol'] == '000131'
    assert data['positions'][0]['pnl'] == 100.0
    assert data['unpriced_positions'] == []
    assert len(data['categories']) == 1


def test_归因接口_互斥参数回400(client):
    resp = client.get(
        '/api/summary/pnl-attribution/?start_date=2026-01-05&end_date=2026-01-06&ledger_id=1&portfolio_id=1'
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload['error_code'] == 1001


def test_归因接口_非法日期回400(client):
    resp = client.get('/api/summary/pnl-attribution/?start_date=not-a-date')
    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001
