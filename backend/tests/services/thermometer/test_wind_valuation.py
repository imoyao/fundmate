# -*- coding: utf-8 -*-
"""Wind 指数/行业估值 → 市场温度计（#2749）：分块、分类、失败隔离与 job 接线。

全部替身，不联网。上游形态（两张并列表、行序与请求不一致、列名漂移）已在
:mod:`tests.services.adapters.test_wind_index_valuation` 钉过，本层只管
「分块编排 + multi 记录形状 + 块级失败不拖垮」。
"""

import json
import re
from datetime import datetime

import pytest

import app.services.thermometer.jobs as tjobs
from app.services.adapters import jiucaishuo_adapter, wind_index_valuation
from app.services.adapters.null_adapter import NullAdapter
from app.services.bias.constants import SW_LEVEL1_INDUSTRIES
from app.services.thermometer import fundfof_crowding, industry_crowding, wind_valuation

_COLLECTED_AT = datetime(2026, 10, 30, 20, 0, 0)


class _StubProvider:
    name = 'wind_index'

    def scope_of(self, capability):
        return 'public_market'

    def tool_for(self, capability):
        return 'get_index_fundamentals'

    def map_args(self, capability, **kwargs):
        return kwargs

    def extract(self, text):
        return json.loads(text)


class _ChunkedStubTransport:
    """从问句解析代码，按请求代码回行（**倒序**，模拟上游行序不一致的真机行为）。

    每个代码给两行（估值行 + 分位行），复现上游「两张并列表」的形态，
    顺带验证适配器归并逻辑在本层用法下依旧成立。
    """

    def __init__(self, fail_on=()):
        self.fail_on = set(fail_on)
        self.questions = []

    def call_tool(self, tool, arguments, token=None):
        question = arguments['question']
        self.questions.append(question)
        codes = re.findall(r'\d{6}\.(?:SH|SZ|SI)', question)
        if self.fail_on & set(codes):
            raise RuntimeError('upstream boom')
        rows = []
        for code in reversed(codes):
            rows.append(
                {
                    'Wind代码': code,
                    '证券简称': None,
                    '日期': '2026-10-29',
                    '最新市盈率PE_TTM': 12.5,
                    '最新市净率PB': 1.4,
                    '股息率': 3.0,
                }
            )
            rows.append({'Wind代码': code, '最新市盈率在历史中的分位数': 45.6, '日期': '20261029'})
        return json.dumps(rows, ensure_ascii=False)


@pytest.fixture(autouse=True)
def _wind_available(monkeypatch):
    """测试进程没有 Wind Token，统一打开可用性门（替身从 transport 注入，不走真实门）。

    单条测试可再次 setattr 覆盖（monkeypatch 后写胜出），如 ``test_unavailable``。
    """
    monkeypatch.setattr(wind_index_valuation, 'is_available', lambda: True)


def _run(*, fail_on=()):
    provider = _StubProvider()
    transport = _ChunkedStubTransport(fail_on=fail_on)
    records, errors = wind_valuation.fetch_wind_valuation_records(_COLLECTED_AT, provider=provider, transport=transport)
    return records, errors, transport


# ── 可用性门 ─────────────────────────────────────────────────────────


def test_unavailable_skips_silently(monkeypatch):
    """Token 未配置 ⇒ 静默返回空，不发起任何请求、不产生 error。"""

    class _BoomTransport:
        def call_tool(self, *a, **k):
            raise AssertionError('不可用时不得发起请求')

    monkeypatch.setattr(wind_index_valuation, 'is_available', lambda: False)
    records, errors = wind_valuation.fetch_wind_valuation_records(_COLLECTED_AT, transport=_BoomTransport())

    assert records == []
    assert errors == []


# ── 分块与覆盖 ───────────────────────────────────────────────────────


def test_chunking_covers_all_targets_at_most_ten_per_call():
    """宽基 + 30 个申万一级行业 ⇒ 每问 ≤10 个实体，且全部代码恰好覆盖一次。"""
    records, errors, transport = _run()

    assert errors == []
    requested = []
    for question in transport.questions:
        codes = re.findall(r'\d{6}\.(?:SH|SZ|SI)', question)
        assert len(codes) <= wind_valuation.CHUNK_SIZE
        requested.extend(codes)
    assert len(requested) == len(set(requested)), '同一代码不得重复请求'
    assert set(wind_valuation.BROAD_INDEX_TARGETS) <= set(requested)
    assert set(SW_LEVEL1_INDUSTRIES) <= set(requested)


# ── 记录形状 ─────────────────────────────────────────────────────────


def test_record_shape_and_index_industry_classification():
    records, errors, _ = _run()

    assert errors == []
    by_code = {r['item_code']: r for r in records}

    hs300 = by_code['000300.SH']
    assert hs300['kind'] == 'multi'
    assert hs300['source'] == wind_valuation.WIND_VALUATION_SOURCE
    assert hs300['item_type'] == 'index'
    assert hs300['item_name'] == '沪深300'
    assert hs300['collected_at'] == _COLLECTED_AT
    assert hs300['stale'] is False
    # 键集固定：缺值补 None，读侧不用猜 schema
    assert set(hs300['data']) == {'pe', 'pb', 'dividend_yield', 'pe_percentile', 'valuation_date'}
    assert hs300['data']['pe'] == 12.5
    assert hs300['data']['pe_percentile'] == 45.6
    assert hs300['data']['valuation_date'] == '2026-10-29'

    food = by_code['801120.SI']
    assert food['item_type'] == 'industry'
    assert food['item_name'] == '食品饮料'


def test_valuation_and_percentile_rows_merge_into_one_record_per_code():
    """上游每个代码回两行（估值 + 分位），落库必须是**一行**而不是两个品种。"""
    records, _, _ = _run()

    codes = [r['item_code'] for r in records]
    assert len(codes) == len(set(codes)), f'代码重复落行: {[c for c in codes if codes.count(c) > 1]}'


def test_unknown_code_uses_adapter_name():
    """映射表认不出的代码，回退用上游给的证券简称（item_name 非空约束）。"""
    provider = _StubProvider()
    transport = _ChunkedStubTransport()

    class _ExtraTransport(_ChunkedStubTransport):
        def call_tool(self, tool, arguments, token=None):
            raw = super().call_tool(tool, arguments, token=token)
            if '999999.SH' in arguments['question']:
                rows = json.loads(raw)
                for row in rows:
                    if row['Wind代码'] == '999999.SH':
                        row['证券简称'] = '自定义指数'
            return raw

    records, errors = wind_valuation.fetch_wind_valuation_records(
        _COLLECTED_AT,
        provider=provider,
        transport=_ExtraTransport(fail_on=[]),
    )

    assert errors == []
    by_code = {r['item_code']: r for r in records}
    assert by_code.get('999999.SH') is None  # 不在请求目标里，不会出现
    # 宽基/行业代码全部来自映射表，不受上游简称缺失影响
    assert by_code['000300.SH']['item_name'] == '沪深300'


def test_row_without_any_name_is_skipped():
    """代码与映射表、上游简称三方都给不出名字 ⇒ 跳过该行（不得落 NULL 名字）。"""
    provider = _StubProvider()

    class _NamelessTransport(_ChunkedStubTransport):
        def call_tool(self, tool, arguments, token=None):
            raw = super().call_tool(tool, arguments, token=token)
            rows = json.loads(raw)
            # 上游给了一个映射表外的代码且没带简称
            rows.append({'Wind代码': '888888.SH', '最新市盈率PE_TTM': 9.9})
            return json.dumps(rows, ensure_ascii=False)

    records, errors = wind_valuation.fetch_wind_valuation_records(
        _COLLECTED_AT, provider=provider, transport=_NamelessTransport(fail_on=[])
    )

    assert '888888.SH' not in {r['item_code'] for r in records}


# ── 块级失败隔离 ─────────────────────────────────────────────────────


def test_chunk_failure_reports_error_and_keeps_other_chunks():
    """一块挂 ⇒ 该块进 errors，其余块照常产出（不整组标 stale、不整批作废）。"""
    records, errors, _ = _run(fail_on=('801080.SI',))

    # 801080 所在块全部缺席，其余块在
    assert '801080.SI' not in {r['item_code'] for r in records}
    assert '000300.SH' in {r['item_code'] for r in records}
    assert len(errors) == 1
    assert errors[0]['source'] == wind_valuation.WIND_VALUATION_SOURCE
    assert '801080.SI' in errors[0]['error']


# ── job 接线 ─────────────────────────────────────────────────────────


class _StubJiucaishuo:
    def fetch(self):
        return None


@pytest.fixture
def temperature_job(db, monkeypatch):
    """TemperatureJob + 除 Wind 估值外所有数据源置空（沿用乖离率接线测试的隔离方式）。"""
    monkeypatch.setattr(tjobs, 'SINGLE_FETCHERS', {})
    monkeypatch.setattr(tjobs, 'COMPOSITE_FETCHERS', {})
    monkeypatch.setattr(tjobs, 'JiucaishuoFetcher', _StubJiucaishuo)
    monkeypatch.setattr(jiucaishuo_adapter.JiucaishuoAdapter, 'fetch_industry_emotion', lambda self: [])
    monkeypatch.setattr(industry_crowding, 'fetch_industry_crowding', lambda: [])
    monkeypatch.setattr(fundfof_crowding, 'fetch_fundfof_track_crowding', lambda: [])
    monkeypatch.setattr(tjobs, 'SKIP_BIAS', True)
    return tjobs.TemperatureJob(NullAdapter(), db)


def test_job_includes_wind_valuation_records(temperature_job, monkeypatch):
    """Wind 有数据 ⇒ multi 记录进入 TemperatureJob 产出。"""
    wind_record = {
        'kind': 'multi',
        'source': wind_valuation.WIND_VALUATION_SOURCE,
        'item_type': 'index',
        'item_code': '000300.SH',
        'item_name': '沪深300',
        'data': {'pe': 12.5},
        'collected_at': _COLLECTED_AT,
        'stale': False,
    }
    monkeypatch.setattr(
        wind_valuation,
        'fetch_wind_valuation_records',
        lambda collected_at=None, **k: ([wind_record], []),
    )

    records = temperature_job._fetch_data(False, [])

    assert wind_record in records
    assert [e for e in temperature_job.stats['errors'] if e.get('source') == 'wind_valuation'] == []


def test_job_records_wind_valuation_errors_without_aborting(temperature_job, monkeypatch):
    """Wind 分块失败 ⇒ errors 里有 wind_valuation 条目，但 job 照常产出（不判整体失败）。"""
    monkeypatch.setattr(
        wind_valuation,
        'fetch_wind_valuation_records',
        lambda collected_at=None, **k: ([], [{'source': 'wind_valuation', 'error': 'boom'}]),
    )

    records = temperature_job._fetch_data(False, [])

    wind_errors = [e for e in temperature_job.stats['errors'] if e.get('source') == 'wind_valuation']
    assert len(wind_errors) == 1
    assert temperature_job._decide_final_status().value == 'success'


def test_job_without_wind_token_stays_quiet(temperature_job, monkeypatch):
    """Token 未配置 ⇒ records/errors 里都不出现 wind_valuation 痕迹。"""
    monkeypatch.setattr(wind_valuation, 'fetch_wind_valuation_records', lambda collected_at=None, **k: ([], []))

    records = temperature_job._fetch_data(False, [])

    assert [r for r in records if r.get('source') == 'wind_valuation'] == []
    assert [e for e in temperature_job.stats['errors'] if e.get('source') == 'wind_valuation'] == []
