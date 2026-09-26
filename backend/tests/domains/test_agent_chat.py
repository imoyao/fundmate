# -*- coding: utf-8 -*-
"""POST /api/agent/chat/ HTTP 层测试（#1121 S1-A；S2 契约演化回归）。

覆盖：三态响应（clarify / result / error）+ 决策轮 prompt 携带工具清单 +
P1 服务端 family_id 覆盖 + 轮次闸 429 信封 + S2 会话（服务端生成 id /
跨轮续接 / 越权 404）。LLM 全部 monkeypatch（不触网），guards 模块级内存态逐例清理
（轮次计数 S2 起落库，由内存库随用例隔离，不再有进程内计数器）。
"""

import pytest

from app.core.exceptions import ErrorCode
from app.domains.agent.models import AgentSession
from app.services.ai_recognizer import guards as ai_guards
from app.services.ai_recognizer import llm as llm_module
from app.services.ai_recognizer import tools as tools_mod


@pytest.fixture(autouse=True)
def _reset_agent_guards(monkeypatch):
    """重置限流/熔断/token 等模块级内存状态，避免用例间相互干扰。"""
    monkeypatch.setattr(ai_guards, 'OCR_RATE_LIMIT_MAX', 1000)
    monkeypatch.setattr(ai_guards, 'OCR_MELTDOWN_THRESHOLD', 1000)
    for state in (ai_guards._RATE_LIMIT_BUCKETS, ai_guards._MELTDOWN_STATE):
        state.clear()
    ai_guards._token_used_today = 0
    yield
    for state in (ai_guards._RATE_LIMIT_BUCKETS, ai_guards._MELTDOWN_STATE):
        state.clear()
    ai_guards._token_used_today = 0


def _post(client, message, session_id=None):
    """S2 请求契约：不带 session_id 即由服务端新建会话。"""
    body = {'message': message}
    if session_id is not None:
        body['session_id'] = session_id
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
    # S2：三态统一携带服务端生成的 session_id（前端下轮回带即续接）
    assert payload['data']['session_id']


def test_chat_result_carries_tools_metadata(client, monkeypatch, db):
    prompts = []

    def fake(content, system_prompt, **kwargs):
        prompts.append(system_prompt)
        if kwargs.get('response_format'):
            return '{"action":"execute_tool","tool_name":"get_assets_overview","tool_params":{}}'
        return '您的净资产为 0 元。'

    monkeypatch.setattr(llm_module, 'call_llm', fake)
    # 会话行先经 db fixture 提交再进请求：测试库是 StaticPool 单连接，请求中途
    # 工具链里 get_session().close() 的连接复位会把**未提交的 INSERT** 连带回滚
    # （实测 b.close() 后行数归零 → teardown 的 UPDATE 匹配 0 行 StaleDataError）；
    # 生产各 Session 走独立连接，只回滚自己的事务，不受影响。预提交后中途回滚
    # 只丢当轮未 flush 的改动，teardown 重发 UPDATE 即可命中。
    db.add(AgentSession(session_id='sess-tools', user_id=1))
    db.commit()
    resp = _post(client, '我的资产总览', session_id='sess-tools')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['type'] == 'result'
    assert data['data']['total_assets_cny'] == 0  # 空内存库，真实 service 返回全零
    # 盲猜修复回归钉：决策轮 prompt 必须携带工具清单
    assert 'get_assets_overview' in prompts[0]


def test_chat_p1_server_family_id_wins(client, monkeypatch, db):
    """P1：状态里的 collected_params 与模型 tool_params 伪造 family_id=999 → 均被服务端值覆盖。"""
    # S2：状态服务端持有——预置含伪造候选值的会话（模拟上一轮遗留的候选参数）
    db.add(AgentSession(session_id='sess-p1', user_id=1, state={'collected_params': {'family_id': 999}}))
    db.commit()
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
    resp = _post(client, '看资产', session_id='sess-p1')
    assert resp.status_code == 200
    assert resp.get_json()['data']['type'] == 'result'
    assert captured['family_id'] != 999  # 伪造值（候选）不进工具


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


def test_chat_turn_limit_429(client, monkeypatch, db):
    """G4 轮次闸 S2 起落库：会话 turn_count 打满 → 429 信封（不再依赖进程内计数器）。"""
    db.add(AgentSession(session_id='sess-limit', user_id=1, turn_count=ai_guards.get_agent_max_turns()))
    db.commit()
    monkeypatch.setattr(llm_module, 'call_llm', lambda *a, **k: '{}')
    resp = _post(client, 'hi', session_id='sess-limit')
    assert resp.status_code == 429
    assert resp.get_json()['error_code'] == ErrorCode.AGENT_TURN_LIMIT_EXCEEDED.code


def test_chat_session_server_side_continuity(client, monkeypatch):
    """S2（P2 修复验收）：客户端只回带 session_id，原文与追问参数由服务端续接。"""
    prompts = []

    def fake(content, system_prompt, **kwargs):
        if kwargs.get('response_format'):
            prompts.append(content[0]['text'])
            if len(prompts) == 1:
                return '{"action":"ask_clarification","missing_params":["period"],"content":"想看多久的走势？"}'
            return '{"action":"execute_tool","tool_name":"get_assets_overview","tool_params":{}}'
        return '您的净资产为 0 元。'

    monkeypatch.setattr(llm_module, 'call_llm', fake)
    resp1 = _post(client, '帮我看下近30天的收益')
    assert resp1.status_code == 200
    sid = resp1.get_json()['data']['session_id']
    assert sid  # 服务端生成的会话 id

    resp2 = _post(client, '就看30天', session_id=sid)
    data2 = resp2.get_json()['data']
    assert resp2.status_code == 200
    assert data2['session_id'] == sid  # 同会话续接
    assert data2['type'] == 'result'
    # 第 2 轮决策 prompt 含第 1 轮原文——历史由服务端回放，客户端未传任何状态
    assert '近30天的收益' in prompts[1]


def test_chat_session_forged_or_unknown_id_404(client, db):
    """S2（P4 修复验收）：伪造 / 越权 / 不存在的 session_id 一律 404，不泄露存在性。"""
    db.add(AgentSession(session_id='sess-owned-by-others', user_id=999))
    db.commit()
    # 越权：id 存在但不属于当前用户
    resp = _post(client, 'hi', session_id='sess-owned-by-others')
    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == ErrorCode.RESOURCE_NOT_FOUND.code
    # 不存在：同样 404（403 会泄露「该 id 存在」）
    resp2 = _post(client, 'hi', session_id='sess-never-existed')
    assert resp2.status_code == 404
    assert resp2.get_json()['error_code'] == ErrorCode.RESOURCE_NOT_FOUND.code
