# -*- coding: utf-8 -*-
"""测试 IndexCatalogSyncJob：指数名录全量重建 + 注册表登记（#1286）。"""

from unittest.mock import MagicMock

import pytest

from app.core.db_factory import DATA_DOMAIN_REGISTRY
from app.domains.indices.models import IndexCatalog
from app.services.sync.jobs.index_catalog_job import IndexCatalogSyncJob


def test_index_catalog_registered_as_market():
    assert DATA_DOMAIN_REGISTRY.get('index_catalog') == 'market'


class TestIndexCatalogSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        return IndexCatalogSyncJob(adapter, db)

    def test_full_rebuild(self, job, db):
        job.adapter.fetch_index_catalog.side_effect = lambda: [
            {'index_code': '000300', 'name': '沪深300', 'exchange': 'SH', 'source': 'sina'},
            {'index_code': '399001', 'name': '深证成指', 'exchange': 'SZ', 'source': 'sina'},
        ]
        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert db.query(IndexCatalog).count() == 2
        sz = db.query(IndexCatalog).filter_by(index_code='399001').one()
        assert sz.exchange == 'SZ'

    def test_replace_existing(self, job, db):
        """覆盖式重建：旧名录条目被清除。"""
        db.add(IndexCatalog(index_code='000016', name='旧指数', exchange='SH'))
        db.commit()
        job.adapter.fetch_index_catalog.side_effect = lambda: [
            {'index_code': '000300', 'name': '沪深300', 'exchange': 'SH'}
        ]
        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert [c.index_code for c in db.query(IndexCatalog)] == ['000300']

    def test_empty_fetch_keeps_existing(self, job, db):
        """接口偶发为空时静默跳过，不清空既有名录。"""
        db.add(IndexCatalog(index_code='000300', name='沪深300', exchange='SH'))
        db.commit()
        job.adapter.fetch_index_catalog.side_effect = lambda: []
        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert db.query(IndexCatalog).count() == 1

    def test_deduplicate_by_code(self, job, db):
        job.adapter.fetch_index_catalog.side_effect = lambda: [
            {'index_code': '000300', 'name': '沪深300', 'exchange': 'SH'},
            {'index_code': '000300', 'name': '重复条目', 'exchange': 'SH'},
        ]
        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert db.query(IndexCatalog).count() == 1
