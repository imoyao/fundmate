# -*- coding: utf-8 -*-
"""测试 FundMetaSyncJob：基金规模 + 近似股票仓位回填。"""

from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund
from app.services.sync.jobs.fund_meta_job import FundMetaSyncJob


class TestFundMetaSyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        return FundMetaSyncJob(adapter, db)

    def test_scale_and_equity_position(self, job, db):
        """规模按 shares×nav 估算并只更新本地已有基金；股票仓位取前十大重仓合计。"""
        db.add(Fund(fund_code='000001', name='测试基金A'))
        db.add(Fund(fund_code='510300', name='沪深300ETF'))
        db.commit()

        # 全市场规模里只有本地两只基金，外加一只库里没有的（应被忽略）
        job.adapter.fetch_fund_scale.return_value = [
            {'fund_code': '000001', 'shares': 1.0e9, 'nav': 1.5},
            {'fund_code': '510300', 'shares': 1.89149e10, 'nav': 4.6147},
            {'fund_code': '999999', 'shares': 1.0e8, 'nav': 2.0},  # 本地无，跳过
        ]
        # 前十大重仓占净值比
        job.adapter.fetch_fund_top_holdings.side_effect = lambda code: (
            ([{'stock_code': '000001', 'stock_name': '平银', 'ratio': 3.46}] for _ in [0]).__next__()
            if code == '000001'
            else [{'stock_code': f'{i:06d}', 'stock_name': f'股{i}', 'ratio': 1.0} for i in range(10)]
        )

        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'

        a = db.query(Fund).filter_by(fund_code='000001').first()
        # 1e9 份 × 1.5 元 = 1.5e9 元 = 15.0 亿
        assert a.scale == 15.0
        assert a.recent_shares == 1.0e9
        assert a.equity_position == 3.46

        b = db.query(Fund).filter_by(fund_code='510300').first()
        assert b.scale == round(1.89149e10 * 4.6147 / 1e8, 2)
        assert b.equity_position == 10.0  # top10 各 1.0%

        # 库里没有的基金不应被新建
        assert db.query(Fund).filter_by(fund_code='999999').first() is None

    def test_no_local_fund_skips(self, job, db):
        job.adapter.fetch_fund_scale.return_value = [{'fund_code': '000001', 'shares': 1.0e9, 'nav': 1.5}]
        job.adapter.fetch_fund_top_holdings.return_value = []
        result = job.run(full_sync=True, targets=['__full__'])
        assert result['status'] == 'success'
        assert db.query(Fund).count() == 0
