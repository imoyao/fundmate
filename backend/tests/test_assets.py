# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 22:00
# File : test_assets.py
# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11
# File : test_assets.py


def test_create_asset(client):
    resp = client.post(
        '/api/assets/', json={'major_category': 'cash', 'name': '活期存款', 'amount': 50000, 'currency': 'CNY'}
    )
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['name'] == '活期存款'
    assert data['amount'] == 50000


def test_list_assets(client):
    client.post('/api/assets/', json={'major_category': 'cash', 'name': '活期', 'amount': 10000})
    client.post('/api/assets/', json={'major_category': 'fixed', 'name': '房产', 'amount': 3000000})
    resp = client.get('/api/assets/')
    data = resp.get_json()['data']
    assert len(data) == 2


def test_filter_assets_by_major_category(client, db):
    """按大类筛选资产"""
    # amount 必须 > 0，负债也传正数（Schema 要求 >0）
    resp1 = client.post(
        '/api/assets/',
        json={
            'major_category': 'liability',
            'name': '信用卡',
            'amount': 5000,  # 改为正数
            'account_name': '招商银行',
            'currency': 'CNY',
        },
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        '/api/assets/',
        json={
            'major_category': 'cash',
            'name': '活期',
            'amount': 2000,
            'account_name': '招商银行',
        },
    )
    assert resp2.status_code == 200

    # 按大类筛选
    resp = client.get('/api/assets/?major_category=liability')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert len(data) >= 1
    assert all(a['major_category'] == 'liability' for a in data)
    # 确认 signed_amount 存在且负债为负
    for a in data:
        assert 'signed_amount' in a
        assert a['signed_amount'] == -a['amount']


def test_update_asset(client):
    """更新资产信息（注意尾部斜杠）"""
    resp = client.post(
        '/api/assets/',
        json={
            'major_category': 'cash',
            'name': '零钱',
            'amount': 2000,
            'account_name': '招商银行',
        },
    )
    asset_id = resp.get_json()['data']['id']

    # PATCH 必须带尾部斜杠
    patch_resp = client.patch(
        f'/api/assets/{asset_id}/',
        json={'amount': 3000},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.get_json()['data']
    assert data['amount'] == 3000
    # 更新后 signed_amount 也应同步
    assert data['signed_amount'] == 3000


def test_delete_asset(client):
    """删除资产（注意尾部斜杠）"""
    resp = client.post(
        '/api/assets/',
        json={
            'major_category': 'cash',
            'name': '删除测试',
            'amount': 1,
            'account_name': '测试',
        },
    )
    asset_id = resp.get_json()['data']['id']

    # DELETE 必须带尾部斜杠
    del_resp = client.delete(f'/api/assets/{asset_id}/')
    assert del_resp.status_code == 200
