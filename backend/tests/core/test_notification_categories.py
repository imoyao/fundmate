# -*- coding: utf-8 -*-
"""通知分类真相源（app/core/notification_categories.py）的契约测试（#875）。

钉死三件事：
1. **枚举值即历史契约**：每个 category / source_type 的字符串值必须与
   既有生产方写入的裸字符串完全一致（改值 = 破坏前端分 Tab / 分色的契约）；
2. **层级映射完备**：每个 source_type 恰好属于一个 category，无遗漏、无重复；
3. **反向查询正确**：`category_of` 能把细类映射回正确的大类。
"""

import pytest

from app.core.notification_categories import (
    CATEGORY_REBALANCE,
    CATEGORY_REPORT,
    CATEGORY_SOURCE_TYPES,
    CATEGORY_STRATEGY,
    CATEGORY_SYSTEM,
    CATEGORY_WATCHLIST,
    NotificationCategory,
    NotificationSourceType,
    category_of,
)


def test_category_枚举值与历史裸字符串一致():
    """category 字符串值不能变——前端 lay-notice 的 noticeTabs 按它分 Tab。"""
    assert NotificationCategory.SYSTEM.value == 'system'
    assert NotificationCategory.STRATEGY.value == 'strategy'
    assert NotificationCategory.WATCHLIST.value == 'watchlist'
    assert NotificationCategory.REBALANCE.value == 'rebalance'
    assert NotificationCategory.REPORT.value == 'report'


def test_source_type_枚举值与历史裸字符串一致():
    """source_type 字符串值不能变——前端按它分色 / 深链。"""
    assert NotificationSourceType.ALLOCATION_DEVIATION.value == 'allocation_deviation'
    assert NotificationSourceType.WATCHLIST_ALERT.value == 'watchlist_alert'
    assert NotificationSourceType.DIVIDEND_TAX_PENDING.value == 'dividend_tax_pending'
    assert NotificationSourceType.DIVIDEND_TAX_SUSPECT.value == 'dividend_tax_suspect'
    assert NotificationSourceType.ADVISOR_REBALANCE.value == 'advisor_rebalance'
    assert NotificationSourceType.PERIODIC_REPORT.value == 'periodic_report'


def test_兼容别名指向枚举值():
    """历史裸字符串别名（供逐点迁移过渡）与枚举值一致。"""
    assert CATEGORY_SYSTEM == NotificationCategory.SYSTEM.value
    assert CATEGORY_STRATEGY == NotificationCategory.STRATEGY.value
    assert CATEGORY_WATCHLIST == NotificationCategory.WATCHLIST.value
    assert CATEGORY_REBALANCE == NotificationCategory.REBALANCE.value
    assert CATEGORY_REPORT == NotificationCategory.REPORT.value


def test_每个细类恰好属于一个大类():
    """层级映射完备：所有 source_type 加起来的集合 == 全部 source_type，
    且互不重叠（不会出现「同一个细类挂在两个大类下」）。"""
    all_sources = set(NotificationSourceType)
    mapped = {source for sources in CATEGORY_SOURCE_TYPES.values() for source in sources}
    assert mapped == all_sources, f'映射遗漏或多余：{all_sources ^ mapped}'


def test_category_of反向查询正确():
    assert category_of(NotificationSourceType.ALLOCATION_DEVIATION) is NotificationCategory.STRATEGY
    assert category_of(NotificationSourceType.WATCHLIST_ALERT) is NotificationCategory.WATCHLIST
    assert category_of(NotificationSourceType.DIVIDEND_TAX_PENDING) is NotificationCategory.SYSTEM
    assert category_of(NotificationSourceType.DIVIDEND_TAX_SUSPECT) is NotificationCategory.SYSTEM
    assert category_of(NotificationSourceType.ADVISOR_REBALANCE) is NotificationCategory.REBALANCE
    assert category_of(NotificationSourceType.PERIODIC_REPORT) is NotificationCategory.REPORT


def test_未登记的细类抛错():
    """未知 source_type 反向查询应显式报错，而非静默回某个默认大类。"""
    with pytest.raises(ValueError):
        category_of(NotificationSourceType('nonexistent_source'))
