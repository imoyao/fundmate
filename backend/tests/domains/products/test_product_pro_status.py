# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/17
# File : test_product_pro_status.py
# tests/domains/products/test_product_pro_status.py
"""`GET /api/products/pro/` 契约测试（#2272 · #994 Phase 1 接口骨架 → #2324 权益驱动）。

覆盖 issue 验收的关键断言：

1. 状态位形状**不变**：``symbol`` / ``asset_type`` / ``pro_enabled`` /
   ``paywall_required`` / ``modules`` 五件套齐全（#2324 验收第 3 条写的就是
   「``paywall_required`` 改由 entitlements 结果驱动，形状不变——契约已预留」）；
2. ``paywall_required`` 由**后端权益**驱动：家庭一份 Pro 权益都没开通 ⇒ true，
   已开通 ⇒ false（前端因此可去掉 ``VITE_PRO_PAYWALL_ENABLED`` 的硬编码假设）；
3. 缺 ``symbol`` → 422（pydantic 层校验被 apiflask 拦下，不落视图；统一错误信封）；
4. ``asset_type`` 入口提示仅回显，不参与判定（给个非法品类也不 400）；
5. 骨架不查库：任何 symbol（含不存在的产品）都回同一形状——「该产品没有 Pro 数据」
   与「产品不存在」在 Phase 1 是同一件事（详情页先 resolve 再挂区块，见 detail.vue）。

为什么不能把响应换成纯权益映射（``{feature: {granted}}``）：``ProductProSection.vue``
读的是 ``data.modules[*].available``，删字段会让详情页 Pro 区块在渲染期 TypeError。
"""

import pytest

PRO_URL = '/api/products/pro/'


@pytest.fixture
def grant_all_pro(db):
    """为 family_id=1 授予全部 Pro 权益（#2324 起 ``paywall_required`` 由权益驱动）。

    与 tests/services/test_pro_allocation.py 的 ``_grant_pro_features`` 同源，
    但本文件属 products 域，故本地再声明一份而不跨文件 import。
    """
    from datetime import datetime

    from app.domains.entitlements.models import Entitlement
    from app.services.entitlement_check import PRO_FEATURES

    for feature in PRO_FEATURES:
        db.merge(
            Entitlement(
                family_id=1,
                feature=feature,
                granted=True,
                granted_at=datetime.utcnow(),
                source='test',
            )
        )
    db.commit()


def test_pro_status_returns_skeleton(client, grant_all_pro):
    """带 symbol + 已开通权益 → 骨架齐全、paywall_required=false、模块按上线节奏逐个翻真。

    Phase 2 起 performance / risk 翻真（内容服务 ``pro_insight.py`` /
    ``pro_risk.py`` 落地）；allocation / report 保持「Phase N 建设中」占位，
    落地时改 ``AVAILABLE_MODULES`` 一处。
    注意「可用」≠「有数据」：available 与标的是否有用户流水无关。
    """
    resp = client.get(PRO_URL, query_string={'symbol': '004369'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'ok'
    data = body['data']
    assert data['symbol'] == '004369'
    # #2324：paywall_required 由后端权益驱动（本用例已开通全部 Pro 权益 ⇒ false）
    assert data['pro_enabled'] is True
    assert data['paywall_required'] is False
    modules = data['modules']
    assert set(modules) == {'performance', 'risk', 'allocation', 'report'}
    assert modules['performance']['available'] is True  # #994 Phase 2 翻真（模块一）
    assert modules['risk']['available'] is True  # #994 Phase 2 翻真（模块二）
    assert modules['allocation']['available'] is True  # #994 提前翻真（模块三，见下方 phase 说明）
    for name, module in modules.items():
        assert module['phase'] in (2, 3, 4)
        if name not in ('performance', 'risk', 'allocation'):
            assert module['available'] is False
    # Phase 标注与 #994 五阶段排期一致：模块一/二 → P2，模块三 → P3，模块四 → P4。
    # ⚠️ 注意：allocation 的 phase **保持 3**（它是 #994 规划的既有事实），与本卡
    # 「提前做完」两件事互不影响——phase 讲排期归属，available 讲是否已上线。
    # 提前落地改的是 AVAILABLE_MODULES 一处，不回头改写规划。
    assert modules['performance']['phase'] == 2
    assert modules['risk']['phase'] == 2
    assert modules['allocation']['phase'] == 3
    assert modules['report']['phase'] == 4


def test_pro_status_paywall_required_without_entitlement(client):
    """未开通任何 Pro 权益 ⇒ paywall_required=true，``entitlements`` 逐位 false。

    「模块可用」与「有没有权益」是两件事：available 讲上线节奏（performance/risk
    ⇒ true），权益位单独披露，前端才能区分「没做」与「没买」。
    """
    resp = client.get(PRO_URL, query_string={'symbol': '004369'}, headers={'X-User-Id': '1'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['paywall_required'] is True
    assert set(data['entitlements']) == {'pro-insight', 'pro-risk', 'pro-allocation', 'pro-status'}
    assert all(item['granted'] is False for item in data['entitlements'].values())
    assert data['modules']['performance']['available'] is True


def test_pro_status_anonymous_requires_paywall(client):
    """未登录 ⇒ paywall_required=true（不查库，逐位回 false，形状与登录态一致）。"""
    resp = client.get(PRO_URL, query_string={'symbol': '004369'})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['paywall_required'] is True
    assert data['symbol'] == '004369'
    assert all(item['granted'] is False for item in data['entitlements'].values())


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
