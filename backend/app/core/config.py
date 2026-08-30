# -*- coding: utf-8 -*-
# app/core/config.py
"""
同步数据源偏好配置（去硬编码选源）。

此前 orchestrator 在 _register_jobs 中把每个 Job 写死绑定到具体适配器
（如 fund_list 永远用 akshare）。本模块把"用哪个数据源"提升为可配置项，
默认 eastmoney（天天基金/东财一等数据源，#1168）。后续 fund_detail_enrich /
fund_type / fund_manager 的选源也走这里扩展，避免再硬编码。
"""

import os

# fund_list 任务使用的数据源：'eastmoney'（默认）或 'akshare'
SYNC__FUND_LIST_SOURCE = os.getenv('SYNC__FUND_LIST_SOURCE', 'eastmoney').strip().lower()
