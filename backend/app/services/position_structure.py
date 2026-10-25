# -*- coding: utf-8 -*-
# Author : imoyao
"""#2617 持仓结构（资产类别占比 / 股基分列 Top N / 集中度）。

为什么不能复用 `summary.distributions`：那个是**家庭级**按产品类型聚合，
没有 `ledger_id` / `portfolio_id` 作用域，也没有 Top N 与集中度。组合页问的是
「这个组合里钱压在哪」，必须能在单账户/单组合口径下回答。

## 三条口径

1. **作用域唯一出口** `services.scope.filter_positions_by_scope`（与归因 / 穿透
   同一条组合语义：显式 `positions.portfolio_id` + 成员账本继承），不在此手写查询。
2. **股基分列、不合并排名**：股票与基金（含 ETF）的份额与价格不可比，合并成一张
   Top N 排行榜没有意义。`other`（债券/货基/逆回购等）只出总额，不参与 Top。
3. **按标的合并再排名**：同一 symbol 在多个账户持有时先合并市值再排序——否则
   「前 5 大持仓」会被同一只基金的账户拆分挤掉，集中度被系统性低估。
   合并后仍保 `accounts` 计数，便于下钻。

市值走唯一口径 `position_valuation.market_value_cents`（外币按 `EXCHANGE_RATES`
折 CNY），与仪表盘 / 穿透 / 归因同源。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.services.position_valuation import market_value_cents
from app.services.scope import filter_positions_by_scope
from app.services.summary_service import _load_user_assets

# 资产类别归属：股票 / 基金（含 ETF）/ 其他
_CLASS_OF = {
    'stock': 'stock',
    'fund': 'fund',
    'etf': 'fund',
}
CLASS_LABELS = {'stock': '股票', 'fund': '基金', 'other': '其他'}
CLASS_ORDER = ('stock', 'fund', 'other')
MAX_TOP_N = 50


def _class_of(asset_type: Optional[str]) -> str:
    return _CLASS_OF.get((asset_type or '').lower(), 'other')


def _ratio(part_cents: int, whole_cents: int) -> Optional[float]:
    return round(part_cents / whole_cents * 100, 2) if whole_cents else None


def build_position_structure(
    db: Session,
    family_id: int = 1,
    *,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """持仓结构（家庭 / 账户 / 组合三级口径）。

    Args:
        ledger_id / portfolio_id: 互斥，同时传抛 ValueError（与归因 / 穿透同文案）。
        top_n: 每组榜单条数（1–50，超出夹取）；集中度固定看前 5。

    Returns:
        `by_asset_class`（三类占比）+ `groups`（股/基各自的 Top N、组内集中度）
        + `concentration`（前 5 占比，整体与分列）。金额一律元（2 位小数）。
    """
    if ledger_id is not None and portfolio_id is not None:
        raise ValueError('ledger_id 与 portfolio_id 互斥')

    positions, _assets = _load_user_assets(db, family_id)
    positions = filter_positions_by_scope(db, family_id, positions, ledger_id=ledger_id, portfolio_id=portfolio_id)

    # ── 1. 逐持仓定值 + 归类 + 按标的合并 ──────────────────────────────
    class_cents: Dict[str, int] = {cls: 0 for cls in CLASS_ORDER}
    merged: Dict[str, Dict[str, Any]] = {}
    total_cents = 0
    for pos in positions:
        rate = EXCHANGE_RATES.get(getattr(pos, 'currency', None), 1.0)
        cents = market_value_cents(pos, rate=rate)
        if cents <= 0:
            continue
        cls = _class_of(getattr(pos, 'asset_type', None))
        class_cents[cls] += cents
        total_cents += cents
        key = f'{cls}:{getattr(pos, "symbol", "") or getattr(pos, "name", "")}'
        row = merged.setdefault(
            key,
            {
                'symbol': getattr(pos, 'symbol', None),
                'name': getattr(pos, 'name', None),
                'asset_type': getattr(pos, 'asset_type', None),
                'class': cls,
                'value_cents': 0,
                'accounts': 0,
            },
        )
        row['value_cents'] += cents
        row['accounts'] += 1

    top_n = max(1, min(int(top_n or 5), MAX_TOP_N))

    # ── 2. 股 / 基各自排名（other 只出总额）─────────────────────────────
    groups: Dict[str, Any] = {}
    for cls in ('stock', 'fund'):
        rows = sorted(
            (r for r in merged.values() if r['class'] == cls),
            key=lambda r: -r['value_cents'],
        )
        group_total = class_cents[cls]
        top = rows[:top_n]
        top5 = rows[:5]
        groups[cls] = {
            'label': CLASS_LABELS[cls],
            'count': len(rows),
            'total_cny': Money.cents_to_yuan(group_total),
            'ratio_of_total': _ratio(group_total, total_cents),
            'top': [
                {
                    'symbol': r['symbol'],
                    'name': r['name'],
                    'asset_type': r['asset_type'],
                    'value_cny': Money.cents_to_yuan(r['value_cents']),
                    'ratio_of_total': _ratio(r['value_cents'], total_cents),
                    'ratio_of_group': _ratio(r['value_cents'], group_total),
                    'accounts': r['accounts'],
                }
                for r in top
            ],
            'top5_ratio_of_group': _ratio(sum(r['value_cents'] for r in top5), group_total),
            'top5_ratio_of_total': _ratio(sum(r['value_cents'] for r in top5), total_cents),
        }

    all_rows = sorted(merged.values(), key=lambda r: -r['value_cents'])
    top5_all_cents = sum(r['value_cents'] for r in all_rows[:5])

    return {
        'scope': 'portfolio' if portfolio_id is not None else ('ledger' if ledger_id is not None else 'family'),
        'ledger_id': ledger_id,
        'portfolio_id': portfolio_id,
        'total_cny': Money.cents_to_yuan(total_cents),
        'position_count': len(positions),
        'by_asset_class': [
            {
                'key': cls,
                'label': CLASS_LABELS[cls],
                'value_cny': Money.cents_to_yuan(class_cents[cls]),
                'ratio_of_total': _ratio(class_cents[cls], total_cents),
            }
            for cls in CLASS_ORDER
        ],
        'groups': groups,
        'concentration': {
            # 整体前 5 占比：含「其他」（债/货基），故可能明显高于股票或基金的组内集中度
            'top5_ratio_of_total': _ratio(top5_all_cents, total_cents),
            'top5_ratio_of_stock': groups['stock']['top5_ratio_of_group'],
            'top5_ratio_of_fund': groups['fund']['top5_ratio_of_group'],
        },
        'notes': [
            '股票与基金分开排名：份额与价格不可比，合并榜单没有意义（卡面硬约束）。',
            '同一标的在多个账户持有时先合并市值再排名，`accounts` 是合并了几个账户。',
            '「其他」含债券/货基/逆回购等，只出总额不参与 Top；货基本质无股票敞口，其行业暴露看穿透面板而不是本面板。',
        ],
    }


__all__ = ['build_position_structure']
