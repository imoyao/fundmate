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

    def test_validate_normal(self, job):
        """正常行情数据通过校验"""
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

    def test_validate_default_adj_close(self, job):
        """未提供 adj_close 时自动使用 close 填充"""
        raw = [
            {
                'security_id': 1,
                'trade_date': date(2025, 1, 2),
                'close': 50.0,
                'open': 49.0,
                'high': 51.0,
                'low': 48.0,
            }
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['adj_close'] == 50.0
        assert validated[0]['source'] == 'mock_akshare'

    def test_validate_missing_key_fields(self, job):
        """缺失必填字段的记录应被过滤"""
        raw = [
            {'trade_date': date(2025, 1, 1), 'close': 100.0},
            {'security_id': 1, 'close': 100.0},
            {'security_id': 2, 'trade_date': date(2025, 1, 3), 'close': 99.0},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['security_id'] == 2

    def test_deduplicate_existing(self, job, db):
        """基于复合键 (security_id, trade_date) 去重"""
        db.add(PriceHistory(security_id=1, trade_date=date(2025, 1, 1), close=10.0))
        db.commit()

        data = [
            {'security_id': 1, 'trade_date': date(2025, 1, 1), 'close': 10.0},
            {'security_id': 1, 'trade_date': date(2025, 1, 2), 'close': 11.0},
            {'security_id': 2, 'trade_date': date(2025, 1, 1), 'close': 20.0},
        ]
        new = job._deduplicate(data)
        assert len(new) == 2

    def test_run_integration(self, job, db):
        """端到端测试：增量同步写入行情数据"""
        sec = Security(symbol='SH600519', name='茅台', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()

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

        result = job.run(full_sync=True, targets=['SH600519'])
        assert result['status'] == 'success'
        assert result['stats']['total'] == 1
        assert result['stats']['success'] == 2

        rows = db.query(PriceHistory).all()
        assert len(rows) == 2
