# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 12:30
# File : test_orchestrator.py
# -*- coding: utf-8 -*-
"""集成测试：Orchestrator 调度完整 Job"""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.domains.securities.models import Security
from app.services.sync.jobs.stock_list_job import StockListSyncJob
from app.services.sync.orchestrator import DataSyncOrchestrator


class TestOrchestratorIntegration:
    @pytest.fixture
    def mock_akshare(self):
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
        # 第一次运行
        orch = DataSyncOrchestrator(db)
        orch.data_sources['akshare'] = mock_akshare.return_value
        # 重新注册 job，避免使用旧的 job 实例

        orch.jobs['stock_list'] = StockListSyncJob(orch.data_sources['akshare'], db)

        result = orch.run_job('stock_list', full_sync=True)
        assert result['status'] == 'success'
        assert result['stats']['success'] == 2
        assert db.query(Security).count() == 2

        # 第二次运行：创建全新的 orchestrator 和 job 实例
        orch2 = DataSyncOrchestrator(db)
        orch2.data_sources['akshare'] = mock_akshare.return_value
        orch2.jobs['stock_list'] = StockListSyncJob(orch2.data_sources['akshare'], db)

        result2 = orch2.run_job('stock_list', full_sync=True)
        assert result2['stats']['success'] == 0  # 已存在，跳过

    def test_run_all_jobs_order(self, db, mock_akshare):
        """验证 run_all_jobs 按顺序执行且所有 job 成功"""
        # 准备基础数据：stock_list 需要 securities 表为空即可，fund_list 需要 fund_companies 自建，fund_nav 需要基金数据...
        # 为简化，mock 适配器返回一条数据即可。

        mock_akshare_instance = mock_akshare.return_value
        mock_akshare_instance.get_name.return_value = 'akshare'
        mock_akshare_instance.get_version.return_value = '1.0'

        # 设置行情数据（只设置一次）
        mock_akshare_instance.fetch_stock_price.return_value = [
            {
                'symbol': 'SH600519',
                'trade_date': date(2025, 1, 1),
                'open': 100.0,
                'high': 105.0,
                'low': 99.0,
                'close': 102.0,
                'volume': 10000,
                'adj_close': 101.5,
                'source': 'akshare',
            }
        ]
        # 返回一条股票、一条基金
        mock_akshare_instance.fetch_stock_list.return_value = [
            {'symbol': 'SH600519', 'name': '茅台', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'},
        ]
        mock_akshare_instance.fetch_fund_list.return_value = [
            {'fund_code': '000001', 'name': '测试基金', 'company_name': '测试基金公司'},
        ]

        with patch('app.services.sync.adapters.xalpha_adapter.XalphaAdapter') as mock_xa:
            xa_instance = mock_xa.return_value
            xa_instance.get_name.return_value = 'xalpha'
            xa_instance.get_version.return_value = '1.0'
            # fund_manager 返回一个经理，fund_nav 返回一条净值
            xa_instance.fetch_fund_manager.return_value = [
                {'name': '张三', 'mgr_code': 'MGR001', 'appointment_date': None},
            ]
            xa_instance.fetch_fund_nav.return_value = [
                {'fund_code': '000001', 'date': date(2025, 1, 1), 'unit_nav': 1.0, 'acc_nav': 2.0},
            ]

            orch = DataSyncOrchestrator(db)
            orch.data_sources['akshare'] = mock_akshare_instance
            orch.data_sources['xalpha'] = xa_instance
            orch._register_jobs()  # 重新注册

            # 执行
            results = orch.run_all_jobs(full_sync=True)
            assert len(results) == 5
            for name in ['stock_list', 'fund_list', 'fund_manager', 'fund_nav', 'price_history']:
                assert name in results
                # fund_list 和 fund_nav 需要前置基金数据，stock_list 独立，price_history 需 securities 数据
                # 由于 mock 返回了数据，且 fund_list 会创建基金，后续 fund_manager 和 fund_nav 可运行
                assert results[name]['status'] == 'success', f'{name} 失败: {results[name]}'

    def test_single_instance_lock(self, db, tmp_path):
        """验证单实例锁：锁文件存在时抛 RuntimeError"""
        # 临时锁文件路径
        lock_file = tmp_path / 'sync.lock'
        lock_file.touch()

        # 因为 Orchestrator 硬编码了 data/sync.lock，这里通过 monkeypatch 改变工作目录或直接测试锁逻辑
        # 简单的做法：直接验证异常
        orch = DataSyncOrchestrator(db)
        # 我们无法直接修改 run_all_jobs 中的锁路径，所以暂时用 monkeypatch 替换 Path 对象
        # 或者改用更简单的单元测试：直接测试锁机制
        # 这里写一个轻量级验证：如果锁文件存在，run_all_jobs 应该 raise
        # 由于硬编码路径，建议重构 orchestrator 锁路径为可配置，但目前保持简单：
        # 我们可以 patch 锁文件的存在性
        with patch.object(Path, 'exists', return_value=True):
            with pytest.raises(RuntimeError, match='另一个同步进程正在运行'):
                orch.run_all_jobs()
