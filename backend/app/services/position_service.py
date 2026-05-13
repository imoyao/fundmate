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

from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.symbol_utils import get_normalizer
from app.domains.positions.models import Position
from app.services.transaction_service import TransactionService

# 允许写入持仓模型的字段白名单（防止注入无效字段）
_ALLOWED_POSITION_FIELDS = {
    'symbol',
    'name',
    'market',
    'asset_type',
    'account_name',
    'quantity',
    'avg_price',
    'currency',
    'current_price',
    'purchase_date',
    'notes',
    'allocation',
}


def _get_default_notes(op_type: str, is_new: bool) -> str:
    """生成默认的交易备注，避免嵌套 if-else."""
    mapping = {
        (False, 'buy'): '追加买入',
        (False, 'deposit'): '追加存入',
        (True, 'buy'): '初始买入',
    }
    return mapping.get((is_new, op_type), '存入')


class PositionService:
    # ── 公开方法 ──────────────────────────────────────────

    @staticmethod
    def process_buy_or_deposit(db: Session, data: dict) -> Position:
        """
        执行买入或存入操作，返回更新或新建的持仓实例。

        data 必须包含：symbol, account_name, quantity, avg_price, purchase_date,
                       op_type (buy/deposit)
        可选：fee, confirm_date, notes, type, market, currency, allocation
        """
        symbol = data.get('symbol', '')
        account = data.get('account_name', '')
        qty = data.get('quantity', 0)
        price = data.get('avg_price', 0)
        op_type = data.get('op_type', 'buy')

        # 输入校验
        if qty <= 0:
            raise ValueError('数量必须大于 0')
        if price <= 0:
            raise ValueError('价格必须大于 0')

        # 标准化 symbol（只更新局部变量，不污染原始 data）
        try:
            normalizer = get_normalizer()
            normalized, _ = normalizer.normalize(symbol)
            if normalized:
                symbol = normalized
        except Exception:
            logger.warning(f'无法标准化符号: {symbol}，保留原值')

        try:
            # 1. 查找或创建持仓
            same = db.query(Position).filter_by(symbol=symbol, account_name=account).first()
            if same:
                # 合并持仓：更新均价、数量，保留 current_price（不覆盖为成本价）
                total_qty = same.quantity + qty
                same.avg_price = (same.avg_price * same.quantity + price * qty) / total_qty
                same.quantity = total_qty
                db.flush()
                position = same
                is_new = False
            else:
                # 新建持仓：只使用白名单字段
                position_data = {k: v for k, v in data.items() if k in _ALLOWED_POSITION_FIELDS}
                if 'type' in data:
                    position_data['asset_type'] = data['type']
                position_data['symbol'] = symbol
                position = Position(**position_data)
                position.current_price = position.avg_price  # 初始市价默认为成本价
                db.add(position)
                db.flush()
                is_new = True

            # 2. 创建交易流水
            txn_type = op_type if op_type in ('buy', 'deposit') else 'buy'
            notes = data.get('notes') or _get_default_notes(op_type, is_new)

            TransactionService.create(
                db=db,
                position_id=position.id,
                txn_type=txn_type,
                trade_date=data['purchase_date'],
                quantity=qty,
                price=price,
                fee=data.get('fee', 0.0),
                amount=qty * price,
                status='success',
                position_name=position.name,
                account_name=position.account_name,
                confirm_date=data.get('confirm_date'),
                notes=notes,
            )

            # 3. 提交并刷新
            db.commit()
            db.refresh(position)
            return position

        except Exception:
            db.rollback()
            logger.exception('买入/存入操作失败')
            raise

    @staticmethod
    def process_sell_or_withdraw(db: Session, data: dict) -> Optional[Position]:
        """
        执行卖出或取出操作。
        成功返回更新后的持仓，若数量减至 0 则删除持仓并返回 None。

        data 必须包含：position_id, quantity, avg_price(卖出单价), purchase_date, op_type (sell/withdraw)
        """
        position_id = data['position_id']
        op_type = data['op_type']
        qty = data['quantity']
        price = data['avg_price']  # 实际语义：卖出单价

        # 1. 校验
        existing = db.query(Position).filter_by(id=position_id).first()
        if not existing:
            logger.error(f'持仓不存在: position_id={position_id}')
            raise ValueError('指定的持仓不存在')
        if qty <= 0:
            logger.error(f'操作数量非法: qty={qty}')
            raise ValueError('操作数量必须大于 0')
        if existing.quantity < qty:
            logger.error(f'持仓数量不足: 持有{existing.quantity}, 拟操作{qty}')
            raise ValueError(f'持仓数量不足：当前持有 {existing.quantity}，拟操作 {qty}')

        try:
            # 2. 扣减数量（删除前保存快照）
            position_name = existing.name
            account_name = existing.account_name
            existing.quantity -= qty

            is_cleared = existing.quantity == 0
            if is_cleared:
                db.delete(existing)
                db.flush()
            else:
                db.flush()

            # 3. 创建流水
            action_cn = '卖出' if op_type == 'sell' else '取出'
            TransactionService.create(
                db=db,
                position_id=position_id,
                txn_type=op_type,
                trade_date=data['purchase_date'],
                quantity=qty,
                price=price,
                fee=data.get('fee', 0.0),
                amount=qty * price,
                status='success',
                position_name=position_name,
                account_name=account_name,
                notes=data.get('notes') or action_cn,
            )

            # 4. 提交
            db.commit()
            if is_cleared:
                return None
            db.refresh(existing)
            return existing

        except Exception:
            db.rollback()
            logger.exception('卖出/取出操作失败')
            raise

    @staticmethod
    def process_dividend(db: Session, data: dict) -> Position:
        """
        处理分红记录，不改变持仓数量。

        data 必须包含：position_id, dividend_amount(分红金额), purchase_date
        """
        position_id = data['position_id']
        dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))

        existing = db.query(Position).filter_by(id=position_id).first()
        if not existing:
            logger.error(f'持仓不存在: position_id={position_id}')
            raise ValueError('指定的持仓不存在')

        try:
            TransactionService.create(
                db=db,
                position_id=position_id,
                txn_type='dividend',
                trade_date=data['purchase_date'],
                quantity=0,
                price=0,
                fee=0,
                amount=dividend_amount,
                status='success',
                position_name=existing.name,
                account_name=existing.account_name,
                notes=data.get('notes') or '现金分红',
            )

            db.commit()
            return existing

        except Exception:
            db.rollback()
            logger.exception('分红操作失败')
            raise
