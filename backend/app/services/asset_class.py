# -*- coding: utf-8 -*-
"""资产大类归属（股票 / 基金 / 其他）唯一出口。

为什么单独成模块：这套映射原先内联在 `position_structure._CLASS_OF`，
而首页「最新收益」卡（`services/today_pnl.py`）需要**同一套分桶**才能保证
卡内「分项之和 ≡ 合计」——两处各写一份映射，`etf` 归哪边迟早分叉，
分叉的表现是「股票 + 基金 ≠ 总收益」，用户第一眼就能算出来。

## 口径（2026-11-04 用户裁定，源用户反馈「首页与自选页当日收益差异过大」）

按**定价方式**分，不按产品形态分：

- `stock` / `etf` / `bond`（可转债）→ `stock`，用户可见标签「股票」：
  三者都有交易所报价（`position_price_job._INTRADAY_ASSET_TYPES` 同一集合），
  盘中能拿到实时价、收盘有收盘价，当日盈亏口径完全一致。集合边界（含 ETF、
  可转债）由前端一行小字说明，不塞进标题（2026-11-06 用户拍板，D91）。
- `fund` → `fund`，用户可见标签「基金」：只有每日净值 / 收盘估值定格，无盘中价。
- 货基 / 逆回购 / 理财 / 实物一律 `other`——它们没有统一的当日估值口径，
  首页卡不进分项列（见 `today_pnl` 的口径说明）。

⚠️ 这与 2026-10 的旧口径（`etf → fund`）相反：旧口径让同一只 ETF 在家庭级算基金、在账户级算股票，
用户看到首页「基金」列盘中跳动而「股票」列不动时无法理解。现家庭级与账户级统一按权益侧归类。
改这条前先读 `docs/spec/decisions.md` 的 D77（分桶口径）与 D91（用户可见标签）——本模块是全站唯一出口。
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
    'etf': CLASS_STOCK,
    'bond': CLASS_STOCK,
    'fund': CLASS_FUND,
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
