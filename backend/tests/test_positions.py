# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 22:48
# File : test_positions.py
from datetime import date, timedelta


# 统一 POST/GET 辅助函数
def _post(client, url, data):
    return client.post(url if url.endswith('/') else url + '/', json=data)


def _get(client, url, params=None):
    return client.get(url if url.endswith('/') else url + '/', query_string=params)


def test_buy_creates_position(client):
    resp = _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',  # 用户输入非标准
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
            'allocation': 'longterm',
            'op_type': 'buy',
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['symbol'] == 'HK00700'  # 期望标准化
    assert data['quantity'] == 100
    assert data['avg_price'] == 350


def test_buy_same_symbol_merges(client):
    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
        },
    )
    resp = _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 50,
            'avg_price': 380,
            'currency': 'HKD',
            'purchase_date': '2026-05-02',
            'op_type': 'buy',
        },
    )
    data = resp.get_json()['data']
    assert data['quantity'] == 150
    assert abs(data['avg_price'] - 360.0) < 0.01


def test_sell_partial(client):
    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
        },
    )
    list_resp = _get(client, '/api/positions')
    pos_id = list_resp.get_json()['data'][0]['id']

    resp = _post(
        client,
        '/api/positions',
        {'op_type': 'sell', 'position_id': pos_id, 'quantity': 30, 'avg_price': 400, 'purchase_date': '2026-05-03'},
    )
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['quantity'] == 70
    assert data['avg_price'] == 350


def test_sell_all_clears_position(client):
    _post(
        client,
        '/api/positions',
        {
            'symbol': 'AAPL',
            'name': '苹果',
            'type': 'stock',
            'market': 'US',
            'account_name': '富途',
            'quantity': 50,
            'avg_price': 180,
            'currency': 'USD',
            'purchase_date': '2026-05-01',
        },
    )
    list_resp = _get(client, '/api/positions')
    pos_id = list_resp.get_json()['data'][0]['id']

    resp = _post(
        client,
        '/api/positions',
        {'op_type': 'sell', 'position_id': pos_id, 'quantity': 50, 'avg_price': 190, 'purchase_date': '2026-05-05'},
    )
    assert resp.status_code == 200
    assert resp.get_json()['message'] == '持仓已清空'


def test_sell_missing_position_id_fails(client):
    resp = _post(
        client, '/api/positions', {'op_type': 'sell', 'quantity': 10, 'avg_price': 100, 'purchase_date': '2026-05-01'}
    )
    assert resp.status_code == 400


def test_sell_exceeding_quantity_fails(client):
    _post(
        client,
        '/api/positions',
        {
            'symbol': 'AAPL',
            'name': '苹果',
            'type': 'stock',
            'market': 'US',
            'account_name': '富途',
            'quantity': 10,
            'avg_price': 180,
            'currency': 'USD',
            'purchase_date': '2026-05-01',
        },
    )
    list_resp = _get(client, '/api/positions')
    pos_id = list_resp.get_json()['data'][0]['id']

    resp = _post(
        client,
        '/api/positions',
        {'op_type': 'sell', 'position_id': pos_id, 'quantity': 20, 'avg_price': 200, 'purchase_date': '2026-05-02'},
    )
    assert resp.status_code == 400


def test_transactions_time_range(client):
    today = date.today()
    old_date = (today - timedelta(days=400)).isoformat()
    recent_date = (today - timedelta(days=5)).isoformat()

    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': old_date,
            'op_type': 'buy',
        },
    )
    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 50,
            'avg_price': 380,
            'currency': 'HKD',
            'purchase_date': recent_date,
            'op_type': 'buy',
        },
    )

    resp = _get(client, '/api/transactions', {'time_range': '1m'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['trade_date'] == recent_date


def test_transactions_type_filter(client):
    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
            'op_type': 'buy',
        },
    )
    resp_sell = _get(client, '/api/transactions', {'type': 'sell'})
    assert len(resp_sell.get_json()['data']) == 0
    resp_buy = _get(client, '/api/transactions', {'type': 'buy'})
    assert len(resp_buy.get_json()['data']) == 1


def test_position_type_field(client):
    """创建持仓后返回的字典必须包含 type 字段且正确"""
    resp = _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',  # 前端依然传 type
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
        },
    )
    data = resp.get_json()['data']
    assert data['type'] == 'stock'
    # 确保 type_label 也生成
    assert 'type_label' in data


def test_update_position_price(client):
    """PATCH 更新 current_price"""
    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
        },
    )
    list_resp = _get(client, '/api/positions')
    pos_id = list_resp.get_json()['data'][0]['id']

    resp = client.patch(f'/api/positions/{pos_id}', json={'current_price': 400})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['current_price'] == 400


def test_delete_position(client):
    """DELETE 删除持仓"""
    _post(
        client,
        '/api/positions',
        {
            'symbol': 'TEST.DEL',
            'name': '测试删除',
            'type': 'stock',
            'market': 'CN_A',
            'account_name': '测试账户',
            'quantity': 10,
            'avg_price': 10,
            'currency': 'CNY',
            'purchase_date': '2026-05-01',
        },
    )
    list_resp = _get(client, '/api/positions')
    pos_id = list_resp.get_json()['data'][0]['id']

    resp = client.delete(f'/api/positions/{pos_id}')
    assert resp.status_code == 200

    # 确认已删除
    list_after = _get(client, '/api/positions')
    assert len(list_after.get_json()['data']) == 0


def test_delete_nonexistent_position(client):
    """删除不存在的持仓返回 404"""
    resp = client.delete('/api/positions/99999')
    assert resp.status_code == 404
