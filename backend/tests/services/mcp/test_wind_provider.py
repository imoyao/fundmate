# -*- coding: utf-8 -*-
"""Wind provider（S3）：请求形状、参数归一化、结果解析，以及「接第二家不改传输层」。

**2026-10-23 起本文件的形状以真实网关采样为准**（`#2516`）：
S3 首版按设计文档推断实现，从未在真网关上跑过；采样后推翻了其中两条假设，
且两者当时的失败形态都是**静默**的（400 报错 / 行数对但值全 None），
故这里的每条用例都对着一次真实报文，而不是文档里的示意结构。

采样证据（脱敏）：
- ``tools/list`` 只有 ``market_search_tools`` / ``market_call_tool``；
- ``_wire`` 若发 ``{toolName, arguments}`` 当整个请求体 ⇒ **HTTP 400**，
  ``Validation error: JSONRPCRequest.method Field required``；
- ``market_call_tool`` 要求 ``arguments`` 是 **JSON 字符串**；
- 业务返回是 ``{data: {columns: [{name, type}], rows: [[...]]}, error: null}``。
"""

import inspect
import json

import pytest

from app.services.mcp import McpTransport, get_provider, provider_names
from app.services.mcp.errors import McpBadResponse
from app.services.mcp.providers.wind import (
    CALL_TOOL,
    INDEX_QUERY_NAMES,
    SEARCH_TOOL,
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
    """网关型 ``post`` 替身：按 ``method`` 区分握手 / 工具调用，并记录收到的载荷。"""

    def __init__(self, text='{}'):
        self.sent = []
        self.methods = []
        self._text = text

    def __call__(self, payload, sid):
        self.sent.append(payload)
        method = payload.get('method')
        self.methods.append(method or f'no-method:{sorted(payload)}')
        if method == 'initialize':
            return _Resp(headers={})
        if method == 'notifications/initialized':
            return _Resp()
        return _Resp(payload={'jsonrpc': '2.0', 'id': 2, 'result': {'content': [{'type': 'text', 'text': self._text}]}})


def _unwrap(args):
    """``market_call_tool`` 的转发参数：``{'toolName': ..., 'arguments': <JSON 字符串>}``。"""
    assert set(args) == {'toolName', 'arguments'}
    assert isinstance(args['arguments'], str), '网关要求字符串，传对象会被拒'
    return args['toolName'], json.loads(args['arguments'])


# ── 注册与元信息 ──
def test_wind_provider_is_registered_with_matching_metadata():
    provider = get_provider('wind')

    assert isinstance(provider, WindProvider)
    assert provider.name == 'wind'
    assert provider.protocol_version == WIND_PROTOCOL_VERSION
    assert provider.client_info == WIND_CLIENT_INFO
    assert 'wind' in provider_names()


def test_capabilities_route_through_the_two_gateway_tools():
    """真实网关只有两个 MCP 工具：业务工具必须经 ``market_call_tool`` 转发。"""
    provider = get_provider('wind')

    assert provider.tool_for('index_fundamentals') == CALL_TOOL
    assert provider.tool_for('index_kline') == CALL_TOOL
    assert provider.tool_for('market_search') == SEARCH_TOOL
    assert set(provider.read_only_tool_names()) == {CALL_TOOL, SEARCH_TOOL}


def test_unknown_capability_raises_key_error():
    with pytest.raises(KeyError, match='Wind 没有能力'):
        get_provider('wind').tool_for('no_such_capability')


def test_scope_is_public_market_for_known_capabilities_and_private_otherwise():
    """已知能力是公开市场数据；未登记能力落基类默认 ``USER_PRIVATE``（不许悄悄烧系统额度）。"""
    provider = get_provider('wind')

    assert provider.scope_of('index_fundamentals').value == 'public_market'
    assert provider.scope_of('index_kline').value == 'public_market'
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


# ── 请求形状（**标准 JSON-RPC**，实测 400 推翻了旧的自定义形状）──
def test_wire_is_standard_jsonrpc():
    """旧版把 ``{toolName, arguments}`` 当整个请求体 ⇒ 真网关 400（``method`` 缺失）。"""
    provider = get_provider('wind')
    body = provider._wire(CALL_TOOL, {'toolName': 'get_index_kline', 'arguments': '{}'})

    assert body['jsonrpc'] == '2.0'
    assert body['method'] == 'tools/call'
    assert body['params'] == {'name': CALL_TOOL, 'arguments': {'toolName': 'get_index_kline', 'arguments': '{}'}}


def test_wire_keeps_chinese_readable():
    """``ensure_ascii=False``：转义成 ``\\uXXXX`` 会让上游日志与采样现场都不可读。"""
    provider = get_provider('wind')
    args = provider.map_args('index_fundamentals', code='000300.SH')

    assert '沪深300' in args['arguments']


# ── §6.2 四个坑 ──
@pytest.mark.parametrize('raw', ['D', 'd', '1d', 'day', 'daily', '10'])
def test_map_args_normalizes_daily_period_aliases(raw):
    wind_tool, args = _unwrap(get_provider('wind').map_args('index_kline', period=raw))

    assert wind_tool == 'get_index_kline'
    assert args == {'period': '10'}


def test_map_args_refuses_unknown_period_instead_of_guessing():
    with pytest.raises(ValueError, match='只支持日 K'):
        get_provider('wind').map_args('index_kline', period='W')


def test_map_args_wraps_business_tool_and_joins_batches():
    """坑②+坑③：批量参数是逗号串，元素做「代码 → 查询名」映射；外层再包转发形态。"""
    wind_tool, args = _unwrap(get_provider('wind').map_args('index_fundamentals', codes=['000300.SH', '000905.SH']))

    assert wind_tool == 'get_index_fundamentals'
    assert args == {'codes': '沪深300,中证500'}


def test_map_args_maps_single_index_code():
    _, args = _unwrap(get_provider('wind').map_args('index_fundamentals', code='399006.SZ'))

    assert args == {'code': INDEX_QUERY_NAMES['399006.SZ']}


def test_index_query_name_raises_for_unregistered_code():
    """未登记代码必须报错：静默透传的失效形态是上游只回 ``Invalid value``，看不出是我们没映射。"""
    with pytest.raises(ValueError, match='未登记查询名'):
        index_query_name('999999.SH')


def test_map_args_keeps_wind_code_for_kline():
    """``get_index_kline`` 的 ``windcode`` **认代码**（实测 ``885002.WI`` 直接可用）。

    坑② 只属于 ``index_fundamentals``：对 K 线多做一次名称映射，会把能取到的代码挡在门外。
    """
    _, args = _unwrap(get_provider('wind').map_args('index_kline', windcode='885002.WI', period='10'))

    assert args == {'windcode': '885002.WI', 'period': '10'}


def test_map_args_leaves_market_search_untouched():
    """检索工具直接走 MCP 工具，不套转发层。"""
    args = get_provider('wind').map_args('market_search', question='沪深300 最近一年收益率', topK=3)

    assert args == {'question': '沪深300 最近一年收益率', 'topK': 3}


# ── 结果解析（坑④，两种表格形状）──
def _doc_shape_payload():
    return {
        'blockClose': {'columnNames': ['日期', '收盘'], 'rows': [['2026-10-20', 4000.1], ['2026-10-21', 4021.5]]},
        'blockInfo': {'columnNames': ['代码', '名称'], 'rows': [['000300.SH', '沪深300']]},
    }


def _real_shape_payload():
    """2026-10-23 真实采样（数值保留，日期为真实交易日）。"""
    return {
        'data': {
            'columns': [
                {'name': 'TIME', 'type': 'string'},
                {'name': 'OPEN', 'type': 'string'},
                {'name': 'MATCH', 'type': 'string'},
            ],
            'rows': [
                ['2026-10-21T00:00:00.000+08:00', '7188.5749', '7201.5089'],
                ['2026-10-22T00:00:00.000+08:00', '7202.1041', '7206.3199'],
            ],
        },
        'error': None,
    }


def test_extract_flattens_multi_block_tables():
    rows = get_provider('wind').extract(json.dumps(_doc_shape_payload(), ensure_ascii=False))

    assert rows == [
        {'日期': '2026-10-20', '收盘': 4000.1},
        {'日期': '2026-10-21', '收盘': 4021.5},
        {'代码': '000300.SH', '名称': '沪深300'},
    ]


def test_extract_reads_real_gateway_shape_with_columns_objects():
    """旧实现在这个形状上返回「行数对、值全 None」的空记录 —— 静默失效，故单独钉住。"""
    rows = get_provider('wind').extract(json.dumps(_real_shape_payload(), ensure_ascii=False))

    assert rows[0] == {
        'TIME': '2026-10-21T00:00:00.000+08:00',
        'OPEN': '7188.5749',
        'MATCH': '7201.5089',
    }
    assert rows[-1]['MATCH'] == '7206.3199'


def test_extract_surfaces_upstream_error_instead_of_empty_rows():
    """``error`` 非空时显式抛错：静默返回 ``[]`` 会让上层读成「这只指数没有数据」。"""
    payload = {'data': None, 'error': {'code': -1, 'message': 'quota exceeded'}}

    with pytest.raises(McpBadResponse, match='quota exceeded'):
        get_provider('wind').extract(json.dumps(payload, ensure_ascii=False))


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
    with pytest.raises(McpBadResponse, match='没有表格'):
        get_provider('wind').extract(json.dumps({'code': 0, 'msg': 'ok'}))


# ── S3 的验收判据 ──
def test_wind_call_goes_through_unmodified_transport(monkeypatch):
    """真实 provider + 真实 transport：只换 ``post``，网关请求形状即生效、会话仍只握手一次。"""
    monkeypatch.setenv(WIND_MCP_URL_ENV, 'http://127.0.0.1:9/mcp')
    provider = get_provider('wind')
    post = _GatewayPost(text=json.dumps(_real_shape_payload(), ensure_ascii=False))
    transport: McpTransport = provider.build_transport(post)
    args = provider.map_args('index_kline', windcode='885002.WI', period='10')

    first = transport.call_tool(CALL_TOOL, args, token='k')
    transport.call_tool(CALL_TOOL, args, token='k')

    tool_calls = [payload for payload in post.sent if payload.get('method') == 'tools/call']
    assert tool_calls[0] == {
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'tools/call',
        'params': {'name': CALL_TOOL, 'arguments': args},
    }
    assert post.methods.count('initialize') == 1  # 会话复用对第二家同样有效
    assert provider.extract(first)[0]['MATCH'] == '7201.5089'


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
    assert 'index_kline' in out
    assert 'get_index_kline' in out


def test_probe_rejects_unknown_capability_without_network(monkeypatch, capsys):
    from app.tools.mcp_probe import main

    monkeypatch.setenv(WIND_MCP_URL_ENV, 'http://127.0.0.1:9/mcp')
    monkeypatch.setenv('WIND_MCP_TOKEN', 'dummy')

    assert main(['--capability', 'write_something']) == 2
    assert '未知能力' in capsys.readouterr().err
