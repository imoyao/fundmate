# -*- coding: utf-8 -*-
"""宏观工具（``query_macro_indicator``）回归网。

打桩在 adapter 边界（``wind_macro``）之上，测的是**工具自己那层决策**：
歧义要不要猜、窗口怎么推、期数怎么截、口径怎么下发。

四条不可退让的性质：
1. **歧义不猜**：多口径时只回候选、**绝不调取数**（猜错的代价是用户拿到别口径的数字）；
2. **窗口按频率推**：季频 8 期不能只用 180 天窗口（会取空）；
3. **期数在本地截**：上游 ``observation`` 参数未生效（实测），只能自己截；
4. **注册链路完整**：metadata 与实现函数同时挂上，``ToolExecutor`` 真能派发。
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.adapters import wind_macro as real_wind_macro
from app.services.ai_recognizer import tools as tools_mod
from app.services.ai_recognizer import tools_macro

TODAY = date(2026, 11, 16)


def _stub(monkeypatch, *, available=True, candidates=None, series=None):
    """装 adapter 替身，返回调用记录 ``{'search': [...], 'series': [...]}``。"""
    calls = {'search': [], 'series': []}

    def search(question):
        calls['search'].append(question)
        return list(candidates or [])

    def fetch(name, begin, end):
        calls['series'].append({'name': name, 'begin': begin, 'end': end})
        return list(series or [])

    monkeypatch.setattr(
        tools_macro,
        'wind_macro',
        SimpleNamespace(
            is_available=lambda: available,
            search_indicators=search,
            fetch_series=fetch,
            normalize=real_wind_macro.normalize,
        ),
    )
    monkeypatch.setattr(tools_macro, 'today_shanghai', lambda: TODAY)
    return calls


def _series(name='中国:GDP:不变价:当季同比', points=None, freq='季', unit='%'):
    return [{'name': name, 'freq': freq, 'unit': unit, 'points': points or {}}]


# ── 正常路径 ─────────────────────────────────────────────────────────────
def test_projects_latest_prev_and_change(monkeypatch):
    """latest / prev / change_vs_prev 三者自洽，points 升序。"""
    _stub(
        monkeypatch,
        candidates=[{'name': '中国:GDP:不变价:当季同比', 'freq': '季'}],
        series=_series(points={date(2026, 6, 30): 4.6, date(2026, 9, 30): 4.8}),
    )

    out = tools_macro._tool_query_macro_indicator({'question': '中国GDP当季同比'})

    assert out['found'] is True and 'ambiguous' not in out
    assert out['latest'] == {'date': '2026-09-30', 'value': 4.8}
    assert out['prev'] == {'date': '2026-06-30', 'value': 4.6}
    assert out['change_vs_prev'] == 0.2
    assert [p['date'] for p in out['points']] == ['2026-06-30', '2026-09-30']
    assert out['unit'] == '%' and out['freq'] == '季'
    assert out['source'] == 'Wind EDB'


def test_single_point_has_no_change(monkeypatch):
    """只有一期时 prev / change_vs_prev 必须是 None，不能编一个 0。"""
    _stub(
        monkeypatch,
        candidates=[{'name': 'A', 'freq': '月'}],
        series=_series('A', {date(2026, 10, 31): 51.2}, freq='月', unit=None),
    )

    out = tools_macro._tool_query_macro_indicator({'question': 'A'})

    assert out['prev'] is None and out['change_vs_prev'] is None


def test_caveats_state_the_change_semantics(monkeypatch):
    """口径必须随数据下发：同比类指标的「变化」是百分点，不是涨跌幅。"""
    _stub(
        monkeypatch,
        candidates=[{'name': 'A', 'freq': '季'}],
        series=_series('A', {date(2026, 6, 30): 4.6, date(2026, 9, 30): 4.8}),
    )

    caveats = ' '.join(tools_macro._tool_query_macro_indicator({'question': 'A'})['caveats'])

    assert '百分点' in caveats and '不是涨跌幅' in caveats
    assert '未补 0' in caveats


# ── 歧义：只回候选，绝不取数 ─────────────────────────────────────────────
def test_ambiguous_returns_candidates_and_skips_fetch(monkeypatch):
    calls = _stub(
        monkeypatch,
        candidates=[
            {'name': '中国:GDP:不变价:当季同比', 'freq': '季'},
            {'name': '中国:GDP:现价:当季值', 'freq': '季'},
            {'name': '中国:GDP:不变价:累计同比', 'freq': '季'},
        ],
    )

    out = tools_macro._tool_query_macro_indicator({'question': 'GDP'})

    assert out['ambiguous'] is True and out['found'] is True
    assert len(out['candidates']) == 3
    assert calls['series'] == [], '歧义时必须放弃取数——猜一个口径比查不到更糟'


def test_exact_name_disambiguates(monkeypatch):
    """用户给出精确名（归一化后相等）→ 直接命中，不再判歧义。"""
    _stub(
        monkeypatch,
        candidates=[
            {'name': '中国:GDP:不变价:当季同比', 'freq': '季'},
            {'name': '中国:GDP:现价:当季值', 'freq': '季'},
        ],
        series=_series(points={date(2026, 9, 30): 4.8}),
    )

    out = tools_macro._tool_query_macro_indicator({'question': '中国：GDP:不变价 当季同比'})

    assert 'ambiguous' not in out
    assert out['indicator'] == '中国:GDP:不变价:当季同比'


def test_unique_substring_disambiguates(monkeypatch):
    """问句是唯一候选的连续子串 → 命中（用户已经写了大半精确名）。"""
    _stub(
        monkeypatch,
        candidates=[
            {'name': '中国:GDP:不变价:当季同比', 'freq': '季'},
            {'name': '中国:GDP:现价:当季值', 'freq': '季'},
        ],
        series=_series(points={date(2026, 9, 30): 4.8}),
    )

    out = tools_macro._tool_query_macro_indicator({'question': '不变价:当季同比'})

    assert out['indicator'] == '中国:GDP:不变价:当季同比'


def test_ambiguous_candidates_are_capped(monkeypatch):
    """候选清单有上限：一路回二十条会把叙事上下文挤掉。"""
    many = [{'name': f'指标{i}', 'freq': '月'} for i in range(20)]
    _stub(monkeypatch, candidates=many)

    out = tools_macro._tool_query_macro_indicator({'question': 'GDP'})

    assert len(out['candidates']) == tools_macro._MAX_CANDIDATES


# ── 缺数据 / 未配置 ──────────────────────────────────────────────────────
def test_unavailable_returns_before_any_upstream_call(monkeypatch):
    """未配置是「可选组件未启用」，不是故障：不触网、不告警，如实回 available=false。"""
    calls = _stub(monkeypatch, available=False)

    out = tools_macro._tool_query_macro_indicator({'question': 'GDP'})

    assert out['available'] is False
    assert calls == {'search': [], 'series': []}


def test_no_candidates_reports_found_false(monkeypatch):
    _stub(monkeypatch, candidates=[])

    out = tools_macro._tool_query_macro_indicator({'question': '火星GDP'})

    assert out['found'] is False
    assert '换一种说法' in out['reason']


def test_empty_series_reports_found_false_with_indicator(monkeypatch):
    """指标找到了但窗口内无点（未发布 / 停更）：要带上是哪个指标，便于用户判断。"""
    _stub(monkeypatch, candidates=[{'name': 'A', 'freq': '季'}], series=[])

    out = tools_macro._tool_query_macro_indicator({'question': 'A'})

    assert out['found'] is False
    assert out['indicator'] == 'A'
    assert 'window' in out


# ── 窗口与截断 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ('freq', 'periods', 'expected_days'),
    [
        ('季', 8, 8 * 92 + 60),  # 796 天：低于两年会取不满 8 个季点
        ('月', 2, 730),  # 2*31+60=122 → 抬到下限 730
        ('日', 40, 730),  # 40*3+60=180 → 抬到下限 730
        ('年', 40, 7300),  # 40*366+60=14700 → 压到上限 7300
        (None, 8, 8 * 92 + 60),  # 认不出按季：窗口偏大只多取，偏小才取空
    ],
)
def test_window_days_follow_frequency(monkeypatch, freq, periods, expected_days):
    calls = _stub(
        monkeypatch,
        candidates=[{'name': 'A', 'freq': freq}],
        series=_series('A', {TODAY - timedelta(days=30): 1.0}, freq=freq or '季'),
    )

    tools_macro._tool_query_macro_indicator({'question': 'A', 'periods': periods})

    assert (TODAY - calls['series'][0]['begin']).days == expected_days


def test_keeps_only_latest_requested_periods(monkeypatch):
    """窗口按「期数 + 余量」推，日频会多取；出参只留最近 periods 期。"""
    points = {date(2026, 9, 1) + timedelta(days=i): float(i) for i in range(10)}
    _stub(monkeypatch, candidates=[{'name': 'A', 'freq': '日'}], series=_series('A', points, freq='日'))

    out = tools_macro._tool_query_macro_indicator({'question': 'A', 'periods': 3})

    assert out['requested_periods'] == 3 and out['returned_periods'] == 3
    assert [p['value'] for p in out['points']] == [7.0, 8.0, 9.0]
    assert out['latest']['value'] == 9.0


@pytest.mark.parametrize(('raw', 'expected'), [(None, 8), (999, 40), (0, 1), ('12', 8), (True, 8), (5, 5)])
def test_periods_are_clamped(raw, expected):
    """schema 的 minimum/maximum **不被校验器执行**，边界必须函数内兜。"""
    assert tools_macro._periods_of(raw) == expected


# ── 注册链路 ─────────────────────────────────────────────────────────────
def test_tool_is_registered_in_both_places():
    """metadata 与实现函数必须同时挂上——只有其一，模型看得见却调不动（或反之）。"""
    names = [m['name'] for m in tools_mod.TOOLS_METADATA]
    assert 'query_macro_indicator' in names
    assert 'query_macro_indicator' in tools_mod._FUNCTION_MAP


def test_schema_requires_question_and_passes_validation():
    meta = next(m for m in tools_mod.TOOLS_METADATA if m['name'] == 'query_macro_indicator')
    assert meta['parameters']['required'] == ['question']

    with pytest.raises(ValueError, match='缺少必填参数'):
        tools_mod._validate_params('query_macro_indicator', {})
    # periods 类型受校验器保护（integer），字符串会被挡在派发之前
    with pytest.raises(ValueError, match='类型应为 integer'):
        tools_mod._validate_params('query_macro_indicator', {'question': 'GDP', 'periods': '8'})
    tools_mod._validate_params('query_macro_indicator', {'question': 'GDP', 'periods': 3})


def test_executor_dispatches_through_registry(monkeypatch):
    """端到端：ToolExecutor 按全量 metadata 校验并派发到实现函数。"""
    _stub(
        monkeypatch,
        candidates=[{'name': 'A', 'freq': '季'}],
        series=_series('A', {date(2026, 6, 30): 4.6, date(2026, 9, 30): 4.8}),
    )

    result = tools_mod.ToolExecutor.run('query_macro_indicator', {'question': 'A', 'periods': 2})

    assert result['status'] == 'success'
    assert result['data']['latest']['value'] == 4.8
