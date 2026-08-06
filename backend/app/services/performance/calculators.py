# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/12 19:27
# File : calculators.py
# app/services/performance/calculators.py
"""
业务层：单持仓与组合年化收益率计算器。
"""

import datetime as dt
from typing import Any, Dict, List, Tuple

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.domains.transactions.models import Transaction
from app.services.performance.constants import EXCLUDED_ASSET_TYPES
from app.services.performance.xirr_engine import calculate_xirr, generate_cashflows, generate_portfolio_cashflows


def _get_fund_latest_nav(db: Session, fund_code: str) -> float:
    """获取基金最新单位净值，失败返回 0.0"""
    try:
        row = (
            db.query(DailyWorth.unit_nav)
            .filter(DailyWorth.fund_code == fund_code)
            .order_by(DailyWorth.date.desc())
            .first()
        )
        return float(row[0]) if row and row[0] else 0.0
    except Exception:
        logger.warning(f'查询基金最新净值失败，fund_code={fund_code}', exc_info=True)
        return 0.0


def _get_stock_latest_price(db: Session, symbol: str) -> float:
    """获取股票最新收盘价，失败返回 0.0"""
    try:
        sec = db.query(Security.id).filter(Security.symbol == symbol).first()
        if not sec:
            return 0.0
        row = (
            db.query(PriceHistory.close)
            .filter(PriceHistory.security_id == sec.id)
            .order_by(PriceHistory.trade_date.desc())
            .first()
        )
        return float(row[0]) if row and row[0] else 0.0
    except Exception:
        logger.warning(f'查询股票最新价格失败，symbol={symbol}', exc_info=True)
        return 0.0


def _batch_get_position_values(db: Session, positions: List[Position]) -> Dict[int, float]:
    fund_codes = [p.symbol for p in positions if p.asset_type == 'fund' and p.symbol]
    stock_symbols = [p.symbol for p in positions if p.asset_type in ('stock', 'etf') and p.symbol]

    fund_nav_map: Dict[str, float] = {}
    if fund_codes:
        latest = (
            db.query(DailyWorth.fund_code, func.max(DailyWorth.date).label('max_date'))
            .filter(DailyWorth.fund_code.in_(fund_codes))
            .group_by(DailyWorth.fund_code)
            .subquery()
        )
        results = (
            db.query(DailyWorth.fund_code, DailyWorth.unit_nav)
            .join(latest, (DailyWorth.fund_code == latest.c.fund_code) & (DailyWorth.date == latest.c.max_date))
            .all()
        )
        fund_nav_map = {code: float(nav) for code, nav in results if nav}

    stock_price_map: Dict[str, float] = {}
    if stock_symbols:
        sec_map = {
            sec.symbol: sec.id
            for sec in db.query(Security.symbol, Security.id).filter(Security.symbol.in_(stock_symbols)).all()
        }
        security_ids = list(sec_map.values())
        if security_ids:
            latest = (
                db.query(PriceHistory.security_id, func.max(PriceHistory.trade_date).label('max_date'))
                .filter(PriceHistory.security_id.in_(security_ids))
                .group_by(PriceHistory.security_id)
                .subquery()
            )
            results = (
                db.query(PriceHistory.security_id, PriceHistory.close)
                .join(
                    latest,
                    (PriceHistory.security_id == latest.c.security_id) & (PriceHistory.trade_date == latest.c.max_date),
                )
                .all()
            )
            id_to_price = {sid: float(price) for sid, price in results if price}
            for symbol, sid in sec_map.items():
                if sid in id_to_price:
                    stock_price_map[symbol] = id_to_price[sid]

    value_map: Dict[int, float] = {}
    for pos in positions:
        # 将内部单位转为元 / 份
        shares = Money.min_unit_to_shares(pos.quantity)

        if pos.asset_type == 'fund' and pos.symbol:
            unit_price = fund_nav_map.get(pos.symbol, 0.0)  # 净值已是元
        elif pos.asset_type in ('stock', 'etf') and pos.symbol:
            unit_price = stock_price_map.get(pos.symbol, 0.0)
        else:
            unit_price = Money.cents_to_yuan(pos.current_price) if pos.current_price else 0.0

        value_map[pos.id] = shares * unit_price if unit_price > 1e-8 else 0.0

    return value_map


def _get_position_current_value(db: Session, position: Position) -> float:
    shares = Money.min_unit_to_shares(position.quantity)

    if position.asset_type == 'fund' and position.symbol:
        unit_price = _get_fund_latest_nav(db, position.symbol)
    elif position.asset_type in ('stock', 'etf') and position.symbol:
        unit_price = _get_stock_latest_price(db, position.symbol)
    else:
        unit_price = Money.cents_to_yuan(position.current_price) if position.current_price else 0.0

    if unit_price <= 1e-8:
        return 0.0
    return shares * unit_price


def _calculate_xirr_for_cashflows(
    cashflows: List[Tuple[dt.date, float]],
    current_market_value: float = 0.0,
) -> Dict[str, Any]:
    """
    根据现金流计算 XIRR 并返回标准结构。

    Args:
        cashflows: 完整现金流列表
        current_market_value: 当前持仓总市值（由调用方传入，不从现金流反推）
    """
    xirr_val = calculate_xirr(cashflows)

    # 总投入：所有负现金流的绝对值之和
    total_invested = sum(abs(a) for _, a in cashflows if a < 0)
    # 总收回：所有正现金流之和（包含虚拟卖出）
    total_withdrawn = sum(a for _, a in cashflows if a > 0)
    # 历史收回（不含虚拟卖出）：从 total_withdrawn 中减去虚拟卖出的部分
    historical_withdrawn = total_withdrawn - current_market_value
    # 总收益 = 当前市值 + 历史收回 - 总投入
    total_return = current_market_value + historical_withdrawn - total_invested

    logger.info(
        f'XIRR计算详情: cashflows前5笔={cashflows[:5]}, total_invested={total_invested}, current_market_value={current_market_value}'
    )
    return {
        'xirr': round(xirr_val, 4),
        'total_invested': round(total_invested, 2),
        'current_value': round(current_market_value, 2),
        'total_withdrawn': round(historical_withdrawn, 2),
        'total_return': round(total_return, 2),
        'cashflow_count': len(cashflows),
    }


def calculate_position_xirr(db: Session, position_id: int, family_id: int = 1) -> Dict[str, Any]:
    """计算单持仓的年化收益率 (XIRR)"""
    position = db.query(Position).filter(Position.id == position_id, Position.family_id == family_id).first()
    if not position:
        raise ValueError('持仓不存在')

    transactions = (
        db.query(Transaction)
        .filter(
            # NULL 的 asset_type 默认视为投资类资产，纳入计算
            Transaction.asset_type.is_(None) | Transaction.asset_type.not_in(EXCLUDED_ASSET_TYPES),
            Transaction.family_id == family_id,
        )
        .all()
    )

    current_value = _get_position_current_value(db, position)
    cashflows = generate_cashflows(transactions, current_value)
    return _calculate_xirr_for_cashflows(cashflows, current_value)


def calculate_portfolio_xirr(db: Session, family_id: int = 1) -> Dict[str, Any]:
    """
    计算整个投资组合的年化收益率 (XIRR)。
    通过 asset_type 字段直接过滤，孤儿交易默认纳入计算（asset_type 为 NULL 不会被 NOT IN 排除）。
    """
    # 直接通过 asset_type 过滤交易，无需 JOIN Position 表
    filtered_transactions = (
        db.query(Transaction)
        .filter(
            Transaction.asset_type.is_(None) | Transaction.asset_type.not_in(EXCLUDED_ASSET_TYPES),
            Transaction.family_id == family_id,
        )
        .all()
    )

    # 获取所有非排除类型的持仓（家庭维度）
    positions = (
        db.query(Position)
        .filter(
            Position.asset_type.not_in(EXCLUDED_ASSET_TYPES),
            Position.quantity > 0,
            Position.family_id == family_id,
        )
        .all()
    )

    # 批量计算持仓市值
    value_map = _batch_get_position_values(db, positions)
    total_value = sum(value_map.values())

    cashflows = generate_cashflows(filtered_transactions, total_value)

    logger.debug(
        f'组合XIRR计算：交易笔数={len(filtered_transactions)}, '
        f'持仓数={len(positions)}, 总市值={total_value:.2f}, '
        f'现金流笔数={len(cashflows)}'
    )

    return _calculate_xirr_for_cashflows(cashflows, total_value)


def calculate_portfolio_xirr_by_id(db: Session, portfolio_id: int, family_id: int = 1) -> Dict[str, Any]:
    """
    计算指定投资组合的年化收益率 (XIRR)。

    步骤：
    1. 校验组合存在且归属当前家庭
    2. 获取组合关联的所有 Ledger
    3. 计算这些 Ledger 下合规资产的持仓总市值
    4. 生成组合现金流（含内部划转过滤）
    5. 送入 XIRR 引擎计算
    """
    from app.domains.portfolios.models import Portfolio

    # 0. 组合归属校验：不存在或跨家庭一律 404，避免泄露存在性
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id, Portfolio.family_id == family_id).first()
    if not portfolio:
        raise ValueError('投资组合不存在')

    # 获取组合关联的所有 Ledger 名称（家庭维度）
    ledger_names = [
        row[0]
        for row in db.query(Ledger.name)
        .filter(Ledger.portfolio_id == portfolio_id, Ledger.family_id == family_id)
        .all()
    ]

    if not ledger_names:
        return {
            'xirr': 0.0,
            'total_invested': 0.0,
            'current_value': 0.0,
            'total_withdrawn': 0.0,
            'total_return': 0.0,
            'cashflow_count': 0,
        }

    # 获取这些账户下的持仓总市值
    positions = (
        db.query(Position)
        .filter(
            Position.account_name.in_(ledger_names),
            Position.asset_type.not_in(EXCLUDED_ASSET_TYPES),
            Position.quantity > 0,
            Position.family_id == family_id,
        )
        .all()
    )

    value_map = _batch_get_position_values(db, positions)
    total_value = sum(value_map.values())

    cashflows = generate_portfolio_cashflows(db, portfolio_id, total_value, family_id=family_id)

    logger.debug(
        f'组合 XIRR 计算(portfolio_id={portfolio_id}): '
        f'账户数={len(ledger_names)}, 持仓数={len(positions)}, '
        f'总市值={total_value:.2f}, 现金流笔数={len(cashflows)}'
    )

    return _calculate_xirr_for_cashflows(cashflows, total_value)
