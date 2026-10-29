# -*- coding: utf-8 -*-
# Author : imoyao
"""#2617 持仓结构（资产类别占比 / 股基分列 Top N / 集中度）。

为什么不能复用 `summary.distributions`：那个是**家庭级**按产品类型聚合，
没有 `ledger_id` / `portfolio_id` 作用域，也没有 Top N 与集中度。组合页问的是
「这个组合里钱压在哪」，必须能在单账户/单组合口径下回答。

## 作用域决定视角（#2739 追加）

账户级作用域下，**视角由账户类型（`ledgers.ledger_type`）决定，不由用户切换**：

| `ledger_type` | 唯一视角 | 理由 |
|---|---|---|
| `stock`（证券账户） | 股票 | 账户就是买股票的 |
| `fund`（基金账户） | 基金 | 账户就是买基金的 |
| `bank`（现金账户） | 基金 | 除现金外按基金视角处理（owner 裁定） |
| `e_account`（基金 E 账户） | 基金 | 基金汇总账户 |

组合级 / 家庭级**仍保留双视角切换**：一个组合可同时含股票账户与基金账户
的持仓（实测组合「嘲风仰望星空」即含 28 只基金持仓），家庭级更是全类型混合，
此时切换才有意义。

⚠️ 字段职责（铁律见 `docs/working-notes/ledger-channel-category-redesign-2026-08-28.md`
§2.2/§2.3）：本模块用 `ledger_type`（内部资产类计算口径键）**驱动视图分支**，
这是它的规定用途；`channel_category` 是用户可见的渠道分组，**不得**用于此。

## 口径细则

1. **作用域唯一出口** `services.scope.filter_positions_by_scope`（与归因 / 穿透
   同一条组合语义：显式 `positions.portfolio_id` + 成员账本继承），不在此手写查询。
2. **股基分列、不合并排名**：股票与基金（含场外基金）的份额与价格不可比，合并成
   一张 Top N 排行榜没有意义。`other`（债券/货基/逆回购等）只出总额，不参与 Top。
3. **按标的合并再排名**：同一 symbol 在多个账户持有时先合并市值再排序——否则
   「前 5 大持仓」会被同一只基金的账户拆分挤掉，集中度被系统性低估。
   合并后仍保 `accounts` 计数，便于下钻。
4. **账户级下 ETF 归权益侧**：ETF 是**场内**交易品种，与股票同为按市价计价，
   合并排名不违反第 2 条（那条约束针对的是场外基金的净值口径）。实测证券账户
   「同花顺（银河证券）」的 ETF 占该账户市值 21.2%，若归入基金侧则会被账户级
   固定视角完全藏起来。组合/家庭级维持原分类（`etf → fund`），避免误伤组合页。
5. **账户级下货基走类现金**：货基本质是现金等价物（见
   `services.fund_utils.is_cash_equivalent_position`），不是「持仓」。
   纳入持仓榜会稀释集中度（货基几乎零波动）并让「前 5 大持仓」失真。
   实测货基仅占家庭总市值 2.9%，排除出榜不损失结构信息。

市值走唯一口径 `position_valuation.market_value_cents`（外币按 `EXCHANGE_RATES`
折 CNY），与仪表盘 / 穿透 / 归因同源。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.services.fund_utils import is_cash_equivalent_position
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

# 账户类型 → 该账户的唯一视角（#2739）。
# `bank` 走基金视角：除现金外按基金处理（owner 裁定）。
# `property` / `family` 不在此表——它们不持有可排名的持仓，返回 None 表示「无固定视角」。
_LEDGER_TYPE_VIEW = {
    'stock': 'stock',
    'fund': 'fund',
    'bank': 'fund',
    'e_account': 'fund',
}


def _class_of(asset_type: Optional[str]) -> str:
    return _CLASS_OF.get((asset_type or '').lower(), 'other')


def _ratio(part_cents: int, whole_cents: int) -> Optional[float]:
    return round(part_cents / whole_cents * 100, 2) if whole_cents else None


def _resolve_ledger_view(db: Session, ledger_id: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    """取该账户的固定视角。

    Returns:
        `(view, ledger_type)`：视角为 `stock` / `fund` / `None`（无固定视角）；
        `ledger_type` 原样返回，供前端展示与口径说明。
    """
    if ledger_id is None:
        return None, None
    ledger = db.query(Ledger).filter(Ledger.id == ledger_id).first()
    if ledger is None:
        return None, None
    ledger_type = (ledger.ledger_type or '').lower()
    return _LEDGER_TYPE_VIEW.get(ledger_type), ledger_type or None


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
        + `concentration`（前 5 占比，整体与分列）+ `view`（账户级固定视角）。
        金额一律元（2 位小数）。
    """
    if ledger_id is not None and portfolio_id is not None:
        raise ValueError('ledger_id 与 portfolio_id 互斥')

    positions, _assets = _load_user_assets(db, family_id)
    positions = filter_positions_by_scope(db, family_id, positions, ledger_id=ledger_id, portfolio_id=portfolio_id)

    # 账户级 ⇒ 固定视角 + 口径改写（ETF 归权益侧 / 货基走类现金）
    fixed_view, ledger_type = _resolve_ledger_view(db, ledger_id)

    # ── 1. 逐持仓定值 + 归类 + 按标的合并 ──────────────────────────────
    class_cents: Dict[str, int] = {cls: 0 for cls in CLASS_ORDER}
    merged: Dict[str, Dict[str, Any]] = {}
    total_cents = 0
    cash_like_cents = 0
    counted_positions = 0
    for pos in positions:
        rate = EXCHANGE_RATES.get(getattr(pos, 'currency', None), 1.0)
        cents = market_value_cents(pos, rate=rate)
        if cents <= 0:
            continue

        # 账户级：货基走类现金，排除出持仓榜（口径 5）
        if fixed_view is not None and is_cash_equivalent_position(pos):
            cash_like_cents += cents
            continue

        counted_positions += 1
        asset_type = (getattr(pos, 'asset_type', None) or '').lower()
        cls = _class_of(asset_type)
        # 账户级 + 股票视角：ETF 归权益侧（口径 4）
        if fixed_view == 'stock' and asset_type == 'etf':
            cls = 'stock'

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

    notes = [
        '股票与基金分开排名：份额与价格不可比，合并榜单没有意义（卡面硬约束）。',
        '同一标的在多个账户持有时先合并市值再排名，`accounts` 是合并了几个账户。',
        '「其他」含债券/货基/逆回购等，只出总额不参与 Top；货基本质无股票敞口，其行业暴露看穿透面板而不是本面板。',
    ]
    if fixed_view == 'stock':
        notes.insert(
            0,
            '本账户是证券账户，只看股票视角：ETF 按场内市价与股票合并排名；'
            '债券等非权益持仓归「其他」只出总额；货币基金走类现金口径，不计入持仓。',
        )
    elif fixed_view == 'fund':
        notes.insert(
            0,
            '本账户是基金账户，只看基金视角：场内 ETF 归基金侧；'
            '非基金持仓归「其他」只出总额；货币基金走类现金口径，不计入持仓。',
        )

    return {
        'scope': 'portfolio' if portfolio_id is not None else ('ledger' if ledger_id is not None else 'family'),
        'ledger_id': ledger_id,
        'portfolio_id': portfolio_id,
        'total_cny': Money.cents_to_yuan(total_cents),
        # 持仓只数：与 total_cny 同口径（账户级下不含走类现金的货基）
        'position_count': counted_positions,
        # 账户级固定视角（组合/家庭级为 None ⇒ 前端保留切换控件）
        'view': fixed_view,
        'ledger_type': ledger_type,
        'cash_like_cny': Money.cents_to_yuan(cash_like_cents),
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
        'notes': notes,
    }


__all__ = ['build_position_structure']
