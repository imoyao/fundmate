# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/20 23:22
# File : constants.py


# MVP 阶段的硬编码汇率，后续可迁移到数据库
EXCHANGE_RATES = {
    'CNY': 1.0,
    'USD': 7.25,
    'HKD': 0.92,
}

TYPE_KEYS = {
    'stock': 'asset-stock',
    'fund': 'asset-fund',
    'bond': 'asset-bond',
    'etf': 'asset-etf',
    'crypto': 'asset-crypto',
    'saving': 'asset-saving',
}

# 资产大类名称与颜色（颜色键已废弃，只保留名称）
CATEGORY_META = {
    'cash': ('流动资金', None),
    'fixed': ('固定资产', None),
    'investment': ('投资理财', None),
    'receivable': ('应收款', None),
    'insurance': ('保险项目', None),
}

# 桑基图需要的常量（之前可能在其他地方定义，统一放这里）
K_TOTAL = '总资产'
K_NET = '净资产'
K_LIABILITY = '总负债'
K_UNCONFIGURED = '未配置资产'
K_LONGTERM = '长期增值'
