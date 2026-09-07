# -*- coding: utf-8 -*-
"""测试 IndexConstituentSyncJob：指数成分回填 + 覆盖式更新 + 注册表登记。"""

from unittest.mock import MagicMock

import pytest

from app.core.db_factory import DATA_DOMAIN_REGISTRY
from app.domains.indices.models import IndexConstituent
from app.services.sync.jobs.index_constituent_job import INDEX_TARGETS, IndexConstituentSyncJob


def test_index_constituents_registered_as_market():
    assert DATA_DOMAIN_REGISTRY.get('index_constituents') == 'market'


class TestIndexConstituentSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        return IndexConstituentSyncJob(adapter, db)

    def test_backfill_and_fallback(self, job, db):
        """csindex 优先；csindex 缺失时回退 sina（含纳入日期）。"""
        job.adapter.fetch_index_constituents_csindex.side_effect = lambda code: (
            [{'symbol': '000001', 'stock_name': '平银', 'index_name': '沪深300'}] if code == '000300' else []
        )
        job.adapter.fetch_index_constituents_sina.side_effect = lambda code: (
            [{'symbol': '600000', 'stock_name': '浦发', 'in_date': '2026-01-01'}] if code == '000001' else []
        )

        result = job.run(full_sync=True, targets=['000300', '000001'])
        assert result['status'] == 'success'

        hs300 = db.query(IndexConstituent).filter_by(index_code='000300').all()
        assert len(hs300) == 1
        assert hs300[0].symbol == '000001'
        assert hs300[0].index_name == '沪深300'

        sh = db.query(IndexConstituent).filter_by(index_code='000001').all()
        assert len(sh) == 1
        assert sh[0].symbol == '600000'
        assert sh[0].in_date == '2026-01-01'

    def test_replace_existing(self, job, db):
        """覆盖式更新：已存在旧成分时再次同步应整体替换（先删后插）。"""
        # 模拟上一次同步已落库的旧成分
        db.add(IndexConstituent(index_code='000300', symbol='000001', stock_name='旧'))
        db.commit()

        job.adapter.fetch_index_constituents_csindex.side_effect = lambda code: (
            [{'symbol': '000002', 'stock_name': '万科', 'index_name': '沪深300'}] if code == '000300' else []
        )
        job.adapter.fetch_index_constituents_sina.side_effect = lambda code: []

        result = job.run(full_sync=True, targets=['000300'])
        assert result['status'] == 'success'
        assert [c.symbol for c in db.query(IndexConstituent).filter_by(index_code='000300')] == ['000002']

    def test_default_targets_defined(self):
        assert '000300' in INDEX_TARGETS
