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

from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ErrorCode, SBException
from app.core.money import Money
from app.core.symbol_utils import get_normalizer
from app.core.utils import get_confirm_date
from app.domains.positions.models import Position, PositionImportMeta
from app.services.async_backfill import trigger_backfill
from app.services.importer.records import compute_position_hash
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
}


def _get_asset_type(data: dict, default: str = 'stock') -> str:
    """
    统一从请求数据中提取资产类型，兼容 `asset_type` 与 `type` 两个 key。

    历史债背景：PositionCreate.asset_type 使用 validation_alias='type'，
    model_dump() 输出的是字段名 `asset_type`，而 importer 路径直接构造 `type` key，
    导致不同调用方传入的 key 不一致。此处收敛读取端，保证流水 asset_type 落库正确。
    """
    return data.get('asset_type') or data.get('type', default)


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
    price_cents = Money.yuan_to_cents(price)
    amount_cents = Money.yuan_to_cents(amount) if amount else Money.multiply_price_quantity(price_cents, qty_units)
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
        price=price_cents,
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
    )
    db.flush()


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
        price_cents = Money.yuan_to_cents(price_yuan)

        # 快照日：优先 snapshot_date，缺失降级为落库当日（规范 §3.3）
        raw_snap = data.get('snapshot_date') or date.today()
        snapshot_date = raw_snap if isinstance(raw_snap, date) else datetime.fromisoformat(str(raw_snap)).date()

        src = data.get('source', 'e_account_holding')
        import_hash = data.get('import_hash') or compute_position_hash(src, ledger_id, symbol, snapshot_date)

        # 查找现有持仓（业务键 ledger_id + symbol，SET 语义定位）
        existing = db.query(Position).filter_by(symbol=symbol, ledger_id=ledger_id, family_id=family_id).first()

        if existing:
            # SET 语义：整条替换快照字段（数量/成本/市价/快照日/溯源）
            existing.quantity = qty_units
            existing.avg_price = price_cents
            existing.current_price = price_cents
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
                avg_price=price_cents,
                current_price=price_cents,
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
        db.flush()

        try:
            trigger_backfill('fund', symbol)
        except Exception:
            pass

        return position

    @staticmethod
    def process_buy_or_deposit(db: Session, data: dict) -> Optional[Position]:
        """
        执行买入或存入操作，返回更新或新建的持仓实例。
        """
        symbol = data.get('symbol', '')
        qty = data.get('quantity', 0)
        price = data.get('avg_price', 0)
        op_type = data.get('op_type', 'buy')
        asset_type = _get_asset_type(data)

        # 现金管理类产品：只记录流水，不创建持仓
        if asset_type in ('money_fund', 'reverse_repo'):
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

        # 校验数量/价格
        qty = data.get('quantity', 0) or 0
        price = data.get('avg_price', 0) or 0
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

        # 转换为内部存储单位
        qty_units = Money.shares_to_min_unit(qty)
        price_cents = Money.yuan_to_cents(price)

        try:
            if same:
                # 合并持仓
                total_qty_units = same.quantity + qty_units
                old_cost = Money.multiply_price_quantity(same.avg_price, same.quantity)
                new_cost = old_cost + Money.multiply_price_quantity(price_cents, qty_units)
                # 用 Decimal 计算均价以避免精度损失
                total_qty = Money.min_unit_to_shares(total_qty_units)
                total_cost = Money.cents_to_yuan(old_cost) + Money.cents_to_yuan(
                    Money.multiply_price_quantity(price_cents, qty_units)
                )
                new_avg_price = Money.yuan_to_cents(round(total_cost / total_qty, 4))
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
                position_data['avg_price'] = price_cents
                position_data['quantity'] = qty_units
                position_data['current_price'] = price_cents
                position_data['symbol'] = final_symbol
                position_data['ledger_id'] = ledger_id
                position_data['family_id'] = family_id
                # issue #928: 生成持仓去重哈希（source|ledger_id|symbol|snapshot_date）
                src = data.get('source', 'manual')
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
                    total_qty_units = existing.quantity + qty_units
                    old_cost = Money.multiply_price_quantity(existing.avg_price, existing.quantity)
                    new_cost = old_cost + Money.multiply_price_quantity(price_cents, qty_units)
                    total_qty = Money.min_unit_to_shares(total_qty_units)
                    existing.avg_price = Money.yuan_to_cents(
                        round(
                            (
                                Money.cents_to_yuan(old_cost)
                                + Money.cents_to_yuan(Money.multiply_price_quantity(price_cents, qty_units))
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
                price=price_cents,
                fee=Money.yuan_to_cents(float(data.get('fee', 0) or 0)),
                amount=Money.multiply_price_quantity(price_cents, qty_units),
                status='success',
                position_name=position.name,
                account_name=position.account_name,
                notes=notes,
                ledger_id=ledger_id,
                import_hash=data.get('import_hash'),
                family_id=family_id,
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
        price_cents = Money.yuan_to_cents(price_yuan)

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
                price=price_cents,
                fee=Money.yuan_to_cents(float(data.get('fee', 0) or 0)),
                amount=Money.multiply_price_quantity(price_cents, qty_units),
                status='success',
                position_name=position_name,
                ledger_id=existing.ledger_id,
                account_name=account_name,
                notes=data.get('notes') or ('卖出' if op_type == 'sell' else '取出'),
                import_hash=data.get('import_hash'),
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
                status='success',
                position_name=existing.name,
                account_name=existing.account_name,
                ledger_id=existing.ledger_id,
                notes=data.get('notes') or '现金分红',
                import_hash=data.get('import_hash'),
                family_id=data.get('family_id', 1),
            )

            db.flush()
            return existing

        except Exception:
            logger.exception('分红操作失败')
            raise

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
        """
        symbol = data.get('symbol', '')
        account = data.get('account_name', '')
        dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))

        existing = (
            db.query(Position)
            .filter_by(symbol=symbol, account_name=account, family_id=data.get('family_id', 1))
            .first()
        )

        if existing:
            return PositionService.process_dividend(
                db,
                {
                    'position_id': existing.id,
                    'dividend_amount': dividend_amount,
                    'confirm_date': data.get('confirm_date'),
                    'trade_date': data.get('trade_date'),
                    'notes': data.get('notes', ''),
                    'import_hash': data.get('import_hash'),
                    'family_id': data.get('family_id', 1),
                },
            )
        else:
            _create_orphan_transaction(
                db,
                data,
                txn_type='dividend',
                quantity=0,
                price=0,
                amount=dividend_amount,
                notes=data.get('notes') or '现金分红',
            )
            return None
