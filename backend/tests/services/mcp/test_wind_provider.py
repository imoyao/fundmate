# -*- coding: utf-8 -*-
"""Wind provider（S3）：请求形状、参数归一化、结果解析，以及「接第二家不改传输层」。

S3 的验收判据只有一句（设计文档 §9 / §10 第 1 条）：**接 Wind 时没有修改 ``transport.py``**。
本文件的 :func:`test_wind_call_goes_through_unmodified_transport` 用**真实** provider +
**真实** transport（只把 ``post`` 换成替身）跑一遍网关请求形状；
:func:`test_transport_stays_provider_agnostic` 再从源码层钉住「传输层不认识 Wind」。

⚠️ 未验证的假设（等真实 Token 采样）：网关的**响应**形状沿用了 JSON-RPC 的
``result.content[].text``。请求侧由 ``_wire`` 覆盖（已测），响应侧若不同，
处置是「给传输层加 provider 级解包扩展点」，而**不是**在传输层里写 provider 名字分支。
"""

import inspect
import json

import pytest

from app.services.mcp import McpTransport, get_provider, provider_names
from app.services.mcp.errors import McpBadResponse
from app.services.mcp.providers.wind import (
    INDEX_QUERY_NAMES,
    WIND_CLIENT_INFO,
    WIND_MCP_URL_ENV,
    WIND_PROTOCOL_VERSION,
    WindEndpointMissing,
    WindProvider,
    index_query_name,
)


# ── 替身 ──
class _Resp:
    """``requests.Response`` 的最小替身（只实现传输层用到的成员）。"""

    def __init__(self, status_code=200, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False) if payload is not None else ''

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=True):
        return iter([])


class _GatewayPost:
    """网关型 ``post`` 替身：按「有没有 method」区分握手 / 工具调用，并记录收到的载荷。"""

    def __init__(self, text='{}'):
        self.sent = []
        self.methods = []
        self._text = text

    def __call__(self, payload, sid):
        self.sent.append(payload)
        method = payload.get('method')
        self.methods.append(method or f'tool:{payload.get("toolName")}')
        if method == 'initialize':
            return _Resp(headers={})
        if method == 'notifications/initialized':
            return _Resp()
        return _Resp(payload={'jsonrpc': '2.0', 'id': 2, 'result': {'content': [{'type': 'text', 'text': self._text}]}})


# ── 注册与元信息 ──
def test_wind_provider_is_registered_with_matching_metadata():
    provider = get_provider('wind')

    assert isinstance(provider, WindProvider)
    assert provider.name == 'wind'
    assert provider.protocol_version == WIND_PROTOCOL_VERSION
    assert provider.client_info == WIND_CLIENT_INFO
    assert 'wind' in provider_names()


def test_capabilities_expose_static_tool_names():
    provider = get_provider('wind')

    assert provider.tool_for('index_fundamentals') == 'get_index_fundamentals'
    assert provider.tool_for('market_search') == 'market_search_tools'
    assert set(provider.read_only_tool_names()) == {provider.tool_for(c) for c in provider.capabilities()}


def test_unknown_capability_raises_key_error():
    with pytest.raises(KeyError, match='Wind 没有能力'):
        get_provider('wind').tool_for('no_such_capability')


def test_scope_is_public_market_for_known_capabilities_and_private_otherwise():
    """已知能力是公开市场数据；未登记能力落基类默认 ``USER_PRIVATE``（不许悄悄烧系统额度）。"""
    provider = get_provider('wind')

    assert provider.scope_of('index_fundamentals').value == 'public_market'
    assert provider.scope_of('no_such_capability').value == 'user_private'


# ── 地址与鉴权 ──
def test_base_url_requires_env_instead_of_guessing_a_default(monkeypatch):
    """没有可确认的官方地址常量 ⇒ 缺 env 当场报错（猜一个只会让现场误判成 WAF / DNS）。"""
    monkeypatch.delenv(WIND_MCP_URL_ENV, raising=False)

    with pytest.raises(WindEndpointMissing, match=WIND_MCP_URL_ENV):
        get_provider('wind').base_url()


def test_base_url_can_be_overridden_for_local_mock(monkeypatch):
    monkeypatch.setenv(WIND_MCP_URL_ENV, 'http://127.0.0.1:9/mcp')

    assert get_provider('wind').base_url() == 'http://127.0.0.1:9/mcp'


def test_empty_token_does_not_forge_authorization_header():
    headers = get_provider('wind').auth_headers('')

    assert 'Authorization' not in headers


def test_token_uses_bearer_scheme():
    assert get_provider('wind').auth_headers('abc') == {'Authorization': 'Bearer abc'}


# ── 请求形状（覆盖基类的 JSON-RPC）──
def test_wire_is_gateway_shaped_not_jsonrpc():
    body = get_provider('wind')._wire('get_index_fundamentals', {'codes': '沪深300'})

    assert body == {'toolName': 'get_index_fundamentals', 'arguments': '{"codes": "沪深300"}'}
    assert 'jsonrpc' not in body
    assert isinstance(body['arguments'], str)  # 网关要字符串，不是对象


def test_wire_keeps_chinese_readable():
    """``ensure_ascii=False``：转义成 ``\\uXXXX`` 会让上游日志与采样现场都不可读。"""
    body = get_provider('wind')._wire('get_index_fundamentals', {'codes': '沪深300'})

    assert '沪深300' in body['arguments']


# ── §6.2 四个坑 ──
@pytest.mark.parametrize('raw', ['D', 'd', '1d', 'day', 'daily', '10'])
def test_map_args_normalizes_daily_period_aliases(raw):
    assert get_provider('wind').map_args('index_fundamentals', period=raw) == {'period': '10'}


def test_map_args_refuses_unknown_period_instead_of_guessing():
    with pytest.raises(ValueError, match='只支持日 K'):
        get_provider('wind').map_args('index_fundamentals', period='W')


def test_map_args_joins_batches_into_comma_string_and_maps_index_names():
    """坑②+坑③：批量参数是逗号串，且元素也要做「代码 → 查询名」的映射。"""
    args = get_provider('wind').map_args('index_fundamentals', codes=['000300.SH', '000905.SH'])

    assert args == {'codes': '沪深300,中证500'}


def test_map_args_maps_single_index_code():
    args = get_provider('wind').map_args('index_fundamentals', code='399006.SZ')

    assert args == {'code': INDEX_QUERY_NAMES['399006.SZ']}


def test_index_query_name_raises_for_unregistered_code():
    """未登记代码必须报错：静默透传的失效形态是上游只回 ``Invalid value``，看不出是我们没映射。"""
    with pytest.raises(ValueError, match='未登记查询名'):
        index_query_name('999999.SH')


def test_map_args_leaves_other_capabilities_untouched():
    """坑①/② 只属于 ``index_fundamentals``，不许扩散到别的能力。"""
    args = get_provider('wind').map_args('market_search', query='000300.SH', limit=5)

    assert args == {'query': '000300.SH', 'limit': 5}


# ── 结果解析（坑④）──
def _tables_payload():
    return {
        'blockClose': {'columnNames': ['日期', '收盘'], 'rows': [['2026-10-20', 4000.1], ['2026-10-21', 4021.5]]},
        'blockInfo': {'columnNames': ['代码', '名称'], 'rows': [['000300.SH', '沪深300']]},
    }


def test_extract_flattens_multi_block_tables():
    rows = get_provider('wind').extract(json.dumps(_tables_payload(), ensure_ascii=False))

    assert rows == [
        {'日期': '2026-10-20', '收盘': 4000.1},
        {'日期': '2026-10-21', '收盘': 4021.5},
        {'代码': '000300.SH', '名称': '沪深300'},
    ]


def test_extract_pads_short_rows_and_missing_columns_with_none():
    """坑④：缺列显式 ``None`` —— 让「上游没给」与「我们没取」在数据上可区分。"""
    payload = {'columnNames': ['日期', '收盘', '成交额'], 'rows': [['2026-10-20']]}

    rows = get_provider('wind').extract(json.dumps(payload, ensure_ascii=False), columns=['换手率'])

    assert rows == [{'日期': '2026-10-20', '收盘': None, '成交额': None, '换手率': None}]


def test_extract_raises_for_non_json_payload():
    """非 JSON ⇒ 类型化错误，不返回空列表（空列表在上层会被读成「这只指数没数据」）。"""
    with pytest.raises(McpBadResponse, match='非 JSON'):
        get_provider('wind').extract('<html>WAF</html>')


def test_extract_raises_when_no_table_shape_found():
    with pytest.raises(McpBadResponse, match='没有 columnNames / rows'):
        get_provider('wind').extract(json.dumps({'code': 0, 'msg': 'ok'}))


# ── S3 的验收判据 ──
def test_wind_call_goes_through_unmodified_transport(monkeypatch):
    """真实 provider + 真实 transport：只换 ``post``，网关请求形状即生效、会话仍只握手一次。"""
    monkeypatch.setenv(WIND_MCP_URL_ENV, 'http://127.0.0.1:9/mcp')
    provider = get_provider('wind')
    post = _GatewayPost(text=json.dumps(_tables_payload(), ensure_ascii=False))
    transport: McpTransport = provider.build_transport(post)

    first = transport.call_tool('get_index_fundamentals', {'codes': '沪深300'}, token='k')
    transport.call_tool('get_index_fundamentals', {'codes': '沪深300'}, token='k')

    tool_calls = [payload for payload in post.sent if 'toolName' in payload]
    assert tool_calls[0] == {'toolName': 'get_index_fundamentals', 'arguments': '{"codes": "沪深300"}'}
    assert post.methods.count('initialize') == 1  # 会话复用对第二家同样有效
    assert provider.extract(first)[0] == {'日期': '2026-10-20', '收盘': 4000.1}


def test_transport_stays_provider_agnostic():
    """源码层判据：``transport.py`` 不认识 Wind，也没有反向依赖 providers（§10 第 1 条）。"""
    from app.services.mcp import transport as transport_module

    source = inspect.getsource(transport_module).lower()

    assert 'wind' not in source
    assert 'from app.services.mcp.providers' not in source


# ── 探针（只读 + 不需要凭据也能列出能力）──
def test_probe_list_works_without_any_credentials(monkeypatch, capsys):
    from app.tools.mcp_probe import main

    monkeypatch.delenv('WIND_MCP_TOKEN', raising=False)
    monkeypatch.delenv(WIND_MCP_URL_ENV, raising=False)

    assert main(['--list']) == 0
    out = capsys.readouterr().out
    assert 'index_fundamentals' in out
    assert 'get_index_fundamentals' in out


def test_probe_rejects_unknown_capability_without_network(monkeypatch, capsys):
    from app.tools.mcp_probe import main

    monkeypatch.setenv(WIND_MCP_URL_ENV, 'http://127.0.0.1:9/mcp')
    monkeypatch.setenv('WIND_MCP_TOKEN', 'dummy')

    assert main(['--capability', 'write_something']) == 2
    assert '未知能力' in capsys.readouterr().err
