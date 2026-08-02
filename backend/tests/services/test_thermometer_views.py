# -*- coding: utf-8 -*-
"""
temperature view 层（API）契约测试（离线）：覆盖
  - GET /api/temperature/overview：成功返回结构
  - GET /api/temperature/history：默认参数 / 带参 / service 异常 500
  - GET /api/temperature/multi：缺 source -> 400 / 正常 -> 200
不依赖真实外部数据源。
"""

from datetime import date

from app.domains.temperature.models import MarketMultiItem, MarketSingleValue


def test_overview_route(client, db):
    db.add(
        MarketSingleValue(
            source='eastmoney_volume',
            name='成交额',
            value=1.0,
            collected_at=date.today(),
        )
    )
    db.commit()

    resp = client.get('/api/temperature/overview')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'success'
    assert 'composites' in body['data']
    assert 'singles' in body['data']
    assert 'multi' in body['data']


def test_history_route_default(client):
    resp = client.get('/api/temperature/history')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['source'] == 'composite_temperature'
    assert 'dates' in data and 'values' in data


def test_history_route_with_params(client, db):
    base = date.today()
    db.add(
        MarketSingleValue(
            source='eastmoney_volume',
            name='成交额',
            value=1.0,
            collected_at=base,
        )
    )
    db.commit()

    resp = client.get('/api/temperature/history?source=eastmoney_volume&days=30')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['source'] == 'eastmoney_volume'
    assert len(data['values']) == 1


def test_multi_route_missing_source(client):
    resp = client.get('/api/temperature/multi')
    assert resp.status_code == 400
    assert 'source' in resp.get_json()['message']


def test_multi_route_ok(client, db):
    db.add(
        MarketMultiItem(
            source='bias',
            item_type='industry',
            item_code='801010',
            item_name='农林牧渔',
            data={'bias': 3.5},
            collected_at=date.today(),
        )
    )
    db.commit()

    resp = client.get('/api/temperature/multi?source=bias')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['source'] == 'bias'
    assert len(data['items']) == 1
    assert data['items'][0]['item_code'] == '801010'


def test_history_route_500_on_service_error(client, monkeypatch):
    from app.services.thermometer.service import TemperatureService

    def boom(source, days=90):
        raise RuntimeError('boom')

    monkeypatch.setattr(TemperatureService, 'get_history', staticmethod(boom))
    resp = client.get('/api/temperature/history')
    assert resp.status_code == 500
