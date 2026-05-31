# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 12:51
# File : test_price_history_job.py
# -*- coding: utf-8 -*-
"""测试 PriceHistorySyncJob"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.sync.jobs.price_history_job import PriceHistorySyncJob


class TestPriceHistorySyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.get_name.return_value = 'mock_akshare'
        return PriceHistorySyncJob(adapter, db)

    # ── _validate_data ──────────────────────────────

    def test_validate_normal(self, job):
        raw = [
            {
                'security_id': 1,
                'trade_date': date(2025, 1, 2),
                'open': 100.0,
                'high': 105.0,
                'low': 99.0,
                'close': 102.0,
                'volume': 10000,
                'adj_close': 101.5,
                'source': 'akshare',
            }
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        item = validated[0]
        assert item['open'] == 100.0
        assert item['source'] == 'akshare'

    def test_validate_default_adj_close(self, job):
        raw = [
            {'security_id': 1, 'trade_date': date(2025, 1, 2), 'close': 50.0, 'open': 49.0, 'high': 51.0, 'low': 48.0}
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        # 未提供 adj_close 时，应填充为 close
        assert validated[0]['adj_close'] == 50.0
        # source 应被设置为适配器名称
        assert validated[0]['source'] == 'mock_akshare'

    def test_validate_missing_key_fields(self, job):
        raw = [
            {'trade_date': date(2025, 1, 1), 'close': 100.0},  # 缺 security_id
            {'security_id': 1, 'close': 100.0},  # 缺 trade_date
            {'security_id': 1, 'trade_date': date(2025, 1, 2)},  # 缺 close
            {'security_id': 2, 'trade_date': date(2025, 1, 3), 'close': 99.0},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['security_id'] == 2

    # ── _deduplicate ────────────────────────────────

    def test_deduplicate_all_new(self, job, db):
        data = [
            {'security_id': 1, 'trade_date': date(2025, 1, 1), 'close': 10.0},
            {'security_id': 1, 'trade_date': date(2025, 1, 2), 'close': 11.0},
        ]
        new = job._deduplicate(data)
        assert len(new) == 2

    def test_deduplicate_existing(self, job, db):
        # 预存一条行情
        db.add(PriceHistory(security_id=1, trade_date=date(2025, 1, 1), close=10.0))
        db.commit()

        data = [
            {'security_id': 1, 'trade_date': date(2025, 1, 1), 'close': 10.0},
            {'security_id': 1, 'trade_date': date(2025, 1, 2), 'close': 11.0},
            {'security_id': 2, 'trade_date': date(2025, 1, 1), 'close': 20.0},
        ]
        new = job._deduplicate(data)
        assert len(new) == 2
        # 验证排除的记录
        kept = {(item['security_id'], item['trade_date']) for item in new}
        assert (1, date(2025, 1, 1)) not in kept
        assert (1, date(2025, 1, 2)) in kept
        assert (2, date(2025, 1, 1)) in kept

    # ── run 集成 ─────────────────────────────────

    def test_run_integration(self, job, db):
        db.add(Security(symbol='SH600519', name='茅台', market='CN_A', type='stock', currency='CNY'))
        db.commit()
        sec_id = db.query(Security.id).first()[0]

        job.adapter.fetch_stock_price.return_value = [
            {
                'symbol': 'SH600519',
                'trade_date': date(2025, 1, 2),
                'open': 100,
                'high': 105,
                'low': 99,
                'close': 102,
                'volume': 1000,
            },
            {
                'symbol': 'SH600519',
                'trade_date': date(2025, 1, 3),
                'open': 102,
                'high': 106,
                'low': 101,
                'close': 104,
                'volume': 1200,
            },
        ]

        result = job.run(full_sync=True)
        assert result['status'] == 'success'
        assert result['stats']['total'] == 2
        assert result['stats']['success'] == 2

        rows = db.query(PriceHistory).all()
        assert len(rows) == 2

        # 第二次运行：新建 job 实例
        job2 = PriceHistorySyncJob(job.adapter, db)
        job2.adapter.fetch_stock_price.return_value = [
            {
                'symbol': 'SH600519',
                'trade_date': date(2025, 1, 2),
                'open': 100,
                'high': 105,
                'low': 99,
                'close': 102,
                'volume': 1000,
            },
        ]
        result2 = job2.run(full_sync=True)
        assert result2['stats']['success'] == 0
