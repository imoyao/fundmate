# -*- coding: utf-8 -*-
"""且慢 MCP 传输层与批量取数（#1876）：会话复用 + 概览/持仓批量 + 缺键降级。

背景：且慢投顾 job 每晚面对 111 只 QIEMAN 组合，原实现「每只各调一次工具 + 每次调用
重新握手」⇒ 442 次工具调用、约 666 个 HTTP 请求。本文件钉住三件事：

1. **会话复用**：实例内 ``Mcp-Session-Id`` 缓存，连续 N 次调用只握手一次；
2. **会话失效**：400/404/非 JSON 时**重新握手一次**并重试同一次调用；再失败才抛；
3. **批量与降级**：111 只概览 = 3 次 ``_call_tool``；持仓批量单次多只；
   批量响应缺某 code 的键 ⇒ 该 code 逐只重取，**数据不丢也不变成空**。

全部 mock，不打真实接口（真实 API key 不在 CI）。
"""

import json

import pytest

from app.services.adapters.qieman_fetcher import (
    QIEMAN_STRATEGY_BATCH_SIZE,
    QIEMAN_STRATEGY_COMPOSITION_TOOL,
    QIEMAN_STRATEGY_DETAIL_TOOL,
    QiemanFetcher,
)


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    monkeypatch.setenv('QIEMAN_API_KEY', 'test-key')


# ── 伪 HTTP 响应 ──


class _FakeResp:
    """requests.Response 的最小替身：只实现 ``_call_tool`` 用到的成员。"""

    def __init__(self, status_code=200, headers=None, payload=None, error_json=False):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self._error_json = error_json

    @property
    def text(self):
        return '' if self._payload is None else json.dumps(self._payload)

    def json(self):
        if self._error_json:
            raise ValueError('Expecting value: line 1 column 1 (char 0)')
        return self._payload

    def iter_lines(self, decode_unicode=True):
        return iter([])


def _json_ok(text: str) -> _FakeResp:
    """tools/call 正常响应（content-type: application/json）。"""
    return _FakeResp(
        headers={'content-type': 'application/json'},
        payload={'jsonrpc': '2.0', 'id': 2, 'result': {'content': [{'type': 'text', 'text': text}]}},
    )


class _Transport:
    """替换 ``_mcp_post``：按 payload 的 method 分派，并记录调用序列。

    ``tools_responses`` 依次消费（用完后重复最后一项），用于模拟会话中途失效。
    ``issue_sid=False`` 模拟且慢真实行为：initialize 200 但**不回** ``Mcp-Session-Id``。
    """

    def __init__(self, tools_responses, issue_sid: bool = True):
        self.calls = []  # [(method, sid)]
        self.handshakes = 0
        self._issue_sid = issue_sid
        self._tools_responses = list(tools_responses)

    def __call__(self, payload: dict, sid):
        method = payload.get('method')
        self.calls.append((method, sid))
        if method == 'initialize':
            self.handshakes += 1
            headers = {'Mcp-Session-Id': f'SID-{self.handshakes}'} if self._issue_sid else {}
            return _FakeResp(headers=headers, payload={})
        if method == 'notifications/initialized':
            return _FakeResp(headers={'Mcp-Session-Id': sid} if sid else {}, payload={})
        if method == 'tools/call':
            resp = self._tools_responses[0]
            if len(self._tools_responses) > 1:
                self._tools_responses.pop(0)
            return resp
        raise AssertionError(f'未预期的 MCP method: {method}')

    @property
    def tool_calls(self):
        return [c for c in self.calls if c[0] == 'tools/call']


def _fetcher_with(monkeypatch, transport: _Transport) -> QiemanFetcher:
    f = QiemanFetcher()
    monkeypatch.setattr(f, '_mcp_post', transport)
    return f


# ── 1. 会话复用 ──


def test_session_reused_across_calls(monkeypatch):
    """连续 5 次 tools/call 只握手 1 次（3 个 HTTP → 1 次握手 + 5 次调用）。"""
    t = _Transport([_json_ok('{"ok":1}')])
    f = _fetcher_with(monkeypatch, t)

    for _ in range(5):
        assert f._call_tool('k', QIEMAN_STRATEGY_DETAIL_TOOL, {}) == '{"ok":1}'

    assert t.handshakes == 1, f'握手次数应为 1，实际 {t.handshakes}'
    assert len(t.tool_calls) == 5
    # 后续调用都带同一个 sid（复用会话，而不是每次换新）
    assert {sid for _m, sid in t.tool_calls} == {'SID-1'}


def test_session_reused_when_server_returns_no_session_id(monkeypatch):
    """**且慢真实形态**：initialize 不回 ``Mcp-Session-Id``，仍只能握手一次。

    否则「没有会话可缓存」会退化成「每次调用都重新握手」，复用等于没做
    （实测 2026-10-20：服务端 nginx 无状态，且不带会话头 tools/call 依然 200）。
    """
    t = _Transport([_json_ok('{"ok":1}')], issue_sid=False)
    f = _fetcher_with(monkeypatch, t)

    for _ in range(4):
        f._call_tool('k', QIEMAN_STRATEGY_DETAIL_TOOL, {})

    assert t.handshakes == 1
    assert len(t.tool_calls) == 4
    assert {sid for _m, sid in t.tool_calls} == {None}  # 无会话头，与原实现一致


def test_session_rehandshake_when_api_key_changes(monkeypatch):
    """换 API key 必须重新握手（不能把旧 key 的会话拿去用）。"""
    t = _Transport([_json_ok('{}')])
    f = _fetcher_with(monkeypatch, t)

    f._call_tool('key-1', QIEMAN_STRATEGY_DETAIL_TOOL, {})
    f._call_tool('key-2', QIEMAN_STRATEGY_DETAIL_TOOL, {})

    assert t.handshakes == 2


# ── 2. 会话失效 → 重握一次 ──


@pytest.mark.parametrize('status', [400, 404])
def test_session_invalid_rehandshakes_once(monkeypatch, status):
    """tools/call 返回 400/404：丢会话、重新握手一次、重试同一次调用即成功。"""
    t = _Transport([_FakeResp(status_code=status), _json_ok('{"ok":1}')])
    f = _fetcher_with(monkeypatch, t)

    assert f._call_tool('k', QIEMAN_STRATEGY_DETAIL_TOOL, {}) == '{"ok":1}'
    assert t.handshakes == 2, '会话失效后应恰好重握一次'
    # 两次 tools/call 用的是不同会话（旧的被丢弃）
    assert [sid for _m, sid in t.tool_calls] == ['SID-1', 'SID-2']


def test_session_invalid_rehandshakes_once_without_session_id(monkeypatch):
    """无会话头形态下同样能重握并重试（真实服务端即此形态）。"""
    t = _Transport([_FakeResp(status_code=400), _json_ok('{"ok":1}')], issue_sid=False)
    f = _fetcher_with(monkeypatch, t)

    assert f._call_tool('k', QIEMAN_STRATEGY_DETAIL_TOOL, {}) == '{"ok":1}'
    assert t.handshakes == 2
    assert len(t.tool_calls) == 2


def test_session_invalid_non_json_rehandshakes_once(monkeypatch):
    """返回非 JSON（会话失效 / WAF 拦截）同样先重握一次，而不是直接判死。"""
    t = _Transport([_FakeResp(error_json=True), _json_ok('{"ok":1}')])
    f = _fetcher_with(monkeypatch, t)

    assert f._call_tool('k', QIEMAN_STRATEGY_DETAIL_TOOL, {}) == '{"ok":1}'
    assert t.handshakes == 2


def test_session_still_invalid_raises_after_one_retry(monkeypatch):
    """重握后仍失效 ⇒ 抛错（不无限重试、不吞成空结果）。"""
    t = _Transport([_FakeResp(status_code=404)])
    f = _fetcher_with(monkeypatch, t)

    with pytest.raises(RuntimeError, match='会话重握后仍失败'):
        f._call_tool('k', QIEMAN_STRATEGY_DETAIL_TOOL, {})

    assert t.handshakes == 2, '只允许重握一次（不得循环重试）'
    assert len(t.tool_calls) == 2, '只允许重试一次'


def test_non_session_error_not_retried(monkeypatch):
    """500 不是会话失效：直接抛，不做无意义的重握。"""
    t = _Transport([_FakeResp(status_code=500)])
    f = _fetcher_with(monkeypatch, t)

    with pytest.raises(RuntimeError, match='HTTP 500'):
        f._call_tool('k', QIEMAN_STRATEGY_DETAIL_TOOL, {})
    assert t.handshakes == 1
    assert len(t.tool_calls) == 1


# ── 3. 概览批量 ──


def _detail_payload(codes):
    return json.dumps(
        {
            'pageSize': 100,
            'rows': [{'策略代码': c, '策略名称': f'组合{c}', '策略净值': 1.5} for c in codes],
            'status': '查询成功',
            'hasMoreRows': False,
        }
    )


def test_overview_111_codes_use_three_tool_calls(monkeypatch):
    """111 只概览 ⇒ 恰好 3 次 tools/call（50/50/11），且传的是批量 code 列表。"""
    codes = [f'ZH{i:06d}' for i in range(111)]
    calls = []

    f = QiemanFetcher()

    def _fake_call_tool(api_key, tool, arguments):
        calls.append((tool, list(arguments['strategyCodes'])))
        return _detail_payload(arguments['strategyCodes'])

    monkeypatch.setattr(f, '_call_tool', _fake_call_tool)
    out = f.fetch_strategy_details(codes)

    assert len(calls) == 3, f'应为 3 次批量调用，实际 {len(calls)}'
    assert [len(c[1]) for c in calls] == [QIEMAN_STRATEGY_BATCH_SIZE, QIEMAN_STRATEGY_BATCH_SIZE, 11]
    assert all(c[0] == QIEMAN_STRATEGY_DETAIL_TOOL for c in calls)
    # 三次的 code 合集恰好是全部 111 只（无遗漏、无重复）
    assert [c for _t, chunk in calls for c in chunk] == codes
    assert len(out) == 111


def test_adapter_overviews_one_call_for_many_codes(monkeypatch):
    """适配器层：111 只概览同样落到 3 次调用（不是逐只 111 次）。"""
    from app.services.adapters.qieman_advisor_adapter import QiemanAdvisorAdapter

    codes = [f'ZH{i:06d}' for i in range(111)]
    f = QiemanFetcher()
    calls = []

    def _fake_call_tool(api_key, tool, arguments):
        calls.append(list(arguments['strategyCodes']))
        return _detail_payload(arguments['strategyCodes'])

    monkeypatch.setattr(f, '_call_tool', _fake_call_tool)
    adapter = QiemanAdvisorAdapter()
    adapter._fetcher = f

    out = adapter.fetch_overviews(codes)

    assert len(calls) == 3
    assert len(out) == 111
    # canonical 形状不变：desc 缺失时回退 summary 不在本用例范围，这里只校验关键键
    assert out[codes[0]]['name'] == f'组合{codes[0]}'


# ── 4. 持仓批量 + 缺键降级 ──


def _composition_payload(mapping):
    """真实结构：{code: {基金类别: {持有成分: [...]}}}。"""
    return json.dumps(
        {
            code: {
                '权益类': {
                    '持有成分': [{'基金代码': '110011', '基金名称': '易方达中小盘', '持仓占比': '32.5%'}],
                    '分类占比': '32.5%',
                }
            }
            for code in mapping
        }
    )


def test_composition_batch_single_call_for_multiple_codes(monkeypatch):
    """持仓批量：多个 code 一次调用，按返回的 {code: ...} 切分。"""
    codes = ['ZH000001', 'ZH000002', 'ZH000003']
    seen = []

    f = QiemanFetcher()

    def _fake_call_tool(api_key, tool, arguments):
        seen.append((tool, list(arguments['strategyCodes'])))
        return _composition_payload(arguments['strategyCodes'])

    monkeypatch.setattr(f, '_call_tool', _fake_call_tool)
    out = f.fetch_strategy_composition_batch(codes)

    assert len(seen) == 1, f'批量应只调 1 次，实际 {len(seen)}'
    assert seen[0] == (QIEMAN_STRATEGY_COMPOSITION_TOOL, codes)
    assert set(out) == set(codes)
    for code in codes:
        assert [h['code'] for h in out[code]] == ['110011']
        assert out[code][0]['ratio'] == 32.5


def test_composition_batch_missing_key_falls_back_per_code(monkeypatch):
    """批量响应缺某 code 的键 ⇒ 该 code 逐只重取，**数据不丢也不变成空**。

    这是「批量语义未被真实接口证实」的防御底线：批量拿不到 ≠ 组合清仓。
    """
    codes = ['ZH000001', 'ZH000002']
    seen = []

    f = QiemanFetcher()

    def _fake_call_tool(api_key, tool, arguments):
        batch = list(arguments['strategyCodes'])
        seen.append(batch)
        if len(batch) > 1:
            # 批量响应只回了第一只（模拟「多只不受支持」或部分失败）
            return _composition_payload([codes[0]])
        return _composition_payload(batch)

    monkeypatch.setattr(f, '_call_tool', _fake_call_tool)
    out = f.fetch_strategy_composition_batch(codes)

    # 第 1 次批量 + 第 2 只逐只重取
    assert seen == [[codes[0], codes[1]], [codes[1]]]
    assert [h['code'] for h in out['ZH000001']] == ['110011']
    assert [h['code'] for h in out['ZH000002']] == ['110011'], '缺键的组合必须靠逐只重取拿到数据'


def test_composition_batch_all_keys_missing_falls_back_each(monkeypatch):
    """整批都认不出（如返回 {'error': …}）⇒ 每个 code 都逐只重取一次。"""
    codes = ['A', 'B']
    seen = []

    f = QiemanFetcher()

    def _fake_call_tool(api_key, tool, arguments):
        batch = list(arguments['strategyCodes'])
        seen.append(batch)
        if len(batch) > 1:
            return json.dumps({'error': 'strategyCodes 仅支持单个'})
        return _composition_payload(batch)

    monkeypatch.setattr(f, '_call_tool', _fake_call_tool)
    out = f.fetch_strategy_composition_batch(codes)

    assert seen == [['A', 'B'], ['A'], ['B']]
    assert all(out[c] for c in codes)


def test_composition_batch_flat_shape_multi_codes_also_falls_back(monkeypatch):
    """扁平形态（旧版只支持单只）在多 code 时无法归属 ⇒ 全部降级逐只，不得错配。"""
    codes = ['A', 'B']
    seen = []

    f = QiemanFetcher()

    def _fake_call_tool(api_key, tool, arguments):
        batch = list(arguments['strategyCodes'])
        seen.append(batch)
        if len(batch) > 1:
            return json.dumps([{'code': '110011', 'ratio': 5.0}])
        return json.dumps([{'code': f'FUND-{batch[0]}', 'ratio': 1.0}])

    monkeypatch.setattr(f, '_call_tool', _fake_call_tool)
    out = f.fetch_strategy_composition_batch(codes)

    assert seen == [['A', 'B'], ['A'], ['B']]
    assert [h['code'] for h in out['A']] == ['FUND-A']
    assert [h['code'] for h in out['B']] == ['FUND-B']


def test_composition_batch_single_call_failure_returns_empty_per_code(monkeypatch):
    """整批调用抛错：每个 code 返回空列表（与单只实现的「失败即空」口径一致）。"""

    def _boom(*_a, **_kw):
        raise RuntimeError('MCP 调用返回为空')

    f = QiemanFetcher()
    monkeypatch.setattr(f, '_call_tool', _boom)

    out = f.fetch_strategy_composition_batch(['A', 'B'])
    assert out == {'A': [], 'B': []}


def test_holdings_batch_adapter_preserves_as_of_date(monkeypatch):
    """适配器批量持仓：快照日取最晚 adj_time（与逐只实现的既有语义一致）。"""
    from app.services.adapters.qieman_advisor_adapter import QiemanAdvisorAdapter

    payload = json.dumps(
        {
            'ZH1': {
                '权益类': {
                    '持有成分': [
                        {'基金代码': '110011', '持仓占比': '10%', '调仓时间': '2026-09-01'},
                        {'基金代码': '161725', '持仓占比': '5%', '调仓时间': '2026-09-08'},
                    ]
                }
            }
        }
    )
    f = QiemanFetcher()
    monkeypatch.setattr(f, '_call_tool', lambda *a, **kw: payload)
    adapter = QiemanAdvisorAdapter()
    adapter._fetcher = f

    out = adapter.fetch_holdings_batch(['ZH1'])

    assert out['ZH1']['as_of_date'] == '2026-09-08'
    assert [x['fund_code'] for x in out['ZH1']['funds']] == ['110011', '161725']
    assert out['ZH1']['funds'][0]['after_ratio'] == 10.0


# ── 5. 一整轮 job 的总账（111 只组合的调用量） ──


class _RoutingTransport(_Transport):
    """按 ``params.name`` + ``arguments`` 现场生成响应的传输替身（供总量测试用）。"""

    def __init__(self, issue_sid: bool = False):
        super().__init__([], issue_sid=issue_sid)

    def __call__(self, payload: dict, sid):
        if payload.get('method') == 'tools/call':
            tool = payload['params']['name']
            args = payload['params']['arguments']
            self.calls.append(('tools/call', sid))
            if tool == QIEMAN_STRATEGY_DETAIL_TOOL:
                return _json_ok(_detail_payload(args['strategyCodes']))
            return _json_ok(_composition_payload(args['strategyCodes']))
        return super().__call__(payload, sid)


def test_one_night_run_total_tool_calls_and_http_posts(monkeypatch):
    """111 只组合的一轮 job：6 次工具调用 + 1 次握手（= 8 个 HTTP 请求）。

    改前基线：111 次概览 + 111 次持仓 = **222 次工具调用**、每次 3 个 HTTP
    ⇒ 约 666 个请求。改后：概览 3 批（50/50/11）+ 持仓 3 批 = 6 次工具调用，
    握手只在第一次发生 ⇒ 2 + 6 = 8 个 HTTP 请求（收敛 ~83 倍）。
    """
    from app.services.adapters.qieman_advisor_adapter import QiemanAdvisorAdapter

    codes = [f'ZH{i:06d}' for i in range(111)]
    t = _RoutingTransport()
    f = QiemanFetcher()
    monkeypatch.setattr(f, '_mcp_post', t)
    adapter = QiemanAdvisorAdapter()
    adapter._fetcher = f

    overviews = adapter.fetch_overviews(codes)
    holdings = adapter.fetch_holdings_batch(codes)

    assert len(overviews) == 111
    assert set(holdings) == set(codes)
    assert t.handshakes == 1, f'整轮只应握手一次，实际 {t.handshakes}'
    assert len(t.tool_calls) == 6, f'整轮应 6 次工具调用，实际 {len(t.tool_calls)}'
    assert len(t.calls) == 8, f'整轮应 8 个 HTTP 请求（2 握手 + 6 调用），实际 {len(t.calls)}'
