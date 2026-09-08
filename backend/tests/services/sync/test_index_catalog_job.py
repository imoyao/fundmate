# -*- coding: utf-8 -*-
"""测试 IndexCatalogSyncJob：三源合并名录全量重建 + 注册表登记（#1286/#1365）。"""

from unittest.mock import MagicMock

import pytest

from app.core.db_factory import DATA_DOMAIN_REGISTRY
from app.domains.indices.models import IndexCatalog
from app.services.sync.jobs.index_catalog_job import IndexCatalogSyncJob


def test_index_catalog_registered_as_market():
    assert DATA_DOMAIN_REGISTRY.get('index_catalog') == 'market'


SINA_ROWS = [{'index_code': '000300', 'name': '沪深300', 'exchange': 'SH', 'source': 'sina'}]
CSI_ROWS = [
    {'index_code': '930950', 'name': '中证偏股基金指数', 'exchange': 'CSI', 'source': 'csindex'},
    {'index_code': '932000', 'name': '中证2000', 'exchange': 'CSI', 'source': 'csindex'},
]
CNI_ROWS = [
    {'index_code': '399317', 'name': '国证A指', 'exchange': 'CNI', 'source': 'cni'},
    {'index_code': '399303', 'name': '国证2000', 'exchange': 'CNI', 'source': 'cni'},
]


class TestIndexCatalogSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.fetch_index_catalog.return_value = []
        adapter.fetch_index_catalog_csindex.return_value = []
        adapter.fetch_index_catalog_cni.return_value = []
        return IndexCatalogSyncJob(adapter, db)

    def test_three_source_merge(self, job, db):
        """三源合并：sina/中证/国证条目全部入库。"""
        job.adapter.fetch_index_catalog.return_value = SINA_ROWS
        job.adapter.fetch_index_catalog_csindex.return_value = CSI_ROWS
        job.adapter.fetch_index_catalog_cni.return_value = CNI_ROWS

        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert db.query(IndexCatalog).count() == 5
        csi = db.query(IndexCatalog).filter_by(index_code='930950').one()
        assert csi.exchange == 'CSI'
        assert csi.source == 'csindex'

    def test_priority_sina_over_csi(self, job, db):
        """去重优先级：同代码时保留先到源（sina > csindex > cni）。"""
        job.adapter.fetch_index_catalog.return_value = SINA_ROWS
        job.adapter.fetch_index_catalog_csindex.return_value = [
            {'index_code': '000300', 'name': '沪深300(中证源)', 'exchange': 'CSI', 'source': 'csindex'}
        ]
        job.adapter.fetch_index_catalog_cni.return_value = []

        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        row = db.query(IndexCatalog).filter_by(index_code='000300').one()
        assert row.source == 'sina'
        assert row.exchange == 'SH'

    def test_single_source_failure_does_not_block(self, job, db):
        """单源抛错不阻断其他源（名录覆盖面优先）。"""
        job.adapter.fetch_index_catalog.side_effect = RuntimeError('sina down')
        job.adapter.fetch_index_catalog_csindex.return_value = CSI_ROWS
        job.adapter.fetch_index_catalog_cni.return_value = CNI_ROWS

        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert db.query(IndexCatalog).count() == 4

    def test_replace_existing(self, job, db):
        """覆盖式重建：旧名录条目被清除。"""
        db.add(IndexCatalog(index_code='000016', name='旧指数', exchange='SH'))
        db.commit()
        job.adapter.fetch_index_catalog.return_value = SINA_ROWS
        job.adapter.fetch_index_catalog_csindex.return_value = []
        job.adapter.fetch_index_catalog_cni.return_value = []

        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert [c.index_code for c in db.query(IndexCatalog)] == ['000300']

    def test_all_sources_empty_keeps_existing(self, job, db):
        """三源全空（接口异常）时静默跳过，不清空既有名录。"""
        db.add(IndexCatalog(index_code='000300', name='沪深300', exchange='SH'))
        db.commit()
        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert db.query(IndexCatalog).count() == 1
