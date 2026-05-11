# -*- coding: utf-8 -*-
# Auther : imoyao
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

from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.services.transaction_service import TransactionService


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
        symbol = data['symbol']
        account = data['account_name']
        qty = data['quantity']
        price = data['avg_price']
        op_type = data.get('op_type', 'buy')

        # 1. 查找或创建持仓
        same = db.query(Position).filter_by(symbol=symbol, account_name=account).first()
        if same:
            # 合并持仓
            total_qty = same.quantity + qty
            same.avg_price = (same.avg_price * same.quantity + price * qty) / total_qty
            same.quantity = total_qty
            same.current_price = price
            db.flush()
            position = same
            is_new = False
        else:
            # 新建持仓
            position_data = {
                k: v
                for k, v in data.items()
                if k not in ('fee', 'confirm_date', 'notes', 'op_type', 'position_id', 'isAfter15', 'interestRate')
            }
            if 'type' in position_data:
                position_data['asset_type'] = position_data.pop('type')
            position = Position(**position_data)
            position.current_price = position.avg_price
            db.add(position)
            db.flush()
            is_new = True

        # 2. 创建交易流水
        txn_type = op_type if op_type in ('buy', 'deposit') else 'buy'
        notes = data.get('notes')
        if not notes:
            notes = (
                '追加买入'
                if (op_type == 'buy' and not is_new)
                else '追加存入'
                if (op_type == 'deposit' and not is_new)
                else '初始买入'
                if op_type == 'buy'
                else '存入'
            )

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

    @staticmethod
    def process_sell_or_withdraw(db: Session, data: dict) -> Optional[Position]:
        """
        执行卖出或取出操作。
        成功返回更新后的持仓，若数量减至 0 则删除持仓并返回 None。
        data 必须包含：position_id, quantity, avg_price, purchase_date, op_type (sell/withdraw)
        """
        position_id = data['position_id']
        op_type = data['op_type']
        qty = data['quantity']
        price = data['avg_price']

        # 1. 校验
        existing = db.query(Position).filter_by(id=position_id).first()
        if not existing:
            raise ValueError('指定的持仓不存在')
        if qty <= 0:
            raise ValueError('操作数量必须大于 0')
        if existing.quantity < qty:
            raise ValueError(f'持仓数量不足：当前持有 {existing.quantity}，拟操作 {qty}')

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

        # 3. 创建流水（无论清空与否，流水只需创建一次）
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

    @staticmethod
    def process_dividend(db: Session, data: dict) -> Position:
        """
        处理分红记录，不改变持仓数量。
        data 必须包含：position_id, avg_price(视为分红金额), purchase_date
        """
        position_id = data['position_id']
        existing = db.query(Position).filter_by(id=position_id).first()
        if not existing:
            raise ValueError('指定的持仓不存在')

        TransactionService.create(
            db=db,
            position_id=position_id,
            txn_type='dividend',
            trade_date=data['purchase_date'],
            quantity=0,
            price=0,
            fee=0,
            amount=data['avg_price'],  # 分红金额暂存在 avg_price
            status='success',
            position_name=existing.name,
            account_name=existing.account_name,
            notes=data.get('notes') or '现金分红',
        )

        db.commit()
        return existing
