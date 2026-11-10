# -*- coding: utf-8 -*-
"""TD-010 市值基准统一契约：品类聚合与家庭总资产必须同源。

同一只基金持仓，两条链路算出的市值分差必须为 0：
- 品类聚合：position_aggregation.aggregate_positions → total_market_value_cents
  （走 NavService 库内 T 日最新净值，position_aggregation.py:236-239）
- 家庭总资产：summary_service.write_asset_snapshot → total_assets
  （现同样走 NavService 库内 T 日最新净值，summary_service.py:_per_ledger_buckets）

此前 summary 走持仓快照价 current_price、聚合走净值，导致「同一持仓两个市值」。
本契约钉死：同一基金持仓，两链路市值相等（都 = 份额 × T 日最新净值）。
"""

from datetime import date as _date

from app.domains.funds.models import DailyWorth
from app.services.position_aggregation import aggregate_positions
from app.services.summary_service import write_asset_snapshot

SNAP_DATE = '2026-08-30'


class TestValuationBasisUnification:
    def test_fund_total_assets_matches_aggregation(self, db, make_position):
        """同一基金持仓：聚合市值 = 家庭总资产 = 份额 × T 日最新净值（300 元），分差为 0。"""
        # 快照价 2.0、库内最新净值 3.0 —— 两套基准必须能区分；若分叉则一链 200、一链 300
        make_position(
            symbol='000001',
            asset_type='fund',
            market='CN_A',
            quantity=100.0,
            avg_price=1.0,
            current_price=2.0,
            account_name='账户A',
        )
        db.add(DailyWorth(fund_code='000001', date=_date.today(), unit_nav=3.0))
        db.commit()

        agg = aggregate_positions(db, 1, ('fund', 'money_fund'))
        agg_total_yuan = agg['total_market_value_cents'] / 100.0

        result = write_asset_snapshot(db, 1, SNAP_DATE)
        summary_total_yuan = result['total_assets']

        # 100 份 × 3.0 净值 = 300 元；两链路必须一致（分差 0），且都不是快照价 200 元
        assert agg_total_yuan == 300.0
        assert summary_total_yuan == 300.0
        assert agg_total_yuan == summary_total_yuan
