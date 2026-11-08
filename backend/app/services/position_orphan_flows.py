# -*- coding: utf-8 -*-
"""持仓**孤儿流水簇**（#2873 第三抽）。

孤儿流水 = 导入时匹配不到持仓的流水（`position_id IS NULL`、`entry_status='orphan'`）。
它们不是「异常数据」：券商交割单里常有、代码缺失时有（#1920 实测真实库 1348/2051 笔
无 symbol），先落孤儿再等建仓时挂回，比丢弃或阻断整批导入安全。

## 为什么单独成模块

这一簇从 `position_service`（god module）整簇搬出，边界是「**只有导入路径会走、
且都以 `position_id=None` 落库**」的写入口：

    _create_orphan_transaction        孤儿流水落库（含费用四列/配对组/来源透传）
    _create_cash_transfer_transaction 货基/逆回购申赎的现金转移流水
    find_orphan_cash_flows            #863 口径 A：待挂回流水的**唯一**匹配入口
    _reattach_orphan_flows            建仓时把历史孤儿挂回持仓（互斥：一处资金一种表达）
    process_orphan_*                  导入路径的卖出/兑付/分红/再投/送股

## 与主模块的依赖方向

`position_service` 在**模块级**导入本模块（re-export 保 facade）；本模块只在**函数内**
延迟导入 `position_service` —— 因为孤儿路径要复用核心命令（卖出、兑付、分红、重算），
而这些命令仍留在主模块。函数级导入是本仓既有范式（185 处），此处集中在 5 个函数入口，
一眼可数，不存在模块加载期的循环依赖。

## 刻意不做的事

不把 `_create_dividend_cash_txn` / `_reinvest_dual_flow` / `_is_reinvest` 一并搬过来：
它们同时被**核心分红路径**（`process_dividend_reinvest`）使用，搬走只会把循环依赖
从「孤儿→核心」扩大成「双向」，收益为零。
"""

import uuid
from typing import NamedTuple, Optional

from loguru import logger
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.constants import PositionSource
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.fund_utils import CASH_EQUIVALENT_ASSET_TYPES, normalize_fund_code
from app.services.position_write_support import (
    _fee_breakdown_kwargs,
    _find_position_by_identity,
    _get_asset_type,
    _resolve_family_id,
)
from app.services.trading import TransactionService


def _create_cash_transfer_transaction(db: Session, data: dict, txn_type: str) -> None:
    """
    为现金管理产品（货币基金/逆回购）创建孤立交易流水。
    金额转换为分后存储。
    """
    net_amount = abs(data.get('net_amount', 0) or 0)
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=data.get('symbol', ''),
        txn_type=txn_type,
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        asset_type=_get_asset_type(data),
        ledger_id=data.get('ledger_id'),
        quantity=0,
        price=0,
        fee=0,
        amount=Money.yuan_to_cents(net_amount),
        status='success',
        position_name=data.get('name', ''),
        account_name=data.get('account_name', ''),
        notes=data.get('notes') or ('现金管理产品申赎' if txn_type == 'buy' else '现金管理产品赎回'),
        import_hash=data.get('import_hash'),
        entry_status='orphan',
        family_id=_resolve_family_id(data),
        # #1232 决策 11：孤儿/现金转移流水来源透传
        source=data.get('source'),
    )
    db.flush()


def _create_orphan_transaction(
    db: Session,
    data: dict,
    txn_type: str,
    quantity: float,
    price: float,
    amount: float,
    notes: str,
) -> None:
    """
    创建孤立交易流水（无法匹配到持仓时使用）。
    所有金额和数量转换为内部单位后存储。
    """
    qty_units = Money.shares_to_min_unit(quantity)
    price_units = Money.yuan_to_price_units(price)
    amount_cents = Money.yuan_to_cents(amount) if amount else Money.multiply_price_quantity(price_units, qty_units)
    fee_cents = Money.yuan_to_cents(data.get('fee', 0) or 0)
    # #2137 费用拆分：data 带明细才落四列，否则四列留 NULL（未拆分）
    fee_breakdown = _fee_breakdown_kwargs(data)

    TransactionService.create(
        db=db,
        position_id=None,
        symbol=data.get('symbol', ''),
        txn_type=txn_type,
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        asset_type=_get_asset_type(data),
        quantity=qty_units,
        price=price_units,
        fee=fee_cents,
        **fee_breakdown,
        amount=amount_cents,
        ledger_id=data.get('ledger_id'),
        status='success',
        position_name=data.get('name', ''),
        account_name=data.get('account_name', ''),
        notes=notes,
        import_hash=data.get('import_hash'),
        entry_status='orphan',
        # 配对组（#2836）：兑息与代扣税都走本函数落库，组名不写进来的话，
        # 前端折叠（按组算的）看起来正常，库里却是两条互不相干的孤儿流水——
        # 后续按组做「净额对账 / 删组回滚」时才发现关联早没了。
        link_group_id=data.get('link_group_id'),
        family_id=_resolve_family_id(data),
        # #1232 决策 11：孤儿流水来源透传
        source=data.get('source'),
    )
    db.flush()


class BondRedeemOutcome(NamedTuple):
    """债券兑付的落账结果（#2832）。

    ``position is None`` 有两种截然不同的含义，**必须分开**：

    - ``is_orphan=False`` → 兑付成功且已清仓（#2343：行保留 + cleared，方法契约同卖出）；
    - ``is_orphan=True``  → 未匹配到持仓，落的是孤儿流水。

    导入侧的 ``orphan_count`` 是给用户看的「有多少笔没归位」，把「兑付清仓」算进去
    会让人以为数据有问题。卖出路径历史上正是用单个 ``None`` 承载了这两种语义
    （`process_orphan_sell_or_withdraw` + 调用方 ``if result is None: orphan_count += 1``），
    这次不复制那个歧义。
    """

    position: Optional['Position']
    is_orphan: bool


def find_orphan_cash_flows(db: Session, ledger_id, symbol: str, family_id: int) -> list[Transaction]:
    """#863 口径 A：同 (ledger_id, family_id, symbol) 的**未挂回**货基 / 逆回购流水（非收益行）。

    匹配口径的**唯一入口**——写入层挂回（`_reattach_orphan_flows`）与一次性修复脚本
    （`scripts/fix_orphan_money_fund_reattach.py`）都必须经本函数，避免两处口径漂移。
    #1657 复审即栽在这：脚本曾用 `symbol` 精确相等，`SZ001937` ↔ `001937` 这类跨形态
    组合被静默漏挂，而本机 3 个成功案例恰好都是裸码对裸码，把缺陷掩盖了。

    口径说明：`normalize_fund_code` 会剥掉 `SZ/SH/BJ` 前缀与分隔符，故原候选集
    `{code, 'SZ'+code, 'SH'+code}` 恒等价于 `{code}`——判定即两侧归一化后相等。

    `symbol` 归一化不出 6 位数字时（非标准基金代码，如测试里的 `MF001`、手工建的
    非基金标的）**退回精确相等**：原实现此时退化为候选集 `{''}`，会让「同样归一化
    失败的流水」互相匹配、把不相干的孤儿流水一并吸走；但直接短路成空又会破坏
    非标准代码的正常挂回（`MF001` ↔ `MF001` 应当命中）。
    """
    # #1305 #17：`or_` 已在模块顶部导入，函数内不再重复 import（原为每次调用重复导入）
    code = normalize_fund_code(symbol)

    rows = (
        db.query(Transaction)
        .filter(
            Transaction.ledger_id == ledger_id,
            Transaction.position_id.is_(None),
            Transaction.family_id == family_id,
            Transaction.asset_type.in_(CASH_EQUIVALENT_ASSET_TYPES),
            or_(Transaction.is_income.is_(None), Transaction.is_income.is_(False)),
        )
        .all()
    )
    if code:
        return [t for t in rows if t.symbol and normalize_fund_code(t.symbol) == code]
    return [t for t in rows if t.symbol == symbol]


def _reattach_orphan_flows(db: Session, ledger_id, symbol: str, position_id: int, family_id: int) -> None:
    """#863 口径 A 写入层互斥：把同 (ledger_id, symbol) 的孤儿货基流水挂回持仓。

    互斥语义：同一资金同一 (ledger_id, symbol) 只能有一种表达——持仓 或 孤儿净额。
    建仓后把历史孤儿流水（position_id IS NULL、非收益行）置 position_id，使其不再
    计入孤儿净额桶；金额由持仓市值承接（净值恒 1，市值≈本金），不双计、不漏计。
    is_income 收益行不挂回（收益桶独立于本金，见 #863 D1）。

    筛选范围由 `find_orphan_cash_flows` 收口（只认现金等价物类型 + 同 ledger/family +
    归一化符号相等）。**调用方不要再拿 `position.is_money_fund` 当闸门**：该列存在历史
    未回填 / 快照判定不一致（本机 pos[445]/pos[26] 为货基却为 0），以它为准会漏挂回
    导致资金双计（#1657）；对非现金等价物持仓本函数天然无操作（幂等）。
    """
    matched = find_orphan_cash_flows(db, ledger_id, symbol, family_id)
    if matched:
        for txn in matched:
            txn.position_id = position_id
        logger.info(f'货基建仓挂回孤儿流水 {len(matched)} 条（ledger={ledger_id}, symbol={symbol}）')


@staticmethod
def process_orphan_bond_redeem(db: Session, data: dict) -> BondRedeemOutcome:
    """导入路径的债券兑付：先按身份键关联持仓，找不到才记孤儿流水。

    返回 :class:`BondRedeemOutcome`，调用方据 ``is_orphan`` 计数——不要用
    ``position is None`` 判断孤儿，那会把「兑付清仓」误算成孤儿（见该类 docstring）。

    与 :meth:`process_orphan_sell_or_withdraw` 的两点不同：

    - 按 ``active_only=True`` 匹配：兑付后持仓已 ``cleared``，再导入同一只债的
      兑付时不该命中那条空壳行（命中了只会报「兑付数量超过持仓」）；
    - **不吞「超量兑付」的 ValueError**：卖出路径会把数量不足降级成孤儿，
      兑付不行——见 :meth:`process_bond_redeem` 第 3 条理由。
    """
    from app.services.position_service import PositionService  # noqa: PLC0415  循环依赖：核心兑付命令仍在主模块

    symbol = data.get('symbol', '')
    name = (data.get('name') or data.get('position_name') or '').strip()

    existing = None
    if symbol:
        existing = _find_position_by_identity(db, data, symbol=symbol, active_only=True)
    if existing is None and name:
        # 交割单「证券名称常有、代码为空」的场景与卖出同源（#1920）
        existing = _find_position_by_identity(db, data, name=name, active_only=True)
        if existing is not None:
            logger.info(
                '债券兑付按名称兜底关联到持仓：symbol=%r name=%r ledger_id=%r → position_id=%s',
                symbol,
                name,
                data.get('ledger_id'),
                existing.id,
            )

    if existing is not None:
        return BondRedeemOutcome(
            position=PositionService.process_bond_redeem(db, {**data, 'position_id': existing.id}),
            is_orphan=False,
        )

    _create_orphan_transaction(
        db,
        data,
        txn_type='bond_redeem',
        quantity=data.get('quantity') or 0,
        price=data.get('avg_price') or 0,
        # 到账额优先；都没有才让 _create_orphan_transaction 按价格×数量兜底
        amount=data.get('net_amount') if data.get('net_amount') is not None else (data.get('amount') or 0),
        notes=data.get('notes') or '债券到期兑付（未匹配到持仓）',
    )
    return BondRedeemOutcome(position=None, is_orphan=True)


@staticmethod
def process_orphan_dividend(db: Session, data: dict) -> Optional[Position]:
    """
    处理分红记录，优先尝试关联持仓；找不到持仓则创建孤立流水。

    红利再投资（dividend_reinvest）走单独分支——分红入账 ＋ 按净值申购，
    使持仓份额真正增加；此前它与现金分红合并进同一分支，份额恒为 0，语义丢失。
    数据不全（缺份额或净值）时降级为现金分红，不阻断整批导入。
    """
    from app.services.position_service import (  # noqa: PLC0415  循环依赖：核心分红命令仍在主模块
        PositionService,
        _is_reinvest,
    )

    symbol = data.get('symbol', '')
    dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
    is_reinvest = _is_reinvest(data)

    # #2372：按身份键 (ledger_id, symbol) 匹配，不再拿可编辑的 account_name 跨账户猜
    existing = _find_position_by_identity(db, data, symbol=symbol)

    common = {
        'dividend_amount': dividend_amount,
        'confirm_date': data.get('confirm_date'),
        'trade_date': data.get('trade_date'),
        'notes': data.get('notes', ''),
        'import_hash': data.get('import_hash'),
        'link_group_id': data.get('link_group_id'),
        'family_id': _resolve_family_id(data),
    }

    if existing:
        if is_reinvest:
            return PositionService.process_orphan_dividend_reinvest(db, data)
        return PositionService.process_dividend(db, {**common, 'position_id': existing.id})
    else:
        _create_orphan_transaction(
            db,
            data,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=dividend_amount,
            notes=data.get('notes') or ('红利再投资（待关联持仓）' if is_reinvest else '现金分红'),
        )
        return None


@staticmethod
def process_orphan_dividend_reinvest(db: Session, data: dict) -> Optional[Position]:
    """导入路径：红利再投资，优先关联既有持仓；找不到持仓或缺少份额则降级。

    - 有持仓且具备再投份额：分红现金 + 按净值申购双流水（_reinvest_dual_flow）。
    - 有持仓但缺份额：降级为现金分红（单笔），不阻断整批导入。
    - 无关联持仓：记孤儿现金分红流水（notes 标明红利再投资），返回 None。
    """
    from app.services.position_service import (  # noqa: PLC0415  循环依赖
        _create_dividend_cash_txn,
        _is_reinvest,
        _reinvest_dual_flow,
    )

    family_id = _resolve_family_id(data)
    symbol = data.get('symbol', '')
    # #2372：按身份键 (ledger_id, symbol) 匹配，不再拿可编辑的 account_name 跨账户猜
    existing = _find_position_by_identity(db, data, symbol=symbol)
    link_group_id = data.get('link_group_id') or uuid.uuid4().hex
    if not existing:
        # 无关联持仓：红利再投资无法落地，记孤儿现金分红流水（notes 标明）
        _create_dividend_cash_txn(db, data, None, link_group_id)
        return None
    if not _is_reinvest(data):
        # 缺份额：降级为现金分红，份额不变，不阻断整批导入
        _create_dividend_cash_txn(db, data, existing, link_group_id, entry_status='success')
        return existing
    _reinvest_dual_flow(db, data, existing, link_group_id)
    return existing


@staticmethod
def process_orphan_split(db: Session, data: dict) -> Optional[Position]:
    """送股/拆分：优先关联既有持仓并把份额计入；找不到持仓或缺少份额则记孤儿流水。

    送股/拆分本质是「零成本的份额增加」：持仓份额 +quantity、总成本不变，均价由
    recompute_position_from_transactions 自动稀释（与买入/卖出回滚同一口径，避免再添分支）。
    手动记账传 position_id 直接定位；导入路径按身份键 (ledger_id, symbol) 匹配
    （#2372：不再按可编辑的 account_name 跨账户匹配）。
    """
    from app.services.position_service import (  # noqa: PLC0415  循环依赖
        PositionService,
        _resolve_fund_name_by_code,
        _resolve_ledger_name_by_id,
    )

    family_id = _resolve_family_id(data)
    qty = data.get('quantity') or 0

    if qty <= 0:
        # 缺份额：无法计入，记孤儿流水（notes 标明），不阻断整批导入
        _create_orphan_transaction(
            db,
            data,
            txn_type='split',
            quantity=0,
            price=0,
            amount=0,
            notes=data.get('notes') or '送股/拆分（缺份额，需手动关联持仓）',
        )
        return None

    qty_units = Money.shares_to_min_unit(qty)
    position_id = data.get('position_id')
    if position_id:
        existing = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
    else:
        # #2372：身份键 (ledger_id, symbol)；ledger_id 为空时只匹配未归档持仓
        existing = _find_position_by_identity(db, data, symbol=data.get('symbol', ''))

    if not existing:
        # 无关联持仓：送股/拆分无法落地，记孤儿流水（notes 标明），返回 None
        _create_orphan_transaction(
            db,
            data,
            txn_type='split',
            quantity=qty,
            price=0,
            amount=0,
            notes=data.get('notes') or '送股/拆分入账（需手动关联持仓）',
        )
        return None

    # 有关联持仓：记成功流水 + 重算份额（split 作为零成本份额增加，均价自动稀释）
    TransactionService.create(
        db=db,
        position_id=existing.id,
        symbol=data.get('symbol') or existing.symbol,  # 以持仓为准（#2855，同卖出路径）
        txn_type='split',
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        asset_type=_get_asset_type(data),
        quantity=qty_units,
        price=0,
        fee=Money.yuan_to_cents(data.get('fee', 0) or 0),
        amount=0,
        status='success',
        entry_status='success',
        # #2372：快照缺失时按 ID 兜底反查，不留 NULL 前端显示「未知资产/未知账户」
        position_name=existing.name or _resolve_fund_name_by_code(db, existing.symbol),
        ledger_id=existing.ledger_id,
        account_name=(
            existing.account_name or _resolve_ledger_name_by_id(db, existing.ledger_id) or data.get('account_name', '')
        ),
        notes=data.get('notes') or '送股/拆分入账',
        import_hash=data.get('import_hash'),
        link_group_id=data.get('link_group_id'),
        family_id=family_id,
        # #1232 决策 11：流水来源透传（记一笔默认 manual）
        source=data.get('source') or PositionSource.MANUAL.value,
    )
    db.flush()
    return PositionService.recompute_position_from_transactions(db, existing.id)
