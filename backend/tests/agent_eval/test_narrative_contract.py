# -*- coding: utf-8 -*-
"""expect.narrative 子问覆盖判据契约单测（D1「用户可感知改善」验收闭环）。

用合成回答文本证明判据真会判红/判绿，并**单独钉住 run_case 接线**：
判据写好却没接进跑批，等于「登记了从不跑」——那比没有判据更糟。
不调用真实模型，也不依赖 cases.yaml 里具体用了哪些锚点。
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPT = BACKEND_DIR / 'scripts' / 'agent_eval.py'

COVERS = [
    {'id': '近3个月收益', 'any': ['近3个月', '近三个月', '三个月', '区间收益']},
    {'id': '亏得最多的标的', 'any': ['亏得最多', '浮亏最大', '亏损最大']},
    {'id': '调仓参考', 'any': ['再平衡', '调仓', '权重']},
    {'id': '是否跟上市场', 'any': ['基准', '跑输', '跑赢', '超额', '归因']},
]
FULL_TEXT = '【结论】近3个月组合收益回落，亏得最多的是一只场内基金。\n【明细】再平衡参考显示权重偏高，相对基准跑输。'
MISSING_LAST_TEXT = '【结论】近3个月组合收益回落，亏得最多的是一只场内基金。\n【明细】再平衡参考显示权重偏高。'


@pytest.fixture(scope='module')
def contract():
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location('agent_eval_narrative_contract', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _expect(narrative=True):
    expect = {'status': 'result', 'tool': 'tool_a'}
    if narrative:
        expect['narrative'] = {'covers': COVERS}
    return expect


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


def _trace(tool='tool_a', status='result'):
    return SimpleNamespace(intent='execute_tool', status=status, tool_name=tool, blocked=False, tokens=10)


def _wire(monkeypatch, contract, reply):
    """把 run_case 的两个外部依赖换成合成实现，返回 (db, case)。"""
    monkeypatch.setattr(
        contract.session_store,
        'load_or_create',
        lambda db, session_id, user_id: SimpleNamespace(session_id='s-eval'),
    )
    monkeypatch.setattr(contract.agent_loop, 'run_agent', lambda text, row: {'type': 'result', 'content': reply})
    return _FakeDB([_trace()]), {'id': 'synth-01', 'turns': ['四连问'], 'expect': _expect()}


def test_narrative_shape_accepts_valid(contract):
    assert contract.validate_narrative_shape({'covers': COVERS}) == []


@pytest.mark.parametrize(
    'bad',
    [
        None,
        [],
        'covers',
        {},
        {'covers': []},
        {'covers': COVERS, 'extra': 1},
        {'covers': [{'id': 'a'}]},
        {'covers': [{'id': 'a', 'any': []}]},
        {'covers': [{'id': 'a', 'any': ['x', '']}]},
        {'covers': [{'id': '', 'any': ['x']}]},
        {'covers': [{'id': 'a', 'any': ['x'], 'extra': 1}]},
        {'covers': ['not-a-dict']},
    ],
)
def test_narrative_shape_rejects_invalid(contract, bad):
    assert contract.validate_narrative_shape(bad), f'非法结构未判红：{bad!r}'


def test_evaluate_narrative_passes_full_coverage(contract):
    assert contract.evaluate_narrative(FULL_TEXT, _expect()) == (True, '')


def test_evaluate_narrative_fails_and_names_missing_subquestion(contract):
    ok, why = contract.evaluate_narrative(MISSING_LAST_TEXT, _expect())
    assert not ok
    assert '是否跟上市场' in why, why
    assert '近3个月收益' not in why, why


@pytest.mark.parametrize('text', ['', '   ', None, 123, {}])
def test_evaluate_narrative_rejects_empty_or_non_text(contract, text):
    ok, why = contract.evaluate_narrative(text, _expect())
    assert not ok, why
    assert '文本为空' in why, why


def test_evaluate_narrative_is_case_insensitive(contract):
    expect = {'narrative': {'covers': [{'id': '英文锚点', 'any': ['Alpha', 'Beta']}]}}
    assert contract.evaluate_narrative('含有 alpha 与 BETA', expect) == (True, '')
    assert not contract.evaluate_narrative('什么都没有', expect)[0]


def test_evaluate_narrative_rejects_broken_spec(contract):
    ok, why = contract.evaluate_narrative(FULL_TEXT, {'narrative': {'covers': []}})
    assert not ok
    assert '结构非法' in why, why


def test_run_case_wires_narrative_check(monkeypatch, contract):
    """回答覆盖四子问 → PASS；这是接线存在的正向证据。"""
    db, case = _wire(monkeypatch, contract, FULL_TEXT)
    result = contract.run_case(db, case)
    assert result['ok'], result['why']


def test_run_case_fails_when_reply_drops_subquestion(monkeypatch, contract):
    """回答丢掉一个子问 → FAIL，且 why 点名子问（不是恒真摆设）。"""
    db, case = _wire(monkeypatch, contract, MISSING_LAST_TEXT)
    result = contract.run_case(db, case)
    assert not result['ok'], result
    assert '是否跟上市场' in result['why'], result['why']


def test_run_case_fails_when_no_reply_captured(monkeypatch, contract):
    """run_agent 没返回 content 时判红，而不是静默放过。"""
    db, case = _wire(monkeypatch, contract, '')
    result = contract.run_case(db, case)
    assert not result['ok'], result
    assert '文本为空' in result['why'], result['why']


def test_run_case_without_narrative_keeps_old_behavior(monkeypatch, contract):
    """既有 47 条无 narrative 字段：连空回答也不该被新判据误伤。"""
    monkeypatch.setattr(
        contract.session_store,
        'load_or_create',
        lambda db, session_id, user_id: SimpleNamespace(session_id='s-eval'),
    )
    monkeypatch.setattr(contract.agent_loop, 'run_agent', lambda text, row: {'type': 'result', 'content': ''})
    case = {'id': 'legacy-01', 'turns': ['单问'], 'expect': _expect(narrative=False)}
    result = contract.run_case(_FakeDB([_trace()]), case)
    assert result['ok'], result['why']


def test_run_case_does_not_mask_earlier_failure(monkeypatch, contract):
    """status 不符时 why 保持原失败原因，不被叙事判定覆盖。"""
    db, case = _wire(monkeypatch, contract, FULL_TEXT)
    db = _FakeDB([_trace(tool='wrong_tool')])
    result = contract.run_case(db, case)
    assert not result['ok'], result
    assert 'tool=' in result['why'], result['why']
