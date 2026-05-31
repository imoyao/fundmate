# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 18:32
# File : money_fund_utils.py
import pandas as pd


def compute_money_fund_yields(nav_df):
    # 确保索引是日期，否则从 'date' 列恢复
    if 'date' in nav_df.columns:
        nav_df = nav_df.set_index('date')
    nav_df = nav_df.sort_index()

    records = []
    prev_netvalue = None
    for idx, row in nav_df.iterrows():
        # 强制转换为 date 对象
        date_val = idx.date() if hasattr(idx, 'date') else pd.Timestamp(idx).date()
        netvalue = float(row['netvalue'])
        if prev_netvalue is not None and prev_netvalue > 0:
            yield_value = round((netvalue - prev_netvalue) * 10000, 4)
        else:
            yield_value = 0.0
        records.append(
            {
                'date': date_val,
                'nav_per_10k': yield_value,
                'annual_return_7d': None,
            }
        )
        prev_netvalue = netvalue
    return records
