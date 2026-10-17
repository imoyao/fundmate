# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/17
# File : test_product_pro_status.py
# tests/domains/products/test_product_pro_status.py
"""`GET /api/products/pro/` 契约测试（#2272 · #994 Phase 1 接口骨架）。

覆盖 issue 验收的关键断言：

1. 状态位形状：``pro_enabled`` / ``paywall_required`` / 四模块可用性位齐全且取值正确
   （一期恒 true / false / false，模块带 Phase 标注）；
2. 缺 ``symbol`` → 422（pydantic 层校验被 apiflask 拦下，不落视图；统一错误信封）；
3. ``asset_type`` 入口提示仅回显，不参与判定（给个非法品类也不 400）；
4. 骨架不查库：任何 symbol（含不存在的产品）都回同一形状——「该产品没有 Pro 数据」
   与「产品不存在」在 Phase 1 是同一件事（详情页先 resolve 再挂区块，见 detail.vue）。
"""

PRO_URL = '/api/products/pro/'


def test_pro_status_returns_skeleton(client):
    """带 symbol → 一期骨架：总开关 true、付费墙 false、四模块全不可用。"""
    resp = client.get(PRO_URL, query_string={'symbol': '004369'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'ok'
    data = body['data']
    assert data['symbol'] == '004369'
    # 一期后端全开无权益校验；付费墙是前端 feature flag，端点恒 false
    assert data['pro_enabled'] is True
    assert data['paywall_required'] is False
    modules = data['modules']
    assert set(modules) == {'performance', 'risk', 'allocation', 'report'}
    for module in modules.values():
        assert module['available'] is False
        assert module['phase'] in (2, 3, 4)
    # Phase 标注与 #994 五阶段排期一致：模块一/二 → P2，模块三 → P3，模块四 → P4
    assert modules['performance']['phase'] == 2
    assert modules['risk']['phase'] == 2
    assert modules['allocation']['phase'] == 3
    assert modules['report']['phase'] == 4


def test_pro_status_requires_symbol(client):
    """缺 symbol → 422（schema 必填校验，错误信封带 error_code，不是 200 + 空 data）。"""
    resp = client.get(PRO_URL, headers={'X-User-Id': '1'})

    assert resp.status_code == 422
    body = resp.get_json()
    assert 'data' in body
    assert body.get('error_code')


def test_pro_status_asset_type_is_echo_only(client):
    """asset_type 仅回显：不给为 null，给了原样带回（一期不做归一/判定）。"""
    without = client.get(PRO_URL, query_string={'symbol': '004369'}, headers={'X-User-Id': '1'})
    assert without.get_json()['data']['asset_type'] is None

    with_hint = client.get(PRO_URL, query_string={'symbol': '004369', 'asset_type': 'fund'}, headers={'X-User-Id': '1'})
    assert with_hint.get_json()['data']['asset_type'] == 'fund'


def test_pro_status_symbol_agnostic(client):
    """骨架与产品是否存在无关：不查库，任意代码同一形状（占位期不做存在性校验）。"""
    resp = client.get(PRO_URL, query_string={'symbol': 'NOSUCHCODE'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 200
    assert resp.get_json()['data']['pro_enabled'] is True
