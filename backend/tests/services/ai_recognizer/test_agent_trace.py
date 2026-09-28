# -*- coding: utf-8 -*-
"""S4 决策 trace（#1736）：每轮一行的红绿判据。

四类出口（result / clarify / error / blocked）+ 参数脱敏 + 旁路容错 + 跨轮序列——
trace 是 agent_eval 四指标与 agent_replay 时间轴的唯一数据源，
这些断言就是「可观测不回退」的回归位。不触网（call_llm 全 mock）。
"""

from app.domains.agent.models import AgentSession, AgentTrace
from app.services.ai_recognizer import agent_loop
from app.services.ai_recognizer import llm as llm_mod
from app.services.ai_recognizer.tools import ToolExecutor


def _attach(db, session_id):
    """会话行挂进 ORM 会话（HTTP 路径经 session_store 同样如此）——trace 才有处可落。"""
    sess = AgentSession(session_id=session_id, user_id=1)
    db.add(sess)
    db.flush()
    return sess


def _one(db, session_id):
    db.flush()
    return db.query(AgentTrace).filter_by(session_id=session_id).one()


def _fake_llm_ok(content, system_prompt, **kwargs):
    """成功路径假件：决策轮回 execute_tool，叙事轮回契约分块；每次回填 42 token。"""
    sink = kwargs.get('usage_sink')
    if sink is not None:
        sink['tokens'] = sink.get('tokens', 0) + 42
    if kwargs.get('response_format'):
        return '{"action":"execute_tool","tool_name":"get_assets_overview","tool_params":{}}'
    return '【结论】x。\n【明细】y。\n【风险提示】暂无。'


# ── 出口 1：result（execute_tool 正常完成） ──
def test_trace_result_turn(db, monkeypatch):
    monkeypatch.setattr(llm_mod, 'call_llm', _fake_llm_ok)
    sess = _attach(db, 'trace_ok')
    out = agent_loop.run_agent('分析我的收益', sess)
    assert out['type'] == 'result'

    trace = _one(db, 'trace_ok')
    assert trace.intent == 'execute_tool'
    assert trace.status == 'result'
    assert trace.tool_name == 'get_assets_overview'
    assert trace.blocked is False
    assert trace.guard_hits == []
    assert trace.turn == 1  # 正常轮：turn_count 自增后即本轮编号
    assert trace.tokens == 84  # 决策 + 叙事两次调用各 42（usage_sink 逐次累加）
    assert trace.latency_ms is not None and trace.latency_ms >= 0
    assert trace.tool_params == {}


# ── 出口 2：clarify（信息不足追问） ──
def test_trace_clarify_turn(db, monkeypatch):
    def fake(content, system_prompt, **kwargs):
        sink = kwargs.get('usage_sink')
        if sink is not None:
            sink['tokens'] = sink.get('tokens', 0) + 42
        return '{"action":"ask_clarification","missing_params":["period"],"content":"想分析多久？"}'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    sess = _attach(db, 'trace_clarify')
    out = agent_loop.run_agent('帮我分析一下', sess)
    assert out['type'] == 'clarify'

    trace = _one(db, 'trace_clarify')
    assert trace.intent == 'ask_clarification'
    assert trace.status == 'clarify'
    assert trace.tool_name is None  # 追问轮没有工具
    assert trace.blocked is False
    assert trace.tokens == 42  # 只有决策轮一次调用
    assert trace.turn == 1


# ── 出口 3：error（工具两次执行失败） ──
def test_trace_error_turn(db, monkeypatch):
    def fake_tool(*args, **kwargs):
        return {'status': 'error', 'msg': 'boom'}

    monkeypatch.setattr(ToolExecutor, 'run', fake_tool)
    monkeypatch.setattr(llm_mod, 'call_llm', _fake_llm_ok)
    sess = _attach(db, 'trace_err')
    out = agent_loop.run_agent('分析我的收益', sess)
    assert out['type'] == 'error'

    trace = _one(db, 'trace_err')
    assert trace.intent == 'execute_tool'
    assert trace.status == 'error'
    assert trace.tool_name == 'get_assets_overview'
    assert trace.blocked is False
    # 两次决策调用（首败 + 重试）各 42，无叙事轮
    assert trace.tokens == 84


# ── 出口 4：blocked（输入侧拦截，零模型调用） ──
def test_trace_blocked_input_turn(db, monkeypatch):
    def fail_llm(*args, **kwargs):
        raise AssertionError('拦截轮不得调模型')

    monkeypatch.setattr(llm_mod, 'call_llm', fail_llm)
    sess = _attach(db, 'trace_block')
    out = agent_loop.run_agent('温度会涨吗', sess)
    assert out['type'] == 'result' and out['data'] == {}

    trace = _one(db, 'trace_block')
    assert trace.blocked is True
    assert trace.status == 'blocked'
    assert trace.intent == 'blocked'
    assert trace.guard_hits  # 命中规则在列（归因依据）
    assert trace.turn == 0  # 拦截轮不计轮次（G4 口径）
    assert trace.tokens == 0
    assert trace.latency_ms is None  # 没有上游调用


# ── 跨轮序列：重放时间轴的基础（created_at 递增 + turn 递增） ──
def test_trace_multi_turn_sequence(db, monkeypatch):
    monkeypatch.setattr(llm_mod, 'call_llm', _fake_llm_ok)
    sess = _attach(db, 'trace_seq')
    agent_loop.run_agent('分析我的收益', sess)
    agent_loop.run_agent('再看看持仓成本', sess)  # 不同问法，不触发重复追问闸

    db.flush()
    rows = db.query(AgentTrace).filter_by(session_id='trace_seq').order_by(AgentTrace.turn).all()
    assert [r.turn for r in rows] == [1, 2]
    assert all(r.status == 'result' for r in rows)
    assert all(r.created_at is not None for r in rows)


# ── 参数脱敏：敏感键置 *、字符串截断、标量原样 ──
def test_redact_params():
    long_str = '90d' * 100
    out = agent_loop._redact_params(
        {
            'fund_code': '000001',
            'password': 'p@ss',
            'api_key': 'sk-xyz',
            'period': long_str,
            'days': 30,
            'flag': True,
            'x': None,
            'lst': [1, 2],
        }
    )
    assert out['password'] == '***'
    assert out['api_key'] == '***'
    assert out['fund_code'] == '000001'  # 普通业务参数原样保留
    assert len(out['period']) == agent_loop._PARAM_VALUE_CAP
    assert out['days'] == 30 and out['flag'] is True and out['x'] is None
    assert out['lst'] == '[1, 2]'  # 非标量转字符串并截断
    assert agent_loop._redact_params(None) == {}
    assert agent_loop._redact_params({}) == {}


# ── 旁路容错：trace 写失败绝不打断对话（可观测不能成为新故障点） ──
def test_trace_write_failure_is_sideline(db, monkeypatch):
    monkeypatch.setattr(llm_mod, 'call_llm', _fake_llm_ok)

    def boom(obj):
        raise RuntimeError('trace 挂了')

    monkeypatch.setattr(agent_loop, 'object_session', boom)
    sess = _attach(db, 'trace_sideline')
    out = agent_loop.run_agent('分析我的收益', sess)
    assert out['type'] == 'result'  # 对话照常返回
    db.flush()
    assert db.query(AgentTrace).filter_by(session_id='trace_sideline').count() == 0
