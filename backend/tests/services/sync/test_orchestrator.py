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
