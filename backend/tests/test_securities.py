# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/11 19:22
# File : test_securities.py
from app.core.symbol_utils import get_normalizer
from app.domains.securities.models import Security


def test_search_securities(client, db):
    """搜索证券：插入标准化代码，搜索应返回对应数据"""
    normalizer = get_normalizer()
    norm_sym, market = normalizer.normalize('00700.HK')
    assert norm_sym == 'HK00700'

    s = Security(symbol=norm_sym, name='腾讯控股', market=market, type='stock')
    db.add(s)
    db.commit()

    # 确认数据库中存在
    assert db.query(Security).count() == 1

    resp = client.get('/api/securities/search/', query_string={'q': '00700'})
    data = resp.get_json()['data']
    assert len(data) == 1, f'返回数据: {data}'
    assert data[0]['symbol'] == 'HK00700'
    assert data[0]['display_symbol'] == '00700.HK'
    assert data[0]['name'] == '腾讯控股'


def test_search_securities_by_name(client, db):
    """按名称搜索"""
    normalizer = get_normalizer()
    norm_sym, market = normalizer.normalize('600519')
    assert norm_sym == 'SH600519'

    s = Security(symbol=norm_sym, name='贵州茅台', market=market, type='stock')
    db.add(s)
    db.commit()

    assert db.query(Security).count() == 1

    resp = client.get('/api/securities/search/', query_string={'q': '茅台'})
    data = resp.get_json()['data']
    assert len(data) == 1, f'返回数据: {data}'
    assert data[0]['symbol'] == 'SH600519'


def test_search_securities_empty(client):
    resp = client.get('/api/securities/search/', query_string={'q': 'zzz_not_exist'})
    data = resp.get_json()['data']
    assert len(data) == 0
