# -*- coding: utf-8 -*-
"""BiasJob 按标的粒度记账 + 失败明细上抛（#2475 同族，本卡）。

核心红线：**全部标的失败 ⇒ FAILED**。此前的形态是「失败只进日志」，
于是「37 个标的全挂」与「今天没有品种要算」在 job 终态上完全同形
（SUCCESS + failed=0 + errors=[]），上游整体挂掉也没人知道。

这批用例全程不联网：`calculate_item` / provider 都是 monkeypatch 出来的假实现。
"""

from datetime import date

import pytest

from app.services.adapters.null_adapter import NullAdapter
from app.services.bias.calculator import BiasCalculator
from app.services.bias.job import BiasJob
from app.services.bias.provider import ProductProvider
from app.services.bias.schemas import BiasResult


def _bias_result(symbol: str, item_type: str = 'index', name: str = '', *, stale: bool = False) -> BiasResult:
    return BiasResult(
        item_type=item_type,
        item_code=symbol,
        item_name=name or symbol,
        close=4000.0,
        bias=10.0,
        ema20=3900.0,
        label='高位区(绿卖)',
        position=70.0,
        position_label='高位区(绿卖)',
        data_date=date.today(),
        stale=stale,
    )


@pytest.fixture
def products():
    """三个标的：两个能算、一个算不出来（用于「部分失败」）。"""
    return [
        ('000300', 'index', '沪深300'),
        ('000905', 'index', '中证500'),
        ('801010', 'industry', '农林牧渔'),
    ]


@pytest.fixture
def job(db, monkeypatch, products):
    """构造 BiasJob，并把品种清单与逐标的计算替换成假实现（零网络、零真实等待）。"""
    job = BiasJob(NullAdapter(), db)
    job.request_interval = 0.0  # 免去 calculate_batch 里 3s/标的的限速睡眠
    monkeypatch.setattr(ProductProvider, 'get_default_list', staticmethod(lambda: products))
    return job


def _fail_only(job: BiasJob, monkeypatch, fail_symbols: set) -> None:
    """让指定标的计算失败（返回 None），其余给出正常结果。"""

    def fake_calculate_item(self, symbol, item_type, name, data_date=None):
        if symbol in fail_symbols:
            return None
        return _bias_result(symbol, item_type, name)

    monkeypatch.setattr(BiasCalculator, 'calculate_item', fake_calculate_item)


# ── 用例 1：计算层必须把逐标的失败交出来 ──


def test_calculate_batch_returns_per_symbol_failures(monkeypatch):
    """`calculate_batch` 返回 `(results, failures)`，失败项带 symbol/item_type/name。

    这是整条链的第一跳：失败明细要是只留在日志里，上层再怎么记账也拿不到。
    """
    monkeypatch.setattr(
        BiasCalculator,
        'calculate_item',
        lambda self, symbol, item_type, name, data_date=None: (
            None if symbol == '801010' else _bias_result(symbol, item_type, name)
        ),
    )
    calc = BiasCalculator()
    results, failures = calc.calculate_batch(
        [('000300', 'index', '沪深300'), ('801010', 'industry', '农林牧渔')],
        date.today(),
        request_interval=0,
    )

    assert [r.item_code for r in results] == ['000300']
    assert failures == [{'symbol': '801010', 'item_type': 'industry', 'name': '农林牧渔'}]


# ── 用例 2/3：部分失败 / 全部失败（核心红线） ──


def test_partial_failure_keeps_success_with_per_symbol_errors(job, monkeypatch):
    """部分标的失败 ⇒ SUCCESS，但 errors 是逐标的明细、total 分母含失败目标。

    `stats['failed']` 不在这里断言：它是基类 `run()` 末尾用 ``len(errors)`` 对齐的
    （#2475），`_fetch_data` 单测不该假装拥有那一层的契约——`run()` 路径见下一条用例。
    """
    _fail_only(job, monkeypatch, {'801010'})

    records = job._fetch_data(False, [])

    assert len(records) == 2
    assert job.stats['total'] == 3
    assert job.stats['success'] == 2
    assert [e['symbol'] for e in job.stats['errors']] == ['801010']
    assert job._decide_final_status().value == 'success'


def test_run_partial_failure_status_and_stats(job, monkeypatch):
    """走完整 `run()`：total 含失败目标（不被吃掉），failed 与 errors 对齐。"""
    _fail_only(job, monkeypatch, {'801010'})

    result = job.run()

    assert result['status'] == 'success'
    assert result['stats']['total'] == 3, '分母必须含失败目标，否则「3 个里挂 1 个」会显示成 2/2 全成功'
    assert result['stats']['success'] == 2
    assert result['stats']['failed'] == 1
    assert len(result['stats']['errors']) == 1


def test_all_targets_failed_marks_job_failed(job, monkeypatch):
    """**全部**标的失败 ⇒ FAILED（本卡核心红线）。"""
    _fail_only(job, monkeypatch, {'000300', '000905', '801010'})

    result = job.run()

    assert result['status'] == 'failed'
    assert result['stats']['failed'] == 3
    assert result['stats']['total'] == 3
    assert result['stats']['success'] == 0
    assert len(result['stats']['errors']) == 3


def test_empty_product_list_is_not_failure(job, monkeypatch):
    """品种清单为空是合法状态（不是失败）：total=0 / failed=0 / SUCCESS。"""
    monkeypatch.setattr(ProductProvider, 'get_default_list', staticmethod(lambda: []))

    result = job.run()

    assert result['status'] == 'success'
    assert result['stats']['total'] == 0
    assert result['stats']['failed'] == 0
    assert result['stats']['errors'] == []


# ── 用例 4：stale 不等于失败 ──


def test_all_stale_results_are_success_not_failure(job, monkeypatch):
    """全部标的 stale（回退旧缓存）但都有值 ⇒ 仍算成功，failed 必须为 0。

    stale 表示「数据滞后但可用」，与「抓不到」是两件事；把它计进 failed
    会让每天的正常降级都变成失败，红线随即失效。
    """
    monkeypatch.setattr(
        BiasCalculator,
        'calculate_item',
        lambda self, symbol, item_type, name, data_date=None: _bias_result(symbol, item_type, name, stale=True),
    )

    result = job.run()

    assert result['status'] == 'success'
    assert result['stats']['failed'] == 0
    assert result['stats']['errors'] == []
    assert result['stats']['total'] == 3
    assert result['stats']['success'] == 3


# ── 用例 5：`run_with_context`（唯一真实在跑的路径）同样要透出失败 ──


def test_run_with_context_surfaces_partial_failures(job, monkeypatch):
    """`run_with_context` 返回显式结果：records + total + failures，调用方读得到。"""
    _fail_only(job, monkeypatch, {'801010'})

    run = job.run_with_context('收盘')

    assert len(run.records) == 2
    assert run.total == 3
    assert run.failed == 1
    assert run.success == 2
    assert [f['symbol'] for f in run.failures] == ['801010']
    # 返回值与 stats 必须同源：两条路径记账口径不一致的话，
    # 「有人读 stats、有人读返回值」就会得出两个结论。
    assert job.stats['errors'] == run.failures
    assert job.stats['total'] == run.total


def test_run_with_context_all_failed_is_distinguishable(job, monkeypatch):
    """有清单但全部失败时，结果与「今天没数据」不再无差别。

    旧实现两者都返回 `[]`，TemperatureJob 只能干看着（本卡的静默失败链路）。
    """
    _fail_only(job, monkeypatch, {'000300', '000905', '801010'})

    run = job.run_with_context('收盘')

    assert run.records == []
    assert run.total == 3
    assert run.failed == 3
    assert run.success == 0


def test_run_with_context_empty_list_is_not_failure(job, monkeypatch):
    """清单为空：`total == 0 == failed`，与「全挂」靠 total 明确区分开。"""
    monkeypatch.setattr(ProductProvider, 'get_default_list', staticmethod(lambda: []))

    run = job.run_with_context('收盘')

    assert run.records == []
    assert run.total == 0
    assert run.failed == 0
