# -*- coding: utf-8 -*-
"""每日调度的「job 级失败可见性」回归网（#2457）。

事故形态：编排器逐 job 兜住异常并写 `sync_logs`，但 `app/tools/scheduler.py`
只把失败 job 名打进日志、**进程照样退 0** ⇒ workflow 判绿 ⇒ 末尾的「失败告警」
步骤（`if: failure()`）不触发 ⇒ **半个链路坏了却没有任何告警**。

本文件钉住三件事：
1. 有 job 失败 ⇒ 退出码非 0；
2. 全部成功 ⇒ 仍退 0（不制造常态红灯）；
3. 退出前把逐 job 结果写成机器可读摘要（告警卡正文要靠它指名道姓）。
"""

import json

from app.tools.scheduler import (
    EXIT_CRASH,
    EXIT_JOB_FAILED,
    EXIT_OK,
    build_run_summary,
    scheduler_exit_code,
    write_run_summary,
)


def _results(**statuses):
    return {name: {'status': status} for name, status in statuses.items()}


def test_failed_jobs_exit_nonzero():
    """有 job 失败 ⇒ 退出码非 0（否则告警链路不触发）。"""
    results = _results(fund_nav='success', price_history='failed', asset_snapshot='success')
    assert scheduler_exit_code(results) == EXIT_JOB_FAILED
    assert EXIT_JOB_FAILED != 0


def test_all_success_exits_zero():
    """全部成功 ⇒ 仍退 0（不能把常态变成红灯）。"""
    results = _results(fund_nav='success', price_history='success')
    assert scheduler_exit_code(results) == EXIT_OK


def test_empty_results_exit_zero():
    """一个 job 都没跑（结果为空）不算失败——那是「没东西可跑」，不是「跑坏了」。"""
    assert scheduler_exit_code({}) == EXIT_OK


def test_manual_intervention_counts_as_failure():
    """`manual_intervention`（重试后仍失败）也是失败，不能当成功。"""
    results = _results(fund_nav='manual_intervention')
    assert scheduler_exit_code(results) == EXIT_JOB_FAILED


def test_exit_codes_are_distinct():
    """「调度崩了」(1) 与「跑完但有 job 失败」(2) 必须能区分。"""
    assert EXIT_CRASH != EXIT_JOB_FAILED
    assert EXIT_OK == 0


def test_summary_file_written(tmp_path):
    """逐 job 结果要落成机器可读摘要（告警卡正文靠它指名道姓）。"""
    results = _results(fund_nav='success', price_history='failed')
    summary = build_run_summary(results, elapsed=12.34)

    assert summary['failed'] == ['price_history']
    assert summary['total'] == 2
    assert summary['jobs']['fund_nav'] == 'success'

    path = write_run_summary(summary, tmp_path / 'last_run_summary.json')
    assert path.is_file()
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['failed'] == ['price_history']
    assert saved['elapsed_seconds'] == 12.3


def test_summary_write_is_atomic(tmp_path):
    """原子写：不留 .tmp 残file，中途失败也不会读到半截 JSON。"""
    path = write_run_summary(build_run_summary(_results(a='success'), 1.0), tmp_path / 's.json')
    assert path.is_file()
    assert not (tmp_path / 's.json.tmp').exists()
