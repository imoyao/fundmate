# -*- coding: utf-8 -*-
"""测试 ConvertibleBondSyncJob：双源合并 + 可转债代码归一 + 覆盖式落库（#1285/#1393）。

假数据字段名对齐 akshare 1.18.91 实测列名（`bond_cb_redeem_jsl` / `bond_zh_cov`）。
"""

from app.domains.securities.models import ConvertibleBondTerm
from app.services.sync.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.jobs.convertible_bond_job import ConvertibleBondSyncJob


class _FakeAdapter:
    """假数据源：强赎（集思录）+ 基本信息（东财），验证 Job 合并/归一逻辑（无需网络）。"""

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
                'redeem_trigger_ratio': 130.0,
                'redeem_count': 3,
                'redeem_required': 15,
                'redeem_status': '已满足强赎条件',
                'redeem_clause': '近30交易日有15日收盘价≥转股价130%',
                'maturity_date': '2027-06-15',
                'source': 'akshare_jsl',
            },
        ]

    def fetch_convertible_bond_basic(self):
        return [
            {
                'bond_code': '113050',
                'name': '南银转债',
                'rating': 'AA+',
                'convert_value': 105.2,
                'premium_rate': 12.3,
                'stock_name': '南京银行',
                'stock_code_raw': '601009',
                'source': 'akshare_bond_zh_cov',
            },
            # 仅有基本信息（如已到期 / 未上市）的也落库，保证名录完整
            {
                'bond_code': '128145',
                'name': '测试转债',
                'rating': 'AA',
                'premium_rate': 8.8,
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
    # 强赎源（真实计数分子/分母 + 状态 + 到期日）
    assert r.redeem_count == 3
    assert r.redeem_required == 15
    assert r.redeem_status == '已满足强赎条件'
    assert r.maturity_date is not None
    # 基本信息源（评级 / 转股价值 / 溢价率）
    assert r.rating == 'AA+'
    assert float(r.premium_rate) == 12.3
    assert float(r.convert_value) == 105.2
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


def test_parse_redeem_count():
    """集思录强赎天计数形如 `3/15 | 3` → (已达, 所需)。"""
    assert AkshareAdapter._parse_redeem_count('3/15 | 3') == (3, 15)
    assert AkshareAdapter._parse_redeem_count('12/30 | 12') == (12, 30)
    assert AkshareAdapter._parse_redeem_count(None) == (None, None)
