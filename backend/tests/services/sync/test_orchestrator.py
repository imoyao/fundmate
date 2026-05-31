# -*- coding: utf-8 -*-
"""测试 DataSyncOrchestrator 的调度和锁机制"""

from unittest.mock import patch

import pytest

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
