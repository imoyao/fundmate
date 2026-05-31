# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 12:27
# File : test_db_utils.py
# -*- coding: utf-8 -*-
"""测试 bulk_insert_if_not_exists"""

from app.core.db_utils import bulk_insert_if_not_exists
from app.domains.securities.models import Security


class TestBulkInsertIfNotExists:
    def test_insert_new_records(self, db):
        data = [
            {'symbol': 'SH600519', 'name': '贵州茅台', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'},
            {'symbol': 'SZ000001', 'name': '平安银行', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'},
        ]
        count = bulk_insert_if_not_exists(db, Security, data, 'symbol')
        assert count == 2
        db.commit()
        assert db.query(Security).count() == 2

    def test_skip_existing(self, db):
        data = [{'symbol': 'SH600519', 'name': '茅台', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'}]
        bulk_insert_if_not_exists(db, Security, data, 'symbol')
        db.commit()
        # 再次插入相同 symbol
        count = bulk_insert_if_not_exists(db, Security, data, 'symbol')
        assert count == 0
        assert db.query(Security).count() == 1

    def test_mixed_new_and_existing(self, db):
        existing = Security(symbol='SH600519', name='茅台', market='CN_A', type='stock', currency='CNY')
        db.add(existing)
        db.commit()
        data = [
            {'symbol': 'SH600519', 'name': '茅台', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'},
            {'symbol': 'SZ000001', 'name': '平安', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'},
        ]
        count = bulk_insert_if_not_exists(db, Security, data, 'symbol')
        assert count == 1
        db.commit()
        assert db.query(Security).count() == 2

    def test_empty_data(self, db):
        count = bulk_insert_if_not_exists(db, Security, [], 'symbol')
        assert count == 0

    def test_batch_insert_large_data(self, db):
        data = [
            {'symbol': f'SH60{i:04d}', 'name': f'股票{i}', 'market': 'CN_A', 'type': 'stock', 'currency': 'CNY'}
            for i in range(2500)
        ]
        count = bulk_insert_if_not_exists(db, Security, data, 'symbol', batch_size=1000)
        assert count == 2500
        db.commit()
        assert db.query(Security).count() == 2500
