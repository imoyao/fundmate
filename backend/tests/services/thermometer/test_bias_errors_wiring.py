# -*- coding: utf-8 -*-
"""TemperatureJob 对乖离率失败的接线（本卡第 4 条要求）。

真实在跑的路径是 ``TemperatureJob._fetch_data → BiasJob.run_with_context``：
乖离率逐标的失败此前只落一句 ``logger.warning``，于是 sync_logs 里
「37 个标的全挂」与「今天没数据」完全同形。这里钉住「必须进 errors」。

为聚焦接线，其余数据源（单值 / 韭圈儿 / 行业恐贪 / 复合 / 两个拥挤度）
一律替成空实现，全程不联网。
"""

import pytest

import app.services.thermometer.jobs as tjobs
from app.services.adapters import jiucaishuo_adapter
from app.services.adapters.null_adapter import NullAdapter
from app.services.bias.job import BiasRunResult
from app.services.thermometer import fundfof_crowding, industry_crowding


class _StubJiucaishuo:
    """韭圈儿整源失败（stub 只需 return None）。"""

    def fetch(self):
        return None


@pytest.fixture
def temperature_job(db, monkeypatch):
    """TemperatureJob + 除乖离率外所有数据源置空。"""
    monkeypatch.setattr(tjobs, 'SINGLE_FETCHERS', {})
    monkeypatch.setattr(tjobs, 'COMPOSITE_FETCHERS', {})
    monkeypatch.setattr(tjobs, 'JiucaishuoFetcher', _StubJiucaishuo)
    monkeypatch.setattr(jiucaishuo_adapter.JiucaishuoAdapter, 'fetch_industry_emotion', lambda self: [])
    monkeypatch.setattr(industry_crowding, 'fetch_industry_crowding', lambda: [])
    monkeypatch.setattr(fundfof_crowding, 'fetch_fundfof_track_crowding', lambda: [])
    return tjobs.TemperatureJob(NullAdapter(), db)


def _bias_errors(job: tjobs.TemperatureJob) -> list:
    return [e for e in job.stats['errors'] if e.get('source') == 'bias']


def _bias_records(records: list) -> list:
    """只挑乖离率记录：其余数据源被 stub 成「整源失败」，会留 stale 占位记录，属噪声。"""
    return [r for r in records if r.get('source') == 'bias']


def test_all_bias_failed_adds_one_summary_error(temperature_job, monkeypatch):
    """全挂 ⇒ errors 里一条 summary，写清 N/N，且**只有一条**（不刷屏）。"""
    failures = [{'symbol': f'8{i:05d}', 'item_type': 'industry', 'name': f'行业{i}'} for i in range(37)]
    monkeypatch.setattr(
        tjobs, 'BiasJob', lambda adapter, db: _make_bias_stub(BiasRunResult(records=[], total=37, failures=failures))
    )

    records = temperature_job._fetch_data(False, [])

    assert _bias_records(records) == []
    bias_errors = _bias_errors(temperature_job)
    assert len(bias_errors) == 1
    assert bias_errors[0]['error'] == '乖离率 37/37 标的失败（全部失败）'
    # 温度任务聚合 6 个数据源，乖离率全挂不得把整体判红
    assert temperature_job._decide_final_status().value == 'success'


def test_partial_bias_failure_adds_summary_and_keeps_records(temperature_job, monkeypatch):
    """部分失败 ⇒ 有记录的照收，errors 里仍有一条 summary（不带「全部失败」）。"""
    record = {
        'kind': 'multi',
        'source': 'bias',
        'item_type': 'index',
        'item_code': '000300',
        'item_name': '沪深300',
        'data': {'bias': 1.0},
        'stale': False,
    }
    failures = [{'symbol': '801010', 'item_type': 'industry', 'name': '农林牧渔'}]
    monkeypatch.setattr(
        tjobs,
        'BiasJob',
        lambda adapter, db: _make_bias_stub(BiasRunResult(records=[record], total=2, failures=failures)),
    )

    records = temperature_job._fetch_data(False, [])

    assert _bias_records(records) == [record]
    bias_errors = _bias_errors(temperature_job)
    assert len(bias_errors) == 1
    assert bias_errors[0]['error'] == '乖离率 1/2 标的失败'


def test_no_bias_failure_adds_no_error(temperature_job, monkeypatch):
    """全部成功 ⇒ 不留 bias 错误（避免「每天都有 error」把 errors 变成噪音）。"""
    record = {'kind': 'multi', 'source': 'bias', 'item_code': '000300', 'data': {'bias': 1.0}, 'stale': False}
    monkeypatch.setattr(
        tjobs,
        'BiasJob',
        lambda adapter, db: _make_bias_stub(BiasRunResult(records=[record], total=1, failures=[])),
    )

    temperature_job._fetch_data(False, [])

    assert _bias_errors(temperature_job) == []


def _make_bias_stub(run_result: BiasRunResult):
    """生成一个 run_with_context 固定返回 ``run_result`` 的 BiasJob 替身。"""

    class _BiasStub:
        def __init__(self, adapter=None, db=None):
            pass

        def run_with_context(self, context: str = '收盘') -> BiasRunResult:
            return run_result

    return _BiasStub()
