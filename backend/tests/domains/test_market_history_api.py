# -*- coding: utf-8 -*-
"""探市资产日线历史接口单测（#1460 P2，/api/market/asset/<key>/history/）。

只测「视图 → service」这一层：取数一律用假的 fetch_asset_series 替换，
断言响应契约（信封 / 字段 / 错误码），不依赖网络与真实行情。
"""

from datetime import date, timedelta


def _weekday_series(end: date, n: int):
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return [x.strftime('%Y-%m-%d') for x in days], [100.0 + i for i in range(n)]


def _patch_fetch(monkeypatch):
    dates, closes = _weekday_series(date(2026, 10, 28), 3)
    monkeypatch.setattr('app.services.market_history_service.fetch_asset_series', lambda asset: (dates, closes))


def test_history_endpoint_returns_series(client, monkeypatch):
    """首次请求即按需回填，返回升序收盘序列（封面结构对齐前端图表消费）。"""
    _patch_fetch(monkeypatch)

    resp = client.get('/api/market/asset/sh000300/history/?days=120')
    assert resp.status_code == 200

    data = resp.get_json()['data']
    assert data['key'] == 'sh000300'
    assert data['name'] == '沪深300'
    assert data['count'] == 3
    assert data['last_date'] == '2026-10-28'
    assert data['stale'] is False
    assert [p['date'] for p in data['points']] == ['2026-10-26', '2026-10-27', '2026-10-28']
    assert all('close' in p for p in data['points'])


def test_history_endpoint_rejects_bad_days(client):
    resp = client.get('/api/market/asset/sh000300/history/?days=abc')
    assert resp.status_code == 400


def test_history_endpoint_unknown_asset_404(client):
    resp = client.get('/api/market/asset/no_such_asset/history/')
    assert resp.status_code == 404


def test_history_endpoint_unavailable_asset_404(client):
    resp = client.get('/api/market/asset/sh932000/history/')
    assert resp.status_code == 404


def test_history_endpoint_503_when_source_fails_without_history(client, monkeypatch):
    def _fail(asset):
        raise ConnectionError('源端不可达（模拟）')

    monkeypatch.setattr('app.services.market_history_service.fetch_asset_series', _fail)

    resp = client.get('/api/market/asset/sh000300/history/')
    assert resp.status_code == 503
