# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/11 19:22
# File : test_securities.py


from app.domains.securities.models import Security


def test_search_securities(client, db):
    s = Security(symbol='00700.HK', name='腾讯控股', market='CN_HK', type='stock')
    db.add(s)
    db.commit()

    resp = client.get('/api/securities/search/', query_string={'q': '00700'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['symbol'] == '00700.HK'


def test_search_securities_empty(client):
    resp = client.get('/api/securities/search/', query_string={'q': 'zzz_not_exist'})
    data = resp.get_json()['data']
    assert len(data) == 0
