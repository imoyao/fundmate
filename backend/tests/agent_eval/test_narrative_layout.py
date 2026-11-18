# -*- coding: utf-8 -*-
"""结构判据（D106）：多子问回答必须分段，否则数字归属判据会静默失效。

判据失效最糟的形态不是判错，而是**静默通过**：整篇一行时每个数字的归属集合都等于
「全部要点」，各问的数值池完全一致，归属判据退化成全文比对——闸门看起来在、实际
不设防。这组用例钉住三件事：
1. 该拦的拦：≥2 个要点要区分数值却全挤在一行；
2. 不该拦的不拦：单一要点、还没覆盖全、正常分段；
3. 真接进了 run_case（写好了不接线 = 登记了从不跑，比没有更糟）。

不调真实模型，也不依赖 cases.yaml 的具体数值。
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPT = BACKEND_DIR / 'scripts' / 'agent_eval.py'

# 与 chain-01 同形：四问里三问要报数（三处 metric 才构成「哪个数配哪一问」的歧义）
COVERS = [
    {'id': '区间收益', 'any': ['近3个月收益'], 'metric': {'tool': 'get_portfolio_vs_benchmark', 'field': 'range_rate'}},
    {
        'id': '亏得最多',
        'any': ['亏得最多'],
        'metric': {'tool': 'list_position_pnl', 'field': 'items.*.pnl', 'pick': 'min'},
    },
    {'id': '调仓参考', 'any': ['调仓']},
    {'id': '跟上市场', 'any': ['跑输'], 'metric': {'tool': 'get_portfolio_vs_benchmark', 'field': 'excess_return'}},
]
ONELINE = '近3个月收益 -19.44%，亏得最多 -8387.89 元，调仓暂无信号，跑输 6.33 个点。'
SECTIONED = (
    '**近3个月收益**：-19.44%\n\n**亏得最多**：某只持仓 -8387.89 元\n\n**调仓**：暂无信号\n\n**跑输**：6.33 个百分点'
)


@pytest.fixture(scope='module')
def contract():
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location('agent_eval_narrative_layout', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ── 一、该拦的拦 ──────────────────────────────────────────────────


def test_single_line_reply_is_rejected(contract):
    """整篇一行：判据无从归属，必须红灯并说清「为什么判不了」。"""
    ok, why = contract.evaluate_layout(ONELINE, COVERS)
    assert not ok
    assert '未分段' in why and '全文比对' in why, why
    assert '第 1 行' in why, why


def test_anchors_crammed_into_one_line_of_many_is_rejected(contract):
    """多行但要点全挤在同一行，等同于整篇一行——后段数字仍会被误归。"""
    text = f'\n{ONELINE}\n以上是本月情况。\n'
    ok, why = contract.evaluate_layout(text, COVERS)
    assert not ok and '未分段' in why, why


# ── 二、不该拦的不拦 ──────────────────────────────────────────────


def test_sectioned_reply_passes(contract):
    assert contract.evaluate_layout(SECTIONED, COVERS) == (True, '')


def test_two_questions_sharing_a_line_is_allowed(contract):
    """一行里并列两个要点是可接受的：归属退到这一行，仍能挡住「串台到别段」。"""
    text = '近3个月收益 -19.44%，亏得最多 -8387.89 元。\n\n调仓暂无信号。\n\n跑输 6.33 个百分点。'
    assert contract.evaluate_layout(text, COVERS) == (True, '')


def test_single_metric_cover_skips_structure(contract):
    """只有一个要点要报数时没有归属歧义，单行回答合理，不拦。"""
    covers = [{'id': '净资产', 'any': ['净资产'], 'metric': {'tool': 'get_assets_overview', 'field': 'net_assets_cny'}}]
    assert contract.evaluate_layout('你的净资产 1630204.52 元。', covers) == (True, '')


def test_no_metric_cover_skips_structure(contract):
    """一个数都不用报的用例，结构要求无从谈起。"""
    covers = [{'id': 'a', 'any': ['近3个月收益']}, {'id': 'b', 'any': ['跑输']}]
    assert contract.evaluate_layout(ONELINE, covers) == (True, '')


def test_missing_anchor_defers_to_coverage(contract):
    """锚点缺失是覆盖判据的活：这里不重复判红，否则同一条回答报两次错。"""
    ok, why = contract.evaluate_layout('近3个月收益 -19.44%。', COVERS)
    assert ok, why


def test_empty_reply_is_rejected(contract):
    ok, why = contract.evaluate_layout('   ', COVERS)
    assert not ok and '文本为空' in why, why


# ── 三、接线证据 ──────────────────────────────────────────────────


class _FakeQuery:
    def __init__(self, traces):
        self._traces = traces

    def filter_by(self, **_kwargs):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return list(self._traces)


class _FakeDB:
    def __init__(self, traces):
        self._traces = traces

    def query(self, *_args):
        return _FakeQuery(self._traces)

    def flush(self):
        return None

    def rollback(self):
        return None


def _wire(monkeypatch, contract, reply, data):
    monkeypatch.setattr(
        contract.session_store,
        'load_or_create',
        lambda db, session_id, user_id: SimpleNamespace(session_id='s-layout'),
    )
    monkeypatch.setattr(
        contract.agent_loop,
        'run_agent',
        lambda text, row: {'type': 'result', 'content': reply, 'data': data},
    )
    trace = SimpleNamespace(intent='execute_tool', status='result', tool_name='tool_a', blocked=False, tokens=10)
    return _FakeDB([trace])


DATA = {
    'steps': [
        {
            'tool': 'get_portfolio_vs_benchmark',
            'data': {'range_rate': -19.44, 'excess_return': -6.33, 'benchmark_range_return': -13.11},
        },
        {'tool': 'list_position_pnl', 'data': {'items': [{'name': 'A', 'pnl': -8387.89}], 'count': 1}},
    ]
}


def _case(reply, numbers=True):
    return {
        'id': 'synth-layout',
        'turns': ['q'],
        'expect': {'status': 'result', 'tool': 'tool_a', 'narrative': {'covers': COVERS, 'numbers': numbers}},
    }


def test_run_case_wires_layout(monkeypatch, contract):
    """接线证据：同一条「数都对」的回答，一行判红、分段通过。"""
    db = _wire(monkeypatch, contract, ONELINE, DATA)
    result = contract.run_case(db, _case(ONELINE))
    assert not result['ok'] and '未分段' in result['why'], result

    db = _wire(monkeypatch, contract, SECTIONED, DATA)
    result = contract.run_case(db, _case(SECTIONED))
    assert result['ok'], result


def test_layout_runs_before_metric(monkeypatch, contract):
    """顺序有意义：归属判不了时先说「结构」而不是「没引用」，否则诊断指向错的地方。

    这条回答里四个数都在、都对，只是全写在一行；metric 判据会**通过**（退回全文），
    真正该报的是结构问题。
    """
    db = _wire(monkeypatch, contract, ONELINE, DATA)
    result = contract.run_case(db, _case(ONELINE))
    assert '未分段' in result['why'], result
    assert '未引用' not in result['why'], result
