# -*- coding: utf-8 -*-
"""POST /api/agent/chat/ HTTP 层测试（#1121 S1-A）。

覆盖：三态响应（clarify / result / error）+ 决策轮 prompt 携带工具清单 +
P1 服务端 family_id 覆盖 + 轮次闸 429 信封。LLM 全部 monkeypatch（不触网），
guards 模块级内存态逐例清理。
"""

import pytest

from app.core.exceptions import ErrorCode
from app.services.ai_recognizer import guards as ai_guards
from app.services.ai_recognizer import llm as llm_module
from app.services.ai_recognizer import tools as tools_mod


@pytest.fixture(autouse=True)
def _reset_agent_guards(monkeypatch):
    """重置限流/熔断/token/轮次等模块级内存状态，避免用例间相互干扰。"""
    monkeypatch.setattr(ai_guards, 'OCR_RATE_LIMIT_MAX', 1000)
    monkeypatch.setattr(ai_guards, 'OCR_MELTDOWN_THRESHOLD', 1000)
    for state in (ai_guards._RATE_LIMIT_BUCKETS, ai_guards._MELTDOWN_STATE, ai_guards._AGENT_TURN_COUNTER):
        state.clear()
    ai_guards._token_used_today = 0
    yield
    for state in (ai_guards._RATE_LIMIT_BUCKETS, ai_guards._MELTDOWN_STATE, ai_guards._AGENT_TURN_COUNTER):
        state.clear()
    ai_guards._token_used_today = 0


def _post(client, message, session_id='sess-1', session_state=None):
    body = {'message': message, 'session_id': session_id}
    if session_state is not None:
        body['session_state'] = session_state
    return client.post('/api/agent/chat/', json=body)


def test_chat_clarify(client, monkeypatch):
    def fake(content, system_prompt, **kwargs):
        return '{"action":"ask_clarification","missing_params":["period"],"content":"想看多久的走势？"}'

    monkeypatch.setattr(llm_module, 'call_llm', fake)
    resp = _post(client, '帮我分析一下')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['message'] == 'ok'
    assert payload['data']['type'] == 'clarify'
    assert payload['data']['missing_params'] == ['period']
    assert 'session_state' in payload['data']


def test_chat_result_carries_tools_metadata(client, monkeypatch):
    prompts = []

    def fake(content, system_prompt, **kwargs):
        prompts.append(system_prompt)
        if kwargs.get('response_format'):
            return '{"action":"execute_tool","tool_name":"get_assets_overview","tool_params":{}}'
        return '您的净资产为 0 元。'

    monkeypatch.setattr(llm_module, 'call_llm', fake)
    resp = _post(client, '我的资产总览')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['type'] == 'result'
    assert data['data']['total_assets_cny'] == 0  # 空内存库，真实 service 返回全零
    # 盲猜修复回归钉：决策轮 prompt 必须携带工具清单
    assert 'get_assets_overview' in prompts[0]


def test_chat_p1_server_family_id_wins(client, monkeypatch):
    """P1：前端 collected_params 与模型 tool_params 伪造 family_id=999 → 被服务端值覆盖。"""
    captured = {}

    def spy(params):
        captured.update(params)
        return {'ok': True}

    monkeypatch.setitem(tools_mod._FUNCTION_MAP, 'get_assets_overview', spy)

    def fake(content, system_prompt, **kwargs):
        if kwargs.get('response_format'):
            return '{"action":"execute_tool","tool_name":"get_assets_overview","tool_params":{"family_id":999}}'
        return '总结完毕'

    monkeypatch.setattr(llm_module, 'call_llm', fake)
    resp = _post(client, '看资产', session_state={'collected_params': {'family_id': 999}})
    assert resp.status_code == 200
    assert resp.get_json()['data']['type'] == 'result'
    assert captured['family_id'] != 999  # 伪造值不进工具


def test_chat_undeclared_scope_rejected(client, monkeypatch):
    """给未声明 family_id 的工具塞 family_id → 未知参数 → error 态（fail-closed）。"""

    def fake(content, system_prompt, **kwargs):
        if kwargs.get('response_format'):
            return (
                '{"action":"execute_tool","tool_name":"get_fund_nav",'
                '"tool_params":{"fund_codes":["110011"],"family_id":999}}'
            )
        return '查不到'

    monkeypatch.setattr(llm_module, 'call_llm', fake)
    resp = _post(client, '查净值')
    assert resp.status_code == 200
    assert resp.get_json()['data']['type'] == 'error'


def test_chat_turn_limit_429(client, monkeypatch):
    for _ in range(ai_guards.get_agent_max_turns()):
        ai_guards.record_agent_turn(1, 'sess-limit')
    monkeypatch.setattr(llm_module, 'call_llm', lambda *a, **k: '{}')
    resp = _post(client, 'hi', session_id='sess-limit')
    assert resp.status_code == 429
    assert resp.get_json()['error_code'] == ErrorCode.AGENT_TURN_LIMIT_EXCEEDED.code
