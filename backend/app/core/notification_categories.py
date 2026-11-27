# -*- coding: utf-8 -*-
"""站内通知的分类真相源（#875 周期报告 → category 收敛）。

背景（2026-11-27 owner 拍板）：`Notification.category` 与 `source_type` 原本是
各处散落的裸字符串，没有唯一枚举真相源——新增一类消息（如周期报告）得自己
决定往 category 里填什么、前端再手动加一个 Tab，这就是「没解耦」。

两级语义（层级，不是并列的两个模糊字段）：
- **category（大类，前端分 Tab）**：`system` / `strategy` / `watchlist` /
  `rebalance` / `report`。
- **source_type（细类，前端分色 / 深链）**：具体到「哪个规则 / 事件」。
  `dividend_tax_service` 的测试明言「不能共用 source_type，否则前端无法分色」。

本模块是**唯一**允许定义这两个字段取值的出口；各生产方只从这里取常量，
禁止再写裸字符串（`strategy` / `watchlist` / `system` / `rebalance` 等）。
"""

from enum import Enum


class NotificationCategory(str, Enum):
    """通知大类（前端据此分 Tab）。"""

    SYSTEM = 'system'
    STRATEGY = 'strategy'
    WATCHLIST = 'watchlist'
    REBALANCE = 'rebalance'
    REPORT = 'report'  # 周期报告（周/月/季/年报，#875）


class NotificationSourceType(str, Enum):
    """通知细类（前端据此分色 / 深链）。"""

    ALLOCATION_DEVIATION = 'allocation_deviation'
    WATCHLIST_ALERT = 'watchlist_alert'
    DIVIDEND_TAX_PENDING = 'dividend_tax_pending'
    DIVIDEND_TAX_SUSPECT = 'dividend_tax_suspect'
    ADVISOR_REBALANCE = 'advisor_rebalance'
    PERIODIC_REPORT = 'periodic_report'  # 周期报告已生成（#875）


# 大类 → 细类归属映射（层级关系：每个 source_type 恰好属于一个 category）。
# 校验入口：任何写通知的生产方都应保证 source_type 落在其 category 的允许集内。
CATEGORY_SOURCE_TYPES: dict[NotificationCategory, frozenset[NotificationSourceType]] = {
    NotificationCategory.SYSTEM: frozenset(
        {
            NotificationSourceType.DIVIDEND_TAX_PENDING,
            NotificationSourceType.DIVIDEND_TAX_SUSPECT,
        }
    ),
    NotificationCategory.STRATEGY: frozenset({NotificationSourceType.ALLOCATION_DEVIATION}),
    NotificationCategory.WATCHLIST: frozenset({NotificationSourceType.WATCHLIST_ALERT}),
    NotificationCategory.REBALANCE: frozenset({NotificationSourceType.ADVISOR_REBALANCE}),
    NotificationCategory.REPORT: frozenset({NotificationSourceType.PERIODIC_REPORT}),
}


def category_of(source_type: NotificationSourceType) -> NotificationCategory:
    """给定细类，回其所属大类（层级关系的反向查询）。"""
    for category, sources in CATEGORY_SOURCE_TYPES.items():
        if source_type in sources:
            return category
    raise ValueError(f'未登记的 source_type: {source_type}')


# 兼容历史裸字符串常量别名：让既有生产方逐点迁移时不至于一次性全改。
# 新代码一律用 `NotificationCategory.*` / `NotificationSourceType.*`，勿用这些别名。
CATEGORY_SYSTEM = NotificationCategory.SYSTEM.value
CATEGORY_STRATEGY = NotificationCategory.STRATEGY.value
CATEGORY_WATCHLIST = NotificationCategory.WATCHLIST.value
CATEGORY_REBALANCE = NotificationCategory.REBALANCE.value
CATEGORY_REPORT = NotificationCategory.REPORT.value
