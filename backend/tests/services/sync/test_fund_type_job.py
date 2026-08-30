# -*- coding: utf-8 -*-
"""测试 FundTypeResolver 与 FundTypeSyncJob（#1155 基金类型回填）。"""

from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund, FundType, FundVariety
from app.services.sync.fund_type_resolution import AkshareRawTypeDecomposer, FundTypeResolver
from app.services.sync.jobs.fund_type_job import FundTypeSyncJob


class TestFundTypeResolver:
    def test_akshare_decompose_dash(self):
        """「大类-细分」按首个 - 拆为 (大类, 整串)。"""
        comp = AkshareRawTypeDecomposer().decompose('混合型-灵活')
        assert comp.variety_name == '混合型'
        assert comp.type_name == '混合型-灵活'

    def test_akshare_decompose_no_dash(self):
        """无 - 时大类=小类=原串。"""
        comp = AkshareRawTypeDecomposer().decompose('ETF')
        assert comp.variety_name == 'ETF'
        assert comp.type_name == 'ETF'

    def test_resolve_creates_and_is_idempotent(self, db):
        """首次解析创建 variety/type，二次返回相同 ID。"""
        type_id, variety_id = FundTypeResolver(db).resolve('混合型-灵活')
        assert type_id is not None and variety_id is not None
        variety = db.query(FundVariety).filter_by(name='混合型').first()
        ftype = db.query(FundType).filter_by(name='混合型-灵活').first()
        assert variety is not None and ftype is not None
        assert ftype.variety_id == variety.id

        type_id2, variety_id2 = FundTypeResolver(db).resolve('混合型-灵活')
        assert type_id2 == type_id and variety_id2 == variety_id

    def test_resolve_links_existing_type_to_variety(self, db):
        """已存在小类但未关联大类时，补全关联。"""
        db.add(FundType(name='指数型-股票'))
        db.commit()
        _, variety_id = FundTypeResolver(db).resolve('指数型-股票')
        ftype = db.query(FundType).filter_by(name='指数型-股票').first()
        assert ftype.variety_id == variety_id


class TestFundTypeSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.fetch_fund_list.return_value = [
            {'fund_code': '000001', 'name': '华夏成长', 'fund_type': '混合型-灵活', 'company_name': ''},
            {'fund_code': '000002', 'name': '易方达蓝筹', 'fund_type': '混合型-偏股', 'company_name': ''},
        ]
        return FundTypeSyncJob(adapter, db)

    def test_full_backfill_fills_null_only(self, job, db):
        """全量回填：缺类型的基金被写入，已有类型的不被覆盖。"""
        db.add(Fund(fund_code='000001', name='华夏成长'))
        db.add(Fund(fund_code='000002', name='易方达蓝筹', fund_type_id=1))  # 已有标注
        db.commit()

        result = job.run(full_sync=True)
        assert result['status'] == 'success'

        f1 = db.query(Fund).filter_by(fund_code='000001').first()
        assert f1.fund_type_id is not None
        assert f1.fund_variety_id is not None

        f2 = db.query(Fund).filter_by(fund_code='000002').first()
        assert f2.fund_type_id == 1  # 未覆盖

    def test_incremental_backfill_by_targets(self, job, db):
        """增量回填：仅处理传入的目标代码。"""
        db.add(Fund(fund_code='000001', name='华夏成长'))
        db.add(Fund(fund_code='519994', name='长信量化', fund_type_id=2))  # 不在目标内
        db.commit()

        job.run(targets=['000001'])
        f1 = db.query(Fund).filter_by(fund_code='000001').first()
        assert f1.fund_type_id is not None
        f_other = db.query(Fund).filter_by(fund_code='519994').first()
        assert f_other.fund_type_id == 2  # 未触碰

    def test_empty_raw_type_skipped(self, job, db):
        """原始类型为空时不写入。"""
        job.adapter.fetch_fund_list.return_value = [
            {'fund_code': '000003', 'name': '某基金', 'fund_type': '', 'company_name': ''}
        ]
        db.add(Fund(fund_code='000003', name='某基金'))
        db.commit()

        job.run(full_sync=True)
        f = db.query(Fund).filter_by(fund_code='000003').first()
        assert f.fund_type_id is None
