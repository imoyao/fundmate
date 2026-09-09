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

# EXCLUDED_ASSET_TYPES 唯一来源为 app.core.asset_types（#1171 枚举一致性）；
# 原 services/performance/constants.py 只是 12 行 re-export 转发层，已删除。
from app.core.asset_types import EXCLUDED_ASSET_TYPES
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.domains.transactions.models import Transaction
from app.services.nav_service import NavService
from app.services.performance.xirr_engine import calculate_xirr, generate_cashflows, generate_portfolio_cashflows


def _get_fund_latest_nav(db: Session, fund_code: str) -> float:
    """获取基金最新单位净值，失败返回 0.0。

    委托 :class:`NavService` 统一入口（#1133）。
    ``allow_remote=False``：XIRR 属同步计算，禁止在请求内触发远程拉取。
    """
    try:
        result = NavService.get_latest_navs(db, [fund_code], allow_remote=False)
        return float(result.get(fund_code, 0.0))
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

    # 委托 NavService 统一入口（#1133）；批量场景禁止触发远程拉取
    fund_nav_map: Dict[str, float] = {}
    if fund_codes:
        fund_nav_map = NavService.get_latest_navs(db, fund_codes, allow_remote=False)

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
            unit_price = Money.price_units_to_yuan(pos.current_price) if pos.current_price else 0.0

        value_map[pos.id] = shares * unit_price if unit_price > 1e-8 else 0.0

    return value_map


def _get_position_current_value(db: Session, position: Position) -> float:
    shares = Money.min_unit_to_shares(position.quantity)

    if position.asset_type == 'fund' and position.symbol:
        unit_price = _get_fund_latest_nav(db, position.symbol)
    elif position.asset_type in ('stock', 'etf') and position.symbol:
        unit_price = _get_stock_latest_price(db, position.symbol)
    else:
        unit_price = Money.price_units_to_yuan(position.current_price) if position.current_price else 0.0

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


def calculate_position_xirr(
    db: Session, position_id: int, family_id: int = 1, include_cash_equivalents: bool = False
) -> Dict[str, Any]:
    """计算单持仓的年化收益率 (XIRR)"""
    position = db.query(Position).filter(Position.id == position_id, Position.family_id == family_id).first()
    if not position:
        raise ValueError('持仓不存在')

    txn_q = db.query(Transaction).filter(Transaction.family_id == family_id)
    if not include_cash_equivalents:
        # NULL 的 asset_type 默认视为投资类资产，纳入计算
        txn_q = txn_q.filter(Transaction.asset_type.is_(None) | Transaction.asset_type.not_in(EXCLUDED_ASSET_TYPES))
    transactions = txn_q.all()

    current_value = _get_position_current_value(db, position)
    cashflows = generate_cashflows(transactions, current_value, include_cash_equivalents=include_cash_equivalents)
    return _calculate_xirr_for_cashflows(cashflows, current_value)


def calculate_portfolio_xirr(db: Session, family_id: int = 1, include_cash_equivalents: bool = False) -> Dict[str, Any]:
    """
    计算整个投资组合的年化收益率 (XIRR)。
    通过 asset_type 字段直接过滤，孤儿交易默认纳入计算（asset_type 为 NULL 不会被 NOT IN 排除）。
    include_cash_equivalents=True 时，货币基金/逆回购/现金也并入分母，得到账户总收益。
    """
    # 直接通过 asset_type 过滤交易，无需 JOIN Position 表
    txn_filter = [Transaction.family_id == family_id]
    if not include_cash_equivalents:
        txn_filter.append(Transaction.asset_type.is_(None) | Transaction.asset_type.not_in(EXCLUDED_ASSET_TYPES))
    filtered_transactions = db.query(Transaction).filter(*txn_filter).all()

    # 获取所有非排除类型的持仓（家庭维度）
    pos_filter = [Position.quantity > 0, Position.family_id == family_id]
    if not include_cash_equivalents:
        pos_filter.append(Position.asset_type.not_in(EXCLUDED_ASSET_TYPES))
    positions = db.query(Position).filter(*pos_filter).all()

    # 批量计算持仓市值
    value_map = _batch_get_position_values(db, positions)
    total_value = sum(value_map.values())

    cashflows = generate_cashflows(
        filtered_transactions, total_value, include_cash_equivalents=include_cash_equivalents
    )

    logger.debug(
        f'组合XIRR计算：交易笔数={len(filtered_transactions)}, '
        f'持仓数={len(positions)}, 总市值={total_value:.2f}, '
        f'现金流笔数={len(cashflows)}, 含现金等价物={include_cash_equivalents}'
    )

    return _calculate_xirr_for_cashflows(cashflows, total_value)


def calculate_portfolio_xirr_by_id(
    db: Session, portfolio_id: int, family_id: int = 1, include_cash_equivalents: bool = False
) -> Dict[str, Any]:
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
    pos_filter = [
        Position.account_name.in_(ledger_names),
        Position.quantity > 0,
        Position.family_id == family_id,
    ]
    if not include_cash_equivalents:
        pos_filter.append(Position.asset_type.not_in(EXCLUDED_ASSET_TYPES))
    positions = db.query(Position).filter(*pos_filter).all()

    value_map = _batch_get_position_values(db, positions)
    total_value = sum(value_map.values())

    cashflows = generate_portfolio_cashflows(
        db, portfolio_id, total_value, family_id=family_id, include_cash_equivalents=include_cash_equivalents
    )

    logger.debug(
        f'组合 XIRR 计算(portfolio_id={portfolio_id}): '
        f'账户数={len(ledger_names)}, 持仓数={len(positions)}, '
        f'总市值={total_value:.2f}, 现金流笔数={len(cashflows)}'
    )

    return _calculate_xirr_for_cashflows(cashflows, total_value)
