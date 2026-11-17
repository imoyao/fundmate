# -*- coding: utf-8 -*-
"""家庭财务规划 API 契约（晴雨表 v2）。

钉死三条最易退化的边界：
1. 未配置 = null，不是 0（0 会让自由度分母为 0，null 是「还没填」）；
2. PUT 只改显式传入的字段，不整体覆盖（前端可能只改年收入）；
3. 负数被拒（年支出/年收入不可能是负）；显式 null 清除单项。
"""

BASE = '/api/financial-plan'


def test_get_empty_returns_nulls(client):
    """未配置时两项都是 null，不是 0。"""
    resp = client.get(f'{BASE}/')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'ok'
    assert body['data'] == {
        'estimated_annual_expense': None,
        'estimated_annual_income': None,
    }


def test_put_and_get_roundtrip(client):
    """元→分→元往返不丢精度；两项都能读回。"""
    resp = client.put(
        f'{BASE}/',
        json={'estimated_annual_expense': 120000.55, 'estimated_annual_income': 300000.88},
    )
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['estimated_annual_expense'] == 120000.55
    assert data['estimated_annual_income'] == 300000.88

    got = client.get(f'{BASE}/').get_json()['data']
    assert got == data


def test_put_only_updates_explicit_fields(client):
    """只传年收入时，已存的年支出保持不变（不整体覆盖）。"""
    client.put(f'{BASE}/', json={'estimated_annual_expense': 100000, 'estimated_annual_income': 200000})
    client.put(f'{BASE}/', json={'estimated_annual_income': 250000})

    got = client.get(f'{BASE}/').get_json()['data']
    assert got['estimated_annual_expense'] == 100000
    assert got['estimated_annual_income'] == 250000


def test_put_explicit_null_clears_one_field(client):
    """显式传 null 清除该项；另一项保留。"""
    client.put(f'{BASE}/', json={'estimated_annual_expense': 100000, 'estimated_annual_income': 200000})
    resp = client.put(f'{BASE}/', json={'estimated_annual_expense': None})
    assert resp.status_code == 200

    got = client.get(f'{BASE}/').get_json()['data']
    assert got['estimated_annual_expense'] is None
    assert got['estimated_annual_income'] == 200000


def test_put_rejects_negative_amounts(client):
    """负数一律 422 + 统一信封。"""
    for payload in (
        {'estimated_annual_expense': -1},
        {'estimated_annual_income': -0.01},
    ):
        resp = client.put(f'{BASE}/', json=payload)
        assert resp.status_code == 422, payload
        assert resp.get_json()['error_code'] == 1001
