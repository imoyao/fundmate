# -*- coding: utf-8 -*-
"""测试 DataSyncOrchestrator 的调度和锁机制"""

from unittest.mock import MagicMock, patch

import pytest

from app.models.sync_log import SyncLog
from app.services.sync.orchestrator import DataSyncOrchestrator


class TestOrchestratorIntegration:
    @pytest.fixture
    def mock_akshare(self):
        """Mock AkshareAdapter"""
        with patch('app.services.sync.adapters.akshare_adapter.AkshareAdapter') as mock:
            instance = mock.return_value
            instance.get_name.return_value = 'akshare'
            instance.get_version.return_value = '1.0'
            instance.fetch_stock_list.return_value = [
                {'symbol': 'SH600519', 'name': '茅台', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'},
                {'symbol': 'SZ000001', 'name': '平安', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'},
            ]
            yield mock

    def test_run_stock_list_job(self, db, mock_akshare):
        orch = DataSyncOrchestrator(db)
        orch.data_sources['akshare'] = mock_akshare.return_value
        from app.services.sync.jobs.stock_list_job import StockListSyncJob

        orch.jobs['stock_list'] = StockListSyncJob(orch.data_sources['akshare'], db)
        # 传入任意 targets（列表不为空，否则 _allow_empty_data 需为 True）
        result = orch.run_job('stock_list', full_sync=True, targets=['dummy'])
        assert result['status'] == 'success'
        assert result['stats']['success'] == 2

    def test_single_instance_lock(self, db):
        orch = DataSyncOrchestrator(db)
        with patch('app.services.sync.orchestrator.acquire_lock', return_value=(False, None)):
            with pytest.raises(RuntimeError, match='另一个同步进程正在运行'):
                orch.run_all_jobs()


class TestExecuteJobErrorAudit:
    """`_execute_job` 异常路径的审计落库（#1402）。

    背景：`run_job` 只在 `job.run` **正常返回**后才写 `sync_logs`；job 抛异常时全链路
    无记录，导致「某 job 到底跑没跑过」无法从审计表回答。
    """

    @staticmethod
    def _boom_job(adapter_name='boom-src', snapshot_time=None):
        """构造一个 run() 必抛异常、且可能「还没来得及进 run」的假 job"""

        class _BoomJob:
            def __init__(self):
                self.adapter = MagicMock()
                self.adapter.get_name.return_value = adapter_name
                self.adapter.get_version.return_value = '0.1'
                # 未进入 run() 就炸的场景：snapshot_time 仍是 None
                self.snapshot_time = snapshot_time

            def run(self, *args, **kwargs):
                raise RuntimeError('上游接口 500')

        return _BoomJob()

    def test_exception_writes_error_row_and_returns_error(self, db):
        orch = DataSyncOrchestrator(db)
        orch.jobs['boom'] = self._boom_job()

        result = orch._execute_job('boom', full_sync=False, targets=['x'])

        assert result['status'] == 'error'
        assert '上游接口 500' in result['error']

        db.expire_all()
        rows = db.query(SyncLog).filter_by(job_name='boom').all()
        assert len(rows) == 1
        assert rows[0].status == 'error'
        assert '上游接口 500' in rows[0].error_detail
        assert rows[0].data_source == 'boom-src'
        # started_at 是 NOT NULL 列，job 没进 run() 时必须兜底为当前时间
        assert rows[0].started_at is not None

    def test_unknown_job_name_still_audited_without_raising(self, db):
        """未注册的 job 名（run_job 抛 ValueError）也要留痕，且不得炸出 KeyError"""
        orch = DataSyncOrchestrator(db)

        result = orch._execute_job('__不存在的任务__', full_sync=False)

        assert result['status'] == 'error'
        assert '未知任务' in result['error']

        db.expire_all()
        rows = db.query(SyncLog).filter_by(job_name='__不存在的任务__').all()
        assert len(rows) == 1
        assert rows[0].status == 'error'
        assert rows[0].data_source is None
        assert rows[0].started_at is not None

    def test_error_audit_failure_does_not_mask_original_exception(self, db):
        """审计写入自身失败时，原始异常仍须照常返回。

        职责边界：本方法存在的意义是「让失败可见」，若它自己炸掉并向上抛，
        调用方拿到的错误就变成了审计错误、真因被掩盖。此处让落库 commit 失败，
        断言返回的仍是原始的上游错误。
        """
        orch = DataSyncOrchestrator(db)
        orch.jobs['boom'] = self._boom_job()

        with patch.object(orch.db, 'commit', side_effect=RuntimeError('审计写库失败')):
            result = orch._execute_job('boom', full_sync=False, targets=['x'])

        assert result['status'] == 'error'
        assert '上游接口 500' in result['error']


class TestExecutionPlanCoversAllJobs:
    """`execution_plan` 必须覆盖 `_register_jobs()` 注册的**全部** job（#1460 修复）。

    背景：`temperature` / `index_valuation` / `convertible_bond` / `amac_institution` /
    `channel_link` 这 5 个 job **注册了却从未进过 `execution_plan`**（`git log -S` 证实是
    历史遗漏而非有意排除）。后果是 `grab.all` / `pdm run sync --all` / CI 的
    `pdm run scheduler` 都不刷新温度计（连带 bias 乖离率、industry_crowding 拥挤度——
    它们跑在 `TemperatureJob` 内部），而 `backend/tasks.py` 与 `tools/sync_cli.py`
    的文案却写着「全部同步任务（元数据 + 温度）」——文案与实现不一致。

    本测试是**回归防线**：新增 job 却忘了进计划，会在这里红。
    """

    @staticmethod
    def _plan_job_names(orch, monkeypatch):
        """跑一遍 run_all_jobs 但只记录执行了哪些 job（不真跑、不备份库）。"""
        seen = []

        def _record(job_name, full_sync, targets=None):
            seen.append(job_name)
            return {'job_name': job_name, 'status': 'success'}

        monkeypatch.setattr(orch, '_execute_job', _record)
        monkeypatch.setattr(orch, '_backup_database', lambda: None)
        monkeypatch.setattr('app.services.sync.orchestrator.acquire_lock', lambda *a, **k: (True, None))
        orch.run_all_jobs()
        return seen

    def test_plan_covers_every_registered_job(self, db, monkeypatch):
        orch = DataSyncOrchestrator(db)
        plan = self._plan_job_names(orch, monkeypatch)

        missing = sorted(set(orch.jobs) - set(plan))
        assert not missing, f'以下 job 已注册但不在 execution_plan，grab.all 会静默漏跑：{missing}'
        extra = sorted(set(plan) - set(orch.jobs))
        assert not extra, f'execution_plan 里有未注册的 job：{extra}'

    def test_previously_missing_jobs_are_now_planned(self, db, monkeypatch):
        """#1460 顺带修复：这 5 个 job 必须回到计划里。"""
        orch = DataSyncOrchestrator(db)
        plan = set(self._plan_job_names(orch, monkeypatch))
        for name in ('temperature', 'index_valuation', 'convertible_bond', 'amac_institution', 'channel_link'):
            assert name in plan, f'{name} 未进 execution_plan'

    def test_market_snapshot_registered_and_planned(self, db, monkeypatch):
        """#1460：探市快照 job 必须注册且进计划（否则读库路径永远拿不到数据）。"""
        orch = DataSyncOrchestrator(db)
        assert 'market_snapshot' in orch.jobs
        assert orch.jobs['market_snapshot'].get_name() == 'market_snapshot'
        assert 'market_snapshot' in set(self._plan_job_names(orch, monkeypatch))

    def test_no_target_pool_jobs_pass_none_not_empty_list(self, db, monkeypatch):
        """无目标池的 job 必须传 `None`，不能传 `[]` 或 `['__full__']`。

        - `[]` 会被基类 `SyncJob.run()` 当成「空目标池」→ 直接跳过（这些 job 的
          `_allow_empty_data=True`），**静默空跑**；
        - `['__full__']` 只对显式过滤该哨兵值的 job 安全：`IndexValuationSyncJob` 是
          `codes = targets if targets else INDEX_VALUATION_TARGETS`，传 `['__full__']`
          会真去抓一个字面代码 `'__full__'`。
        """
        orch = DataSyncOrchestrator(db)
        captured = {}

        def _record(job_name, full_sync, targets=None):
            captured[job_name] = targets
            return {'job_name': job_name, 'status': 'success'}

        monkeypatch.setattr(orch, '_execute_job', _record)
        monkeypatch.setattr(orch, '_backup_database', lambda: None)
        monkeypatch.setattr('app.services.sync.orchestrator.acquire_lock', lambda *a, **k: (True, None))
        orch.run_all_jobs()

        for name in ('temperature', 'index_valuation', 'convertible_bond', 'amac_institution', 'channel_link'):
            assert captured.get(name) is None, f'{name} 应传 None，实际 {captured.get(name)!r}'
