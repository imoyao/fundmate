# -*- coding: utf-8 -*-
"""账本精灵 AgentLoop / ToolExecutor 离线单测（不触网；DB 为 conftest 内存库）。

验证四件最易碎的事：
1. parse_agent_action 的容错（围栏 / 无 JSON / 数组 / 非法 action 都降级为澄清）；
2. ToolExecutor 的 schema 校验（缺参 / 未知参 / 类型或格式非法 -> error）；
3. run_agent 在 monkeypatch 掉 call_llm 后能跑通 execute_tool 路径，且 G4 超限抛异常；
4. #1718 决策轮对齐：缺省 goal 不得虚构进 prompt、指令为三选一、工具术语点名贪恐指数。
"""

import json

import pytest

from app.core.exceptions import ErrorCode, SBException
from app.domains.agent.models import AgentSession
from app.services.ai_recognizer import agent_loop, guards, session_store
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
        return '您的净资产约为 X 元。'  # 叙事

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('分析我的收益', AgentSession(session_id='s1', user_id=1))
    assert out['type'] == 'result'
    assert calls['n'] == 2  # 1 次决策 + 1 次叙事


def test_run_agent_clarify(monkeypatch):
    def fake(content, system_prompt, **kwargs):
        return '{"action":"ask_clarification","missing_params":["period"],"content":"想分析多久？"}'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('分析我的收益', AgentSession(session_id='s2', user_id=1))
    assert out['type'] == 'clarify'
    assert out['missing_params'] == ['period']


def test_run_agent_turn_limit(monkeypatch):
    """G4（S2 起落库）：turn_count 打满的会话行再进对话 → AGENT_TURN_LIMIT_EXCEEDED。"""

    def fake(content, system_prompt, **kwargs):
        return '{"action":"ask_clarification","missing_params":["period"]}'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    session = AgentSession(
        session_id='sess_limit',
        user_id=1,
        turn_count=guards.get_agent_max_turns(),
    )
    with pytest.raises(SBException) as exc:
        agent_loop.run_agent('hi', session)
    assert exc.value.code == ErrorCode.AGENT_TURN_LIMIT_EXCEEDED.code


# ── #1718 决策轮对齐：prompt 组装断言（不触网，mock call_llm 抓真实入参）──
def _capture_decision(monkeypatch, session, user_input='现在市场温度是多少？'):
    """跑一轮 run_agent，抓决策轮的真实 prompt 与 system prompt（首轮即 clarify 收尾）。"""
    seen: dict = {}

    def fake(content, system_prompt, **kwargs):
        if not seen:
            seen['prompt'] = content[0]['text']
            seen['system'] = system_prompt
        return '{"action":"ask_clarification","missing_params":[],"content":"好的"}'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    agent_loop.run_agent(user_input, session)
    return seen


def test_prompt_without_goal_not_fabricated(monkeypatch):
    """会话没设过目标 → prompt 不得虚构「分析账户收益」（#1718 根因①）。"""
    seen = _capture_decision(monkeypatch, AgentSession(session_id='g1', user_id=1))
    assert '分析账户收益' not in seen['prompt']
    assert '当前分析目标：无' in seen['prompt']
    assert '以用户最新一轮提问为准' in seen['prompt']


def test_prompt_default_goal_treated_as_unset(monkeypatch):
    """session_store.DEFAULT_GOAL 是展示用缺省标题，进 prompt 一律按「未设目标」处理。

    线上每个新建会话行都会被 load_or_create 写入该缺省值，历史存量行同样如此，
    所以只改回退值不够，必须把缺省值本身过滤掉。
    """
    from app.services.ai_recognizer import session_store

    session = AgentSession(session_id='g2', user_id=1, goal=session_store.DEFAULT_GOAL)
    seen = _capture_decision(monkeypatch, session)
    assert '分析账户收益' not in seen['prompt']
    assert '当前分析目标：无' in seen['prompt']


def test_prompt_user_goal_kept_but_demoted(monkeypatch):
    """用户显式设过的目标保留，但必须降级为背景、让位于最新提问。"""
    session = AgentSession(session_id='g3', user_id=1, goal='分析未来三年开销')
    seen = _capture_decision(monkeypatch, session)
    assert '分析未来三年开销' in seen['prompt']
    assert '仅作背景，仍以用户最新一轮提问为准' in seen['prompt']


def test_prompt_decision_rule_is_three_way(monkeypatch):
    """指令不再是「信息齐不齐」二元判断，且 system prompt 含对齐铁律。"""
    seen = _capture_decision(monkeypatch, AgentSession(session_id='g4', user_id=1))
    assert '判断顺序' in seen['prompt']
    assert '没有工具能回答' in seen['prompt']
    assert '请判断：信息是否齐全' not in seen['prompt']
    assert '以用户最新一轮提问为准' in seen['system']
    assert '禁止反问用户「是否继续原目标」' in seen['system']


def test_temperature_tool_description_names_fear_greed():
    """术语加固：工具清单里必须点名「贪恐 / 恐惧贪婪指数」，否则模型无从建立术语映射。"""
    from app.services.ai_recognizer.tools import TOOLS_METADATA

    meta = next(t for t in TOOLS_METADATA if t['name'] == 'get_market_temperature')
    assert '贪恐' in meta['description']
    assert '恐惧贪婪' in meta['description']


def test_narrative_prompt_carries_user_question(monkeypatch):
    """叙事轮必须带上用户本轮提问 + 工具语义说明（#1718 第二处根因）。

    修复前叙事 prompt 只有「基于以下数据…总结给用户」，模型不知道用户问了什么，
    产出通用的「市场温度总结」，三个子问题一个都不覆盖。
    """
    seen: dict = {}

    def fake(content, system_prompt, **kwargs):
        if kwargs.get('response_format'):  # 决策轮
            return '{"action":"execute_tool","tool_name":"get_market_temperature","tool_params":{}}'
        seen['narrative'] = content[0]['text']
        return '短期档即贪恐指数 21，数据来源见页面清单。'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('贪恐指数是多少？', AgentSession(session_id='n1', user_id=1))
    assert out['type'] == 'result'
    text = seen['narrative']
    assert '贪恐指数是多少' in text  # 用户本轮提问进了叙事 prompt
    assert '恐惧贪婪' in text  # 工具语义说明（短期档=贪恐指数）进了叙事 prompt
    assert '逐个覆盖' in text  # 覆盖子问题 + 缺数据要明说的硬要求


def test_multi_turn_intent_follows_latest_question(monkeypatch):
    """主验收（#1718）：第 1 轮问温度、第 2 轮问来源/频率/贪恐 → 不得再被执行收益工具。

    决策用**探针伪模型**：只要 prompt 里还残留编造的缺省 goal 就照旧选收益工具，
    否则按最新提问选温度工具——把「模型被 goal 牵引」这一机制变成确定性断言，
    修复失效（缺省 goal 冒头）时本用例立刻变红。
    """
    decision_prompts: list[str] = []

    def fake(content, system_prompt, **kwargs):
        if kwargs.get('response_format'):  # 决策轮
            text = content[0]['text']
            decision_prompts.append(text)
            tool = 'get_portfolio_performance' if '分析账户收益' in text else 'get_market_temperature'
            return json.dumps(
                {'action': 'execute_tool', 'tool_name': tool, 'tool_params': {}},
                ensure_ascii=False,
            )
        return '短期档即韭圈儿恐惧贪婪指数 21.0；数据最新 2026-09-24、距今 2 天未过期。'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    session = AgentSession(
        session_id='intent-1',
        user_id=1,
        goal=session_store.DEFAULT_GOAL,  # 生产口径：新建会话行都被写入该缺省值
    )
    r1 = agent_loop.run_agent('现在市场温度是多少？', session)
    r2 = agent_loop.run_agent('为什么数据没有更新？数据来源是什么？贪恐指数是多少？', session)
    assert r1['type'] == 'result'
    assert r2['type'] == 'result'
    assert len(decision_prompts) == 2
    # 第 2 轮决策 prompt 里既不得再冒出缺省 goal，也不得因此被拽去收益工具
    assert '分析账户收益' not in decision_prompts[1]
    assert 'get_portfolio_performance' not in str(r2.get('data') or '')


def test_unanswerable_question_clarifies(monkeypatch):
    """无匹配工具时必须 ask_clarification（不硬凑、不硬执行），且 prompt 带该条规则。"""
    seen: dict = {}

    def fake(content, system_prompt, **kwargs):
        if kwargs.get('response_format'):
            seen['prompt'] = content[0]['text']
            return '{"action":"ask_clarification","missing_params":[],"content":"当前暂不支持生成研究报告类请求。"}'
        raise AssertionError('澄清路径不应触发叙事调用')

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('帮我写一篇基金投资研究报告', AgentSession(session_id='n2', user_id=1))
    assert out['type'] == 'clarify'
    assert out['missing_params'] == []
    assert '不支持' in out['content']
    assert '没有工具能回答' in seen['prompt']
