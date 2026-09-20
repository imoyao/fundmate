# -*- coding: utf-8 -*-
"""测试 DataSyncOrchestrator 的调度和锁机制"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.time_utils import now_shanghai
from app.domains.funds.models import DailyWorth, Fund
from app.models.sync_log import SyncLog
from app.services.sync.orchestrator import DataSyncOrchestrator


class TestOrchestratorIntegration:
    @pytest.fixture
    def mock_akshare(self):
        """Mock AkshareAdapter"""
        with patch('app.services.adapters.akshare_adapter.AkshareAdapter') as mock:
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


class TestRunJobAuditSurvivesPoisonedSession:
    """#1550 第 3 环：`job.run()` 正常返回 ≠ Session 健康，审计仍必须留痕。

    案发形态（2026-09-16）：job 内部批量写入 flush 撞唯一约束后把 Session 留在
    必须先 rollback 的状态，`job.run` 照常返回结果；`run_job` 随后写 `sync_logs`
    时 commit 抛 PendingRollbackError 并冒泡出去，`daily_scheduler` 只做
    `logger.exception` 吞掉——`sync_logs` 里连一行都没有，`fund_nav` 因此静默失败
    整整一个月（最后一条成功记录停在 2026-08-14 / id=128）。
    """

    @staticmethod
    def _poisoning_job(db):
        """run() 先污染 Session（模拟 flush 撞唯一约束）再返回失败结果。

        刻意**不在 run() 里 commit**：让事务停在「必须 rollback」的状态，
        正是案发形态（job 吞掉 IntegrityError、照常返回结果，Session 已中毒）。
        """

        class _PoisoningJob:
            def __init__(self):
                self.adapter = MagicMock()
                self.adapter.get_name.return_value = 'poisoned-src'
                self.adapter.get_version.return_value = '0.1'
                self.snapshot_time = None

            def run(self, *args, **kwargs):
                self.snapshot_time = now_shanghai()
                # 与测试预置的行同键 → flush 撞唯一约束
                db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 1), unit_nav=1.0))
                try:
                    db.flush()
                except IntegrityError:
                    pass
                return {'status': 'manual_intervention', 'stats': {'errors': ['UNIQUE constraint failed']}}

        return _PoisoningJob()

    def test_audit_row_written_even_when_session_is_poisoned(self, db):
        _seed_daily_worth_row(db)
        orch = DataSyncOrchestrator(db)
        orch.jobs['poisoned'] = self._poisoning_job(db)

        result = orch.run_job('poisoned', full_sync=False, targets=['000001'])

        assert result['status'] == 'manual_intervention', 'run_job 不得把审计异常替换成新异常'
        db.expire_all()
        rows = db.query(SyncLog).filter_by(job_name='poisoned').all()
        assert len(rows) == 1, '审计表必须留下「跑过且失败」这一行'
        assert rows[0].status == 'manual_intervention', '降级记录须保留 job 真实终态，而非一律 error'

    def test_audit_failure_never_bubbles_out_of_run_job(self, db):
        """审计连挂两次时，run_job 仍须正常返回结果（不能让审计把任务带崩）"""
        _seed_daily_worth_row(db)
        orch = DataSyncOrchestrator(db)
        orch.jobs['poisoned'] = self._poisoning_job(db)

        with patch.object(orch.db, 'commit', side_effect=RuntimeError('磁盘只读')):
            result = orch.run_job('poisoned', full_sync=False, targets=['000001'])

        assert result['status'] == 'manual_intervention'


def _seed_daily_worth_row(db) -> None:
    """预置一行 daily_worth，用于构造「flush 撞唯一约束」的中毒场景"""
    if not db.query(Fund).filter_by(fund_code='000001').first():
        db.add(Fund(fund_code='000001', name='测试基金'))
    db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 1), unit_nav=1.0))
    db.commit()
