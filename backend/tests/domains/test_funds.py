# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 19:34
# File : test_funds.py
from datetime import date, timedelta

from app.domains.funds.models import DailyWorth, Fund, Manager


def test_search_funds(client, db):
    f = Fund(fund_code='000001', name='华夏成长', pinyin_abbr='HXCZ')
    db.add(f)
    db.commit()

    resp = client.get('/api/funds/search/', query_string={'q': '华夏'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['code'] == '000001'
    assert data[0]['type'] == 'fund'


def test_search_managers(client, db):
    m = Manager(mgr_code='MGR001', name='李四', mgr_type='fund_manager')
    db.add(m)
    db.commit()

    resp = client.get('/api/funds/managers/search/', query_string={'q': '李四'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['name'] == '李四'
    assert data[0]['type'] == 'fund_manager'


def test_search_funds_empty(client):
    resp = client.get('/api/funds/search/', query_string={'q': 'zzz_not_exist'})
    data = resp.get_json()['data']
    assert len(data) == 0


def test_get_fund_nav_from_db(client, db):
    """数据库中已有净值时直接返回"""
    fund = Fund(fund_code='000001', name='测试基金')
    db.add(fund)
    db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 15), unit_nav=1.2345, acc_nav=1.2345))
    db.commit()

    resp = client.post('/api/funds/nav/', json={'symbols': ['000001'], 'date': '2025-01-15'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['fund_code'] == '000001'
    assert data[0]['unit_nav'] == 1.2345
    assert data[0]['date'] == '2025-01-15'


def test_get_fund_nav_no_data(client, db):
    """数据库中无净值时，触发实时拉取（可能失败或返回空）"""
    resp = client.post('/api/funds/nav/', json={'symbols': ['999999'], 'date': '2025-01-15'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data == []  # 返回空数组


def test_get_fund_nav_invalid_date(client):
    """日期格式错误应返回 400"""
    resp = client.post(
        '/api/funds/nav/',
        json={
            'symbols': ['000001'],
            'date': '2025/01/15',  # 错误格式
        },
    )
    assert resp.status_code == 422


def test_get_fund_nav_missing_params(client):
    """缺少必填参数应返回 400"""
    resp = client.post(
        '/api/funds/nav/',
        json={
            'symbols': ['000001']
            # 缺少 date
        },
    )
    assert resp.status_code == 422

    resp = client.post(
        '/api/funds/nav/',
        json={
            'date': '2025-01-15'
            # 缺少 symbols
        },
    )
    assert resp.status_code == 422


def test_get_fund_nav_empty_symbols(client):
    """symbols 为空数组应返回 400"""
    resp = client.post('/api/funds/nav/', json={'symbols': [], 'date': '2025-01-15'})
    assert resp.status_code == 422


def test_get_fund_nav_realtime_fetch(client, db):
    """正向测试：数据库中无净值时，通过 xalpha 实时拉取并返回"""
    fund = db.query(Fund).filter_by(fund_code='000001').first()
    if not fund:
        fund = Fund(fund_code='000001', name='华夏成长')
        db.add(fund)
        db.commit()

    test_date = date.today() - timedelta(days=1)
    if test_date.weekday() >= 5:
        test_date -= timedelta(days=test_date.weekday() - 4)

    resp = client.post('/api/funds/nav/', json={'symbols': ['000001'], 'date': test_date.strftime('%Y-%m-%d')})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert len(data) == 1
    item = data[0]
    assert item['fund_code'] == '000001', f'未能获取到 {test_date} 的净值'
    assert item['unit_nav'] > 0, '获取到的净值必须大于 0'
    assert item['date'] == test_date.strftime('%Y-%m-%d')
