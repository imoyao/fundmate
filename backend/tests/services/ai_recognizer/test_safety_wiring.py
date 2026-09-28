# -*- coding: utf-8 -*-
"""S3 护栏接线测试（agent_loop.run_agent 的三处接入点）。

纯函数测试证明「规则本身对」；本文件证明「规则被接在正确的位置」：
① 输入侧拦截在**轮次闸之前**（不消耗用户轮次、零模型调用）；
② 重复追问达阈同样零模型调用；
③ 输出侧对追问与叙事都生效，情绪复合则加风险提示前缀。

不触网：`llm.call_llm` 一律 monkeypatch。
"""

from app.domains.agent.models import AgentSession
from app.services.ai_recognizer import agent_loop, guards, safety
from app.services.ai_recognizer import llm as llm_mod
from app.services.ai_recognizer.safety import repeat_tracker

CLARIFY = '{"action":"ask_clarification","missing_params":["period"],"content":"想看多久的走势？"}'
EXECUTE = '{"action":"execute_tool","tool_name":"get_assets_overview","tool_params":{}}'


def _fake_llm(monkeypatch, narrative='你的净资产是 0 元。'):
    """装一个可计数的假模型：记录调用次数与最后叙事文本。"""
    calls = {'n': 0}

    def fake(content, system_prompt, **kwargs):
        calls['n'] += 1
        if kwargs.get('response_format'):
            return EXECUTE
        return narrative

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    return calls


def test_prediction_input_blocked_without_model_call(monkeypatch):
    """输入侧拦截必须发生在模型之前：零调用、零轮次消耗、标准话术可回放。"""
    calls = _fake_llm(monkeypatch)
    session = AgentSession(session_id='guard-block-1', user_id=1, turn_count=0)
    out = agent_loop.run_agent('白酒基金下周会涨吗', session)

    assert out['type'] == 'result'
    assert calls['n'] == 0, '越界提问不该进模型'
    assert '预测' in out['content'] or '无法' in out['content']
    assert session.turn_count == 0, '拦截回合不消耗分析轮次预算'
    assert out['data'] == {}  # 无指标 chips（防前端渲染假数据）
    # 原文照常落库：历史会话回放（#1719）必须看得到这段问答
    assert session.messages[-1]['user'] == '白酒基金下周会涨吗'
    assert session.messages[-1]['assistant'] == out['content']


def test_advice_input_blocked_with_data_exit(monkeypatch):
    calls = _fake_llm(monkeypatch)
    out = agent_loop.run_agent('我该不该现在卖出', AgentSession(session_id='guard-block-2', user_id=1))
    assert calls['n'] == 0
    assert out['type'] == 'result'
    assert '查' in out['content']  # 给安全出口，而非干瘪拒绝


def test_repeat_threshold_returns_standard_reply(monkeypatch):
    """同一问法连续 N 次 → 强制标准话术，不让模型在反复追问下松口。"""
    calls = _fake_llm(monkeypatch)
    session = AgentSession(session_id='guard-repeat-1', user_id=1)
    repeat_tracker.reset(session.session_id)
    # 前两次正常走模型（假模型返回叙事），第三次达阈 → 标准话术且不再调模型
    agent_loop.run_agent('看我的收益', session)
    agent_loop.run_agent('看我的收益?', session)  # 换标点仍是同一问
    calls_before = calls['n']  # 前两问的模型调用数
    agent_loop.run_agent('看我的收益', session)

    assert repeat_tracker.count(session.session_id) == 3
    assert calls['n'] == calls_before, '达阈那一问不该再调模型'
    assert session.messages[-1]['assistant'] != '你的净资产是 0 元。'


def test_different_question_does_not_trigger_repeat(monkeypatch):
    calls = _fake_llm(monkeypatch)
    session = AgentSession(session_id='guard-repeat-2', user_id=1)
    repeat_tracker.reset(session.session_id)
    for i in range(4):
        agent_loop.run_agent(f'看第{i}个问题', session)
    assert repeat_tracker.count(session.session_id) == 1  # 换问法即重数
    assert calls['n'] > 0  # 正常走模型


def test_emotion_composite_prefixes_risk_notice(monkeypatch):
    """D 情绪 + 建议复合：不拦，但回复必须带风险提示（防顺情绪给安慰式建议）。"""
    _fake_llm(monkeypatch, narrative='你的净资产是 0 元。')
    session = AgentSession(session_id='guard-emotion-1', user_id=1)
    out = agent_loop.run_agent('亏惨了怎么办', session)
    assert out['type'] == 'result'
    assert out['content'].startswith(safety.RISK_NOTICE)


def test_narrative_filtered_on_output_side(monkeypatch):
    """输出侧兜底：模型即使吐出越界建议，返回用户前也会被替换。"""
    _fake_llm(monkeypatch, narrative='你的净资产是 0 元。建议你现在卖出。')
    out = agent_loop.run_agent('看我的收益', AgentSession(session_id='guard-out-1', user_id=1))
    assert out['type'] == 'result'
    assert '建议你现在卖出' not in out['content'], '越界句必须被替换'
    assert '你的净资产是 0 元。' in out['content'], '合规内容保留（不整篇拒答）'


def test_clarify_filtered_on_output_side(monkeypatch):
    """追问路径同样过输出侧（且 used_tools=False 启用 E1）。"""

    def fake(content, system_prompt, **kwargs):
        return CLARIFY.replace('想看多久的走势？', '我建议你现在就清仓，你先说要多久的走势？')

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('看我的收益', AgentSession(session_id='guard-out-2', user_id=1))
    assert out['type'] == 'clarify'
    assert '我建议你现在就清仓' not in out['content']


def test_normal_data_query_unaffected(monkeypatch):
    """回归护栏：正常数据查询不得被误拦（误伤会直接逼死产品）。"""
    calls = _fake_llm(monkeypatch)
    for text, sid in (
        ('分析我的收益', 'guard-normal-1'),
        ('现在市场温度是多少', 'guard-normal-2'),
        ('近一年涨跌幅是多少', 'guard-normal-3'),
        ('帮我看下近30天的收益', 'guard-normal-4'),
    ):
        out = agent_loop.run_agent(text, AgentSession(session_id=sid, user_id=1))
        assert out['type'] == 'result', f'正常查询被误拦：{text}'
        assert calls['n'] > 0
    assert out['content'].startswith(safety.RISK_NOTICE) is False


def test_blocked_turn_does_not_consume_turn_budget(monkeypatch):
    """连续 10 次越界提问不应触发 G4 轮次闸（拦截不花钱就不占预算）。"""
    calls = _fake_llm(monkeypatch)
    session = AgentSession(session_id='guard-budget-1', user_id=1, turn_count=guards.get_agent_max_turns() - 1)
    for _ in range(10):
        out = agent_loop.run_agent('会涨吗', session)
        assert out['type'] == 'result'
    assert session.turn_count == guards.get_agent_max_turns() - 1
    assert calls['n'] == 0


# ── G6 意图路由（#1742）：A 分类驱动的二级拦截 ─────────────────────────


def test_prediction_cue_broader_than_b_rules_blocked_by_route(monkeypatch):
    """B 窄规则未命中的预测句式由意图路由接住：不进模型、不占轮次、标准话术可回放。

    「大盘走势会如何」——B1 的「会涨吗 / 你觉得…涨跌」都匹配不上，但 classify
    归为 prediction；G6 之前它会照常进查询工具链（违反「预测/建议类不进入查询链路」）。
    """
    calls = _fake_llm(monkeypatch)
    session = AgentSession(session_id='route-pred-1', user_id=1, turn_count=0)
    out = agent_loop.run_agent('大盘走势会如何', session)

    assert out['type'] == 'result'
    assert calls['n'] == 0, '预测类不该进入查询链路'
    assert session.turn_count == 0, '路由拦截同样不消耗轮次预算'
    assert '无法预测涨跌' in out['content']  # REPLY_PREDICTION
    assert session.messages[-1]['assistant'] == out['content']
    assert out['data'] == {}


def test_advice_cue_broader_than_b_rules_blocked_by_route(monkeypatch):
    """「基金亏了怎么办」：B2/B3 的对象型句式匹配不上，classify 归为 advice → 路由拦截。"""
    calls = _fake_llm(monkeypatch)
    session = AgentSession(session_id='route-advice-1', user_id=1)
    out = agent_loop.run_agent('基金亏了怎么办', session)

    assert calls['n'] == 0, '建议类不该进入查询链路'
    assert out['type'] == 'result'
    assert '不能替你做决定' in out['content']  # REPLY_ADVICE，且带数据出口


def test_route_without_reply_falls_back_to_tool_chain(monkeypatch):
    """防御分支：类别被路由到「拦截」却缺话术 → 不回空白，回退工具链。"""
    from app.services.ai_recognizer import registry
    from app.services.ai_recognizer.safety.intent_guard import CATEGORY_KNOWLEDGE

    calls = _fake_llm(monkeypatch)
    # 通用知识类没有标准话术，把它临时改道为拦截，正好触发缺话术防御
    registry.register_intent_route(CATEGORY_KNOWLEDGE, registry.ROUTE_STANDARD_REPLY)
    try:
        out = agent_loop.run_agent('什么是市盈率', AgentSession(session_id='route-fallback-1', user_id=1))
    finally:
        registry.register_intent_route(CATEGORY_KNOWLEDGE, registry.ROUTE_TOOL_CHAIN)  # 还原

    assert calls['n'] > 0, '缺话术时不该拦截，应回退工具链'
    assert out['content'], '任何路径都不允许返回空白回复'
