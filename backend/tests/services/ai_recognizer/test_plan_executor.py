# -*- coding: utf-8 -*-
"""P&E 最小编排单测（owner 裁定 D101）。

四条判据：
1. 无 plan 时逐键等价改造前的单工具路径（既有 47 条评估用例行为不变）；
2. 有 plan 时按序执行，参数引用占位由代码侧换成真实数值，决策轮模型看不到；
3. 非法 plan（未知工具 / 超步数 / 前向引用 / 路径不存在 / 中途失败）显式报错，
   不静默退化成「只答第一问」；
4. 每步落一条成功 execute_tool trace，序列能被 D3 的 evaluate_plan 判绿。
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.ai_recognizer import agent_loop, plan_executor
from app.services.ai_recognizer.tools import TOOLS_METADATA

BACKEND_DIR = Path(__file__).resolve().parents[3]  # backend/tests/services/ai_recognizer/
_EVAL_SCRIPT = BACKEND_DIR / 'scripts' / 'agent_eval.py'

T1, T2, T3 = 'list_position_pnl', 'get_fund_nav', 'get_portfolio_performance'


def _tool_exists(name):
    return any(m['name'] == name for m in TOOLS_METADATA)


@pytest.fixture(scope='module')
def eval_module():
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location('agent_eval_for_plan_executor', _EVAL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _out(data=None, status='success'):
    return {'status': status, 'data': data if data is not None else {'v': 1}}


def _collect_writer():
    rows = []

    def writer(session, **kwargs):
        rows.append(SimpleNamespace(**kwargs))

    return rows, writer


# ── 判据 1：单工具路径逐键等价 ────────────────────────────────────────────
def test_single_tool_returns_runner_result_unchanged():
    calls = []

    def runner(name, params, server_ctx=None):
        calls.append((name, params, server_ctx))
        return _out({'items': [{'symbol': 'A'}]})

    action = {'action': 'execute_tool', 'tool_name': T1, 'tool_params': {'days': 30}}
    result = plan_executor.execute(action, {'family_id': 1, 'days': 30}, {'family_id': 9}, runner)
    assert result == _out({'items': [{'symbol': 'A'}]})
    assert calls == [(T1, {'family_id': 1, 'days': 30}, {'family_id': 9})]
    assert '_plan' not in result, '单工具路径不得附加任何内部键'


def test_single_tool_prompt_helpers_are_byte_identical_to_before():
    result = _out({'v': 1})
    desc = next(m['description'] for m in TOOLS_METADATA if m['name'] == T1)
    assert plan_executor.describe(result, T1) == desc
    assert plan_executor.source_line(result, T1, '{"v": 1}') == (f'基于以下分析数据（来自工具 {T1}）：{{"v": 1}}\n')


def test_single_tool_writes_exactly_one_trace_with_same_args():
    rows, writer = _collect_writer()
    plan_executor.write_traces(
        writer,
        object(),
        _out(),
        tool_name=T1,
        tool_params={'days': 30},
        latency_ms=12,
        tokens=34,
        guard_hits=['r1'],
    )
    assert len(rows) == 1
    r = rows[0]
    assert (r.intent, r.status, r.tool_name) == ('execute_tool', 'result', T1)
    assert r.tool_params == {'days': 30}
    assert (r.latency_ms, r.tokens, r.guard_hits) == (12, 34, ['r1'])


def test_decision_system_prompt_exposes_plan_instruction():
    sys_prompt = agent_loop._decision_system_prompt()
    assert 'plan' in sys_prompt and '$from_step' in sys_prompt
    assert '不要凭空猜测任何数值' in sys_prompt


# ── 判据 2：多步执行与代码侧参数注入 ──────────────────────────────────────
def _two_step_plan():
    return [
        {'tool': T1, 'tool_params': {}},
        {
            'tool': T2,
            'tool_params': {'symbol': {'$from_step': 0, 'path': 'items.0.symbol'}},
            'params_from': 0,
        },
    ]


def test_plan_runs_steps_in_order_and_injects_real_value():
    assert _tool_exists(T1) and _tool_exists(T2)
    seen = []

    def runner(name, params, server_ctx=None):
        seen.append((name, dict(params)))
        if name == T1:
            return _out({'items': [{'symbol': '000001', 'pnl': -12.5}]})
        return _out({'nav': 1.23, 'symbol': params.get('symbol')})

    result = plan_executor.execute({'action': 'execute_tool', 'plan': _two_step_plan()}, {}, None, runner)
    assert result['status'] == 'success'
    assert [name for name, _ in seen] == [T1, T2]
    assert seen[1][1]['symbol'] == '000001', '引用占位没有被上一步真实数值替换'
    assert [s['tool'] for s in result['data']['steps']] == [T1, T2]


def test_injected_value_never_lands_in_trace_params():
    def runner(name, params, server_ctx=None):
        if name == T1:
            return _out({'items': [{'symbol': 'SECRET-VALUE'}]})
        return _out({'ok': True})

    result = plan_executor.execute({'action': 'execute_tool', 'plan': _two_step_plan()}, {}, None, runner)
    rows, writer = _collect_writer()
    plan_executor.write_traces(
        writer,
        object(),
        result,
        tool_name=T1,
        tool_params={},
        latency_ms=1,
        tokens=2,
        guard_hits=[],
    )
    serialized = json.dumps([r.tool_params for r in rows], ensure_ascii=False)
    assert 'SECRET-VALUE' not in serialized, '注入值不得写进 trace（只留模型给的结构占位）'


def test_first_step_keeps_collected_params_but_later_steps_do_not():
    seen = []

    def runner(name, params, server_ctx=None):
        seen.append((name, dict(params)))
        return _out({'items': [{'symbol': 'A'}]})

    plan_executor.execute({'action': 'execute_tool', 'plan': _two_step_plan()}, {'days': 90}, None, runner)
    assert seen[0][1].get('days') == 90, '首步应沿用 collected_params（既有工作内存语义）'
    assert 'days' not in seen[1][1], '后续步只认模型给的结构，不继承首步工作参数'


def test_multi_step_prompt_helpers_cover_every_step():
    result = {
        'status': 'success',
        '_plan': {'tools': [T1, T2], 'trace_steps': [{'tool': T1, 'params': {}}, {'tool': T2, 'params': {}}]},
    }
    assert T1 in plan_executor.describe(result, T1) and T2 in plan_executor.describe(result, T1)
    line = plan_executor.source_line(result, T1, '{}')
    assert 'steps 数组按执行顺序' in line and '不要遗漏任何一步' in line


# ── 判据 3：非法 plan 显式报错，不静默丢子问 ──────────────────────────────
@pytest.mark.parametrize(
    'plan, needle',
    [
        ([{'tool': 'not_a_real_tool'}], '白名单'),
        ([{'tool': T1}, {'tool': T2}, {'tool': T3}, {'tool': T1}, {'tool': T2}], '最多'),
        ([{'tool': T1}, {'tool': T2, 'params_from': 1}], 'params_from'),
        ([{'tool': T1}, {'tool': T2, 'tool_params': []}], 'tool_params'),
        ('not-a-list', '必须是数组'),
    ],
)
def test_invalid_plan_is_rejected_before_any_tool_runs(plan, needle):
    called = []

    def runner(name, params, server_ctx=None):
        called.append(name)
        return _out()

    result = plan_executor.execute({'action': 'execute_tool', 'plan': plan}, {}, None, runner)
    assert result['status'] == 'error' and needle in result['msg']
    assert not called, '非法 plan 不得先跑一半工具'


def test_forward_ref_in_params_is_rejected():
    def runner(name, params, server_ctx=None):
        return _out({'items': [{'symbol': 'A'}]})

    plan = [{'tool': T1}, {'tool': T2, 'tool_params': {'symbol': {'$from_step': 1, 'path': 'x'}}}]
    result = plan_executor.execute({'action': 'execute_tool', 'plan': plan}, {}, None, runner)
    assert result['status'] == 'error' and '引用步骤越界' in result['msg']


def test_missing_ref_path_is_reported_not_silently_none():
    def runner(name, params, server_ctx=None):
        return _out({'items': [{'symbol': 'A'}]})

    plan = [{'tool': T1}, {'tool': T2, 'tool_params': {'symbol': {'$from_step': 0, 'path': 'rows.9.x'}}}]
    result = plan_executor.execute({'action': 'execute_tool', 'plan': plan}, {}, None, runner)
    assert result['status'] == 'error' and '路径不可解析' in result['msg']


def test_step_failure_aborts_plan_with_step_number():
    seen = []

    def runner(name, params, server_ctx=None):
        seen.append(name)
        if name == T1:
            return _out({'items': [{'symbol': 'A'}]})
        return {'status': 'error', 'msg': '上游超时'}

    result = plan_executor.execute({'action': 'execute_tool', 'plan': _two_step_plan()}, {}, None, runner)
    assert result['status'] == 'error' and '第 2 步' in result['msg'] and '上游超时' in result['msg']
    assert seen == [T1, T2]


def test_empty_plan_falls_back_to_single_tool():
    def runner(name, params, server_ctx=None):
        return _out({'ok': True})

    result = plan_executor.execute({'action': 'execute_tool', 'plan': [], 'tool_name': T1}, {}, None, runner)
    assert result == _out({'ok': True})


# ── 判据 4：每步一条 trace，序列能被 D3 evaluate_plan 判绿 ────────────────
def test_traces_form_a_sequence_evaluate_plan_accepts(eval_module):
    def runner(name, params, server_ctx=None):
        return _out({'items': [{'symbol': 'A'}]})

    result = plan_executor.execute({'action': 'execute_tool', 'plan': _two_step_plan()}, {}, None, runner)
    rows, writer = _collect_writer()
    plan_executor.write_traces(
        writer,
        object(),
        result,
        tool_name=T1,
        tool_params={},
        latency_ms=99,
        tokens=7,
        guard_hits=[],
    )
    assert len(rows) == 2
    assert [r.tool_name for r in rows] == [T1, T2]
    assert all(r.intent == 'execute_tool' and r.status == 'result' for r in rows)
    assert rows[0].tokens == 0 and rows[0].latency_ms is None, '统计只记最后一条，不重复计数'
    assert rows[-1].tokens == 7 and rows[-1].latency_ms == 99

    expect = {'status': 'result', 'plan': [{'tool': T1}, {'tool': T2, 'params_from': 0}]}
    ok, why = eval_module.evaluate_plan(rows, expect)
    assert ok, why
    ok2, why2 = eval_module.evaluate_plan(rows, {'status': 'result', 'plan': [{'tool': T2}, {'tool': T1}]})
    assert not ok2, '错序仍须判红，否则序列断言是恒真的'


# ── 集成：run_agent 走 plan，叙事吃全部步骤数据 ───────────────────────────
def test_run_agent_plan_path_feeds_all_steps_into_narrative(monkeypatch):
    from app.domains.agent.models import AgentSession
    from app.services.ai_recognizer import llm as llm_mod

    prompts = {'system': '', 'narrative': ''}
    seen = []

    def fake_llm(content, system_prompt, **kwargs):
        if kwargs.get('response_format'):
            prompts['system'] = system_prompt
            return json.dumps({'action': 'execute_tool', 'plan': _two_step_plan()}, ensure_ascii=False)
        prompts['narrative'] = content[0]['text']
        return '【结论】两只标的已核对。\n【明细】逐条说明。\n【风险提示】暂无。'

    def fake_run(name, params, server_ctx=None):
        seen.append((name, dict(params)))
        if name == T1:
            return {'status': 'success', 'data': {'items': [{'symbol': '000001', 'pnl': -12.5}]}}
        return {'status': 'success', 'data': {'nav': 1.23, 'symbol': params.get('symbol')}}

    traces = []

    def fake_trace(session, **kwargs):
        traces.append(SimpleNamespace(**kwargs))

    monkeypatch.setattr(llm_mod, 'call_llm', fake_llm)
    monkeypatch.setattr(agent_loop.ToolExecutor, 'run', staticmethod(fake_run))
    monkeypatch.setattr(agent_loop, '_write_trace', fake_trace)

    out = agent_loop.run_agent('近 3 个月收益如何？亏最多的那个净值呢？', AgentSession(session_id='pe1', user_id=1))

    assert out['type'] == 'result'
    assert [name for name, _ in seen] == [T1, T2]
    assert seen[1][1]['symbol'] == '000001'
    assert 'plan' in prompts['system'] and '$from_step' in prompts['system']
    assert 'steps 数组按执行顺序' in prompts['narrative']
    assert '000001' in prompts['narrative'] and '1.23' in prompts['narrative']
    assert [t.tool_name for t in traces] == [T1, T2]
    assert len(out['data']['steps']) == 2
