# -*- coding: utf-8 -*-
"""`--job` 的目标池解析（#870 回归，2026-10-01 生产复现）。

案发形态：`pdm run sync --job fund_position`（AGENTS.md 与 PR #1804 正文都这么写）
拿到 `targets=None`，而该 job 对 `None` 的语义是「目标池为空 → 显式跳过」，
于是**先静默跑成 0 只**，再因 `run_job` 的 duration 算 `datetime - None` 抛
TypeError 以 exit 1 收尾——手工回填的人只会看到「同步失败」，不知道其实一条都没抓。

两个独立成因：
1. `--target-file` 的基金分支里没有 `fund_position`（job 名硬编码在元组里）；
2. 不给任何显式目标时，CLI 不会像 `daily_scheduler` 那样从库里取核心池。
"""

from unittest.mock import MagicMock

import pytest

from app.tools.sync_metadata import DB_POOL_JOBS, FUND_TARGET_JOBS, resolve_job_targets

FUND_CODES = ['000001', '110022']
STOCK_CODES = ['SH600519']


@pytest.fixture
def orch():
    """最小 orchestrator 替身：只提供 `resolve_targets`。"""
    o = MagicMock()
    o.resolve_targets.return_value = {'fund': list(FUND_CODES), 'stock': list(STOCK_CODES)}
    return o


def test_fund_position_without_explicit_targets_takes_db_pool(orch):
    """裸调用必须解析出库内核心池 —— 这是 CLI 与调度器的语义对齐点。"""
    assert resolve_job_targets(orch, 'fund_position', None, None) == FUND_CODES


def test_explicit_targets_win(orch):
    assert resolve_job_targets(orch, 'fund_position', '000001, 000002 ', None) == ['000001', '000002']


def test_target_file_works_for_fund_position(orch):
    """回归：`fund_position` 原先不在基金分支的元组里，`--target-file` 对它无效。"""
    assert 'fund_position' in FUND_TARGET_JOBS
    assert resolve_job_targets(orch, 'fund_position', None, 'codes.csv') == FUND_CODES


def test_target_file_stock_branch(orch):
    assert resolve_job_targets(orch, 'price_history', None, 'codes.csv') == STOCK_CODES


@pytest.mark.parametrize('job', ['fund_nav', 'fund_detail_enrich', 'fund_manager'])
def test_other_per_target_jobs_keep_none_semantics(orch, job):
    """`None` 对这些 job 是「子类自取核心池」的既有语义，不得被改成显式列表。

    赋成显式列表会把执行切到 `_execute_batches` 分批路径 —— 属行为变更，需单独评估。
    """
    assert job not in DB_POOL_JOBS
    assert resolve_job_targets(orch, job, None, None) is None


def test_unknown_job_with_target_file_stays_none(orch):
    """`--target-file` 给了但 job 不认这类代码时，仍保持 None（与改动前一致）。"""
    assert resolve_job_targets(orch, 'temperature', None, 'codes.csv') is None


def test_db_pool_jobs_only_contains_fund_position():
    """锁住范围：这份表只应放「None 会被当成显式跳过」的 job。"""
    assert DB_POOL_JOBS == {'fund_position': 'fund'}
