# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 21:46
# File : position_service.py

"""
持仓业务逻辑服务层。

职责：
- 处理买入/存入的持仓合并与创建
- 处理卖出/取出的数量扣减与清空
- 处理分红流水记录
- 所有方法接收 SQLAlchemy Session 与原始数据字典
- 业务异常通过 ValueError 抛出，由视图层捕获并转为 HTTP 异常
"""

import uuid
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import PositionSource, ValuationMode
from app.core.exceptions import ErrorCode, SBException
from app.core.money import Money
from app.core.symbol_utils import derive_security_type, get_normalizer, split_symbol
from app.core.utils import get_confirm_date
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta, resolve_sales_institution_id
from app.domains.transactions.models import Transaction
from app.services.async_backfill import trigger_backfill
from app.services.fund_utils import CASH_EQUIVALENT_ASSET_TYPES, is_money_fund_symbol, normalize_fund_code
from app.services.importer.records import compute_position_hash
from app.services.pnl_service import compute_sell_realized_cents
from app.services.trade_rules import validate_buy, validate_sell
from app.services.transaction_service import TransactionService

# 允许写入持仓模型的字段白名单（防止注入无效字段）
_ALLOWED_POSITION_FIELDS = {
    'symbol',
    'name',
    'market',
    'asset_type',
    'account_name',
    'ledger_id',
    'quantity',
    'avg_price',
    'currency',
    'current_price',
    'confirm_date',
    'notes',
    'allocation',
    # issue #928: 去重与溯源字段，允许透传落库
    'import_hash',
    'source',
    'source_import_id',
    'source_broker',
    # #1174 双态计价：balance 模式建仓需透传计价模式与可写市值
    'valuation_mode',
    'market_value_override',
}


def auto_purchase_money_fund(
    db: Session,
    ledger_id: Optional[int],
    amount_cents: int,
    trade_date=None,
    confirm_date=None,
    family_id: int = 1,
) -> None:
    """#1137 卖出/赎回回款自动申购账户绑定的类现金产品（「余额宝」）。

    仅在账户显式开启 `auto_purchase_money_fund` 且绑定了有效货基时执行——
    遵循「用户不操作，系统不代劳」，开关由用户在账户设置里自行开启。

    - 回款净额 <= 0 时不申购；
    - 生成**孤儿流水**（asset_type='money_fund'）：货基不建持仓，与导入器、
      `money_fund_income` 的既有口径一致（货基市值按流水净额计入总资产）；
    - 调用方须自行排除货基 / 逆回购自身的卖出，避免「赎回 → 自动申购」死循环
      （货基卖出在 `process_orphan_sell_or_withdraw` 里走现金转移分支，不进入本函数）。

    失败（绑定产品缺失等）仅告警不抛出：自动申购是增值行为，不应阻断卖出主流程。
    """
    if not ledger_id or amount_cents <= 0:
        return
    ledger = db.query(Ledger).filter_by(id=ledger_id, family_id=family_id).first()
    if not ledger or not ledger.auto_purchase_money_fund or not ledger.linked_money_fund_id:
        return
    fund = db.get(Fund, ledger.linked_money_fund_id)
    if not fund:
        logger.warning(f'账户 {ledger_id} 绑定的类现金产品 {ledger.linked_money_fund_id} 不存在，跳过自动申购')
        return
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=fund.fund_code,
        txn_type='buy',
        trade_date=trade_date,
        confirm_date=confirm_date,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=amount_cents,
        status='success',
        position_name=fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='卖出回款自动申购类现金产品',
        entry_status='orphan',
        family_id=family_id,
    )


# 录入阶段已显式给出的具体类型，直接信任，不再做代码推断（避免误伤基金等）
_SPECIFIC_ASSET_TYPES = {'etf', 'bond', 'fund', 'money_fund', 'reverse_repo', 'cash'}


def _get_asset_type(data: dict, default: str = 'stock') -> str:
    """
    录入阶段确定资产类型：显式具体类型 > 代码前缀推断 > 默认 stock。

    历史债背景：PositionCreate.asset_type 使用 validation_alias='type'，
    model_dump() 输出的是字段名 `asset_type`，而 importer 路径直接构造 `type` key，
    导致不同调用方传入的 key 不一致。此处收敛读取端，保证流水 asset_type 落库正确。

    分类下沉到录入阶段（#1264 / #1266）：仅当显式类型缺失，或显式为泛化默认 'stock' 时，
    才按代码前缀推断（沪 51/56/58、深 15/16 → ETF；11/12 → 可转债），
    以免把已正确标注为 fund/money_fund 的基金（代码前缀可能与股票/可转债重合）误判成股票。
    """
    explicit = data.get('asset_type') or data.get('type')
    if explicit and explicit in _SPECIFIC_ASSET_TYPES:
        return explicit
    symbol = data.get('symbol') or ''
    market, code = split_symbol(symbol)
    derived = derive_security_type(code, market)
    return derived or (explicit or default)


def _get_default_notes(op_type: str, is_new: bool) -> str:
    """生成默认的交易备注."""
    mapping = {
        (False, 'buy'): '追加买入',
        (False, 'deposit'): '追加存入',
        (True, 'buy'): '初始买入',
    }
    return mapping.get((is_new, op_type), '存入')


def _create_cash_transfer_transaction(db: Session, data: dict, txn_type: str) -> None:
    """
    为现金管理产品（货币基金/逆回购）创建孤立交易流水。
    金额转换为分后存储。
    """
    net_amount = abs(float(data.get('net_amount', 0) or 0))
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
        family_id=data.get('family_id', 1),
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
    fee_cents = Money.yuan_to_cents(float(data.get('fee', 0) or 0))

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
        amount=amount_cents,
        ledger_id=data.get('ledger_id'),
        status='success',
        position_name=data.get('name', ''),
        account_name=data.get('account_name', ''),
        notes=notes,
        import_hash=data.get('import_hash'),
        entry_status='orphan',
        family_id=data.get('family_id', 1),
        # #1232 决策 11：孤儿流水来源透传
        source=data.get('source'),
    )
    db.flush()


def _is_reinvest(data: dict) -> bool:
    """
    是否为「可执行」的红利再投资：类型命中 dividend_reinvest，且具备申购所需的份额与价格。

    份额必填；净值缺失时允许用 金额/份额 反推（由 process_dividend_reinvest 执行）。
    数据不全时返回 False，调用方降级按现金分红处理，避免一条脏数据阻断整批导入。
    """
    if data.get('op_type') != 'dividend_reinvest':
        return False

    shares = float(data.get('quantity') or 0)
    nav = float(data.get('nav') or 0)
    amount = float(data.get('dividend_amount') or 0)

    if shares <= 0:
        logger.warning('红利再投资缺少份额，降级按现金分红处理')
        return False
    if nav <= 0 and amount <= 0:
        logger.warning('红利再投资缺少净值且无法由金额反推，降级按现金分红处理')
        return False
    return True


def _create_dividend_cash_txn(
    db: Session, data: dict, position: Optional[Position], link_group_id: str, entry_status: str = 'orphan'
) -> None:
    """红利再投资的第一条流水：分红现金（txn_type='dividend'，份额为 0，link_group_id 与申购流水配对）。

    position 为 None 时记孤儿流水（无关联持仓）。entry_status 默认 orphan，
    双流水场景由调用方传 'success'。
    """
    base_hash = data.get('import_hash')
    dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
    TransactionService.create(
        db=db,
        position_id=position.id if position else None,
        txn_type='dividend',
        symbol=position.symbol if position else data.get('symbol'),
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        asset_type=_get_asset_type(data),
        link_group_id=link_group_id,
        quantity=0,
        price=0,
        fee=0,
        amount=Money.yuan_to_cents(dividend_amount),
        # 红利再投资的分红入账同样计入已实现盈亏（#1183）：与随后的申购流水（记投入、
        # 抬高成本基数）一进一出，对总盈亏净额为 0，与 XIRR「reinvest 记流出」自洽
        realized_pnl=Money.yuan_to_cents(dividend_amount),
        status='success',
        position_name=position.name if position else data.get('name', ''),
        account_name=position.account_name if position else data.get('account_name', ''),
        ledger_id=position.ledger_id if position else data.get('ledger_id'),
        notes=data.get('notes') or '红利再投资（分红入账）',
        import_hash=base_hash,
        entry_status=entry_status,
        family_id=data.get('family_id', 1),
        # #1232 决策 11：红利再投资分红流水来源透传
        source=data.get('source'),
    )
    db.flush()


def _build_reinvest_buy_data(data: dict, position: Optional[Position], link_group_id: str) -> dict:
    """构造红利再投资第二条流水（申购）的业务字典：price=净值，quantity=再投份额。"""
    nav = data.get('nav', data.get('avg_price', 0))
    dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
    shares = data.get('quantity') or (dividend_amount / nav if nav else 0)
    base_hash = data.get('import_hash')
    # 申购流水使用独立幂等键，避免与分红流水撞 UNIQUE(ledger_id, import_hash)；
    # 分红流水保留原始 import_hash 承担记录级去重（导入路径同键重导整体跳过）。
    buy_hash = None if not base_hash else f'{base_hash}#reinvest'
    return {
        'symbol': position.symbol if position else data.get('symbol'),
        'name': position.name if position else data.get('name'),
        'market': data.get('market', 'CN_A'),
        'asset_type': _get_asset_type(data),
        'account_name': position.account_name if position else data.get('account_name', ''),
        'ledger_id': position.ledger_id if position else data.get('ledger_id'),
        'quantity': shares,
        'avg_price': nav,
        'currency': data.get('currency', 'CNY'),
        'trade_date': data.get('trade_date'),
        'confirm_date': data.get('confirm_date'),
        'fee': data.get('fee', 0),
        'notes': data.get('notes') or '红利再投资（申购）',
        'op_type': 'buy',
        'link_group_id': link_group_id,
        'import_hash': buy_hash,
        'family_id': data.get('family_id', 1),
        'position_id': position.id if position else None,
        # #1232 决策 11：红利再投资申购流水来源透传（走 process_buy_or_deposit 落库）。
        # 缺失时兜底 manual——Position.source 非空校验拒绝 None，而流水 source 缺省可空。
        'source': data.get('source') or PositionSource.MANUAL.value,
    }


def _resolve_money_fund_flag(symbol: str, asset_type: str | None, hint=None) -> bool:
    """写路径货基判定（#863）：显式 hint > money_fund 类型 > 名录/代码段解析。

    reverse_repo 不是货基（即使与货基同属现金等价物聚合桶），不落 is_money_fund。
    """
    if hint is not None:
        return bool(hint)
    if asset_type == 'money_fund':
        return True
    if asset_type == 'reverse_repo':
        return False
    return is_money_fund_symbol(symbol)


def _reattach_orphan_flows(db: Session, ledger_id, symbol: str, position_id: int, family_id: int) -> None:
    """#863 口径 A 写入层互斥：把同 (ledger_id, symbol) 的孤儿货基流水挂回持仓。

    互斥语义：同一资金同一 (ledger_id, symbol) 只能有一种表达——持仓 或 孤儿净额。
    建仓后把历史孤儿流水（position_id IS NULL、非收益行）置 position_id，使其不再
    计入孤儿净额桶；金额由持仓市值承接（净值恒 1，市值≈本金），不双计、不漏计。
    is_income 收益行不挂回（收益桶独立于本金，见 #863 D1）。
    """
    from sqlalchemy import or_

    candidate = {normalize_fund_code(symbol)} | {p + normalize_fund_code(symbol) for p in ('SZ', 'SH')}
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
    matched = [t for t in rows if t.symbol and normalize_fund_code(t.symbol) in candidate]
    if matched:
        for txn in matched:
            txn.position_id = position_id
        logger.info(f'货基建仓挂回孤儿流水 {len(matched)} 条（ledger={ledger_id}, symbol={symbol}）')


def _reinvest_dual_flow(db: Session, data: dict, position: Position, link_group_id: str) -> None:
    """已知持仓上的红利再投资双流水：分红现金 + 按净值申购（合并入持仓，份额增加）。"""
    nav = data.get('nav', data.get('avg_price', 0))
    dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
    shares = data.get('quantity') or 0
    # 双向兜底：只给净值→按「金额/净值」算份额；只给份额→按「金额/份额」反推净值
    if shares <= 0 and nav > 0 and dividend_amount > 0:
        shares = dividend_amount / nav
    if nav <= 0 and shares > 0 and dividend_amount > 0:
        nav = dividend_amount / shares
    if nav <= 0 or shares <= 0:
        raise ValueError('红利再投资净值(nav)或再投份额无效')
    # 反推结果写回 data，确保下方 _build_reinvest_buy_data 取到一致的净值/份额
    data['nav'] = nav
    data['quantity'] = shares
    _create_dividend_cash_txn(db, data, position, link_group_id, entry_status='success')
    db.flush()
    PositionService.process_buy_or_deposit(db, _build_reinvest_buy_data(data, position, link_group_id))


class PositionService:
    # ── 公开方法 ──────────────────────────────────────────

    @staticmethod
    def upsert_from_holding(db: Session, data: dict, ownership_status: str = 'active') -> Position:
        """持仓快照 upsert（#1012 核心新方法）：以 (ledger_id, symbol) 为业务键，SET 语义整条替换。

        与 process_buy_or_deposit 的本质区别（持仓 vs 交易流水）：
        - 快照是某日点位的绝对值：quantity / avg_price / current_price 按快照**整条替换**，
          不累加（用户已确认 SET 语义，快照比手动录更权威）；
        - **绝不调用 TransactionService.create** —— 导入持仓不产生交易流水；
        - 溯源元数据（基金管理人/平台账号/分红方式/市值等）写入 position_import_meta（1:1 upsert），
          保证 E账户样本信息不丢失。

        ownership_status 参数（E账户对账扩展，#1021）：
        - 'active'（默认）：参与总资产，渠道正常持仓；
        - 'shadow'：仅对账不参与总资产（影子记录走专用 upsert，不调用本方法）。
        现有调用方不传则默认 'active'，行为不变。

        data 关键字段：
            symbol / name / asset_type / ledger_id / account_name / quantity(份) /
            avg_price(元,缺失降级为 current_price 近似) / current_price(元) /
            snapshot_date(date,缺失降级为落库当日) / currency / source / source_broker /
            source_import_id / family_id / meta(dict: fund_manager/share_class/fund_account/
            trade_account/dividend_preference/market_value)
        """
        symbol = data.get('symbol', '')
        ledger_id = data.get('ledger_id')
        family_id = data.get('family_id', 1)
        if not symbol or not ledger_id:
            raise ValueError('持仓快照导入必须提供 symbol 与 ledger_id')

        qty = data.get('quantity', 0) or 0
        if qty <= 0:
            raise ValueError('数量必须大于 0')

        # 成本均价：优先显式 avg_price，缺失降级为当前净值近似（用户已确认）
        price_yuan = data.get('avg_price') or data.get('current_price') or 0
        if price_yuan <= 0:
            raise ValueError('成本均价与当前净值均缺失，无法确定价格')

        qty_units = Money.shares_to_min_unit(qty)
        price_units = Money.yuan_to_price_units(price_yuan)

        # 快照日：优先 snapshot_date，缺失降级为落库当日（规范 §3.3）
        raw_snap = data.get('snapshot_date') or date.today()
        snapshot_date = raw_snap if isinstance(raw_snap, date) else datetime.fromisoformat(str(raw_snap)).date()

        src = data.get('source', PositionSource.E_ACCOUNT.value)
        import_hash = data.get('import_hash') or compute_position_hash(src, ledger_id, symbol, snapshot_date)

        # 查找现有持仓（业务键 ledger_id + symbol，SET 语义定位）
        existing = db.query(Position).filter_by(symbol=symbol, ledger_id=ledger_id, family_id=family_id).first()

        if existing:
            # SET 语义：整条替换快照字段（数量/成本/市价/快照日/溯源）
            existing.quantity = qty_units
            existing.avg_price = price_units
            existing.current_price = price_units
            existing.confirm_date = snapshot_date
            existing.name = data.get('name') or existing.name
            existing.account_name = data.get('account_name') or existing.account_name
            existing.currency = data.get('currency') or existing.currency
            existing.import_hash = import_hash
            existing.source = src
            existing.source_broker = data.get('source_broker')
            # 对账扩展：调用方显式传 shadow 时同步更新（防渠道记录被误标为影子）
            if existing.ownership_status != ownership_status:
                existing.ownership_status = ownership_status
            position = existing
        else:
            position = Position(
                symbol=symbol,
                name=data.get('name') or symbol,
                market=data.get('market', 'CN_A'),
                asset_type=data.get('asset_type', 'fund'),
                ledger_id=ledger_id,
                account_name=data.get('account_name', ''),
                quantity=qty_units,
                avg_price=price_units,
                current_price=price_units,
                currency=data.get('currency', 'CNY'),
                confirm_date=snapshot_date,
                allocation=data.get('allocation', 'longterm'),
                import_hash=import_hash,
                source=src,
                source_broker=data.get('source_broker'),
                ownership_status=ownership_status,
                family_id=family_id,
            )
            db.add(position)

        db.flush()

        # #863 口径 A：快照持仓也落货基冗余判定（SET 覆盖，聚合分类归「现金」桶）
        position.is_money_fund = _resolve_money_fund_flag(symbol, position.asset_type, data.get('is_money_fund'))

        # 溯源元数据 1:1 upsert（position_import_meta，保留末次快照的溯源信息）
        meta = data.get('meta') or {}
        meta_row = db.query(PositionImportMeta).filter_by(position_id=position.id).first()
        if meta_row is None:
            meta_row = PositionImportMeta(position_id=position.id, family_id=family_id)
            db.add(meta_row)
        meta_row.symbol = symbol
        meta_row.ledger_id = ledger_id
        meta_row.snapshot_date = snapshot_date
        meta_row.source = src
        meta_row.source_import_id = data.get('source_import_id')
        meta_row.source_broker = data.get('source_broker')
        meta_row.fund_manager = meta.get('fund_manager')
        meta_row.share_class = meta.get('share_class')
        meta_row.fund_account = meta.get('fund_account')
        meta_row.trade_account = meta.get('trade_account')
        meta_row.dividend_preference = meta.get('dividend_preference')
        meta_row.market_value = (
            Money.yuan_to_cents(meta['market_value']) if meta.get('market_value') is not None else None
        )
        meta_row.sales_institution_id = resolve_sales_institution_id(db, data.get('source_broker'))
        db.flush()

        # #863 口径 A 写入层互斥：快照持有货基持仓时，把同 (ledger, symbol) 孤儿流水挂回
        # （金额以持仓表达承接，避免与孤儿净额桶双计）
        if position.is_money_fund:
            _reattach_orphan_flows(db, ledger_id, symbol, position.id, family_id)

        try:
            trigger_backfill('fund', symbol)
        except Exception:
            pass

        return position

    @staticmethod
    def process_buy_or_deposit(db: Session, data: dict, force_create_position: bool = False) -> Optional[Position]:
        """
        执行买入或存入操作，返回更新或新建的持仓实例。

        force_create_position（#1233 决策 5「货基/逆回购保持建持仓」）：
        - 默认 False（交易导入）：money_fund / reverse_repo 只记孤儿资金流水、不建持仓（既有行为，
          市值由 `orphan_money_fund_net_by_ledger` 按流水净额计入总资产）；
        - True（记一笔手动记账）：跳过现金转移分支，照常建持仓，流水关联持仓（position_id 非空），
          不再计入孤儿净额口径（与 summary 不重复计数，见 test_summary_money_fund 的持仓用例）。
        """
        symbol = data.get('symbol', '')
        qty = data.get('quantity', 0)
        price = data.get('avg_price', 0)
        op_type = data.get('op_type', 'buy')
        asset_type = _get_asset_type(data)

        # 现金管理类产品：只记录流水，不创建持仓（交易导入既有行为；
        # 记一笔 force_create_position=True 时跳过此分支，走正常建仓逻辑）
        if asset_type in ('money_fund', 'reverse_repo') and not force_create_position:
            # #863 口径 A 写入层互斥：若该 (ledger, symbol) 已有 active 持仓，本笔买入并入
            # 持仓表达（走下方正常建仓合并），不产生孤儿流水——同一资金不得双表达双计。
            _lid = data.get('ledger_id')
            _family_id = data.get('family_id', 1)
            _sym = normalize_fund_code(symbol)
            _codes = {_sym} | {f'{p}{_sym}' for p in ('SZ', 'SH')}
            existing_pos = None
            if _lid:
                existing_pos = (
                    db.query(Position)
                    .filter(
                        Position.ledger_id == _lid,
                        Position.family_id == _family_id,
                        Position.symbol.in_(_codes),
                        # 仅匹配 active 持仓，避免把已平仓 / NULL 状态旧持仓误判为可复用
                        Position.ownership_status == 'active',
                    )
                    # 取最新一条（id 降序），确保命中最近建仓的持仓
                    .order_by(Position.id.desc())
                    .first()
                )
            if existing_pos is not None:
                force_create_position = True  # 复用下方正常建仓逻辑（含孤儿流水挂回）
            else:
                _create_cash_transfer_transaction(db, data, 'buy')
                return None

        # 标准化 symbol
        search_symbol = symbol
        if asset_type not in ('fund', 'money_fund', 'reverse_repo', 'bond'):
            try:
                normalizer = get_normalizer()
                normalized, _, _ = normalizer.normalize(symbol)
                if normalized:
                    symbol = normalized
                    search_symbol = normalized
            except Exception:
                logger.warning(f'无法标准化符号: {symbol}，保留原值')

        # 查找现有持仓（家庭维度）——统一身份键 (symbol, ledger_id, family_id)（#911 M3）。
        # 历史实现还按 (symbol, account_name) 二次匹配，与 ledger 键可能指向不同记录，
        # 存在「同一标的建出重复持仓」隐患；且标准化后 search_symbol 恒等于 symbol，该分支为死代码。
        ledger_id = data.get('ledger_id')
        family_id = data.get('family_id', 1)
        same = db.query(Position).filter_by(symbol=search_symbol, ledger_id=ledger_id, family_id=family_id).first()
        final_symbol = search_symbol

        # ── 计价模式（#1174 / 决策 D2）──
        # nav：份额 × 净值（要求 quantity + avg_price）；balance：直接余额（只要求 amount）。
        # 用显式模式分支，而不是靠「有没有传净值」隐式推断。
        mode = data.get('valuation_mode') or ValuationMode.NAV.value
        is_balance = mode == ValuationMode.BALANCE.value
        amount = data.get('amount', 0) or 0

        # 校验数量/价格
        qty = data.get('quantity', 0) or 0
        price = data.get('avg_price', 0) or 0
        # #1233 货基/逆回购手动建仓：净值恒为 1.0，缺失时兜底，
        # 避免净值接口不可用时用户无法记货基（买入金额 + 份额已足以建仓）。
        if force_create_position and asset_type in ('money_fund', 'reverse_repo') and not is_balance and price <= 0:
            price = 1.0
            data['avg_price'] = 1.0
        if is_balance:
            # balance 模式没有份额/净值概念，只校验金额——市值即由金额累加而来
            if amount <= 0:
                raise ValueError('balance 模式必须提供大于 0 的金额（amount）')
        else:
            if qty <= 0:
                raise ValueError('数量必须大于 0')
            if price <= 0:
                raise ValueError('价格必须大于 0')

            # lot check：买入仅校验本次数量合法（起买单位/步长），与当前持有量无关
            valid, err_msg = validate_buy(symbol, data.get('market', ''), asset_type, qty)
            if not valid:
                raise ValueError(err_msg)

            if price <= 0:
                raise SBException(
                    code=ErrorCode.INVALID_PARAMS.code,
                    message=ErrorCode.INVALID_PARAMS.msg,
                    status_code=400,
                    detail={'field': 'avg_price', 'value': price},
                )

        # 转换为内部存储单位（balance 模式份额/价格恒为 0，金额单独转分）
        qty_units = 0 if is_balance else Money.shares_to_min_unit(qty)
        price_units = 0 if is_balance else Money.yuan_to_price_units(price)
        amount_cents = Money.yuan_to_cents(amount) if is_balance else 0

        try:
            if same:
                if is_balance:
                    # balance 合并：份额/均价无意义（quantity 恒为 0，直接除会 ZeroDivisionError），
                    # 只累加可写市值并刷新覆写时间
                    same.market_value_override = (same.market_value_override or 0) + amount_cents
                    same.value_override_at = datetime.now()
                else:
                    # 合并持仓
                    total_qty_units = same.quantity + qty_units
                    old_cost = Money.multiply_price_quantity(same.avg_price, same.quantity)
                    new_cost = old_cost + Money.multiply_price_quantity(price_units, qty_units)
                    # 用 Decimal 计算均价以避免精度损失
                    total_qty = Money.min_unit_to_shares(total_qty_units)
                    total_cost = Money.cents_to_yuan(old_cost) + Money.cents_to_yuan(
                        Money.multiply_price_quantity(price_units, qty_units)
                    )
                    new_avg_price = Money.yuan_to_price_units(round(total_cost / total_qty, 4))
                    same.avg_price = new_avg_price
                    same.quantity = total_qty_units
                # issue #928: 合并时同步溯源字段（交割单覆盖手动录），并刷新 import_hash
                if 'source' in data:
                    same.source = data['source']
                if 'source_broker' in data:
                    same.source_broker = data['source_broker']
                raw_snap = data.get('confirm_date') or date.today()
                snap = raw_snap if isinstance(raw_snap, date) else datetime.fromisoformat(raw_snap).date()
                same.import_hash = compute_position_hash(
                    source=same.source, ledger_id=ledger_id, symbol=final_symbol, snapshot_date=snap
                )
                db.flush()
                position = same
                is_new = False
            else:
                # 新建持仓
                position_data = {k: v for k, v in data.items() if k in _ALLOWED_POSITION_FIELDS}
                position_data['asset_type'] = asset_type
                position_data['avg_price'] = price_units
                position_data['quantity'] = qty_units
                position_data['current_price'] = price_units
                position_data['symbol'] = final_symbol
                position_data['ledger_id'] = ledger_id
                position_data['family_id'] = family_id
                # #1174 双态计价：显式落计价模式；balance 模式把金额直接写成可写市值
                position_data['valuation_mode'] = mode
                if is_balance:
                    position_data['market_value_override'] = amount_cents
                    position_data['value_override_at'] = datetime.now()
                # issue #928: 生成持仓去重哈希（source|ledger_id|symbol|snapshot_date）
                src = data.get('source', PositionSource.MANUAL.value)
                # 快照日：优先 confirm_date；缺失降级为落库当日（规范 §3.3，保证同日同产品汇总一条）
                raw_snap = data.get('confirm_date') or date.today()
                snapshot_date = raw_snap
                if isinstance(raw_snap, str):
                    snapshot_date = datetime.fromisoformat(raw_snap).date()
                position_data['source'] = src
                position_data['import_hash'] = compute_position_hash(
                    source=src, ledger_id=ledger_id, symbol=final_symbol, snapshot_date=snapshot_date
                )
                try:
                    position = Position(**position_data)
                    db.add(position)
                    db.flush()
                except IntegrityError:
                    # 撞 uq_positions_import_hash：同内容持仓已存在（如手动录后又交割单导入），
                    # 转 upsert 语义——合并数量/成本，溯源跟随末次写入（交割单优先级高于手动录）。
                    db.rollback()
                    logger.info('持仓 import_hash 撞 key，转 upsert 更新既有记录')
                    existing = db.query(Position).filter(Position.import_hash == position_data['import_hash']).first()
                    if existing is None:
                        raise
                    if is_balance:
                        # 同 B1：balance 模式只累加可写市值，不碰份额/均价
                        existing.market_value_override = (existing.market_value_override or 0) + amount_cents
                        existing.value_override_at = datetime.now()
                    else:
                        total_qty_units = existing.quantity + qty_units
                        old_cost = Money.multiply_price_quantity(existing.avg_price, existing.quantity)
                        new_cost = old_cost + Money.multiply_price_quantity(price_units, qty_units)
                        total_qty = Money.min_unit_to_shares(total_qty_units)
                        existing.avg_price = Money.yuan_to_price_units(
                            round(
                                (
                                    Money.cents_to_yuan(old_cost)
                                    + Money.cents_to_yuan(Money.multiply_price_quantity(price_units, qty_units))
                                )
                                / total_qty,
                                4,
                            )
                        )
                        existing.quantity = total_qty_units
                    # 溯源字段跟随末次导入来源（交割单覆盖手动录）
                    existing.source = src
                    existing.source_broker = data.get('source_broker')
                    db.flush()
                    position = existing
                is_new = True

            # #863 口径 A：写路径货基冗余判定 + 互斥挂回（孤儿流水并入持仓表达，
            # 使同 (ledger, symbol) 资金只以持仓市值计入总资产，不双计、不漏计）
            position.is_money_fund = _resolve_money_fund_flag(symbol, asset_type, data.get('is_money_fund'))
            if position.is_money_fund:
                db.flush()  # 确保新建持仓已落库拿到 id，避免挂回孤儿流水时 position_id 为 None
                _reattach_orphan_flows(db, ledger_id, symbol, position.id, family_id)

            # 创建交易流水
            txn_type = op_type if op_type in ('buy', 'deposit') else 'buy'
            notes = data.get('notes') or _get_default_notes(op_type, is_new)

            confirm_date = data.get('confirm_date')
            if asset_type == 'fund' and data.get('confirm_date'):
                try:
                    trade_date = data.get('trade_date')
                    if isinstance(trade_date, str):
                        trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
                    is_after_15 = data.get('isAfter15', False)
                    fund_type = data.get('fund_type', 'domestic')
                    confirm_date = get_confirm_date(trade_date, fund_type=fund_type, is_after_15=is_after_15)
                except Exception:
                    logger.warning('确认日计算失败，使用前端传入值')

            TransactionService.create(
                db=db,
                position_id=position.id,
                txn_type=txn_type,
                symbol=symbol,
                trade_date=data.get('trade_date'),
                confirm_date=confirm_date,
                asset_type=_get_asset_type(data),
                link_group_id=data.get('link_group_id'),
                quantity=qty_units,
                price=price_units,
                fee=Money.yuan_to_cents(float(data.get('fee', 0) or 0)),
                # balance 模式没有 price×qty 可算，流水金额直接取用户录入的金额
                amount=amount_cents if is_balance else Money.multiply_price_quantity(price_units, qty_units),
                status='success',
                position_name=position.name,
                account_name=position.account_name,
                notes=notes,
                ledger_id=ledger_id,
                import_hash=data.get('import_hash'),
                family_id=family_id,
                # #1232 决策 11：流水来源与持仓同源（记一笔默认 manual，交易导入/对账补录按 data.source）
                source=data.get('source') or PositionSource.MANUAL.value,
            )

            db.flush()
            db.refresh(position)
            try:
                trigger_backfill(asset_type, symbol)
            except Exception:
                pass
            return position

        except Exception:
            logger.exception('买入/存入操作失败')
            raise

    @staticmethod
    def process_sell_or_withdraw(db: Session, data: dict, skip_lot_check: bool = False) -> Optional[Position]:
        """
        执行卖出或取出操作。
        成功返回更新后的持仓，若数量减至 0 则删除持仓并返回 None。
        """
        position_id = data['position_id']
        op_type = data['op_type']
        qty_shares = data['quantity']
        price_yuan = data['avg_price']

        qty_units = Money.shares_to_min_unit(qty_shares)
        price_units = Money.yuan_to_price_units(price_yuan)

        existing = db.query(Position).filter_by(id=position_id, family_id=data.get('family_id', 1)).first()
        if not existing:
            raise ValueError('指定的持仓不存在')
        if qty_units <= 0:
            raise ValueError('操作数量必须大于 0')
        if existing.quantity < qty_units:
            raise ValueError(
                f'持仓数量不足：当前持有 {Money.min_unit_to_shares(existing.quantity)}，拟操作 {qty_shares}'
            )

        if not skip_lot_check:
            symbol = existing.symbol or ''
            valid, err_msg = validate_sell(
                symbol,
                existing.market or '',
                existing.asset_type or 'stock',
                Money.min_unit_to_shares(existing.quantity),  # 转回份
                Money.min_unit_to_shares(qty_units),
            )
            if not valid:
                raise ValueError(err_msg)

        try:
            position_name = existing.name
            account_name = existing.account_name
            # 卖出清空持仓时会 delete，ledger_id 需提前取出（#1137 自动申购要用）
            ledger_id = existing.ledger_id

            # ── 已实现盈亏结转（#1183）──
            # 必须在份额扣减前取成本均价：移动加权下卖出本不改均价，但显式提前取值
            # 可避免后续重构引入顺序依赖。结果落在流水的 realized_pnl 上而不是持仓上，
            # 因为清仓时持仓行会被 delete，记在持仓上会随持仓一起丢失。
            fee_cents = Money.yuan_to_cents(float(data.get('fee', 0) or 0))
            realized_cents = compute_sell_realized_cents(
                price_units=price_units,
                avg_price_units=existing.avg_price or 0,
                qty_units=qty_units,
                fee_cents=fee_cents,
            )

            existing.quantity -= qty_units

            is_cleared = existing.quantity == 0
            if is_cleared:
                db.delete(existing)
                db.flush()
            else:
                db.flush()

            TransactionService.create(
                db=db,
                position_id=position_id,
                symbol=data.get('symbol'),
                txn_type=op_type,
                trade_date=data.get('trade_date'),
                confirm_date=data.get('confirm_date'),
                asset_type=_get_asset_type(data),
                link_group_id=data.get('link_group_id'),
                quantity=qty_units,
                price=price_units,
                fee=fee_cents,
                amount=Money.multiply_price_quantity(price_units, qty_units),
                realized_pnl=realized_cents,
                status='success',
                position_name=position_name,
                ledger_id=ledger_id,
                account_name=account_name,
                notes=data.get('notes') or ('卖出' if op_type == 'sell' else '取出'),
                import_hash=data.get('import_hash'),
                family_id=data.get('family_id', 1),
                # #1232 决策 11：流水来源透传（记一笔默认 manual）
                source=data.get('source') or PositionSource.MANUAL.value,
            )

            # #1137 卖出回款自动申购账户绑定的类现金产品（余额宝）。
            # 净额 = 成交额 - 手续费；货基/逆回购自身的卖出不触发，避免「赎回 → 自动申购」死循环。
            if _get_asset_type(data) not in ('money_fund', 'reverse_repo'):
                gross_cents = Money.multiply_price_quantity(price_units, qty_units)
                auto_purchase_money_fund(
                    db,
                    ledger_id=ledger_id,
                    amount_cents=gross_cents - fee_cents,
                    trade_date=data.get('trade_date'),
                    confirm_date=data.get('confirm_date'),
                    family_id=data.get('family_id', 1),
                )

            db.flush()
            if is_cleared:
                return None
            db.refresh(existing)
            return existing

        except Exception:
            logger.exception('卖出/取出操作失败')
            raise

    @staticmethod
    def recompute_position_from_transactions(db: Session, position_id: int):
        """删除/编辑交易后，依据该持仓剩余流水重算份额与成本均价（#948 后续回滚）。

        卖出/取出使持仓份额减少；删除该类流水必须把份额加回，否则账面份额丢失。
        采用「从流水重算」而非只做反向加减：
        - 能正确处理部分卖出（剩余流水仍有买入，净份额>0，更新现有持仓）；
        - 也能在「整笔卖出清空持仓」后删除该卖出流水时（持仓行已被 process_sell 删掉）
          依据剩余买入流水重建持仓，避免份额彻底丢失。
        净份额 = Σ买入/存入 - Σ卖出/取出；净份额<=0 则删除（或保持不存在）持仓行。
        成本均价按买入加权（与 process_buy_or_deposit 一致），卖出/取出不改变成本均价。
        """
        txns = (
            db.query(Transaction)
            .filter(Transaction.position_id == position_id)
            .order_by(Transaction.trade_date, Transaction.id)
            .all()
        )
        pos = db.query(Position).filter_by(id=position_id).first()

        if not txns:
            if pos:
                db.delete(pos)
                db.flush()
            return None

        buy_qty = 0
        buy_cost = 0  # 分
        sell_qty = 0
        for t in txns:
            if t.txn_type in ('buy', 'deposit'):
                buy_qty += t.quantity
                buy_cost += Money.multiply_price_quantity(t.price, t.quantity)
            elif t.txn_type == 'split':
                # 送股/拆分（#P2-2）：份额增加、成本不变，仅稀释均价
                buy_qty += t.quantity
            elif t.txn_type in ('sell', 'withdraw'):
                sell_qty += t.quantity

        net_qty = buy_qty - sell_qty
        if net_qty <= 0:
            if pos:
                db.delete(pos)
                db.flush()
            return None

        avg_price_units = (
            Money.yuan_to_price_units(round(Money.cents_to_yuan(buy_cost) / buy_qty, 4)) if buy_qty > 0 else 0
        )

        if pos:
            pos.quantity = net_qty
            pos.avg_price = avg_price_units
            if pos.current_price in (None, 0):
                pos.current_price = avg_price_units
            db.flush()
            return pos

        # 持仓行已被整笔卖出清空删除：依据剩余买入流水重建
        # （Transaction 不携带 market/currency，缺失时取默认值）
        first = txns[0]
        new_pos = Position(
            ledger_id=first.ledger_id,
            family_id=first.family_id,
            symbol=first.symbol or '',
            name=first.position_name or first.symbol or '',
            asset_type=first.asset_type,
            market='CN_A',
            currency='CNY',
            quantity=net_qty,
            avg_price=avg_price_units,
            current_price=avg_price_units,
            confirm_date=first.confirm_date,
            account_name=first.account_name,
            allocation='longterm',
            notes='',
        )
        db.add(new_pos)
        db.flush()
        for t in txns:
            t.position_id = new_pos.id
        db.flush()
        return new_pos

    @staticmethod
    def process_dividend(db: Session, data: dict) -> Position:
        """处理分红记录，不改变持仓数量。"""
        position_id = data['position_id']
        dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))

        existing = db.query(Position).filter_by(id=position_id, family_id=data.get('family_id', 1)).first()
        if not existing:
            logger.error(f'持仓不存在: position_id={position_id}')
            raise ValueError('指定的持仓不存在')

        try:
            TransactionService.create(
                db=db,
                position_id=position_id,
                txn_type='dividend',
                symbol=data.get('symbol'),
                trade_date=data.get('trade_date'),
                confirm_date=data.get('confirm_date'),
                asset_type=_get_asset_type(data),
                link_group_id=data.get('link_group_id'),
                quantity=0,
                price=0,
                fee=0,
                amount=Money.yuan_to_cents(dividend_amount),
                # 现金分红全额计入已实现盈亏（#1183）：与 XIRR 的 dividend_cash 正现金流同口径，
                # 修复「汇总排除 dividend、XIRR 却计入」的口径分叉
                realized_pnl=Money.yuan_to_cents(dividend_amount),
                status='success',
                position_name=existing.name,
                account_name=existing.account_name,
                ledger_id=existing.ledger_id,
                notes=data.get('notes') or '现金分红',
                import_hash=data.get('import_hash'),
                family_id=data.get('family_id', 1),
                # #1232 决策 11：流水来源透传（记一笔默认 manual）
                source=data.get('source') or PositionSource.MANUAL.value,
            )

            db.flush()
            return existing

        except Exception:
            logger.exception('分红操作失败')
            raise

    @staticmethod
    def process_dividend_reinvest(db: Session, data: dict) -> Optional[Position]:
        """
        处理红利再投资：分红到账（现金流入）＋ 按当日净值申购份额（份额增加）。

        WHY 拆成两笔流水，而不是记一笔 `dividend_reinvest`：
        1. 语义真实——先分红入账、再用这笔钱按净值申购，本就是两件事；
        2. XIRR 自洽——`services/performance/xirr_engine.py` 按类型分流现金流方向：
           dividend_cash 记流入、buy/dividend_reinvest 记流出。两笔金额相等、一进一出，
           净额为 0，与「红利再投资不产生实际现金进出」相符；若只记一笔流出，
           会虚增投入、低估年化。（流水的 amount 字段恒为正，方向由 txn_type 决定，此处不取负）
        3. 两笔以 link_group_id 配对，便于前端折叠展示为一条「红利再投资」。

        去重：分红流水沿用原始 import_hash（重导时命中即跳过整条记录，见 orchestrator.commit），
        申购流水用派生 hash `{原 hash}#reinvest`，避开 uq_txn_import_hash 唯一约束。
        """
        position_id = data.get('position_id')
        if not position_id:
            raise ValueError('红利再投资必须指定关联持仓（position_id）')
        family_id = data.get('family_id', 1)
        existing = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
        if not existing:
            raise ValueError('指定的持仓不存在')
        link_group_id = data.get('link_group_id') or uuid.uuid4().hex
        _reinvest_dual_flow(db, data, existing, link_group_id)
        return existing

    @staticmethod
    def process_orphan_sell_or_withdraw(db: Session, data: dict) -> Optional[Position]:
        """
        处理卖出/取出记录，优先尝试关联持仓；找不到持仓则创建孤立流水。
        """
        asset_type = _get_asset_type(data)
        if asset_type in ('money_fund', 'reverse_repo'):
            _create_cash_transfer_transaction(db, data, 'sell')
            return None

        symbol = data.get('symbol', '')
        account = data.get('account_name', '')
        qty = data.get('quantity', 0)
        price = data.get('avg_price', 0)

        # 尝试查找现有持仓（家庭维度）
        existing = (
            db.query(Position)
            .filter_by(symbol=symbol, account_name=account, family_id=data.get('family_id', 1))
            .first()
        )

        if existing:
            try:
                return PositionService.process_sell_or_withdraw(
                    db,
                    {
                        'position_id': existing.id,
                        'quantity': qty,
                        'avg_price': price,
                        'trade_date': data.get('trade_date'),
                        'confirm_date': data.get('confirm_date'),
                        'op_type': data.get('op_type', 'sell'),
                        'fee': data.get('fee', 0.0),
                        'notes': data.get('notes', ''),
                        'import_hash': data.get('import_hash'),
                        'family_id': data.get('family_id', 1),
                    },
                    skip_lot_check=True,
                )
            except ValueError as e:
                if '持仓数量不足' not in str(e):
                    raise
                logger.warning(f'持仓 {existing.symbol} 数量不足，转为孤儿交易')

        # 无持仓或数量不足，统一创建孤儿流水
        _create_orphan_transaction(
            db,
            data,
            txn_type=data.get('op_type', 'sell'),
            quantity=qty,
            price=price,
            amount=0,  # 自动计算
            notes=data.get('notes') or ('卖出' if data.get('op_type') == 'sell' else '取出'),
        )
        return None

    @staticmethod
    def process_orphan_dividend(db: Session, data: dict) -> Optional[Position]:
        """
        处理分红记录，优先尝试关联持仓；找不到持仓则创建孤立流水。

        红利再投资（dividend_reinvest）走单独分支——分红入账 ＋ 按净值申购，
        使持仓份额真正增加；此前它与现金分红合并进同一分支，份额恒为 0，语义丢失。
        数据不全（缺份额或净值）时降级为现金分红，不阻断整批导入。
        """
        symbol = data.get('symbol', '')
        account = data.get('account_name', '')
        dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
        is_reinvest = _is_reinvest(data)

        existing = (
            db.query(Position)
            .filter_by(symbol=symbol, account_name=account, family_id=data.get('family_id', 1))
            .first()
        )

        common = {
            'dividend_amount': dividend_amount,
            'confirm_date': data.get('confirm_date'),
            'trade_date': data.get('trade_date'),
            'notes': data.get('notes', ''),
            'import_hash': data.get('import_hash'),
            'link_group_id': data.get('link_group_id'),
            'family_id': data.get('family_id', 1),
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
        family_id = data.get('family_id', 1)
        symbol = data.get('symbol', '')
        account = data.get('account_name', '')
        existing = db.query(Position).filter_by(symbol=symbol, account_name=account, family_id=family_id).first()
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
        手动记账传 position_id 直接定位；导入路径按 (symbol, account_name, family_id) 匹配。
        """
        family_id = data.get('family_id', 1)
        qty = float(data.get('quantity') or 0)

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
            symbol = data.get('symbol', '')
            account = data.get('account_name', '')
            existing = db.query(Position).filter_by(symbol=symbol, account_name=account, family_id=family_id).first()

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
            symbol=data.get('symbol'),
            txn_type='split',
            trade_date=data.get('trade_date'),
            confirm_date=data.get('confirm_date'),
            asset_type=_get_asset_type(data),
            quantity=qty_units,
            price=0,
            fee=Money.yuan_to_cents(float(data.get('fee', 0) or 0)),
            amount=0,
            status='success',
            entry_status='success',
            position_name=existing.name,
            ledger_id=existing.ledger_id,
            account_name=data.get('account_name', existing.account_name),
            notes=data.get('notes') or '送股/拆分入账',
            import_hash=data.get('import_hash'),
            link_group_id=data.get('link_group_id'),
            family_id=family_id,
            # #1232 决策 11：流水来源透传（记一笔默认 manual）
            source=data.get('source') or PositionSource.MANUAL.value,
        )
        db.flush()
        return PositionService.recompute_position_from_transactions(db, existing.id)
