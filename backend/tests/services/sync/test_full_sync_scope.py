# -*- coding: utf-8 -*-
"""测试 --full-sync 范围强制校验与 T 日净值护栏（#824 / #1776 ④）"""

from datetime import date, timedelta

import pytest

from app.services.sync.jobs.fund_nav_job import FundNavSyncJob
from app.services.sync.orchestrator import SYMBOL_BACKFILL_JOBS, require_full_sync_scope


class TestRequireFullSyncScope:
    def test_incremental_no_scope_ok(self):
        # 增量同步无需范围
        require_full_sync_scope('fund_nav', full_sync=False, has_targets=False)

    def test_backfill_job_with_targets_ok(self):
        require_full_sync_scope('fund_nav', full_sync=True, has_targets=True)

    def test_backfill_job_bare_full_sync_rejected(self):
        with pytest.raises(ValueError):
            require_full_sync_scope('fund_nav', full_sync=True, has_targets=False)

    def test_list_job_bare_full_sync_ok(self):
        # 列表 / 指数型 Job 裸 --full-sync 是正常模式（全市场刷新，不依赖用户目标池）
        require_full_sync_scope('fund_list', full_sync=True, has_targets=False)
        require_full_sync_scope('index_daily', full_sync=True, has_targets=False)

    def test_temperature_bare_full_sync_ok(self):
        require_full_sync_scope('temperature', full_sync=True, has_targets=False)

    def test_symbol_backfill_jobs_complete(self):
        # 与 run_all_jobs 执行计划中的逐标的 Job 保持一致
        expected = {
            'fund_nav',
            'price_history',
            'fund_detail_enrich',
            'fund_manager',
            'fund_type',
            'fund_company_backfill',
            'fund_position',
            'position_price',
            'dividend_split',
        }
        assert SYMBOL_BACKFILL_JOBS == expected


class TestFundNavTMinusOneGuard:
    @pytest.fixture
    def job(self, db):
        from unittest.mock import MagicMock

        adapter = MagicMock()
        return FundNavSyncJob(adapter, db)

    def test_today_nav_dropped(self, job):
        raw = [
            {'fund_code': '000001', 'date': date.today(), 'unit_nav': 1.234},
            {'fund_code': '000001', 'date': date.today() - timedelta(days=1), 'unit_nav': 1.2},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['date'] == date.today() - timedelta(days=1)

    def test_future_nav_dropped(self, job):
        raw = [{'fund_code': '000001', 'date': date.today() + timedelta(days=3), 'unit_nav': 1.0}]
        assert job._validate_data(raw) == []

    def test_past_nav_kept(self, job):
        raw = [{'fund_code': '000001', 'date': date(2025, 1, 2), 'unit_nav': 1.234}]
        assert len(job._validate_data(raw)) == 1
