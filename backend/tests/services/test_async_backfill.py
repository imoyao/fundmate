# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 18:13
# File : test_async_backfill.py
# tests/services/test_async_backfill.py


import pandas as pd

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
