# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 18:13
# File : test_async_backfill.py
# tests/services/test_async_backfill.py


from datetime import date
from unittest.mock import patch

import pandas as pd

from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.async_backfill import _backfill_stock_price
from app.services.sync.money_fund_utils import compute_money_fund_yields


def test_compute_money_fund_yields():
    """验证万份收益计算正确（使用真实xalpha数据片段）"""
    nav_df = pd.DataFrame(
        {'netvalue': [1.430995, 1.431030, 1.431063]}, index=pd.to_datetime(['2026-05-25', '2026-05-26', '2026-05-27'])
    )
    records = compute_money_fund_yields(nav_df)
    assert len(records) == 3
    assert records[0]['nav_per_10k'] == 0.0
    assert records[1]['nav_per_10k'] == 0.35  # (1.431030 - 1.430995) * 10000 = 0.35
    assert records[2]['nav_per_10k'] == 0.33  # (1.431063 - 1.431030) * 10000 = 0.33


class TestBackfillStockPrice:
    """测试股票行情异步回填"""

    def test_backfill_stock_price_success(self, db):
        """正常回填股票行情，symbol 字段正确写入"""
        sec = Security(symbol='SH601012', name='隆基绿能', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()
        sec_id = sec.id

        mock_records = [
            {
                'trade_date': date(2024, 1, 2),
                'open': 10.0,
                'high': 10.5,
                'low': 9.8,
                'close': 10.2,
                'volume': 1000000.0,
                'symbol': 'SH601012',
            },
            {
                'trade_date': date(2024, 1, 3),
                'open': 10.2,
                'high': 10.8,
                'low': 10.1,
                'close': 10.6,
                'volume': 1200000.0,
                'symbol': 'SH601012',
            },
        ]

        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.services.async_backfill.SessionLocal') as mock_session,
        ):
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.fetch_stock_price.return_value = mock_records
            mock_session.return_value = db

            _backfill_stock_price('SH601012')

        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH601012').all()
        assert len(rows) == 2
        assert rows[0].security_id == sec_id
        assert rows[0].symbol == 'SH601012'
        assert rows[0].close == 10.2

    def test_backfill_stock_price_filters_unknown_columns(self, db):
        """多余字段被过滤，不引发插入错误"""
        sec = Security(symbol='SH601012', name='隆基绿能', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()

        mock_records = [
            {
                'trade_date': date(2024, 1, 2),
                'open': 10.0,
                'close': 10.2,
                'volume': 1000000.0,
                'symbol': 'SH601012',
                'unknown_col': 'should_be_filtered',
            },
        ]

        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.services.async_backfill.SessionLocal') as mock_session,
        ):
            mock_adapter_class.return_value.fetch_stock_price.return_value = mock_records
            mock_session.return_value = db

            _backfill_stock_price('SH601012')

        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH601012').all()
        assert len(rows) == 1
        assert rows[0].close == 10.2

    def test_backfill_stock_price_security_not_found(self, db):
        """证券不存在时静默返回，不抛异常"""
        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.services.async_backfill.SessionLocal') as mock_session,
        ):
            mock_session.return_value = db

            _backfill_stock_price('SH999999')

            mock_adapter_class.assert_not_called()

    def test_backfill_stock_price_empty_records(self, db):
        """适配器返回空数据时不写入"""
        sec = Security(symbol='SH601012', name='隆基绿能', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()

        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.services.async_backfill.SessionLocal') as mock_session,
        ):
            mock_adapter_class.return_value.fetch_stock_price.return_value = []
            mock_session.return_value = db

            _backfill_stock_price('SH601012')

        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH601012').all()
        assert len(rows) == 0

    def test_backfill_stock_price_duplicate_handling(self, db):
        """已存在的行情数据不重复插入"""
        sec = Security(symbol='SH601012', name='隆基绿能', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()
        sec_id = sec.id

        existing = PriceHistory(
            security_id=sec_id,
            symbol='SH601012',
            trade_date=date(2024, 1, 2),
            close=10.0,
        )
        db.add(existing)
        db.commit()

        mock_records = [
            {'trade_date': date(2024, 1, 2), 'close': 10.5, 'symbol': 'SH601012'},
            {'trade_date': date(2024, 1, 3), 'close': 11.0, 'symbol': 'SH601012'},
        ]

        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.services.async_backfill.SessionLocal') as mock_session,
        ):
            mock_adapter_class.return_value.fetch_stock_price.return_value = mock_records
            mock_session.return_value = db

            _backfill_stock_price('SH601012')

        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH601012').all()
        assert len(rows) == 2
