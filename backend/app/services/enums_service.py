# -*- coding: utf-8 -*-
"""前后端共用枚举的可下发载荷（`GET /api/utils/enums` 的唯一组装处）。

## 为什么单独成 service 而不是留在视图里

`scripts/check_view_thickness.py` 对 `domains/utils/views.py` 的基线是**只减不增**。
往里加一组映射就会顶穿基线，而正解不是调基线（守卫会拒），也不是把注释搬去别处
凑行数，而是把「把若干常量拼成一个响应体」这种**纯数据组装**从视图挪进 service，
视图只留 HTTP 编排（判据：`docs/spec/decisions.md` 视图层职责边界 / #1606）。

## 边界

只读常量、无副作用、不碰 DB。因此可以直接在单测里调用比对，不需要 app context。

前端禁止手抄第二份：资产类型 / 大类 / 分档 / 市场 / 场所的标签都从这里取
（`frontend/src/composables/useEnumLabels.ts`），前端镜像文件仅在枚举未拉取时兜底。
"""

from __future__ import annotations

from app.core.asset_types import (
    ASSET_CATEGORY_LABELS,
    ASSET_TYPE_LABELS,
    ASSET_TYPE_VALUES,
    INVESTMENT_MINOR_CATEGORIES,
)
from app.core.constants import MARKET_LABELS, OP_TYPE_LABEL, POSITION_SOURCE_LABELS, VENUE_LABELS
from app.core.investment_tiers import ASSET_TYPE_TIER, TIER_LABELS, TIER_SCOPES, TIER_VALUES


def build_enums_payload() -> dict:
    """组装 `/api/utils/enums` 的 `data` 段。

    为什么这个端点必须存在：持仓来源（`Position.source`）等枚举的中文 label 只在后端
    `core.constants` / `core.asset_types` 定义，是唯一真相源；前端展示徽标时必须从这里取，
    禁止手抄第二份（否则两处漂移）。端点免登录——探市页 /explore 免登录也展示来源徽标。

    新增「需要前后端一致的枚举标签」统一加在这里，不要在 `frontend/src/constants/`
    再写一份镜像（镜像只作 redis 未命中时的兜底）。
    """
    return {
        'position_source': POSITION_SOURCE_LABELS,
        'asset_type': ASSET_TYPE_LABELS,
        # #1527：合法取值集合（与标签映射同源），供前端共用、做运行时校验
        'asset_type_values': sorted(ASSET_TYPE_VALUES),
        'asset_category': ASSET_CATEGORY_LABELS,
        # #1354：投资理财下的细分子类（写 minor_category），前端禁止再建平级大类
        'investment_minor': INVESTMENT_MINOR_CATEGORIES,
        'op_type_labels': OP_TYPE_LABEL,
        # #1286：市场码 → 中文标签（含无市场实体 '' → 通用）
        'market': MARKET_LABELS,
        # #1969：交易场所标签（EXCHANGE/OTC 原键不再直接上屏）
        'venue': VENUE_LABELS,
        # 投资分档（主动投资 / 稳健 / 其他，判据表见 core/investment_tiers）：
        # 前端做三层收益展示时从这里取，禁止手抄 asset_type → tier 的第二份映射。
        # `investment_tier_scopes` 是对用户暴露的三个口径，刻意不含 other——
        # 房产 / 保险这类没有交易流水，单独算年化没有意义，它们只用于把「全账户」凑齐。
        'investment_tier': ASSET_TYPE_TIER,
        'investment_tier_labels': TIER_LABELS,
        'investment_tier_values': list(TIER_VALUES),
        'investment_tier_scopes': list(TIER_SCOPES),
    }
