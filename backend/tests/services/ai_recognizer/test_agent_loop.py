# -*- coding: utf-8 -*-
"""账本精灵 AgentLoop / ToolExecutor 离线单测（不触网；DB 为 conftest 内存库）。

验证三件最易碎的事：
1. parse_agent_action 的容错（围栏 / 无 JSON / 数组 / 非法 action 都降级为澄清）；
2. ToolExecutor 的 schema 校验（缺参 / 未知参 / 类型或格式非法 -> error）；
3. run_agent 在 monkeypatch 掉 call_llm 后能跑通 execute_tool 路径，且 G4 超限抛异常。
"""

import pytest

from app.core.exceptions import ErrorCode, SBException
from app.services.ai_recognizer import agent_loop, guards
from app.services.ai_recognizer import llm as llm_mod
from app.services.ai_recognizer.agent_loop import validate_session_state
from app.services.ai_recognizer.tools import ToolExecutor


# ── parse_agent_action 容错 ──
def test_parse_valid():
    assert agent_loop.parse_agent_action('{"action":"execute_tool","tool_name":"x"}')['action'] == 'execute_tool'


def test_parse_fenced():
    raw = '```json\n{"action":"ask_clarification","missing_params":["period"]}\n```'
    out = agent_loop.parse_agent_action(raw)
    assert out['action'] == 'ask_clarification'
    assert out['missing_params'] == ['period']


def test_parse_no_json():
    out = agent_loop.parse_agent_action('抱歉我没法处理')
    assert out['action'] == 'ask_clarification'
    assert out['error'] == 'no_json_object'


def test_parse_array_not_object():
    out = agent_loop.parse_agent_action('[1,2,3]')
    assert out['action'] == 'ask_clarification'


def test_parse_invalid_action():
    out = agent_loop.parse_agent_action('{"action":"boom"}')
    assert out['action'] == 'ask_clarification'
    assert out['error'] == 'invalid_action'


# ── ToolExecutor 校验（S1-A 换真实工具后的四例） ──
def test_tool_success():
    # 空内存库：资产总览返回全零指标，链路真实跑通
    r = ToolExecutor.run('get_assets_overview', {})
    assert r['status'] == 'success'
    assert r['data']['total_assets_cny'] == 0


def test_tool_missing_required():
    r = ToolExecutor.run('get_fund_nav', {})  # 缺 fund_codes
    assert r['status'] == 'error'


def test_tool_unknown_param():
    r = ToolExecutor.run('get_assets_overview', {'scope': 'all'})
    assert r['status'] == 'error'


def test_tool_bad_pattern():
    r = ToolExecutor.run('get_fund_nav', {'fund_codes': ['not-a-code']})  # 数组元素不匹配 ^\d{6}$
    assert r['status'] == 'error'


# ── session_manager 白名单 ──
def test_session_validate_ok():
    s = validate_session_state({'goal': 'g', 'collected_params': {'period': '90d'}})
    assert s['goal'] == 'g'


def test_session_validate_rejects_unknown_key():
    with pytest.raises(SBException):
        validate_session_state({'goal': 'g', 'hack': 'drop table'})


# ── run_agent 集成（monkeypatch call_llm）──
def test_run_agent_execute(monkeypatch):
    calls = {'n': 0}

    def fake(content, system_prompt, **kwargs):
        calls['n'] += 1
        if kwargs.get('response_format'):
            return '{"action":"execute_tool","tool_name":"get_assets_overview","tool_params":{}}'
        # 叙事：按 #1712 小节契约输出（决策轮 / 叙事轮以 response_format 区分）
        return '【结论】净资产约 X 元。\n【明细】详情如下。\n【风险提示】暂无。'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('分析我的收益', {}, user_id=1, session_id='s1')
    assert out['type'] == 'result'
    assert calls['n'] == 2  # 1 次决策 + 1 次叙事
    # 契约分块（#1712）：blocks 解析成功，结构可被前端直接渲染
    assert out['blocks'] is not None
    assert [b['type'] for b in out['blocks']] == ['summary', 'text', 'risk']
    # 兜底字段保留：content 原文仍在，前端可回退纯文本渲染
    assert out['content'].startswith('【结论】')


def test_run_agent_narrative_drift_falls_back(monkeypatch):
    """叙事模型漂移（不按小节输出）→ blocks=None，前端降级纯文本，不崩。"""

    def fake(content, system_prompt, **kwargs):
        if kwargs.get('response_format'):
            return '{"action":"execute_tool","tool_name":"get_assets_overview","tool_params":{}}'
        return '就是一段没有小节标记的普通总结。'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('分析我的收益', {}, user_id=1, session_id='s1_drift')
    assert out['type'] == 'result'
    assert out['blocks'] is None
    assert out['content'] == '就是一段没有小节标记的普通总结。'


def test_run_agent_clarify(monkeypatch):
    def fake(content, system_prompt, **kwargs):
        return '{"action":"ask_clarification","missing_params":["period"],"content":"想分析多久？"}'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('分析我的收益', {}, user_id=1, session_id='s2')
    assert out['type'] == 'clarify'
    assert out['missing_params'] == ['period']


def test_run_agent_turn_limit(monkeypatch):
    def fake(content, system_prompt, **kwargs):
        return '{"action":"ask_clarification","missing_params":["period"]}'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    for _ in range(guards.get_agent_max_turns()):
        guards.record_agent_turn(1, 'sess_limit')
    with pytest.raises(SBException) as exc:
        agent_loop.run_agent('hi', {}, user_id=1, session_id='sess_limit')
    assert exc.value.code == ErrorCode.AGENT_TURN_LIMIT_EXCEEDED.code
    guards.reset_agent_session(1, 'sess_limit')  # 清理，避免影响其他用例
