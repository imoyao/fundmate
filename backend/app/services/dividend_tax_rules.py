# -*- coding: utf-8 -*-
"""红利税应税判定规则（2026-11-08 从 `dividend_tax_service` 拆出）。

为什么单独一个模块：这两件事都是**纯规则**——「这笔是不是该考虑红利税的分红」和
「这个标的是不是免税品种」；而服务主体要同时做取数、配对、落库。混在一起会把服务
推过体量与复杂度闸门（`scripts/guard_service_size.py`），也让同一套口径没法复用。

#1661 / 2026-11-07：货基持仓的 `asset_type` 仍是 `fund`，「是不是货币基金」记在
`positions.is_money_fund` 上（见 `core/investment_tiers.py` 的说明）。只读
`asset_type` 会让场内货基的收益被当成现金分红、误报「漏扣红利税」——而货基收益本
就不在 `NO_DIVIDEND_TAX_ASSET_TYPES` 的应税范围里。

代码口径：场内代码可能带 `SH`/`SZ` 前缀，而持仓表存裸 6 位码（或反过来）。所有
「代码 → 资产类型」的查找都同时登记原码与剥前缀后的裸码；只按原码查会查不到，
免税白名单就会**静默失效**。
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.core.symbol_utils import strip_exchange_prefix
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction

# 分红类流入的白名单关键词：操作名（`notes`）里出现这些才算「分红 / 派息」。
# 取自活表 `importer/mappings.THS_OP_MAP` 里落成 `dividend_cash` 的操作名，
# 外加「利息」——存款/理财利息也被映射成 dividend，这里用「含利息 ⇒ 排除」反着用。
DIVIDEND_KEYWORDS = ('红利', '分红', '派息', '股息', '兑息')
# 非分红类的关键词：命中即排除（利息 / 兑付 / 退款 / 零款）。
NOT_DIVIDEND_KEYWORDS = ('利息', '兑付', '退款', '退息', '零款', '兑息')
# 不给红利税补记提示的资产类型：可转债（`bond`）的派息是利息，货基/逆回购同理。
# bank_wealth（银行理财）与 bank（银行存款）的到账是「理财收益 / 存款利息」，同样不是股息，
# 提示红利税会让用户以为漏扣了税。
NO_DIVIDEND_TAX_ASSET_TYPES = frozenset({'bond', 'money_fund', 'reverse_repo', 'cash', 'bank', 'bank_wealth'})


def position_asset_types(db: Session, family_id: int) -> dict[str, str]:
    """标的代码 → 资产类型（持仓表快照；流水自带 `asset_type` 时优先用流水的）。"""
    rows = (
        db.query(Position.symbol, Position.asset_type, Position.is_money_fund)
        .filter(Position.family_id == family_id, Position.symbol.isnot(None))
        .all()
    )
    out: dict[str, str] = {}
    for symbol, asset_type, is_money_fund in rows:
        if not symbol:
            continue
        value = 'money_fund' if is_money_fund is True else asset_type
        if not value:
            continue
        raw = symbol.strip()
        out.setdefault(raw, value)
        bare = strip_exchange_prefix(raw)
        if bare:
            out.setdefault(bare, value)
    return out


def resolve_asset_type(
    raw_symbol: str,
    txn_asset_type: Optional[str],
    position_types: dict[str, str],
) -> Optional[str]:
    """这笔流水该按什么资产类型判定。

    持仓侧的免税判定（如 `is_money_fund`）**优先于**流水上的 `asset_type`：货基标记
    不在 `asset_type` 上，流水写 `fund` 不能把它变成要交红利税的股票。
    """
    symbol = (raw_symbol or '').strip()
    position_asset = position_types.get(strip_exchange_prefix(symbol)) or position_types.get(symbol)
    if position_asset in NO_DIVIDEND_TAX_ASSET_TYPES:
        return position_asset
    return txn_asset_type or position_asset


def is_dividend_income(txn: Transaction, asset_type: Optional[str]) -> bool:
    """这笔 `txn_type='dividend'` 是不是「该考虑红利税」的那一类现金分红。

    三道判据（任一命中即排除）：

    1. 资产类型是债 / 货基 / 逆回购 / 存款——它们的派息是利息，与红利税无关；
    2. 操作名里含「利息 / 兑付 / 退款 / 退息 / 零款」——同花顺把这些也映射成 dividend；
    3. 操作名里既没有「红利 / 分红 / 派息 / 股息 / 兑息」，也不是空（手动记账常写
       「现金分红」，含「分红」二字）。
    """
    if asset_type and asset_type in NO_DIVIDEND_TAX_ASSET_TYPES:
        return False
    notes = (txn.notes or '').strip()
    if notes:
        # 注：`DIVIDEND_KEYWORDS` 里也含「兑息」（基金/债券的派息说法），所以
        # 排除表里必须显式带上「兑息」并**先判**——顺序不能反，否则「债券兑息」
        # 会走成「这是分红」。
        if any(word in notes for word in NOT_DIVIDEND_KEYWORDS):
            return False
        return any(word in notes for word in DIVIDEND_KEYWORDS)
    # 手动记账 / 未标 notes 的分红：默认算分红（宁可提醒，不可漏）
    return True
