# -*- coding: utf-8 -*-
"""Wind provider（S3）：两级网关请求形状、参数归一化、真机报文解析。

S3 的验收判据只有一句（设计文档 §9 / §10 第 1 条）：**接 Wind 时没有修改 ``transport.py``**
的**结构**。本文件的 :func:`test_wind_call_goes_through_unmodified_transport` 用**真实**
provider + **真实** transport（只把 ``post`` 换成替身）跑一遍网关请求形状；
:func:`test_transport_stays_provider_agnostic` 再从源码层钉住「传输层不认识 Wind」。

⚠️ 2026-10-23 真机采样（#2516）推翻了 S3 的两条假设，本文件随之改写：

| 原假设 | 实测 |
|---|---|
| 请求体是 ``{'toolName':…, 'arguments':'…'}``（非 JSON-RPC） | 上游按 pydantic 校验**拒收**（HTTP 400 + 11 条 ``JSONRPCMessage`` 字段缺失）；body 必须是 JSON-RPC |
| 返回是 ``{columnNames, rows}`` | ``data.columns[].name`` + ``data.rows``；``get_index_basicinfo`` 还多包一层 ``data.data[]`` |
| 存在 ``get_index_fundamentals`` | 只有 ``market_search_tools`` / ``market_call_tool`` 两个工具，数据查询一律经后者转发 |
"""

import inspect
import json

import pytest

from app.services.mcp import McpTransport, get_provider, provider_names
from app.services.mcp.errors import McpBadResponse
from app.services.mcp.providers.wind import (
    GATEWAY_CALL_TOOL,
    INDEX_QUERY_NAMES,
    MARKET_SEARCH_TOOL,
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
        if self._payload is None:
            raise ValueError('Expecting value: line 1 column 1 (char 0)')
        return self._payload

    def iter_lines(self, decode_unicode=True):
        return iter([])


class _GatewayPost:
    """JSON-RPC ``post`` 替身：握手 / 通知 / ``tools/call`` 分别回，并记录收到的载荷。"""

    def __init__(self, result=None):
        self.sent = []
        self.methods = []
        #: 上游真实形状（``get_index_kline`` 采样片段，2026-10-23）
        self._result = (
            result
            if result is not None
            else {'content': [{'type': 'text', 'text': json.dumps(_KLINE_PAYLOAD, ensure_ascii=False)}]}
        )

    def __call__(self, payload, sid):
        self.sent.append(payload)
        method = payload.get('method')
        self.methods.append(method or '(无 method)')
        if method == 'initialize':
            return _Resp(headers={})
        if method == 'notifications/initialized':
            return _Resp()
        return _Resp(payload={'jsonrpc': '2.0', 'id': 2, 'result': self._result})


#: ``get_index_kline`` 的真实返回（沪深300 日 K，已截断为 1 行）
_KLINE_PAYLOAD = {
    'data': {
        'columns': [
            {'name': 'TIME', 'type': 'string'},
            {'name': 'OPEN', 'type': 'string'},
            {'name': 'MATCH', 'type': 'string'},
        ],
        'rows': [['2026-10-22T00:00:00.000+08:00', '4110.65', '4036.30']],
        'unit': {'TURNOVER 单位': '元'},
    },
    'error': None,
}

#: ``get_index_basicinfo`` 的真实返回（多包一层 ``data.data`` 且是数组）
_BASICINFO_PAYLOAD = {
    'data': {
        'data': [
            {
                'columns': [
                    {'name': 'Wind代码', 'type': 'string'},
                    {'name': '证券简称', 'type': 'string'},
                    {'name': '发布机构', 'type': 'string'},
                ],
                'rows': [['399300.SZ', '沪深300', '中证指数有限公司']],
            }
        ]
    },
    'error': None,
}


# ── 注册与元信息 ──
def test_wind_provider_is_registered_with_matching_metadata():
    provider = get_provider('wind')

    assert isinstance(provider, WindProvider)
    assert provider.name == 'wind'
    assert provider.protocol_version == WIND_PROTOCOL_VERSION
    assert provider.client_info == WIND_CLIENT_INFO
    assert 'wind' in provider_names()


def test_capabilities_expose_static_tool_names():
    """能力表只登记**实测确认过**的工具名（2026-10-23 真机 ``tools/list``）。"""
    provider = get_provider('wind')

    assert provider.tool_for('index_kline') == 'get_index_kline'
    assert provider.tool_for('index_basicinfo') == 'get_index_basicinfo'
    assert provider.tool_for('index_technicals') == 'get_index_technicals'
    assert provider.tool_for('market_search') == MARKET_SEARCH_TOOL
    assert set(provider.read_only_tool_names()) == {provider.tool_for(c) for c in provider.capabilities()}
    assert GATEWAY_CALL_TOOL not in provider.read_only_tool_names(), '网关入口不是可直接调的能力'


def test_every_registered_tool_is_a_real_upstream_tool():
    """钉住「不许再冒出 ``get_index_fundamentals`` 这种不存在的工具名」。

    实测：上游只有两类工具 —— 检索入口与网关入口；数据工具是网关的**参数**，
    不是 ``tools/list`` 里的条目。所以能力表里的每个值都必须是我们实测过的具体工具。
    """
    known = {'get_index_kline', 'get_index_basicinfo', 'get_index_technicals', MARKET_SEARCH_TOOL}

    assert set(get_provider('wind').read_only_tool_names()) == known


def test_unknown_capability_raises_key_error():
    with pytest.raises(KeyError, match='Wind 没有能力'):
        get_provider('wind').tool_for('no_such_capability')


def test_scope_is_public_market_for_known_capabilities_and_private_otherwise():
    """已知能力是公开市场数据；未登记能力落基类默认 ``USER_PRIVATE``（不许悄悄烧系统额度）。"""
    provider = get_provider('wind')

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


# ── 请求形状（JSON-RPC + 二级网关转发）──
def test_wire_is_jsonrpc_tools_call():
    """实测：非 JSON-RPC 的 body 会被上游按 pydantic 校验拒收（HTTP 400）。"""
    body = get_provider('wind')._wire('get_index_kline', {'windcode': '000300.SH'})

    assert body['jsonrpc'] == '2.0'
    assert body['id'] == 2, '传输层按 id == 2 取 SSE 里的那一条'
    assert body['method'] == 'tools/call'


def test_wire_forwards_data_tools_through_the_gateway():
    """数据工具不是 ``tools/list`` 条目，必须经 ``market_call_tool`` 转发（且参数是 JSON 串）。"""
    body = get_provider('wind')._wire('get_index_kline', {'windcode': '000300.SH', 'period': '10'})
    params = body['params']

    assert params['name'] == GATEWAY_CALL_TOOL
    assert params['arguments']['toolName'] == 'get_index_kline'
    assert json.loads(params['arguments']['arguments']) == {'windcode': '000300.SH', 'period': '10'}
    assert isinstance(params['arguments']['arguments'], str), '网关要字符串，不是对象'


def test_wire_calls_search_tool_directly():
    """检索入口是真实工具，直接按名调用（不再套一层网关）。"""
    body = get_provider('wind')._wire(MARKET_SEARCH_TOOL, {'question': '沪深300'})

    assert body['params'] == {'name': MARKET_SEARCH_TOOL, 'arguments': {'question': '沪深300'}}


def test_wire_keeps_chinese_readable():
    """``ensure_ascii=False``：转义成 ``\\uXXXX`` 会让上游日志与采样现场都不可读。"""
    body = get_provider('wind')._wire('get_index_basicinfo', {'question': '沪深300的发布机构'})
    inner = body['params']['arguments']['arguments']

    assert '沪深300' in inner


# ── §6.2 实测坑 ──
@pytest.mark.parametrize('raw', ['D', 'd', '1d', 'day', 'daily', '10'])
def test_map_args_normalizes_daily_period_aliases(raw):
    assert get_provider('wind').map_args('index_kline', period=raw) == {'period': '10'}


def test_map_args_refuses_unknown_period_instead_of_guessing():
    with pytest.raises(ValueError, match='只支持日 K'):
        get_provider('wind').map_args('index_kline', period='W')


def test_map_args_maps_index_codes_for_question_style_capabilities():
    """``question`` 类工具认名称：把代码换成名称，再交给调用方拼问题。"""
    provider = get_provider('wind')

    assert provider.map_args('index_basicinfo', code='399006.SZ') == {'code': INDEX_QUERY_NAMES['399006.SZ']}
    assert provider.map_args('index_technicals', codes=['000300.SH', '000905.SH']) == {'codes': '沪深300,中证500'}


def test_map_args_leaves_windcode_untouched_for_kline():
    """``get_index_kline`` 两种都认（文档原文「指数名称或者指数代码」），故不替换 ——
    替换反而丢了调用方本来给的那个更精确的代码。"""
    args = get_provider('wind').map_args('index_kline', windcode='000300.SH')

    assert args == {'windcode': '000300.SH'}


def test_index_query_name_raises_for_unregistered_code():
    """未登记代码必须报错：静默透传的失效形态是上游只回 ``Invalid value``，看不出是我们没映射。"""
    with pytest.raises(ValueError, match='未登记查询名'):
        index_query_name('999999.SH')


def test_map_args_leaves_other_capabilities_untouched():
    args = get_provider('wind').map_args('market_search', question='沪深300估值', topK=5)

    assert args == {'question': '沪深300估值', 'topK': 5}


# ── 结果解析（坑④，实测两种形状）──
def test_extract_reads_real_kline_shape():
    """``data.columns[].name`` + ``data.rows``：真机 ``get_index_kline`` 的形状。"""
    rows = get_provider('wind').extract(json.dumps(_KLINE_PAYLOAD, ensure_ascii=False))

    assert rows == [{'TIME': '2026-10-22T00:00:00.000+08:00', 'OPEN': '4110.65', 'MATCH': '4036.30'}]


def test_extract_reads_real_basicinfo_shape_with_extra_data_level():
    """``data.data[]``：真机 ``get_index_basicinfo`` 比 kline 多包一层，且是数组。"""
    rows = get_provider('wind').extract(json.dumps(_BASICINFO_PAYLOAD, ensure_ascii=False))

    assert rows == [{'Wind代码': '399300.SZ', '证券简称': '沪深300', '发布机构': '中证指数有限公司'}]


def test_extract_still_accepts_legacy_column_names_shape():
    """旧形状（``columnNames: [str]``）保留：``market_search_tools`` 与历史夹具都是它。"""
    payload = {'columnNames': ['toolName', 'serverId'], 'rows': [['get_index_kline', 'vserver_index_data']]}

    assert get_provider('wind').extract(json.dumps(payload, ensure_ascii=False)) == [
        {'toolName': 'get_index_kline', 'serverId': 'vserver_index_data'}
    ]


def test_extract_flattens_multi_block_tables():
    payload = {
        'blockClose': {'columnNames': ['日期', '收盘'], 'rows': [['2026-10-20', 4000.1], ['2026-10-21', 4021.5]]},
        'blockInfo': {'columnNames': ['代码', '名称'], 'rows': [['000300.SH', '沪深300']]},
    }

    rows = get_provider('wind').extract(json.dumps(payload, ensure_ascii=False))

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


def test_extract_raises_when_business_error_is_present():
    """``error`` 非空即抛：不许把业务失败当成「这次没数据」。"""
    payload = {'data': {'columns': [], 'rows': []}, 'error': {'code': 400, 'message': '工具不存在: x'}}

    with pytest.raises(McpBadResponse, match='工具不存在'):
        get_provider('wind').extract(json.dumps(payload, ensure_ascii=False))


def test_extract_raises_for_non_json_payload():
    """非 JSON ⇒ 类型化错误，不返回空列表（空列表在上层会被读成「这只指数没数据」）。"""
    with pytest.raises(McpBadResponse, match='非 JSON'):
        get_provider('wind').extract('<html>WAF</html>')


def test_extract_raises_when_no_table_shape_found():
    with pytest.raises(McpBadResponse, match='没有可识别的表格'):
        get_provider('wind').extract(json.dumps({'code': 0, 'msg': 'ok'}))


# ── S3 的验收判据 ──
def test_wind_call_goes_through_unmodified_transport(monkeypatch):
    """真实 provider + 真实 transport：只换 ``post``，网关请求形状即生效、会话仍只握手一次。"""
    monkeypatch.setenv(WIND_MCP_URL_ENV, 'http://127.0.0.1:9/mcp')
    provider = get_provider('wind')
    post = _GatewayPost()
    transport: McpTransport = provider.build_transport(post)

    first = transport.call_tool('get_index_kline', {'windcode': '000300.SH'}, token='k')
    transport.call_tool('get_index_kline', {'windcode': '000300.SH'}, token='k')

    tool_calls = [payload for payload in post.sent if payload.get('method') == 'tools/call']
    assert tool_calls[0]['params']['name'] == GATEWAY_CALL_TOOL
    assert tool_calls[0]['params']['arguments']['toolName'] == 'get_index_kline'
    assert post.methods.count('initialize') == 1  # 会话复用对第二家同样有效
    assert provider.extract(first)[0]['MATCH'] == '4036.30'


def test_wind_call_maps_is_error_to_typed_error(monkeypatch):
    """实测：工具名错时上游是 **HTTP 200 + isError**。传输层必须当失败，不许当数据。"""
    monkeypatch.setenv(WIND_MCP_URL_ENV, 'http://127.0.0.1:9/mcp')
    provider = get_provider('wind')
    post = _GatewayPost(
        result={
            'content': [{'type': 'text', 'text': '工具不存在: vserver_wind_tools, get_index_fundamentals'}],
            'structuredContent': {'code': 400, 'message': '工具不存在: vserver_wind_tools, get_index_fundamentals'},
            'isError': True,
        }
    )

    with pytest.raises(McpBadResponse, match='工具不存在'):
        provider.build_transport(post).call_tool('get_index_kline', {}, token='k')


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
