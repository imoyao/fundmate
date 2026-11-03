# -*- coding: utf-8 -*-
"""资产大类归属（股票 / 基金 / 其他）唯一出口。

为什么单独成模块：这套映射原先内联在 `position_structure._CLASS_OF`，
而首页「最新收益」卡（`services/today_pnl.py`）需要**同一套分桶**才能保证
卡内「分项之和 ≡ 合计」——两处各写一份映射，`etf` 归哪边迟早分叉，
分叉的表现是「股票 + 基金 ≠ 总收益」，用户第一眼就能算出来。

⚠️ 口径边界：
- `etf` 归 **基金**（组合 / 家庭级口径，与 `position_structure` 第 4 条一致：
  账户级证券视角下 ETF 可归权益侧，那是**视图**规则，不在本模块）；
- 债券 / 货基 / 逆回购 / 理财 / 实物一律 `other`——它们没有统一的当日估值口径，
  首页卡不进分项列（见 `today_pnl` 的口径说明）。
"""

from __future__ import annotations

from typing import Optional

CLASS_STOCK = 'stock'
CLASS_FUND = 'fund'
CLASS_OTHER = 'other'

CLASS_LABELS = {CLASS_STOCK: '股票', CLASS_FUND: '基金', CLASS_OTHER: '其他'}
CLASS_ORDER = (CLASS_STOCK, CLASS_FUND, CLASS_OTHER)

_CLASS_OF = {
    'stock': CLASS_STOCK,
    'fund': CLASS_FUND,
    'etf': CLASS_FUND,
}


def class_of_asset_type(asset_type: Optional[str]) -> str:
    """`positions.asset_type` → 大类键；未知 / 空一律 `other`（不猜）。"""
    return _CLASS_OF.get((asset_type or '').lower(), CLASS_OTHER)


def class_of_position(pos) -> str:
    """持仓对象 → 大类键（只读 `asset_type`，不碰账户类型等视图规则）。"""
    return class_of_asset_type(getattr(pos, 'asset_type', None))


__all__ = [
    'CLASS_STOCK',
    'CLASS_FUND',
    'CLASS_OTHER',
    'CLASS_LABELS',
    'CLASS_ORDER',
    'class_of_asset_type',
    'class_of_position',
]
