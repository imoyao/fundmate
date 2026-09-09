# -*- coding: utf-8 -*-
"""账本精灵 AgentLoop / ToolExecutor 离线单测（不触网、不触 DB）。

验证三件最易碎的事：
1. parse_agent_action 的容错（围栏 / 无 JSON / 数组 / 非法 action 都降级为澄清）；
2. ToolExecutor 的 schema 校验（缺参 / 未知参 / 非法值 -> error）；
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


# ── ToolExecutor 校验 ──
def test_tool_success():
    r = ToolExecutor.run('get_portfolio_performance', {'scope': 'all', 'period': '90d'})
    assert r['status'] == 'success'


def test_tool_missing_required():
    r = ToolExecutor.run('get_portfolio_performance', {'scope': 'all'})  # 缺 period
    assert r['status'] == 'error'


def test_tool_unknown_param():
    r = ToolExecutor.run('get_portfolio_performance', {'scope': 'all', 'period': '90d', 'bad': 1})
    assert r['status'] == 'error'


def test_tool_bad_enum():
    r = ToolExecutor.run('get_portfolio_performance', {'scope': 'galaxy', 'period': '90d'})
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
            return '{"action":"execute_tool","tool_name":"get_portfolio_performance","tool_params":{"scope":"all","period":"90d"}}'
        return '您的年化收益约为 X%。'  # 叙事

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('分析我的收益', {}, user_id=1, session_id='s1')
    assert out['type'] == 'result'
    assert calls['n'] == 2  # 1 次决策 + 1 次叙事


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
