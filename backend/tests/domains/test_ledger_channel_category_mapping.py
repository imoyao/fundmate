# -*- coding: utf-8 -*-
"""渠道分类映射契约（2026-10-28）。

`constants.py` 自称「org_type→channel_category 与分组→ledger_type 的唯一映射源」，
但映射表的键必须与 AMAC 名录里 `sales_institutions.org_type` 的**实际取值**一致。
原表按直觉命名，与名录对不上：本地 400 家机构里 99 家落进了 `other`——

===============  =====  ==========================
org_type         家数   原映射结果
===============  =====  ==========================
城市商业银行        75   other（应 bank）
在华外资法人银行      11   other（应 bank）
公募基金管理公司销售子公司  9   other（可接受）
保险代理公司和保险经纪公司  4   other（应 insurance）
===============  =====  ==========================

后果不是「分组不好看」而已：`ledger_type` 由 `channel_category` 派生
（`CHANNEL_CATEGORY_TO_LEDGER_TYPE`），`other` 派生 `bank`，于是 E账户导入把
「深圳前海微众银行」建成**基金类型**的账户，账户卡在「银行」分组里挂着「基」徽标。

本文件钉两件事：
1. 名录中出现过的每一种 org_type 都必须在表里有明确归属（不能靠 other 兜底）；
2. 银行类机构一律进 bank 分组。
"""

import pytest

from app.domains.ledgers.constants import (
    CHANNEL_CATEGORY_TO_LEDGER_TYPE,
    ORG_TYPE_TO_CHANNEL_CATEGORY,
    map_channel_category_to_ledger_type,
    map_org_type_to_channel_category,
)

# 本地名录（`select distinct org_type from sales_institutions`，2026-10-28 实测 400 家）
AMAC_ORG_TYPES = [
    '证券公司',
    '独立基金销售机构',
    '城市商业银行',
    '农村商业银行',
    '期货公司',
    '全国性商业银行',
    '在华外资法人银行',
    '证券投资咨询机构',
    '公募基金管理公司销售子公司',
    '保险公司',
    '保险代理公司和保险经纪公司',
]


@pytest.mark.parametrize(
    'org_type,expected',
    [
        # 银行类：四种实际命名的都要进 bank（原表只覆盖两种）
        ('城市商业银行', 'bank'),
        ('全国性商业银行', 'bank'),
        ('农村商业银行', 'bank'),
        ('在华外资法人银行', 'bank'),
        ('商业银行', 'bank'),
        # 证券 / 基金 / 保险 / 期货
        ('证券公司', 'securities'),
        ('证券投资咨询机构', 'securities'),
        ('独立基金销售机构', 'fund_platform'),
        ('基金销售支付结算机构', 'fund_platform'),
        ('保险公司', 'insurance'),
        ('保险代理公司和保险经纪公司', 'insurance'),
        ('期货公司', 'futures'),
        # 基金公司直销：装的是基金，但渠道不属任何销售平台，归 other
        ('基金公司', 'other'),
        ('基金管理公司子公司', 'other'),
        ('公募基金管理公司销售子公司', 'other'),
    ],
)
def test_org_type_maps_to_expected_channel(org_type, expected):
    assert map_org_type_to_channel_category(org_type) == expected


def test_every_known_org_type_is_explicitly_mapped():
    """名录里出现过的 org_type 不能靠 `other` 兜底。

    兜底会把真实差异静默吃掉：`other` 派生出 `ledger_type='bank'`，一个基金销售平台
    可能因此被建成银行账户。名录扩项时这条会先红，提醒回来补表。
    """
    missing = [t for t in AMAC_ORG_TYPES if t not in ORG_TYPE_TO_CHANNEL_CATEGORY]
    assert missing == [], f'以下 org_type 未显式映射，会落 other 兜底：{missing}'


def test_bank_org_types_never_fall_back_to_other():
    """银行类机构的 channel_category 必须逐一是 bank（防「城市商业银行」再次漏配）。"""
    bank_types = [t for t in AMAC_ORG_TYPES if '银行' in t]
    assert bank_types, '名录样本里应当包含银行类机构'
    for org_type in bank_types:
        assert map_org_type_to_channel_category(org_type) == 'bank', f'{org_type} 应归 bank 分组'


def test_unknown_org_type_still_falls_back_to_other():
    """防过宽：真未知的类型仍走 other，不要为凑覆盖率乱塞。"""
    assert map_org_type_to_channel_category('某个还没出现过的机构类型') == 'other'
    assert map_org_type_to_channel_category(None) == 'other'


def test_every_channel_category_derives_a_ledger_type():
    """每个分组都要能派生出 ledger_type，否则导入侧建号会拿到 None。"""
    for channel_category in ORG_TYPE_TO_CHANNEL_CATEGORY.values():
        assert channel_category in CHANNEL_CATEGORY_TO_LEDGER_TYPE, f'{channel_category} 没有对应的 ledger_type'
        assert map_channel_category_to_ledger_type(channel_category)
