# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11
# File : test_transactions.py

from datetime import date, timedelta

from app.domains.transactions.models import Transaction
from tests.test_positions import _get, _post


def test_transaction_types_coverage(client):
    """覆盖所有操作类型：buy, sell, dividend, deposit, withdraw"""
    # 1. 买入创建持仓
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

    # 2. 卖出部分
    _post(
        client,
        '/api/positions',
        {
            'op_type': 'sell',
            'position_id': pos_id,
            'quantity': 30,
            'avg_price': 400,
            'purchase_date': '2026-05-03',
            'account_name': '富途',
        },
    )
    # 3. 分红
    _post(
        client,
        '/api/positions',
        {
            'op_type': 'dividend',
            'position_id': pos_id,
            'avg_price': 500,  # 分红金额暂存
            'purchase_date': '2026-05-04',
            'account_name': '富途',
        },
    )
    # 4. 存入
    _post(
        client,
        '/api/positions',
        {
            'op_type': 'deposit',
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 50,
            'avg_price': 360,
            'currency': 'HKD',
            'purchase_date': '2026-05-02',
        },
    )
    # 5. 取出（先取出部分，避免清空）
    _post(
        client,
        '/api/positions',
        {
            'op_type': 'withdraw',
            'position_id': pos_id,
            'quantity': 20,
            'avg_price': 370,
            'purchase_date': '2026-05-05',
            'account_name': '富途',
        },
    )

    # 查询所有流水
    resp = _get(client, '/api/transactions')
    txn_list = resp.get_json()['data']
    assert len(txn_list) == 5
    type_set = {t['type'] for t in txn_list}
    assert type_set == {'buy', 'sell', 'dividend', 'deposit', 'withdraw'}


def test_transactions_filter_by_type(client):
    """按操作类型筛选"""
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
    _post(
        client,
        '/api/positions',
        {
            'op_type': 'sell',
            'position_id': pos_id,
            'quantity': 10,
            'avg_price': 190,
            'purchase_date': '2026-05-05',
            'account_name': '富途',
        },
    )

    resp_buy = _get(client, '/api/transactions', {'type': 'buy'})
    assert len(resp_buy.get_json()['data']) == 1

    resp_sell = _get(client, '/api/transactions', {'type': 'sell'})
    assert len(resp_sell.get_json()['data']) == 1


def test_transactions_time_range(client):
    """时间范围筛选"""
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
        },
    )

    resp = _get(client, '/api/transactions', {'time_range': '1m'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['trade_date'] == recent_date


def test_transactions_pagination(client):
    """分页测试"""
    for i in range(5):
        _post(
            client,
            '/api/positions',
            {
                'symbol': f'00{i}00.HK',
                'name': f'股票{i}',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 10,
                'avg_price': 100,
                'currency': 'HKD',
                'purchase_date': '2026-05-01',
            },
        )

    resp = _get(client, '/api/transactions', {'page': 1, 'per_page': 2})
    result = resp.get_json()
    assert len(result['data']) == 2
    assert result['total'] == 5
    assert result['page'] == 1


def test_transactions_asset_type_filter(client):
    """按资产类型筛选（stock / fund）"""
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
    _post(
        client,
        '/api/positions',
        {
            'symbol': '000001',
            'name': '华夏成长',
            'type': 'fund',
            'market': 'CN_A',
            'account_name': '支付宝',
            'quantity': 1000,
            'avg_price': 1.5,
            'currency': 'CNY',
            'purchase_date': '2026-05-01',
        },
    )

    resp_stock = _get(client, '/api/transactions', {'asset_type': 'stock'})
    data_stock = resp_stock.get_json()['data']
    assert len(data_stock) == 1

    resp_fund = _get(client, '/api/transactions', {'asset_type': 'fund'})
    data_fund = resp_fund.get_json()['data']
    assert len(data_fund) == 1


def test_transactions_status_filter(client, db):
    """按交易状态筛选（手动创建非 success 记录）"""
    # 先创建一个普通 success 记录
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

    # 插入一条 failed 记录
    failed_txn = Transaction(
        position_id=1,
        txn_type='buy',
        trade_date=date.today(),
        quantity=50,
        price=100,
        amount=5000,
        status='failed',
        position_name='测试',
        account_name='测试账户',
    )
    db.add(failed_txn)
    db.commit()

    resp = _get(client, '/api/transactions', {'status': 'failed'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['status'] == 'failed'


def test_transaction_type_field(client):
    """交易流水返回的 type 字段正确映射"""
    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 10,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
        },
    )
    resp = _get(client, '/api/transactions')
    t_list = resp.get_json()['data']
    assert len(t_list) == 1
    assert t_list[0]['type'] == 'buy'
