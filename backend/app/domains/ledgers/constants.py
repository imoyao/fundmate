# -*- coding: utf-8 -*-
"""账本渠道分类映射（#1101 后续重设计）。

权威说明见 docs/working-notes/ledger-channel-category-redesign-2026-08-28.md。
本文件是 org_type→channel_category 与 分组→ledger_type 的唯一映射源，禁止在别处硬编码。

字段职责（铁律见设计文档 §2.3，两字段正交、禁止互相赋值）：
- channel_category：用户可见的「机构渠道类别 / 分组标签」
  (bank/securities/fund_platform/insurance/futures/other)。账户列表分组、类型标签、
  排序、筛选一律只读它，绝不读 ledger_type 当展示。由系统据销售机构 org_type 或用户
  所选分组写入，用户从不直接编辑。
- ledger_type：内部「资产类计算口径键」(stock/fund/bank/property/e_account/family)，
  只进计算 / 费率 / 视图分支逻辑，用户不可见、不当展示标签。由系统据 channel_category
  或机构 org_type 派生；编辑带数据账户时不可变（改类型返回 409）。
"""

ORG_TYPE_TO_CHANNEL_CATEGORY = {
    '商业银行': 'bank',
    '全国性商业银行': 'bank',
    '农村商业银行': 'bank',
    '外资银行': 'bank',
    '证券公司': 'securities',
    '证券投资咨询机构': 'securities',
    '独立基金销售机构': 'fund_platform',
    '基金销售支付结算机构': 'fund_platform',
    '保险公司': 'insurance',
    '期货公司': 'futures',
    '基金公司': 'other',
    '基金管理公司子公司': 'other',
}

CHANNEL_CATEGORY_TO_LEDGER_TYPE = {
    'bank': 'bank',
    'securities': 'stock',
    'fund_platform': 'fund',
    'insurance': 'property',
    'futures': 'stock',
    'other': 'bank',
}

CHANNEL_CATEGORY_CHOICES = ['bank', 'securities', 'fund_platform', 'insurance', 'futures', 'other']


def map_org_type_to_channel_category(org_type):
    if not org_type:
        return 'other'
    return ORG_TYPE_TO_CHANNEL_CATEGORY.get(org_type, 'other')


def map_channel_category_to_ledger_type(channel_category):
    if not channel_category:
        return 'bank'
    return CHANNEL_CATEGORY_TO_LEDGER_TYPE.get(channel_category, 'bank')


# 无销售机构时，按 ledger_type 反推 channel_category 的回退映射（向后兼容旧调用方）。
# 取值依据设计文档 §6 存量回归规则：bank→bank, stock→securities, fund→fund_platform,
# property→other, e_account→other, family→other。
LEDGER_TYPE_TO_CHANNEL_CATEGORY_FALLBACK = {
    'bank': 'bank',
    'stock': 'securities',
    'fund': 'fund_platform',
    'property': 'other',
    'e_account': 'other',
    'family': 'other',
}


def map_ledger_type_to_channel_category(ledger_type):
    if not ledger_type:
        return 'other'
    return LEDGER_TYPE_TO_CHANNEL_CATEGORY_FALLBACK.get(ledger_type, 'other')
