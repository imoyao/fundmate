# -*- coding: utf-8 -*-
"""逐标的类 job「全部目标都失败」的终态判据（#2495）。

事故形态：`fund_nav` / `price_history` / `fund_type` 这类逐标的 job，把单只异常
收进 `stats['errors']` 后继续（**这是对的**，一只坏不该拖垮整批），但**全部目标
都失败**时旧实现仍以 `status=success` 收尾 —— `success=0 / failed=N` 只落在另一个
字段里，任何按 `status` 过滤的看板、降级与告警都读到假绿。

本文件钉住基类 `_decide_final_status()` 的四条边界，以及两个真实 job 的端到端形态：

1. 全部目标失败 ⇒ `failed`；
2. 部分失败 ⇒ 仍 `success`（不得把常态抖动判成故障）；
3. 「今天没有新数据」（`failed == 0`）⇒ 仍 `success`；
4. 抓到数据但全被去重（`skipped > 0`）⇒ 仍 `success`。

判据刻意不碰 `errors` 的量纲（一行未必等于一个目标），只看「有没有任何一个目标
成功」+「有没有失败」，故对 `fund_nav` / `price_history` / `index_daily` 一视同仁。
"""

from unittest.mock import MagicMock

from app.domains.securities.models import Security
from app.services.job_base import SyncJob
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob
from app.services.sync.jobs.price_history_job import PriceHistorySyncJob


class _StubJob(SyncJob):
    """最小可运行 job：不落任何真实表，只按 targets 产出「成功行 / 失败目标」。

    用它隔离「基类终态判定」这一件事，避免断言被某个具体 job 的校验 / 去重逻辑带偏。
    """

    def __init__(self, db, *, rows=None, fail=(), allow_empty=True, drop_all=False, extra_errors=0):
        super().__init__(adapter=object(), db=db)
        self._rows = rows or {}
        self._fail = set(fail)
        self._allow_empty = allow_empty
        self._drop_all = drop_all
        self._extra_errors = extra_errors

    def get_name(self) -> str:
        return 'stub_all_targets_failed'

    @property
    def _allow_empty_data(self) -> bool:
        return self._allow_empty

    def _fetch_data(self, full_sync, targets):
        rows = []
        for code in targets:
            if code in self._fail:
                self.stats.setdefault('errors', []).append({'target': code, 'error': 'boom'})
                continue
            rows.extend(self._rows.get(code, []))
        for _ in range(self._extra_errors):
            # 记录级失败：一条 errors 未必等于一个目标（量纲与 total 不同）
            self.stats.setdefault('errors', []).append({'target': 'record', 'error': 'record-level'})
        return rows

    def _validate_data(self, raw_data):
        return list(raw_data)

    def _deduplicate(self, data):
        # drop_all 模拟「库内全都有」：拿到数据但一条都不需要新增
        return [] if self._drop_all else list(data)

    def _save_data(self, new_data):
        return None


# ── 基类判定的四条边界 ──


def test_all_targets_failed_is_failure(db):
    """全部目标都失败 ⇒ failed（旧行为是 success + failed=N 的假绿）。"""
    job = _StubJob(db, fail=('000001', '000002'))

    result = job.run(full_sync=True, targets=['000001', '000002'])

    assert result['status'] == 'failed'
    assert result['stats']['success'] == 0
    assert result['stats']['failed'] == 2
    assert len(result['stats']['errors']) == 2


def test_partial_failure_stays_success(db):
    """部分成功 ⇒ 仍 success，但失败明细必须保留（红灯常态化会淹没真故障）。"""
    job = _StubJob(db, rows={'000001': [{'k': 1}]}, fail=('000002',))

    result = job.run(full_sync=True, targets=['000001', '000002'])

    assert result['status'] == 'success'
    assert result['stats']['success'] == 1
    assert result['stats']['failed'] == 1
    assert len(result['stats']['errors']) == 1


def test_no_new_data_still_success(db):
    """「今天没有新数据」（无异常、failed=0）⇒ 仍 success，不得判死。"""
    job = _StubJob(db)

    result = job.run(full_sync=True, targets=['000001'])

    assert result['status'] == 'success'
    assert result['stats']['failed'] == 0
    assert result['stats']['success'] == 0


def test_empty_targets_still_success(db):
    """目标列表为空且允许空数据（空跑）⇒ 仍 success。"""
    job = _StubJob(db)

    result = job.run(full_sync=True, targets=[])

    assert result['status'] == 'success'
    assert result['stats']['failed'] == 0


def test_all_deduped_still_success(db):
    """抓到数据但全被去重 ⇒ 仍 success。

    「一条都没**新增**」与「一条都没**拿到**」是两件事——后者由 failed/errors 表达，
    前者只是 skipped。混为一谈会让每个已同步过的标的在第二次运行后集体报红。
    """
    job = _StubJob(db, rows={'000001': [{'k': 1}]}, drop_all=True)

    result = job.run(full_sync=True, targets=['000001'])

    assert result['status'] == 'success'
    assert result['stats']['success'] == 0
    assert result['stats']['skipped'] == 1
    assert result['stats']['failed'] == 0


def test_record_level_errors_do_not_fail_a_job_that_wrote_data(db):
    """`errors` 的量纲可能大于目标数：只要写成功了，就不许被记成「全部失败」。

    有些 job 把「逐记录失败」塞进 errors（一条 ≠ 一个目标），此时
    `failed` 会大于 `total`。若判据只看 `failed >= total`，这类 job 会被误判成红
    —— 故必须同时要求「一条都没写成功」。
    """
    job = _StubJob(db, rows={'000001': [{'k': 1}]}, extra_errors=2)

    result = job.run(full_sync=True, targets=['000001'])

    assert result['stats']['failed'] >= result['stats']['total']
    assert result['stats']['success'] == 1
    assert result['status'] == 'success'


# ── 两个真实 job 的端到端形态 ──


def test_fund_nav_all_targets_failed(db):
    """`fund_nav` 全挂：单只异常进 errors 后继续，全部失败 ⇒ failed。"""
    adapter = MagicMock()
    adapter.fetch_fund_nav.side_effect = RuntimeError('数据源不可用')

    job = FundNavSyncJob(adapter, db)
    result = job.run(full_sync=True, targets=['000001', '000002'])

    assert result['status'] == 'failed'
    assert result['stats']['success'] == 0
    assert result['stats']['failed'] == 2
    assert {e['fund_code'] for e in result['stats']['errors']} == {'000001', '000002'}


def test_price_history_all_targets_failed(db):
    """`price_history` 全挂：同上（#1833 已把异常写进 errors，但终态曾仍是 success）。"""
    db.add_all(
        [
            Security(symbol='SH600519', name='测试证券A', market='CN_A', type='stock', currency='CNY'),
            Security(symbol='SZ000568', name='测试证券B', market='CN_A', type='stock', currency='CNY'),
        ]
    )
    db.commit()

    adapter = MagicMock()
    adapter.fetch_stock_price.side_effect = RuntimeError('数据源不可用')

    job = PriceHistorySyncJob(adapter, db)
    result = job.run(full_sync=True, targets=['SH600519', 'SZ000568'])

    assert result['status'] == 'failed'
    assert result['stats']['success'] == 0
    assert result['stats']['failed'] == 2
    assert {e['symbol'] for e in result['stats']['errors']} == {'SH600519', 'SZ000568'}
