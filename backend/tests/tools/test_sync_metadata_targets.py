# -*- coding: utf-8 -*-
"""`--job` 的目标池解析（#870 回归，2026-10-01 生产复现）。

案发形态：`pdm run sync --job fund_position`（AGENTS.md 与 PR #1804 正文都这么写）
拿到 `targets=None`，而该 job 对 `None` 的语义是「目标池为空 → 显式跳过」，
于是**先静默跑成 0 只**，再因 `run_job` 的 duration 算 `datetime - None` 抛
TypeError 以 exit 1 收尾——手工回填的人只会看到「同步失败」，不知道其实一条都没抓。

两个独立成因：
1. `--target-file` 的基金分支里没有 `fund_position`（job 名硬编码在元组里）；
2. 不给任何显式目标时，CLI 不会像 `daily_scheduler` 那样从库里取核心池。

#1983 遗留①：resolve_targets() 现在分出 fund / stock / etf 三池，
fund_position 需要 fund + etf 两池（场内 ETF 的底层持仓 / 行业配置
同样要抓），与 daily_scheduler 的 target_kind=('fund', 'etf') 同源。
"""

from unittest.mock import MagicMock

import pytest

from app.tools.sync_metadata import (
    DB_POOL_JOBS,
    FUND_TARGET_JOBS,
    STOCK_TARGET_JOBS,
    _combine_pools,
    resolve_job_targets,
)

FUND_CODES = ['000001', '110022']
STOCK_CODES = ['SH600519']
ETF_CODES = ['159857']


@pytest.fixture
def orch():
    """最小 orchestrator 替身：只提供 `resolve_targets`。"""
    o = MagicMock()
    o.resolve_targets.return_value = {
        'fund': list(FUND_CODES),
        'stock': list(STOCK_CODES),
        'etf': list(ETF_CODES),
    }
    return o


def test_fund_position_without_explicit_targets_takes_db_pool(orch):
    """裸调用必须解析出库内核心池（fund + etf 两池）——这是 CLI 与调度器的语义对齐点。"""
    resolved = resolve_job_targets(orch, 'fund_position', None, None)
    assert resolved == FUND_CODES + ETF_CODES
    # etf 池确实被并入（#1983：调度侧 target_kind=('fund','etf')，CLI 同源覆盖）
    assert ETF_CODES[0] in resolved
    orch.resolve_targets.assert_called_once_with()


def test_explicit_targets_win(orch):
    assert resolve_job_targets(orch, 'fund_position', '000001, 000002 ', None) == ['000001', '000002']


def test_target_file_works_for_fund_position(orch):
    """回归：`fund_position` 原先不在基金分支的元组里，`--target-file` 对它无效。"""
    assert 'fund_position' in FUND_TARGET_JOBS
    assert resolve_job_targets(orch, 'fund_position', None, 'codes.csv') == FUND_CODES + ETF_CODES


def test_target_file_fund_nav_only_takes_fund_pool(orch):
    """钉住「只有 fund_position 吃 etf 池」：fund_nav 的 --target-file 仍只取 fund 池。"""
    assert 'fund_nav' not in DB_POOL_JOBS
    assert resolve_job_targets(orch, 'fund_nav', None, 'codes.csv') == FUND_CODES


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


def test_db_pool_jobs_scope_is_explicit():
    """锁住范围：这份表只放「`None` 会被当成显式跳过」的 job，值为池键（str 或元组）。"""
    assert DB_POOL_JOBS == {
        'fund_position': ('fund', 'etf'),
        'bond_adjust_log': 'stock',
        'fund_style': ('fund', 'etf'),
    }


def test_fund_style_cli_takes_core_pool(orch):
    """#2628：风格箱 job 与 fund_position 同形——裸调用取库内核心池（fund + etf）。

    漏登记的后果不是「少一个池」而是**整条 CLI 入口失效**：`--targets` 会被
    静默忽略、跑成 `total=0 / status=success`（2026-10-27 实测）。
    """
    assert resolve_job_targets(orch, 'fund_style', None, None) == FUND_CODES + ETF_CODES


def test_fund_style_cli_honors_explicit_targets(orch):
    """显式 `--targets` 必须优先于库内核心池，且能逗号分隔。"""
    assert resolve_job_targets(orch, 'fund_style', '110011, 000001 ', None) == ['110011', '000001']
    orch.resolve_targets.assert_not_called()


def test_fund_style_cli_honors_target_file(orch):
    """`--target-file` 同样走 fund + etf 两池（与 daily_scheduler 同源覆盖）。"""
    assert resolve_job_targets(orch, 'fund_style', None, 'codes.csv') == FUND_CODES + ETF_CODES
    assert 'fund_style' not in FUND_TARGET_JOBS, '风格箱不按日期回填，不该混进 FUND_TARGET_JOBS'


def test_bond_adjust_log_takes_stock_pool_and_filters_nothing(orch):
    """#2585：转债落在 stock 池（带前缀符号），池里混着股票/ETF —— 由 job 按前缀过滤。

    CLI 这一层不做转债过滤：它只负责「把用户触达范围交出去」，
    多交出来的股票/ETF 会被 job 记进 `not_bond`（不是失败）。
    """
    assert resolve_job_targets(orch, 'bond_adjust_log', None, None) == STOCK_CODES
    # --target-file 同样走 stock 池（漏登记会静默退化成 0 只处理）
    assert 'bond_adjust_log' in STOCK_TARGET_JOBS
    assert resolve_job_targets(orch, 'bond_adjust_log', None, 'codes.csv') == STOCK_CODES


def test_combine_pools_dedup_preserves_order():
    """同一裸码同时出现在 fund 与 etf 池时只保留一次，顺序保 fund 先（#1983）。"""
    resolved = {'fund': ['159857', '000001'], 'stock': [], 'etf': ['159857', '159919']}
    assert _combine_pools(resolved, DB_POOL_JOBS['fund_position']) == ['159857', '000001', '159919']


def test_combine_pools_accepts_single_str_key():
    """防御性：池键为单个 str（DB_POOL_JOBS 的旧值形态）时拼池行为不变。"""
    resolved = {'fund': ['000001'], 'etf': ['159857']}
    assert _combine_pools(resolved, 'fund') == ['000001']
