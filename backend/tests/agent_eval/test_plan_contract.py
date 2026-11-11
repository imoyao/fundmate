# -*- coding: utf-8 -*-
"""expect.plan 多步断言契约单测（owner 裁定 D3，范式文档 §8 #5）。

能力先行：用合成 trace 证明 evaluate_plan 真会判红/判绿，不依赖 P&E 编排是否
落地，也不调用真实模型。chain-01 保持弱断言，等编排落地当天升级即可自动生效。
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPT = BACKEND_DIR / 'scripts' / 'agent_eval.py'


@pytest.fixture(scope='module')
def contract():
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location('agent_eval_plan_contract', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trace(tool, status='result', intent='execute_tool'):
    return SimpleNamespace(intent=intent, status=status, tool_name=tool)


def _plan(*tools):
    return [{'tool': t} for t in tools]


def _expect(plan, status='result'):
    return {'status': status, 'plan': plan}


def test_plan_shape_accepts_valid_steps(contract):
    assert contract.validate_plan_shape(_plan('a', 'b')) == []
    assert contract.validate_plan_shape([{'tool': ['a', 'b']}, {'tool': 'c', 'params_from': 0}]) == []


@pytest.mark.parametrize(
    'plan',
    [
        None,
        [],
        'not-a-list',
        [{'tool': ''}],
        [{'tool': None}],
        [{'tool': 'a', 'unknown': 1}],
        [{'tool': 'a', 'params_from': 0}],
        [{'tool': 'a'}, {'tool': 'b', 'params_from': 2}],
        [{'tool': 'a'}, {'tool': 'b', 'params_from': True}],
        ['not-a-step'],
    ],
)
def test_plan_shape_rejects_invalid(contract, plan):
    assert contract.validate_plan_shape(plan), f'非法 plan 未被拒绝：{plan}'


def test_evaluate_plan_passes_on_full_sequence(contract):
    traces = [_trace('get_portfolio_performance'), _trace('list_position_pnl')]
    ok, why = contract.evaluate_plan(
        traces,
        _expect(_plan('get_portfolio_performance', 'list_position_pnl')),
    )
    assert ok, why


def test_evaluate_plan_fails_when_only_one_tool_ran(contract):
    """当前运行时只跑一个工具 ⇒ 多步 plan 必 FAIL（chain-01 暂不升级的原因）。"""
    ok, why = contract.evaluate_plan([_trace('get_portfolio_performance')], _expect(_plan('a', 'b')))
    assert not ok and '只执行了 1 步' in why


def test_evaluate_plan_fails_on_wrong_order(contract):
    traces = [_trace('list_position_pnl'), _trace('get_portfolio_performance')]
    ok, why = contract.evaluate_plan(
        traces,
        _expect(_plan('get_portfolio_performance', 'list_position_pnl')),
    )
    assert not ok and '第 1 步' in why


def test_evaluate_plan_fails_on_wrong_status(contract):
    ok, why = contract.evaluate_plan([_trace('a')], _expect(_plan('a'), status='clarify'))
    assert not ok and '末轮 status' in why


def test_evaluate_plan_ignores_error_traces(contract):
    traces = [_trace('get_assets_overview', status='error'), _trace('get_portfolio_performance')]
    ok, why = contract.evaluate_plan(traces, _expect(_plan('get_portfolio_performance')))
    assert ok, why


def test_evaluate_plan_rejects_malformed_expectation(contract):
    ok, why = contract.evaluate_plan([_trace('a')], _expect([]))
    assert not ok and '结构非法' in why


def test_existing_single_tool_evaluate_unchanged(contract):
    """既有 47 条仍走原判定路径：这一步钉住 D3 没有改坏旧行为。"""
    ok, why = contract.evaluate(
        _trace('get_assets_overview'),
        {'status': 'result', 'tool': 'get_assets_overview'},
    )
    assert ok, why
    ok2, _ = contract.evaluate(
        _trace('get_assets_overview'),
        {'status': 'result', 'tool': 'list_position_pnl'},
    )
    assert not ok2
