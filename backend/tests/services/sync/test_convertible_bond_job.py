# -*- coding: utf-8 -*-
"""测试 ConvertibleBondSyncJob：可转债条款归一（symbol）+ 合并 + 覆盖式落库（#1285/#1393）。"""

from app.domains.securities.models import ConvertibleBondTerm
from app.services.sync.jobs.convertible_bond_job import ConvertibleBondSyncJob


class _FakeAdapter:
    """假数据源：强赎数据 + 基本信息，验证 Job 的合并与归一逻辑（无需网络）。"""

    def fetch_convertible_bond_redeem(self):
        return [
            {
                'bond_code': '113050',
                'name': '南银转债',
                'price': 118.5,
                'stock_name': '南京银行',
                'stock_code_raw': '601009',
                'issue_size': 200.0,
                'remain_size': 199.9,
                'convert_price': 8.22,
                'force_redeem_price': 10.69,
                'redeem_count': 3,
                'redeem_clause': '近30交易日有15日收盘价≥转股价130%',
                'source': 'akshare_jsl',
            },
        ]

    def fetch_convertible_bond_basic(self):
        return [
            {
                'bond_code': '113050',
                'name': '南银转债',
                'rating': 'AA+',
                'maturity_date': '2027-06-15',
                'source': 'akshare_bond_zh_cov',
            },
            # 仅有基本信息（如已到期 / 未上市）的也落库，保证名录完整
            {
                'bond_code': '128145',
                'name': '测试转债',
                'rating': 'AA',
                'maturity_date': '2026-12-01',
                'source': 'akshare_bond_zh_cov',
            },
        ]


def test_convertible_bond_job_upsert_and_merge(db):
    job = ConvertibleBondSyncJob(_FakeAdapter(), db)
    result = job.run()
    assert result['status'] == 'success'

    rows = db.query(ConvertibleBondTerm).all()
    assert len(rows) == 2

    r = db.query(ConvertibleBondTerm).filter_by(bond_code='113050').one()
    assert r.symbol == 'SH113050'
    # 强赎数据（含真实计数）+ 基本信息（评级 / 到期日）合并
    assert r.redeem_count == 3
    assert r.rating == 'AA+'
    assert r.maturity_date is not None
    assert r.stock_symbol is not None

    # 仅有基本信息的记录也应落库（无强赎字段）
    r2 = db.query(ConvertibleBondTerm).filter_by(bond_code='128145').one()
    assert r2.rating == 'AA'
    assert r2.redeem_count is None


def test_convertible_bond_job_idempotent(db):
    job = ConvertibleBondSyncJob(_FakeAdapter(), db)
    job.run()
    job.run()
    # 覆盖式 upsert：重复跑不产生重复行
    assert db.query(ConvertibleBondTerm).count() == 2
