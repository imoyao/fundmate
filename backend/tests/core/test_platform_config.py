# -*- coding: utf-8 -*-
"""平台级实时估值开关（双层估值开关的平台级总闸，issue #826）测试。

背景：实时估值是「用户级开关（前端 localStorage）+ 平台级总闸（后端 env
`REALTIME_QUOTES_ENABLED`）」双层结构。平台级为总闸：数据源压力过大或合规收紧时，
运维改 env 即可一键关闭全站实时估值，无需发版。

本测试锁定以下不变量：
1. `GET /api/utils/config/` 默认（未配置 env）返回 `realtime_quotes_enabled: true`，
   避免默认关闭导致线上估值突然消失；
2. env `REALTIME_QUOTES_ENABLED=false` 时返回 false（truthy 解析：'1'/'true'/'yes'/'on'）；
3. 白名单回归：未登录（无 token）请求 `/api/utils/config/` 应 200（免登录），
   探市页 /explore 匿名访客依赖此总闸。
"""


class TestPlatformConfigEndpoint:
    def test_default_enabled_true(self, client):
        resp = client.get('/api/utils/config/')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['message'] == 'ok'
        assert body['data']['realtime_quotes_enabled'] is True

    def test_env_false_disables(self, client, monkeypatch):
        monkeypatch.setenv('REALTIME_QUOTES_ENABLED', 'false')
        resp = client.get('/api/utils/config/')
        assert resp.status_code == 200
        assert resp.get_json()['data']['realtime_quotes_enabled'] is False

    def test_env_truthy_variants(self, client, monkeypatch):
        # truthy 解析：'1'/'true'/'yes'/'on' → True，其余 False
        for value in ('1', 'true', 'yes', 'on'):
            monkeypatch.setenv('REALTIME_QUOTES_ENABLED', value)
            resp = client.get('/api/utils/config/')
            assert resp.get_json()['data']['realtime_quotes_enabled'] is True, value
        for value in ('0', 'false', 'no', 'off', 'anything'):
            monkeypatch.setenv('REALTIME_QUOTES_ENABLED', value)
            resp = client.get('/api/utils/config/')
            assert resp.get_json()['data']['realtime_quotes_enabled'] is False, value

    def test_anonymous_request_is_public(self, client):
        # 无 token、无 X-User-Id 旁路头：白名单放行，应 200 而非 401
        resp = client.get('/api/utils/config/')
        assert resp.status_code == 200
