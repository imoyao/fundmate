# -*- coding: utf-8 -*-
"""``/api/health`` 的 MCP 段回归测试（S2，#2490）。

本端点**免登录**，所以它只能读两种内部事实：env 有没有配（不看值）+ 内部审计表。
两条口径在这里被钉死：

1. **未配置 Token = ``disabled``（可选组件关闭），不是故障** —— 否则每个未接入 MCP 的
   部署天天报红，真故障反而被淹没（#1720 同口径）；
2. **读不到审计表 = ``unknown``，且拉低整体状态** —— 拿不到输入却报 healthy 就是假绿
   （CNB #171 那类形态）。相反，偶发抖动（5xx / 频控）只算 ``degraded``，**不**拉低整体。

插入审计行必须走 ``market_session()``：``mcp_call_logs`` 是 ``market`` 域，
而 ``db`` 夹具只绑 user 引擎。
"""

from datetime import datetime

import pytest

from app.core.database import market_session
from app.core.time_utils import SHANGHAI_TZ, now_shanghai
from app.models.mcp_call_log import McpCallLog

_BOTH_ENV = ('QIEMAN_API_KEY', 'WIND_MCP_TOKEN')


def _insert_call(*, provider='qieman', ok, error_kind=None, message=None) -> None:
    """插一行**当日**审计（naive 东八区墙钟，与 ``called_at`` 落库口径一致）。"""
    with market_session() as db:
        db.add(
            McpCallLog(
                provider=provider,
                capability='strategy_composition',
                scope='platform_public',
                ok=ok,
                error_kind=error_kind,
                message=message,
                called_at=now_shanghai().replace(tzinfo=None),
            )
        )
        db.commit()


def _mcp(client) -> dict:
    body = client.get('/api/health').get_json()
    return body['components']['mcp']


def test_no_token_configured_reports_disabled(monkeypatch, client):
    """一个都没配 ⇒ 整体 ``disabled``。**不是** "healthy"：没启用与都正常是两件事。"""
    for env in _BOTH_ENV:
        monkeypatch.delenv(env, raising=False)

    mcp = _mcp(client)

    assert mcp['status'] == 'disabled'
    assert set(mcp['providers']) >= {'qieman'}
    assert all(p['configured'] is False for p in mcp['providers'].values())


def test_configured_provider_with_auth_failure_is_unhealthy_and_drags_overall(monkeypatch, client):
    """授权失效要人处理 ⇒ ``unhealthy``，并把整体状态拉成 ``degraded``。"""
    monkeypatch.setenv('QIEMAN_API_KEY', 'fake-token-for-test')
    _insert_call(ok=False, error_kind='auth', message='且慢 授权已失效，请更新 Token')

    body = client.get('/api/health').get_json()

    assert body['components']['mcp']['status'] == 'unhealthy'
    assert body['components']['mcp']['providers']['qieman']['last_error_kind'] == 'auth'
    assert body['status'] == 'degraded'


@pytest.mark.parametrize('kind', ['quota', 'billing'])
def test_quota_and_billing_are_also_unhealthy(monkeypatch, client, kind):
    """额度用尽 / 欠费同样需要人介入，与 auth 同档。"""
    monkeypatch.setenv('QIEMAN_API_KEY', 'fake-token-for-test')
    _insert_call(ok=False, error_kind=kind)

    assert _mcp(client)['status'] == 'unhealthy'


def test_transient_failure_only_degrades_without_dragging_overall(monkeypatch, client):
    """偶发 5xx ⇒ ``degraded``，**不**拉低整体（抖动常态化报红会让真故障被淹没）。"""
    monkeypatch.setenv('QIEMAN_API_KEY', 'fake-token-for-test')
    _insert_call(ok=False, error_kind='unavailable')

    body = client.get('/api/health').get_json()

    assert body['components']['mcp']['status'] == 'degraded'
    assert body['status'] == 'ok'


def test_readable_table_with_success_only_is_healthy(monkeypatch, client):
    monkeypatch.setenv('QIEMAN_API_KEY', 'fake-token-for-test')
    _insert_call(ok=True)

    mcp = _mcp(client)

    assert mcp['status'] == 'healthy'
    assert mcp['providers']['qieman']['calls_today'] == 1
    assert mcp['providers']['qieman']['errors_24h'] == 0


def test_unreadable_audit_table_reports_unknown_and_drags_overall(monkeypatch, client):
    """**关键**：读不到审计表 ⇒ ``unknown`` + 整体 ``degraded``，绝不退化成 healthy。"""
    monkeypatch.setenv('QIEMAN_API_KEY', 'fake-token-for-test')
    monkeypatch.setattr(
        'app.domains.health.provider_snapshot',
        lambda provider, **kw: {'available': False, 'reason': 'no such table: mcp_call_logs'},
    )

    body = client.get('/api/health').get_json()

    assert body['components']['mcp']['status'] == 'unknown'
    assert '本次结论不可信' in body['components']['mcp']['providers']['qieman']['message']
    assert body['status'] == 'degraded'


def test_health_never_echoes_token_value(monkeypatch, client):
    """免登录端点回显凭据就是泄漏；``disabled`` 的提示语只提**变量名**。"""
    secret = 'super-secret-token-value'
    monkeypatch.setenv('WIND_MCP_TOKEN', secret)
    for env in ('QIEMAN_API_KEY',):
        monkeypatch.delenv(env, raising=False)

    raw = client.get('/api/health').get_data(as_text=True)

    assert secret not in raw
    assert 'QIEMAN_API_KEY' in raw  # 提示的是变量名，不是值


def test_mcp_component_carries_no_realtime_probe_fields(client):
    """免登录端点禁止实时外部调用：MCP 段只允许出现内部审计字段。"""
    mcp = _mcp(client)

    assert set(mcp) == {'status', 'providers', 'message'}
    for entry in mcp['providers'].values():
        assert set(entry) == {
            'configured',
            'status',
            'last_error_kind',
            'last_error_at',
            'last_ok_at',
            'calls_today',
            'errors_24h',
            'message',
        }


def test_scheduler_disabled_does_not_mask_mcp_status(monkeypatch, client):
    """调度未开启是独立组件：它报 ``disabled`` 不应影响 MCP 段自己的结论。"""
    monkeypatch.delenv('SCHEDULER_ENABLED', raising=False)
    for env in _BOTH_ENV:
        monkeypatch.delenv(env, raising=False)

    body = client.get('/api/health').get_json()

    assert body['components']['scheduler']['status'] == 'disabled'
    assert body['components']['mcp']['status'] == 'disabled'
    assert body['status'] == 'ok'


def test_timestamps_are_iso_with_shanghai_offset(monkeypatch, client):
    """时间口径与 scheduler 段一致：库里是 naive 墙钟，输出带 ``+08:00``（避免前端按 UTC 解读）。"""
    monkeypatch.setenv('QIEMAN_API_KEY', 'fake-token-for-test')
    _insert_call(ok=False, error_kind='auth')

    entry = _mcp(client)['providers']['qieman']

    assert entry['last_error_at'].endswith('+08:00')
    assert entry['last_error_at'].startswith(datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d'))
