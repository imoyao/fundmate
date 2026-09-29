# -*- coding: utf-8 -*-
"""分红与股息 API 契约（#872）。

只测端点契约（信封 / 状态码 / 参数校验 / 读写往返），统计口径的回归在
`tests/services/test_dividend_service.py`——避免同一判据两处维护。
"""

from app.core.money import Money

BASE = '/api/dividends'


def test_summary_empty_envelope(client):
    """空账本也能拿到完整结构（前端首屏不做空值分支）。"""
    resp = client.get(f'{BASE}/summary/')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'ok'

    data = body['data']
    assert set(data) == {'as_of', 'period', 'totals', 'by_year', 'portfolio', 'holdings', 'target'}
    assert data['period']['months'] == 12
    assert data['totals']['ttm']['net_cents'] == 0
    assert data['totals']['all_time']['net_cents'] == 0
    assert data['by_year'] == []
    assert data['holdings'] == []
    assert data['portfolio']['yield_on_cost_pct'] is None
    assert data['target']['configured'] is False


def test_summary_rejects_out_of_range_params(client):
    """months/years 越界一律 422 + 统一信封（error_code=1001）。"""
    for url in (
        f'{BASE}/summary/?months=0',
        f'{BASE}/summary/?months=61',
        f'{BASE}/summary/?years=0',
        f'{BASE}/summary/?years=21',
        f'{BASE}/summary/?months=abc',
    ):
        resp = client.get(url)
        assert resp.status_code == 422, url
        body = resp.get_json()
        assert body['data'] is None
        assert body['error_code'] == 1001
        assert body['message']


def test_summary_accepts_custom_window(client):
    resp = client.get(f'{BASE}/summary/?months=24&years=3')
    assert resp.status_code == 200
    period = resp.get_json()['data']['period']
    assert period['months'] == 24
    assert period['start'] < period['end']


def test_target_lifecycle_roundtrip(client, db, make_position, make_transaction):
    """PUT → summary 见到目标与达成度 → DELETE 清空（幂等）。"""
    holding = make_position(
        symbol='600519',
        name='测试股票',
        asset_type='stock',
        account_name='测试账户',
        quantity=1000,
        avg_price=10.0,
        current_price=12.0,
    )
    # 现金分红 500 元 / 成本 10000 元 = 5%
    make_transaction(
        position_id=holding.id,
        ledger_id=holding.ledger_id,
        txn_type='dividend',
        quantity=0,
        price=0,
        amount=500.0,
        symbol=holding.symbol,
    )
    db.commit()

    resp = client.put(f'{BASE}/target/', json={'target_yield_pct': 4.0, 'notes': '退休现金流'})
    assert resp.status_code == 200
    assert resp.get_json()['data'] == {'configured': True, 'target_yield_pct': 4.0, 'notes': '退休现金流'}

    target = client.get(f'{BASE}/summary/').get_json()['data']['target']
    assert target['configured'] is True
    assert target['target_yield_pct'] == 4.0
    assert target['progress_pct'] == 125.0
    assert target['gap_pct'] == 1.0
    assert target['met'] is True

    # 重复 PUT 覆盖目标值，不产生第二行
    assert client.put(f'{BASE}/target/', json={'target_yield_pct': 8.0}).status_code == 200
    assert client.get(f'{BASE}/summary/').get_json()['data']['target']['met'] is False

    assert client.delete(f'{BASE}/target/').get_json()['data']['configured'] is False
    # 清除是幂等的：没目标时再清一次仍 200，不抛 404
    repeat = client.delete(f'{BASE}/target/')
    assert repeat.status_code == 200
    assert repeat.get_json()['data']['configured'] is False


def test_target_validation(client):
    for payload in (
        {},
        {'target_yield_pct': 0},
        {'target_yield_pct': -1},
        {'target_yield_pct': 101},
        {'target_yield_pct': 4, 'notes': 'x' * 201},
    ):
        resp = client.put(f'{BASE}/target/', json=payload)
        assert resp.status_code == 422, payload
        body = resp.get_json()
        assert body['data'] is None
        assert body['error_code'] == 1001


def test_summary_holdings_carry_cents_and_ratios(client, db, make_position, make_transaction):
    """逐持仓行给到前端可直接消费的字段（金额=分，比率=百分比 float）。"""
    holding = make_position(
        symbol='000001',
        name='测试基金',
        asset_type='fund',
        account_name='测试账户',
        quantity=1000,
        avg_price=10.0,
        current_price=12.0,
    )
    make_transaction(
        position_id=holding.id,
        ledger_id=holding.ledger_id,
        txn_type='dividend',
        quantity=0,
        price=0,
        amount=100.0,
        symbol=holding.symbol,
    )
    db.commit()

    row = client.get(f'{BASE}/summary/').get_json()['data']['holdings'][0]
    assert set(row) >= {
        'position_id',
        'symbol',
        'name',
        'asset_type',
        'account_name',
        'ledger_id',
        'cost_cents',
        'market_value_cents',
        'cash_cents',
        'reinvest_cents',
        'tax_cents',
        'net_cents',
        'event_count',
        'split_count',
        'yield_on_cost_pct',
        'cash_yield_on_cost_pct',
        'yield_on_value_pct',
        'all_time_cash_cents',
        'all_time_net_cents',
        'all_time_event_count',
        'reinvest_gain_cents',
        'last_dividend_date',
    }
    assert row['cost_cents'] == Money.yuan_to_cents(10000)
    assert row['cash_cents'] == Money.yuan_to_cents(100)
