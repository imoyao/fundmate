# -*- coding: utf-8 -*-
"""每日调度的「预算分配」回归网（#1490）。

事故形态（2026-10-22 实测 run 39797606370）：每日调度在 CI 上 90 分钟被掐，
而时间全花在两个**全市场名录** job 上——`stock_list` 29.4 分钟（东财 ETF 名录 502 →
回退同花顺）、`fund_list` 又跑了 52 分钟未完。它们当时排在执行计划**最前面**，
于是 `fund_nav` / `price_history` / `asset_snapshot` 这些「当天必须刷新」的 job
一次都没轮到 ⇒ 用户看到的净值永远是旧值，**连「部分完成」都做不到**。

本文件钉住三件事：
1. 名录类 job 周频门控：距上次**成功**不足 6 天即跳过；失败记录**不**计入频控；
2. `skipped` 既不算成功也不算失败（退 0、不进 `failed` 栏），否则每周会有 6 天红灯；
3. 执行计划的顺序：核心数据 job 必须排在名录类 job **之前**。
"""

from datetime import timedelta

import pytest

from app.core.time_utils import now_shanghai
from app.models.sync_log import SyncLog
from app.services.sync.orchestrator import (
    WEEKLY_JOB_MIN_INTERVAL_DAYS,
    WEEKLY_JOBS,
    DataSyncOrchestrator,
    build_execution_plan,
)
from app.tools.scheduler import EXIT_OK, build_run_summary, scheduler_exit_code


def _log(db, job_name: str, status: str, days_ago: float) -> None:
    """写一条 sync_logs 记录。

    `started_at` 在库里是 **naive 的东八区墙钟时间**（与生产写入口径一致），
    故意不写 aware——那才是 `_skip_if_recent` 实际会遇到的数据形态。
    """
    started = now_shanghai().replace(tzinfo=None) - timedelta(days=days_ago)
    db.add(SyncLog(job_name=job_name, status=status, full_sync=False, started_at=started))
    db.commit()


def _orchestrator(db) -> DataSyncOrchestrator:
    return DataSyncOrchestrator(db)


class TestWeeklyGate:
    def test_weekly_job_skipped_when_recent_success(self, db):
        """1 天前刚成功过 ⇒ 跳过，且理由里说清「距上次成功多少天」。"""
        _log(db, 'stock_list', 'success', days_ago=1)
        result = _orchestrator(db)._skip_if_recent('stock_list')

        assert result is not None
        assert result['status'] == 'skipped'
        assert result['job_name'] == 'stock_list'
        assert '天' in result['reason']
        assert result['stats']['last_success_at']

    def test_weekly_job_runs_when_last_success_old(self, db):
        """超过 6 天 ⇒ 照常执行（周频不是「永不执行」）。"""
        _log(db, 'fund_list', 'success', days_ago=WEEKLY_JOB_MIN_INTERVAL_DAYS + 4)
        assert _orchestrator(db)._skip_if_recent('fund_list') is None

    def test_weekly_job_runs_without_history(self, db):
        """没有任何记录（新库 / 首次部署）⇒ 必须执行，不能因为「没跑过」而跳过。"""
        assert _orchestrator(db)._skip_if_recent('fund_list') is None

    def test_failed_log_does_not_count(self, db):
        """失败记录不计入频控：昨天失败、今天该重试，不能被当成「刚跑过」永久跳过。"""
        _log(db, 'stock_list', 'error', days_ago=0.5)
        assert _orchestrator(db)._skip_if_recent('stock_list') is None

    def test_non_weekly_job_never_skipped(self, db):
        """核心数据 job（fund_nav）即使 1 小时前刚成功过也必须执行——它就是要每天刷。"""
        _log(db, 'fund_nav', 'success', days_ago=0.04)
        assert _orchestrator(db)._skip_if_recent('fund_nav') is None

    @pytest.mark.parametrize('job_name', WEEKLY_JOBS)
    def test_all_weekly_jobs_are_gated(self, db, job_name):
        """`WEEKLY_JOBS` 里每一个都必须真的受门控（漏一个就等于没改）。"""
        _log(db, job_name, 'success', days_ago=1)
        assert _orchestrator(db)._skip_if_recent(job_name) is not None


class TestSkippedIsNotFailure:
    def test_skipped_does_not_redden_the_run(self):
        """跳过的名录 job 不能把整轮判失败，否则每周有 6 天红灯。"""
        results = {
            'fund_nav': {'status': 'success'},
            'stock_list': {'status': 'skipped'},
        }
        assert scheduler_exit_code(results) == EXIT_OK

    def test_real_failure_still_reddens(self):
        """真失败照旧红——门控不能顺手把失败也饶过去。"""
        results = {'fund_nav': {'status': 'success'}, 'stock_list': {'status': 'error'}}
        assert scheduler_exit_code(results) != EXIT_OK

    def test_summary_separates_skipped_from_failed(self):
        """摘要里 skipped 单独成栏，不进 failed（告警卡正文按 failed 点名）。"""
        summary = build_run_summary(
            {
                'fund_nav': {'status': 'success'},
                'stock_list': {'status': 'skipped'},
                'fund_list': {'status': 'error'},
            },
            elapsed=1.0,
        )
        assert summary['skipped'] == ['stock_list']
        assert summary['failed'] == ['fund_list']
        assert summary['total'] == 3


class TestExecutionPlanOrder:
    """顺序即优先级：跑不完时，必须保证「用户当天要看的数据」已经跑过。"""

    @staticmethod
    def _names():
        plan = build_execution_plan({'fund': ['000001'], 'stock': ['SH600519'], 'etf': ['SH510300']})
        return [name for name, _targets in plan]

    def test_core_data_before_catalog(self):
        names = self._names()
        core = ('fund_nav', 'price_history', 'asset_snapshot')
        catalog = ('stock_list', 'fund_list', 'index_catalog')
        for job in core:
            assert names.index(job) < names.index(catalog[0]), f'{job} 必须排在名录类之前'
        for job in catalog:
            assert names.index(job) > names.index('asset_snapshot'), f'{job} 应排在快照之后'

    def test_asset_snapshot_after_its_inputs(self):
        """快照读的是 current_price / 风险指标，必须排在这两者之后（#1104 / #167）。"""
        names = self._names()
        assert names.index('asset_snapshot') > names.index('position_price')
        assert names.index('asset_snapshot') > names.index('fund_risk_metrics')
        assert names.index('asset_snapshot') > names.index('fund_nav')

    def test_plan_covers_every_registered_plan_job(self):
        """去重且不缺项：漏一个 job 就等于「悄悄停更」。"""
        names = self._names()
        assert len(names) == len(set(names))
        assert set(names) == set(
            {
                'fund_nav',
                'price_history',
                'dividend_split',
                'position_price',
                'fund_risk_metrics',
                'asset_snapshot',
                'market_asset_daily',
                'industry_pbroe',
                'index_daily',
                'index_constituents',
                'fund_detail_enrich',
                'fund_type',
                'fund_scale',
                'fund_position',
                'fund_style',
                'fund_manager',
                'fund_company_backfill',
                'orphan_backfill',
                'advisor_portfolio',
                'stock_list',
                'fund_list',
                'index_catalog',
            }
        )

    def test_targets_flow_into_their_jobs(self):
        """目标池要真的传进对应 job（顺序改了不能把参数接错）。"""
        plan = dict(build_execution_plan({'fund': ['000001'], 'stock': ['SH600519'], 'etf': ['SH510300']}))
        assert plan['fund_nav'] == ['000001']
        assert plan['price_history'] == ['SH600519']
        # #1983：场内 ETF 裸码只进 fund_position / fund_style，不进 fund_nav
        assert plan['fund_position'] == ['000001', 'SH510300']
        assert plan['fund_style'] == ['000001', 'SH510300']
