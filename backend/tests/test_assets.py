# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/11 22:00
# File : test_assets.py
# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/11
# File : test_assets.py
from app.domains.assets.models import Asset


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
    # 插入两条资产（补全 account_name 等可能必填的字段）
    resp1 = client.post(
        '/api/assets/',
        json={
            'major_category': 'liability',
            'name': '信用卡',
            'amount': -5000,
            'account_name': '招商银行',  # 补齐
            'currency': 'CNY',
        },
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        '/api/assets/',
        json={'major_category': 'cash', 'name': '现金', 'amount': 10000, 'account_name': '招商银行', 'currency': 'CNY'},
    )
    assert resp2.status_code == 200

    # 直接验证数据库
    all_assets = db.query(Asset).all()
    assert len(all_assets) == 2

    # 筛选负债
    resp = client.get('/api/assets/', query_string={'major_category': 'liability'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['name'] == '信用卡'


def test_update_asset(client):
    resp = client.post('/api/assets/', json={'major_category': 'cash', 'name': '零钱', 'amount': 2000})
    asset_id = resp.get_json()['data']['id']
    patch_resp = client.patch(f'/api/assets/{asset_id}', json={'amount': 3000})
    assert patch_resp.get_json()['data']['amount'] == 3000


def test_delete_asset(client):
    resp = client.post('/api/assets/', json={'major_category': 'cash', 'name': '删除测试', 'amount': 1})
    asset_id = resp.get_json()['data']['id']
    del_resp = client.delete(f'/api/assets/{asset_id}')
    assert del_resp.status_code == 200
    list_resp = client.get('/api/assets/')
    assert len(list_resp.get_json()['data']) == 0
