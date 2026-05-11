# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/11 19:34
# File : test_funds.py

from app.domains.funds.models import Fund, Manager


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
