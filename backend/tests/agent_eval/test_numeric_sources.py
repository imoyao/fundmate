# -*- coding: utf-8 -*-
"""expect.narrative 数值来源判据（D103）：回答里的指标值必须能溯源到工具数据。

用合成数据证明三件事，且每件都单独钉住：
1. 合理表述（舍入 / 千分位 / 负号被「亏损」吸收）**不误判**为编造；
2. 编造的数（含数据为空却报数）**一定判红**并点名；
3. 判据真接进了 run_case（写好了不接线 = 登记了从不跑，比没有更糟）。

不调用真实模型，也不依赖 cases.yaml 的具体数值。
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPT = BACKEND_DIR / 'scripts' / 'agent_eval.py'

# 真实数据副本（2026-11-11）那次的四个数：组合区间收益 / 沪深300 / 超额 / 单只持仓盈亏
PLAN_DATA = {
    'steps': [
        {'tool': 'get_portfolio_vs_benchmark', 'data': {'range_rate': -20.66, 'benchmark_range_return': -12.61}},
        {
            'tool': 'list_position_pnl',
            'data': {'items': [{'name': '金地集团', 'pnl': -8387.89, 'pnl_rate': -35.2}], 'count': 1},
        },
        {'tool': 'get_rebalance_reference', 'data': {'excess_return': -8.05}},
    ]
}
COVERS = [{'id': '近3个月收益', 'any': ['近3个月', '区间收益']}]


@pytest.fixture(scope='module')
def contract():
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location('agent_eval_numeric_sources', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _expect(**narrative_extra):
    return {'status': 'result', 'tool': 'tool_a', 'narrative': {'covers': COVERS, **narrative_extra}}


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
    """把 run_case 的外部依赖换成合成实现；data 就是工具返回值里的 data 字段。"""
    monkeypatch.setattr(
        contract.session_store,
        'load_or_create',
        lambda db, session_id, user_id: SimpleNamespace(session_id='s-eval'),
    )
    monkeypatch.setattr(
        contract.agent_loop,
        'run_agent',
        lambda text, row: {'type': 'result', 'content': reply, 'data': data},
    )
    trace = SimpleNamespace(intent='execute_tool', status='result', tool_name='tool_a', blocked=False, tokens=10)
    return _FakeDB([trace])


# ── 一、合理表述不误判 ────────────────────────────────────────────


@pytest.mark.parametrize(
    'text',
    [
        '近3个月组合收益 -20.66%。',
        '近3个月组合收益 -20.7%。',  # 1 位小数舍入
        '近3个月亏损 20.66%。',  # 负号被语义词吸收
        '近3个月回落了 20.7 个百分点',
        '近3个月下跌 0.2066',  # 小数化百分比
        '近3个月跑输 8.1 个点',  # ULP/2 才命中，固定 0.5% 会漏
        '金地集团亏了 8388 元',  # 整数舍入
        '金地集团 -8,387.89 元',  # 千分位
        '近3个月收益 -20.66%，沪深300 -12.61%，跑输 8.05 个点，金地集团 -8387.89 元。',
    ],
)
def test_plausible_restatements_have_sources(contract, text):
    ok, why = contract.evaluate_numeric_sources(text, PLAN_DATA)
    assert ok, f'合理表述被误判为编造：{text!r} -> {why}'


@pytest.mark.parametrize(
    'text',
    [
        '近3个月收益不好，共 4 只持仓，前 5 大占比 30%。',
        '数据截至 2026 年 11 月，近 3 个月无记录。',
        '区间起点 2026-11-01，近3个月无记录。',  # 日期整体豁免
        '基金 000001 的近3个月无数据。',  # 代码形态豁免
    ],
)
def test_counts_and_dates_are_exempt(contract, text):
    ok, why = contract.evaluate_numeric_sources(text, {})
    assert ok, f'普通计数被误判成编造：{text!r} -> {why}'


# ── 二、编造必须判红 ──────────────────────────────────────────────


def test_fabricated_number_is_flagged_and_named(contract):
    ok, why = contract.evaluate_numeric_sources('近3个月组合跌了 25.33%。', PLAN_DATA)
    assert not ok
    assert '25.33' in why, why


def test_fabricated_number_flagged_even_when_data_is_empty(contract):
    """数据为空却报具体数值，是最硬的幻觉铁证——不能因为「没法比对」就跳过。"""
    ok, why = contract.evaluate_numeric_sources('近3个月组合收益 -20.66%。', None)
    assert not ok
    assert '-20.66' in why, why
    assert '没有任何数值' in why, why


def test_bool_is_not_a_numeric_source(contract):
    """True/False 是 int 子类，若不排除会让「1」凭空获得来源。"""
    ok, why = contract.evaluate_numeric_sources('近3个月收益 1.00%', {'ok': True, 'done': False})
    assert not ok, why


def test_string_numbers_are_not_sources(contract):
    """字符串里的数字不算来源：symbol / 日期里的数字不是可引用指标。"""
    ok, why = contract.evaluate_numeric_sources('近3个月收益 12.34%', {'symbol': '12.34', 'date': '2026-11-11'})
    assert not ok, why


# ── 三、门槛与归一化细节 ──────────────────────────────────────────


@pytest.mark.parametrize(
    ('raw', 'value', 'is_percent', 'is_year', 'want'),
    [
        ('20.66', 20.66, False, False, True),  # 2 位小数
        ('20.7', 20.7, True, False, True),  # 1 位小数 + 百分比标记
        ('20.7', 20.7, False, False, False),  # 1 位小数无标记（可能是万元换算）
        ('3', 3, False, False, False),  # 普通计数
        ('2026', 2026, False, True, False),  # 年份
        ('8388', 8388, False, False, True),  # 金额量级
        ('000001', 1.0, False, False, False),  # 代码形态
    ],
)
def test_high_entropy_gate(contract, raw, value, is_percent, is_year, want):
    assert contract._is_high_entropy(raw, value, is_percent, is_year) is want


def test_tolerance_follows_written_precision(contract):
    """容差取文本末位一半：写 8.1 允许 ±0.05（命中 8.05），写 8 允许 ±0.5。"""
    token_1dp = ('8.1', 8.1, True, False)
    token_int = ('8', 8.0, True, False)
    assert contract._number_has_source(token_1dp, [-8.05])
    assert contract._number_has_source(token_int, [-8.05])
    assert not contract._number_has_source(('8.6', 8.6, True, False), [-8.05])


def test_precision_tightens_not_loosens(contract):
    """写得越精确要求越严：20.66 不能命中 20.7 的来源（差 0.04 > 0.005）。"""
    assert not contract._number_has_source(('20.66', 20.66, True, False), [-20.7])
    assert contract._number_has_source(('20.7', 20.7, True, False), [-20.66])


# ── 四、接线与开关 ────────────────────────────────────────────────


def test_run_case_wires_numeric_sources(monkeypatch, contract):
    """判据接进 run_case 的证据：同一段回答，有数据来源过、无来源判红。"""
    reply = '近3个月区间收益 -20.66%。'

    db = _wire(monkeypatch, contract, reply, PLAN_DATA)
    result = contract.run_case(db, {'id': 'synth-01', 'turns': ['q'], 'expect': _expect()})
    assert result['ok'], result

    db = _wire(monkeypatch, contract, reply, {'steps': []})
    result = contract.run_case(db, {'id': 'synth-02', 'turns': ['q'], 'expect': _expect()})
    assert not result['ok']
    assert '无工具来源' in result['why'], result


def test_numbers_false_disables_check(monkeypatch, contract):
    db = _wire(monkeypatch, contract, '近3个月收益 -99.99%。', {})
    case = {'id': 'synth-03', 'turns': ['q'], 'expect': _expect(numbers=False)}
    assert contract.run_case(db, case)['ok']


def test_shape_accepts_numbers_bool_and_rejects_others(contract):
    assert contract.validate_narrative_shape({'covers': COVERS, 'numbers': False}) == []
    for bad in ('false', 0, 1, None):
        assert contract.validate_narrative_shape({'covers': COVERS, 'numbers': bad}), f'未拦住 numbers={bad!r}'


def test_empty_reply_is_rejected(contract):
    ok, why = contract.evaluate_numeric_sources('   ', PLAN_DATA)
    assert not ok and '文本为空' in why, why


# ── 五、正向 metric（抓回避与串台）────────────────────────────────

METRIC_DATA = {
    'steps': [
        {
            'tool': 'get_portfolio_vs_benchmark',
            'data': {'range_rate': -20.66, 'excess_return': -8.05, 'benchmark_range_return': -12.61},
        },
        {
            'tool': 'list_position_pnl',
            'data': {'items': [{'name': 'A', 'pnl': -100.0}, {'name': 'B', 'pnl': -8387.89}], 'count': 2},
        },
    ]
}
METRIC_COVERS = [
    {'id': '区间收益', 'any': ['区间收益'], 'metric': {'tool': 'get_portfolio_vs_benchmark', 'field': 'range_rate'}},
    {
        'id': '亏得最多',
        'any': ['亏得最多'],
        'metric': {'tool': 'list_position_pnl', 'field': 'items.*.pnl', 'pick': 'min'},
    },
    {'id': '调仓参考', 'any': ['调仓']},
    {'id': '跟上市场', 'any': ['跑输'], 'metric': {'tool': 'get_portfolio_vs_benchmark', 'field': 'excess_return'}},
]


def test_metric_presence_passes_when_all_cited(contract):
    text = '区间收益 -20.66%，亏得最多的一只 -8387.89 元，跑输 8.05 个点；调仓方面暂无明显信号。'
    ok, why = contract.evaluate_metric_presence(text, METRIC_DATA, METRIC_COVERS)
    assert ok, why


def test_metric_presence_accepts_rounding_and_percent_forms(contract):
    text = '区间收益亏损 20.7%，那只亏了 8388 元，跑输 8.1 个点。'
    ok, why = contract.evaluate_metric_presence(text, METRIC_DATA, METRIC_COVERS)
    assert ok, why


def test_metric_presence_flags_avoidance(contract):
    """只写「收益不好」不给数 = 回避，必须判红并点名缺哪个字段。"""
    ok, why = contract.evaluate_metric_presence(
        '区间收益不太好，亏得最多的是 B，调仓暂无信号，跑输基准。', METRIC_DATA, METRIC_COVERS
    )
    assert not ok
    assert '区间收益' in why and 'range_rate' in why, why


def test_metric_presence_flags_cross_talk(contract):
    """串台：把沪深300 的 -12.61% 当成组合区间收益 → range_rate 未被引用，判红。"""
    text = '区间收益 -12.61%，亏得最多的一只 -8387.89 元，跑输 8.05 个点。'
    ok, why = contract.evaluate_metric_presence(text, METRIC_DATA, METRIC_COVERS)
    assert not ok
    assert 'range_rate' in why, why


def test_metric_presence_skips_when_field_has_no_value(contract):
    """字段为 None / 工具没跑 → 跳过，不能把「如实说没有数据」判成回避。"""
    text = '区间收益、亏损、调仓、跑输都暂无数据。'
    ok, why = contract.evaluate_metric_presence(
        text, {'steps': [{'tool': 'get_portfolio_vs_benchmark', 'data': {'range_rate': None}}]}, METRIC_COVERS
    )
    assert ok, why
    ok, why = contract.evaluate_metric_presence(text, None, METRIC_COVERS)
    assert ok, why


def test_metric_presence_ignores_covers_without_metric(contract):
    covers = [{'id': '调仓参考', 'any': ['调仓']}]
    assert contract.evaluate_metric_presence('调仓方面暂无信号。', {}, covers) == (True, '')


def test_metric_values_supports_single_tool_shape(contract):
    """单工具路径没有 steps，data 就是工具输出本身。"""
    data = {'range_rate': -3.14}
    metrics = [{'id': 'x', 'any': ['x'], 'metric': {'tool': 'get_portfolio_vs_benchmark', 'field': 'range_rate'}}]
    assert contract.evaluate_metric_presence('区间 -3.14%', data, metrics) == (True, '')


def test_metric_multi_source_accepts_either_caliber(contract):
    """同一问有多个等价口径（金额 / 年化小数）时，报任一个都算给出。"""
    covers = [
        {
            'id': '区间收益',
            'any': ['区间收益'],
            'metric': [
                {'tool': 'get_portfolio_vs_benchmark', 'field': 'range_rate'},
                {'tool': 'get_portfolio_performance', 'field': 'xirr'},
            ],
        }
    ]
    data = {
        'steps': [
            {'tool': 'get_portfolio_vs_benchmark', 'data': {'range_rate': -10214.99}},
            {'tool': 'get_portfolio_performance', 'data': {'xirr': 0.3675}},
        ]
    }
    assert contract.evaluate_metric_presence('区间收益 -10214.99 元', data, covers) == (True, '')
    assert contract.evaluate_metric_presence('区间年化 36.75%', data, covers) == (True, '')
    ok, why = contract.evaluate_metric_presence('区间收益 -15.38%', data, covers)
    assert not ok and '区间收益' in why, why


@pytest.mark.parametrize(
    'bad',
    [
        'not-a-dict',
        {},
        {'tool': 'x'},
        {'field': 'y'},
        {'tool': 'x', 'field': 'y', 'pick': 'average'},
        {'tool': 'x', 'field': 'y', 'extra': 1},
    ],
)
def test_metric_shape_rejected(contract, bad):
    ok, why = contract.evaluate_narrative(
        '区间收益', {'narrative': {'covers': [{'id': 'a', 'any': ['区间收益'], 'metric': bad}]}}
    )
    assert not ok and 'metric' in why, why


def test_run_case_wires_metric_presence(monkeypatch, contract):
    """接线证据：同一条回答，有 metric 数据时判红、字段无值时放过。"""
    reply = '区间收益 -12.61%，亏得最多的一只 -8387.89 元，跑输 8.05 个点。'
    covers = [
        {'id': '区间收益', 'any': ['区间收益'], 'metric': {'tool': 'get_portfolio_vs_benchmark', 'field': 'range_rate'}}
    ]

    db = _wire(monkeypatch, contract, reply, METRIC_DATA)
    case = {
        'id': 'synth-m1',
        'turns': ['q'],
        'expect': {'status': 'result', 'tool': 'tool_a', 'narrative': {'covers': covers}},
    }
    result = contract.run_case(db, case)
    assert not result['ok'] and 'range_rate' in result['why'], result

    db = _wire(monkeypatch, contract, reply, {'steps': []})
    # 隔离出 metric 一层：字段无值时它必须放过；这条回答的数值在空数据里会被
    # numbers 判红，所以关掉 numbers 才能证明「跳过」而不是「碰巧通过」。
    metric_only = {**case, 'expect': {**case['expect'], 'narrative': {'covers': covers, 'numbers': False}}}
    assert contract.run_case(db, metric_only)['ok']
