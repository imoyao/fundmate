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

from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.exceptions import ErrorCode, SBException
from app.core.money import Money
from app.core.symbol_utils import get_normalizer
from app.core.utils import get_confirm_date
from app.domains.positions.models import Position
from app.services.async_backfill import trigger_backfill
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
    def process_buy_or_deposit(db: Session, data: dict, skip_lot_check: bool = False) -> Optional[Position]:
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

        # lot check 的当前持有量基于目标账户（与合并身份键一致），不再按 account_name 二次查询（#911 M3）
        current_hold_shares = Money.min_unit_to_shares(same.quantity) if same else 0.0
        if not skip_lot_check:
            valid, err_msg = validate_buy(symbol, data.get('market', ''), asset_type, current_hold_shares, qty)
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
                position = Position(**position_data)
                db.add(position)
                db.flush()
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
