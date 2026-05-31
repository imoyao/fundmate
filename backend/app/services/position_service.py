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
from app.core.symbol_utils import get_normalizer
from app.core.utils import get_confirm_date
from app.domains.positions.models import Position
from app.services.async_backfill import trigger_backfill
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
        asset_type = data.get('type', 'stock')  # 获取类型字段

        # 现金管理类产品：只记录流水，不创建持仓，跳过数量/价格校验
        if asset_type in ('money_fund', 'reverse_repo'):
            try:
                TransactionService.create(
                    db=db,
                    position_id=None,  # 不关联持仓
                    txn_type='buy',  # 保持交易类型为买入
                    trade_date=data['purchase_date'],
                    quantity=0,
                    price=0,
                    fee=0,
                    amount=abs(float(data.get('net_amount', 0) or 0)),  # 金额取发生额的绝对值
                    status='success',
                    position_name=data.get('name', symbol),
                    account_name=account,
                    notes=data.get('notes') or '现金管理产品申赎',
                    import_hash=data.get('import_hash'),
                    entry_status='orphan',  # 标记为孤立交易，不影响持仓
                )
                db.flush()  # 注意：只 flush 不 commit，事务控制权在调用方
                return None  # 无持仓返回
            except Exception:
                db.rollback()
                raise

        # 输入校验
        if qty <= 0:
            raise SBException(
                code=ErrorCode.INVALID_PARAMS.code,
                message=ErrorCode.INVALID_PARAMS.msg,
                status_code=400,
                detail={'field': 'quantity', 'value': qty},
            )
        if price <= 0:
            raise SBException(
                code=ErrorCode.INVALID_PARAMS.code,
                message=ErrorCode.INVALID_PARAMS.msg,
                status_code=400,
                detail={'field': 'avg_price', 'value': price},
            )

        # 标准化 symbol（同时生成搜索用的符号）
        search_symbol = symbol
        # 标准化 symbol（只更新局部变量，不污染原始 data）
        try:
            normalizer = get_normalizer()
            normalized, _, _ = normalizer.normalize(symbol)
            if normalized:
                symbol = normalized
                search_symbol = normalized
        except Exception:
            logger.warning(f'无法标准化符号: {symbol}，保留原值')
        # 查找或创建持仓
        # 优先用标准化后的符号查找
        same = db.query(Position).filter_by(symbol=search_symbol, account_name=account).first()
        # 如果没找到，尝试用原始符号再查一次（兼容历史数据）
        if not same and search_symbol != symbol:
            same = db.query(Position).filter_by(symbol=symbol, account_name=account).first()

        # 用于最终存储的符号（统一为搜索到的符号，确保一致性）
        final_symbol = search_symbol

        # 输入校验
        # 防御性处理：确保 quantity 和 price 不是 None
        qty = data.get('quantity', 0) or 0
        price = data.get('avg_price', 0) or 0
        if qty <= 0:
            raise ValueError('数量必须大于 0')
        if price <= 0:
            raise ValueError('价格必须大于 0')

        try:
            # 1. 查找或创建持仓
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
                elif 'asset_type' in data:
                    position_data['asset_type'] = data['asset_type']
                position_data['symbol'] = final_symbol
                position = Position(**position_data)
                position.current_price = position.avg_price  # 初始市价默认为成本价
                db.add(position)
                db.flush()
                is_new = True

            # 2. 创建交易流水
            txn_type = op_type if op_type in ('buy', 'deposit') else 'buy'
            notes = data.get('notes') or _get_default_notes(op_type, is_new)

            # 计算场外基金确认日（使用中国交易日历）
            confirm_date = data.get('confirm_date')  # 前端传的预估，仅作后备
            if asset_type == 'fund' and data.get('purchase_date'):
                try:
                    purchase_date = data['purchase_date']
                    if isinstance(purchase_date, str):
                        purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()
                    is_after_15 = data.get('isAfter15', False)
                    # 基金类型默认 'domestic'，后期可从证券元数据获取是否 QDII
                    fund_type = data.get('fund_type', 'domestic')
                    confirm_date = get_confirm_date(purchase_date, fund_type=fund_type, is_after_15=is_after_15)
                except Exception:
                    logger.warning('确认日计算失败，使用前端传入值')
            TransactionService.create(
                db=db,
                position_id=position.id,
                txn_type=txn_type,
                trade_date=data['purchase_date'],
                link_group_id=data.get('link_group_id'),
                quantity=qty,
                price=price,
                fee=data.get('fee', 0.0),
                amount=qty * price,
                status='success',
                position_name=position.name,
                account_name=position.account_name,
                confirm_date=data.get('confirm_date'),
                notes=notes,
                import_hash=data.get('import_hash'),
            )

            # 3. 提交并刷新
            db.flush()
            db.refresh(position)
            try:
                trigger_backfill(asset_type, symbol)
            except Exception:
                # 回填失败不影响主流程
                pass
            return position

        except Exception:
            db.rollback()
            logger.exception('买入/存入操作失败')
            raise

    @staticmethod
    def process_sell_or_withdraw(db: Session, data: dict, skip_lot_check: bool = False) -> Optional[Position]:
        """
        执行卖出或取出操作。
        成功返回更新后的持仓，若数量减至 0 则删除持仓并返回 None。

        data 必须包含：position_id, quantity, avg_price(卖出单价), purchase_date, op_type (sell/withdraw)
        skip_lot_check: 若为 True，跳过一手规则校验（用于导入历史交易）
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

        # 一手规则校验（仅限场内交易品种，且非导入场景）
        if not skip_lot_check:
            asset_type = existing.asset_type or 'stock'
            market = existing.market or ''
            symbol = existing.symbol or ''

            if asset_type in ('stock', 'etf', 'bond') and market not in ('US', 'CRYPTO'):
                lot_size = 1
                if asset_type == 'bond':
                    lot_size = 10
                elif market in ('SH', 'SZ'):
                    if symbol.startswith('688'):
                        lot_size = 200
                    elif symbol.startswith('8'):
                        lot_size = 100
                    else:
                        lot_size = 100
                elif market == 'CN_HK':
                    lot_size = 100  # MVP 固定，后期可查询

                if existing.quantity < lot_size:
                    if qty != existing.quantity:
                        raise ValueError(
                            f'当前持仓不足一手（{lot_size}股/张），只能一次性全部卖出（当前持有{existing.quantity}）'
                        )
                else:
                    allow_increment = market in ('SH', 'SZ') and (symbol.startswith('688') or symbol.startswith('8'))
                    if not allow_increment and qty % lot_size != 0:
                        raise ValueError(f'卖出数量必须是{lot_size}的整数倍')
                    if qty < lot_size:
                        raise ValueError(f'卖出数量不能低于一手（{lot_size}股/张）')
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
                link_group_id=data.get('link_group_id'),
                quantity=qty,
                price=price,
                fee=data.get('fee', 0.0),
                amount=qty * price,
                status='success',
                position_name=position_name,
                account_name=account_name,
                notes=data.get('notes') or action_cn,
                import_hash=data.get('import_hash'),
            )

            # 4. 提交
            db.flush()
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
                link_group_id=data.get('link_group_id'),
                quantity=0,
                price=0,
                fee=0,
                amount=dividend_amount,
                status='success',
                position_name=existing.name,
                account_name=existing.account_name,
                notes=data.get('notes') or '现金分红',
                import_hash=data.get('import_hash'),
            )

            db.flush()
            return existing

        except Exception:
            db.rollback()
            logger.exception('分红操作失败')
            raise

    @staticmethod
    def process_orphan_sell_or_withdraw(db: Session, data: dict) -> Optional[Position]:
        """
        处理卖出/取出记录，优先尝试关联持仓；找不到持仓则创建孤立流水。

        data 必须包含：symbol, account_name, quantity, avg_price(卖出单价),
                       purchase_date, op_type (sell/withdraw)
        """
        asset_type = data.get('type', 'stock')
        if asset_type in ('money_fund', 'reverse_repo'):
            try:
                TransactionService.create(
                    db=db,
                    position_id=None,
                    txn_type='sell',
                    trade_date=data['purchase_date'],
                    quantity=0,
                    price=0,
                    fee=0,
                    amount=abs(float(data.get('net_amount', 0) or 0)),
                    status='success',
                    position_name=data.get('name', ''),
                    account_name=data.get('account_name', ''),
                    notes=data.get('notes') or '现金管理产品赎回',
                    import_hash=data.get('import_hash'),
                    entry_status='orphan',
                )
                db.flush()
                return None
            except Exception:
                db.rollback()
                raise

        symbol = data.get('symbol', '')
        account = data.get('account_name', '')
        op_type = data.get('op_type', 'sell')
        qty = data.get('quantity', 0)
        price = data.get('avg_price', 0)
        trade_date = data.get('purchase_date')

        # 尝试查找现有持仓
        existing = db.query(Position).filter_by(symbol=symbol, account_name=account).first()

        if existing:
            # 有持仓，走正常卖出流程
            return PositionService.process_sell_or_withdraw(
                db,
                {
                    'position_id': existing.id,
                    'quantity': qty,
                    'avg_price': price,
                    'purchase_date': trade_date,
                    'op_type': op_type,
                    'fee': data.get('fee', 0.0),
                    'notes': data.get('notes', ''),
                    'import_hash': data.get('import_hash'),
                },
                skip_lot_check=True,  # 新增参数
            )
        else:
            # 无持仓，创建孤立流水
            amount = qty * price
            TransactionService.create(
                db=db,
                position_id=None,
                txn_type=op_type,
                trade_date=trade_date,
                quantity=qty,
                price=price,
                fee=data.get('fee', 0.0),
                amount=amount,
                status='success',
                position_name=data.get('name', symbol),
                account_name=account,
                notes=data.get('notes') or ('卖出' if op_type == 'sell' else '取出'),
                import_hash=data.get('import_hash'),
                entry_status='orphan',
            )
            db.flush()
            return None

    @staticmethod
    def process_orphan_dividend(db: Session, data: dict) -> Optional[Position]:
        """
        处理分红记录，优先尝试关联持仓；找不到持仓则创建孤立流水。

        data 必须包含：symbol, account_name, dividend_amount, purchase_date
        """
        symbol = data.get('symbol', '')
        account = data.get('account_name', '')
        dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))

        existing = db.query(Position).filter_by(symbol=symbol, account_name=account).first()

        if existing:
            return PositionService.process_dividend(
                db,
                {
                    'position_id': existing.id,
                    'dividend_amount': dividend_amount,
                    'purchase_date': data.get('purchase_date'),
                    'notes': data.get('notes', ''),
                    'import_hash': data.get('import_hash'),
                },
            )
        else:
            TransactionService.create(
                db=db,
                position_id=None,
                txn_type='dividend',
                trade_date=data.get('purchase_date'),
                link_group_id=data.get('link_group_id'),
                quantity=0,
                price=0,
                fee=0,
                amount=dividend_amount,
                status='success',
                position_name=data.get('name', symbol),
                account_name=account,
                notes=data.get('notes') or '现金分红',
                import_hash=data.get('import_hash'),
                entry_status='orphan',
            )
            db.flush()
            return None
