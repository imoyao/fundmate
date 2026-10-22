# -*- coding: utf-8 -*-
"""Pro 端点权益拦截的**响应契约**测试（#2324 收口）。

为什么单独一篇：这条 403 的「形状」比「状态码」重要得多。

旧实现用 ``abort(403, description={...})``，经 ``main.py`` 的 HTTPException 处理器后，
``message`` 变成了**一个 dict**（信封里嵌套信封）。前端据此无法判断「该升级」，
只能统一显示「暂时取不到」——用户因此把权限问题误判成服务故障（2026-10-20 实测）。

本文件钉住三件事：

1. ``error_code == 1007``（``PRO_NOT_ENTITLED``，与通用 403/1006 分开）；
2. ``message`` 是**字符串**，不是 dict——这是旧 bug 的回归探针；
3. ``data`` 携带 ``feature`` / ``reason``，前端可据此渲染权益态而不必解析文案。
"""

import pytest

URLS = [
    ('/api/products/pro-insight/?symbol=012708&asset_type=fund', 'pro-insight'),
    ('/api/products/pro-risk/?symbol=012708&asset_type=fund', 'pro-risk'),
    ('/api/products/pro-allocation/?symbol=012708&asset_type=fund', 'pro-allocation'),
]


@pytest.mark.parametrize(('url', 'feature'), URLS)
def test_pro_endpoint_denies_with_dedicated_code(client, db, url, feature):
    """未开通权益 → 403 + 1007 + 字符串 message + data.feature。"""
    from app.domains.entitlements.models import Entitlement

    assert db.query(Entitlement).count() == 0  # 前置：本用例依赖「一条都没开通」

    resp = client.get(url)
    assert resp.status_code == 403

    body = resp.get_json()
    assert body['error_code'] == 1007
    assert body['message'] == 'Pro 功能未开通'
    assert isinstance(body['message'], str), 'message 必须是字符串（旧实现把整个 dict 塞了进来）'
    assert body['data']['feature'] == feature
    assert body['data']['reason'] == 'not_granted'


def test_expired_entitlement_reports_reason(client, db):
    """过期权益同样 403，但 ``reason`` 要能区分 ``expired``——前端据此 wording 不同。"""
    from datetime import datetime, timedelta

    from app.domains.entitlements.models import Entitlement

    db.add(
        Entitlement(
            family_id=1,
            feature='pro-risk',
            granted=True,
            granted_at=datetime.utcnow(),
            expires_at=datetime.utcnow() - timedelta(days=1),
            source='test',
        )
    )
    db.commit()

    resp = client.get('/api/products/pro-risk/?symbol=012708&asset_type=fund')
    assert resp.status_code == 403
    assert resp.get_json()['data']['reason'] == 'expired'


def test_granted_entitlement_passes_gate(client, db):
    """开通后不再被权益拦截（是否 200 取决于数据，但绝不能是 403/1007）。"""
    from datetime import datetime

    from app.domains.entitlements.models import Entitlement

    db.add(
        Entitlement(
            family_id=1,
            feature='pro-risk',
            granted=True,
            granted_at=datetime.utcnow(),
            source='test',
        )
    )
    db.commit()

    resp = client.get('/api/products/pro-risk/?symbol=012708&asset_type=fund')
    assert resp.status_code != 403
