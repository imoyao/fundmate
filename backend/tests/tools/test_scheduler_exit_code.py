# -*- coding: utf-8 -*-
"""每日调度的「job 级失败可见性」回归网（#2457）。

事故形态：编排器逐 job 兜住异常并写 `sync_logs`，但 `app/tools/scheduler.py`
只把失败 job 名打进日志、**进程照样退 0** ⇒ workflow 判绿 ⇒ 末尾的「失败告警」
步骤（`if: failure()`）不触发 ⇒ **半个链路坏了却没有任何告警**。

本文件钉住三件事：
1. 有 job 失败 ⇒ 退出码非 0；
2. 全部成功 ⇒ 仍退 0（不制造常态红灯）；
3. 退出前把逐 job 结果写成机器可读摘要（告警卡正文要靠它指名道姓）。

#3083 追加第四条：**巡检结论必须进摘要**。`run_due_checks` 原来跑在 `write_run_summary`
之后，判了 `bloated` 也只有日志里一行 warning，workflow 判绿 ⇒ 「判了膨胀，谁看得见？」
的答案是没人。判据分两层：摘要结构（本文件）+ 调用顺序（`test_local_checks` 的 ast 断言）。
"""

import ast
import json
from pathlib import Path

from app.tools.scheduler import (
    EXIT_CRASH,
    EXIT_JOB_FAILED,
    EXIT_OK,
    build_run_summary,
    scheduler_exit_code,
    write_run_summary,
)

SCHEDULER_SRC = Path(__file__).resolve().parents[2] / 'app' / 'tools' / 'scheduler.py'


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


class TestCheckResultsInSummary:
    """巡检结论必须落进摘要，否则「判了膨胀」只活在日志里（#3083）。"""

    def test_bloated_check_lands_in_summary(self):
        checks = [
            {'job_name': 'cold_set_bloat_guard', 'status': 'bloated', 'stats': {'total_stale': 93375, 'growth': 14734}}
        ]
        summary = build_run_summary(_results(a='success'), 3.0, checks=checks)

        assert summary['checks']['cold_set_bloat_guard']['status'] == 'bloated'
        # 数字也要进摘要：卡正文写「膨胀 +14734」才有意义，只写「有异常」还得翻库。
        assert summary['checks']['cold_set_bloat_guard']['stats']['growth'] == 14734
        assert summary['checks_attention'] == ['cold_set_bloat_guard']

    def test_healthy_check_not_in_attention(self):
        """`ok` / `success` 都算健康；漏判会让健康巡检天天开卡（红灯失去可信度）。"""
        checks = [
            {'job_name': 'guard_a', 'status': 'ok'},
            {'job_name': 'guard_b', 'status': 'success'},
        ]
        summary = build_run_summary(_results(a='success'), 1.0, checks=checks)
        assert summary['checks_attention'] == []

    def test_error_check_needs_attention(self):
        """`error` 不能因为「没算出异常」被读成健康。"""
        summary = build_run_summary(_results(a='success'), 1.0, checks=[{'job_name': 'g', 'status': 'error'}])
        assert summary['checks_attention'] == ['g']

    def test_check_keys_absent_when_not_passed(self):
        """未传 `checks` ⇒ 键不出现 = 「说不清」，与「本轮无到期巡检」（空 dict）区分。"""
        summary = build_run_summary(_results(a='success'), 1.0)
        assert 'checks' not in summary
        assert 'checks_attention' not in summary

    def test_empty_check_list_is_present_but_empty(self):
        """传空列表 ⇒ 键存在且为空 = 「本轮没有到期巡检」，可被渲染成 `none`。"""
        summary = build_run_summary(_results(a='success'), 1.0, checks=[])
        assert summary['checks'] == {}
        assert summary['checks_attention'] == []

    def test_summary_with_checks_survives_json_roundtrip(self, tmp_path):
        """摘要要落盘再被 `daily_run_alert.py` 读回——`stats` 里不能有非 JSON 类型。"""
        checks = [{'job_name': 'g', 'status': 'bloated', 'stats': {'growth': 14734}}]
        path = write_run_summary(build_run_summary(_results(a='success'), 1.0, checks=checks), tmp_path / 's.json')
        saved = json.loads(path.read_text(encoding='utf-8'))
        assert saved['checks']['g']['status'] == 'bloated'
        assert saved['checks_attention'] == ['g']


class TestCheckCallOrder:
    """顺序判据：巡检必须在 `build_run_summary` **之前**跑（#3083）。

    放在之后 ⇒ 结论落在摘要之外，只剩日志一行，而 workflow 判绿、卡不触发。
    这条只能用 ast 读源码：`app.tools.scheduler` 顶层会加载 ORM 与 dotenv。
    """

    @staticmethod
    def _main_calls():
        src = SCHEDULER_SRC
        tree = ast.parse(src.read_text(encoding='utf-8'), filename=str(src))
        main = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'main')
        return [n for n in ast.walk(main) if isinstance(n, ast.Call)]

    def test_due_checks_runs_before_summary_build(self):
        calls = self._main_calls()

        def lines(pred):
            return [c.lineno for c in calls if pred(c)]

        due = lines(lambda c: isinstance(c.func, ast.Name) and c.func.id == 'run_due_checks')
        build = lines(lambda c: isinstance(c.func, ast.Name) and c.func.id == 'build_run_summary')
        assert due, '一次性路径没调 run_due_checks ⇒ 巡检在 CI 上等于不存在'
        assert build and due[0] < build[0], '巡检必须在 build_run_summary 之前跑，否则结论进不了摘要'

    def test_checks_passed_into_summary(self):
        """只「先跑」还不够：结果必须作为 `checks=` 传给摘要，否则照样看不见。"""
        calls = self._main_calls()
        build = [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == 'build_run_summary']
        assert build, 'main() 里没有 build_run_summary 调用'
        keywords = {kw.arg for c in build for kw in (c.keywords or [])}
        assert 'checks' in keywords, 'build_run_summary 没收到 checks= ⇒ 巡检结论不会进摘要'
