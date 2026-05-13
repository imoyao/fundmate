# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 22:01
# File : test_summary.py
# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11
# File : test_summary.py

from tests.test_positions import _post


def test_summary_empty(client):
    """无持仓和资产时总资产为0"""
    resp = client.get('/api/summary/')
    data = resp.get_json()['data']
    assert data['total_assets_cny'] == 0
    assert data['total_pnl_cny'] == 0
    assert data['total_liabilities_cny'] == 0
    assert data['net_assets_cny'] == 0


def test_summary_with_positions_and_liabilities(client):
    """持仓、现金资产和负债的汇总计算"""
    # 1. 创建港股持仓：100股腾讯，成本350 HKD，当前价同成本，盈亏为0
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
    # 2. 创建现金资产：10万人民币
    cash_resp = client.post('/api/assets/', json={'major_category': 'cash', 'name': '活期存款', 'amount': 100000})
    assert cash_resp.status_code == 200

    # 3. 创建负债：信用卡欠款5000元（正数表示负债金额）
    liability_resp = client.post('/api/assets/', json={'major_category': 'liability', 'name': '信用卡', 'amount': 5000})
    assert liability_resp.status_code == 200

    # 4. 获取汇总
    resp = client.get('/api/summary/')
    data = resp.get_json()['data']

    # 预期计算：
    # 持仓市值：100 * 350 * 0.92(HKD→CNY) = 32200
    # 现金：100000
    # 总资产 = 32200 + 100000 = 132200
    # 负债 = 5000
    # 净资产 = 132200 - 5000 = 127200
    # 盈亏：持仓现价等于成本，为0
    assert data['total_assets_cny'] == 132200.0
    assert data['total_liabilities_cny'] == 5000.0
    assert data['net_assets_cny'] == 127200.0
    assert data['total_pnl_cny'] == 0.0
    # 验证市场分布（至少包含港股）
    assert 'CN_HK' in data['market_distribution']


def test_summary_with_pnl_and_multi_currency(client):
    """不同货币持仓的盈亏与资产汇总"""
    # 港股持仓：100股腾讯，成本350，现价400，盈利
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
    # 更新市价为400（通过 PATCH 接口）
    list_resp = client.get('/api/positions/')
    pos_id = list_resp.get_json()['data'][0]['id']
    client.patch(f'/api/positions/{pos_id}', json={'current_price': 400.0})

    # 美股持仓：10股苹果，成本180 USD，现价200 USD
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
    list_resp2 = client.get('/api/positions/')
    # 找到苹果持仓的id
    apple_pos = [p for p in list_resp2.get_json()['data'] if p['symbol'] == 'AAPL'][0]
    client.patch(f'/api/positions/{apple_pos["id"]}', json={'current_price': 200.0})

    # 汇总
    resp = client.get('/api/summary/')
    data = resp.get_json()['data']

    # 计算：
    # 腾讯市值：100 * 400 * 0.92 = 36800  盈亏：(400-350)*100*0.92 = 4600
    # 苹果市值：10 * 200 * 7.25 = 14500   盈亏：(200-180)*10*7.25 = 1450
    # 总资产 = 36800 + 14500 = 51300
    # 总盈亏 = 4600 + 1450 = 6050
    assert data['total_assets_cny'] == 51300.0
    assert data['total_pnl_cny'] == 6050.0
    assert len(data['market_distribution']) == 2
