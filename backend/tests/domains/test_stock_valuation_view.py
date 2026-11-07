# -*- coding: utf-8 -*-
"""个股估值分位端点（#2944）：统一信封 / 空数据 / 参数边界 / 降级形态。

视图只做编排，外部取数一律替身（``conventions.md`` §2.5：正常、边界、空、异常、权限）。
"""

URL = '/api/stocks/valuation/'


def test_endpoint_returns_standard_envelope(client, monkeypatch):
    captured = {}

    def _fake(db, family_id, codes):
        captured['family_id'] = family_id
        captured['codes'] = codes
        return {
            'items': [{'wind_code': '600519.SH', 'pe_percentile': 32.7828, 'window': '5y'}],
            'window': '5y',
            'source': 'wind_stock_valuation',
            'count': 1,
            'requested': 1,
            'truncated': False,
            'degraded': False,
            'warning': None,
        }

    monkeypatch.setattr('app.domains.stocks.views.get_stock_valuations', _fake)
    resp = client.get(URL + '?codes=600519.SH')
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['message'] == 'ok'
    assert body['data']['items'][0]['pe_percentile'] == 32.7828
    # 权限分支：未启用鉴权的本地/测试态回退默认家庭 1，且 codes 原样下传
    assert captured['family_id'] == 1
    assert captured['codes'] == '600519.SH'


def test_endpoint_without_codes_returns_empty_not_zero(client):
    """空目标池：items 必须是空数组，不能出现「0 分位」这种假数据。"""
    resp = client.get(URL)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    assert data['items'] == []
    assert data['count'] == 0
    assert data['degraded'] is False


def test_endpoint_rejects_too_many_codes(client):
    codes = ','.join(f'600{i:03d}' for i in range(51))
    resp = client.get(URL + '?codes=' + codes)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['error_code'] == 1001
    assert '最多' in body['message']


def test_endpoint_rejects_unrecognizable_codes(client):
    resp = client.get(URL + '?codes=ZH012926')
    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001


def test_endpoint_degraded_shape_is_explicit(client, monkeypatch):
    monkeypatch.setattr(
        'app.domains.stocks.views.get_stock_valuations',
        lambda db, family_id, codes: {
            'items': [],
            'window': '5y',
            'source': 'wind_stock_valuation',
            'count': 0,
            'requested': 1,
            'truncated': False,
            'degraded': True,
            'warning': '个股估值数据源暂时不可用',
        },
    )
    resp = client.get(URL + '?codes=600519.SH')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['degraded'] is True
    assert data['items'] == []
    assert data['warning']
