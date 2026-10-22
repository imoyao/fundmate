# -*- coding: utf-8 -*-
"""MCP 凭据路由单测（S2，#2490）。

这个文件的核心是一条**红线**：用户私有能力在用户没配 Token 时，**绝不回退系统 Token**。
它被写成 ``McpUserTokenMissing`` 而不是注释，因为回退是这条红线唯一真正的失效方式 ——
一旦发生，系统额度被用户私有请求消耗、数据归属错乱（别人的账户数据算到系统头上），
而且**没有任何红灯**。所以这里用类型断言把它钉死。

副线是「不猜」：未登记的 provider 抛错，而不是按 ``{NAME}_MCP_TOKEN`` 去猜变量名 ——
猜会让「没配」与「配错变量名」在故障现场无法区分。
"""

import pytest

from app.services.mcp.credentials import (
    DataScope,
    is_configured,
    resolve_token,
    system_token,
    token_env_name,
)
from app.services.mcp.errors import McpTokenMissing, McpUserTokenMissing

_SYSTEM_TOKEN = 'sys-token-xyz'


@pytest.fixture
def qieman_token(monkeypatch):
    """配置好系统 Token（且慢真实环境里就是这么用的）。"""
    monkeypatch.setenv('QIEMAN_API_KEY', _SYSTEM_TOKEN)
    return _SYSTEM_TOKEN


def test_data_scope_values_are_stable_strings():
    """scope 会落 ``mcp_call_logs.scope``，值即契约。"""
    assert {s.value for s in DataScope} == {'public_market', 'platform_public', 'user_private'}


def test_user_private_never_falls_back_to_system_token(qieman_token):
    """**红线**：即便系统 Token 已配好，用户私有能力也必须抛错，不得代取。"""
    with pytest.raises(McpUserTokenMissing) as excinfo:
        resolve_token('qieman', DataScope.USER_PRIVATE, user_id='u-1')

    err = excinfo.value
    assert err.kind == 'user_token_missing'
    assert err.action == 'configure_token'
    # 凭据不得出现在任何可落日志的字段里
    assert _SYSTEM_TOKEN not in str(err)
    assert _SYSTEM_TOKEN not in err.user_message
    assert _SYSTEM_TOKEN not in err.detail


def test_user_private_without_system_token_also_raises_user_token_missing(monkeypatch):
    """未配系统 Token 时也不能退化成 ``McpTokenMissing``：缺的是**用户**凭据，提示语不同。"""
    monkeypatch.delenv('QIEMAN_API_KEY', raising=False)

    with pytest.raises(McpUserTokenMissing):
        resolve_token('qieman', DataScope.USER_PRIVATE)


@pytest.mark.parametrize('scope', [DataScope.PLATFORM_PUBLIC, DataScope.PUBLIC_MARKET, 'platform_public'])
def test_public_scopes_use_system_token(qieman_token, scope):
    """平台公开 / 公开市场能力走系统 Token；scope 传字符串同样成立（StrEnum 的调用方友好性）。"""
    assert resolve_token('qieman', scope) == _SYSTEM_TOKEN


def test_missing_or_blank_system_token_raises_token_missing(monkeypatch):
    """未配置 / 纯空白都算「没配」，且 ``action`` 指向"去配 Token"（而不是"等"或"报告"）。"""
    monkeypatch.delenv('QIEMAN_API_KEY', raising=False)
    with pytest.raises(McpTokenMissing) as excinfo:
        system_token('qieman')
    assert excinfo.value.action == 'configure_token'

    monkeypatch.setenv('QIEMAN_API_KEY', '   ')
    assert is_configured('qieman') is False
    with pytest.raises(McpTokenMissing):
        system_token('qieman')


def test_configured_token_is_stripped(monkeypatch):
    """真实 .env 里常带尾随空格：返回前统一 strip，否则空白会被拼进鉴权头而 401。"""
    monkeypatch.setenv('QIEMAN_API_KEY', '  tok-with-space  ')

    assert system_token('qieman') == 'tok-with-space'


def test_token_env_name_is_registry_not_guess():
    """新接一家服务必须显式登记变量名；未登记抛错，不按命名约定猜。"""
    assert token_env_name('qieman') == 'QIEMAN_API_KEY'
    assert token_env_name('wind') == 'WIND_MCP_TOKEN'

    with pytest.raises(ValueError):
        token_env_name('newco')


def test_is_configured_answers_boolean_without_raising_for_unknown_provider(monkeypatch):
    """health 免登录端点会遍历它，故未登记 provider 只能返回 False，不能抛。"""
    monkeypatch.delenv('QIEMAN_API_KEY', raising=False)

    assert is_configured('qieman') is False
    assert is_configured('newco') is False

    monkeypatch.setenv('QIEMAN_API_KEY', _SYSTEM_TOKEN)
    assert is_configured('qieman') is True


def test_unknown_scope_raises_value_error(qieman_token):
    """scope 写错必须当场炸，不能默认成公开能力（那会把私有请求送进系统额度）。"""
    with pytest.raises(ValueError):
        resolve_token('qieman', 'user-private-typo')


def test_is_configured_never_returns_the_value(monkeypatch):
    """只回答有没有，不返回值 —— 它是免登录端点的数据来源，返回值等于把凭据暴露出去。"""
    monkeypatch.setenv('QIEMAN_API_KEY', _SYSTEM_TOKEN)

    result = is_configured('qieman')

    assert result is True
    assert _SYSTEM_TOKEN not in repr(result)
