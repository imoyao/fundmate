# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/12 19:26
# File : xirr_engine.py
# app/services/performance/xirr_engine.py
"""
XIRR 核心算法与现金流生成。

优先使用 pyxirr（与 Excel 完全一致），不可用时降级为纯 Python 实现。
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from app.domains.transactions.models import Transaction  # 实际路径待确认

from loguru import logger

try:
    from pyxirr import xirr as pyxirr_xirr

    PYXIRR_AVAILABLE = True
except ImportError:
    PYXIRR_AVAILABLE = False
    logger.warning('pyxirr 不可用，将使用纯 Python 实现作为兜底')

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.transactions.models import Transaction
from app.services.importer.mappings import BusinessType
from app.services.performance.constants import EXCLUDED_ASSET_TYPES


def _safe_return(value: float) -> float:
    """统一的范围校验，确保返回值在 [-1.0, 10.0] 内，极小值归零"""
    if -1.0 < value < 10.0:
        return value if abs(value) > 1e-8 else 0.0
    return 0.0


def _try_newton(
    cashflows: List[Tuple[dt.date, float]],
    first_date: dt.date,
    initial_guess: float,
    max_iter: int = 100,
) -> Optional[float]:
    """
    单次牛顿-拉夫逊迭代尝试，计算XIRR。

    Args:
        cashflows: 已按日期升序排列的现金流列表
        first_date: 第一笔现金流的日期，用于计算时间差
        initial_guess: 初始猜测值
        max_iter: 最大迭代次数

    Returns:
        收敛时返回年化收益率，不收敛返回None
    """
    guess = initial_guess
    for _ in range(max_iter):
        f = 0.0
        f_prime = 0.0
        for date, amount in cashflows:
            t = (date - first_date).days / 365.0
            denominator = (1 + guess) ** t
            f += amount / denominator
            f_prime -= t * amount / (denominator * (1 + guess))

        if abs(f) < 1e-8:
            return guess

        new_guess = guess - f / f_prime
        if abs(new_guess - guess) < 1e-8:
            return new_guess

        guess = new_guess

    return None


def _pure_python_xirr(cashflows: List[Tuple[dt.date, float]], initial_guess: float = 0.01) -> float:
    """
    xalpha 纯 Python XIRR 实现，作为兜底。

    基于牛顿-拉夫逊迭代法，与 Excel 采用相同的 ACT/365 日计数惯例。
    入参 cashflows 必须已按日期升序排列、无零值、至少2笔且正负现金流同时存在。
    """
    if not cashflows:
        return 0.0

    first_date = cashflows[0][0]

    # 尝试默认初始值
    result = _try_newton(cashflows, first_date, initial_guess, max_iter=100)
    if result is not None:
        return _safe_return(result)

    # 尝试多个备选初始值
    for g in [0.1, -0.1, 0.5, -0.5, 1.0, -1.0]:
        result = _try_newton(cashflows, first_date, g, max_iter=50)
        if result is not None:
            return _safe_return(result)

    return 0.0


def calculate_xirr(cashflows: List[Tuple[dt.date, float]]) -> float:
    """
    计算 XIRR 年化收益率，优先使用 pyxirr，失败时降级为纯 Python 实现。

    Args:
        cashflows: [(日期, 金额), ...]，支出为负，收入为正

    Returns:
        年化收益率，如 0.12 表示 12%。异常情况返回 0.0。
    """
    if not cashflows or len(cashflows) < 2:
        return 0.0

    # 过滤零值现金流
    cf = [(d, a) for d, a in cashflows if abs(a) > 1e-8]
    if len(cf) < 2:
        return 0.0

    # 检查现金流方向（必须有正有负）
    has_positive = any(a > 0 for _, a in cf)
    has_negative = any(a < 0 for _, a in cf)
    if not (has_positive and has_negative):
        return 0.0

    if PYXIRR_AVAILABLE:
        try:
            dates = [d for d, _ in cf]
            amounts = [a for _, a in cf]
            result = pyxirr_xirr(dates, amounts)
            return _safe_return(result)
        except Exception as e:
            logger.warning(f'pyxirr 计算失败（现金流数量 {len(cf)}），异常: {e}，降级为纯 Python 实现')

    # 降级为纯 Python 实现，增加异常保护确保兜底逻辑健壮
    try:
        return _pure_python_xirr(cf)
    except Exception as e:
        logger.warning(f'纯 Python XIRR 计算失败: {e}')
        return 0.0


def generate_cashflows(
    transactions: list[Transaction],
    current_value: float = 0.0,
    end_date: Optional[dt.date] = None,
    include_cash_equivalents: bool = False,
) -> List[Tuple[dt.date, float]]:
    """
    从交易记录生成 XIRR 所需的现金流列表。

    【重要说明】
    1. 本函数不做资产类型过滤，调用方需提前排除货币基金、逆回购、现金等非投资类资产
    2. 交易对象需包含以下属性：confirm_date（交易确认日期）、txn_type（交易类型）、amount（交易金额）

    Args:
        transactions: 交易记录列表，需包含 confirm_date, txn_type, amount 属性
        current_value: 当前持仓总市值，大于0时会作为最后一笔正现金流加入
        end_date: 计算截止日期，默认今天

    Returns:
        按日期升序排列的现金流列表：[(日期, 金额), ...]，支出为负，收入为正
    """
    if end_date is None:
        end_date = dt.date.today()
    elif isinstance(end_date, dt.datetime):
        end_date = end_date.date()

    cashflows: List[Tuple[dt.date, float]] = []

    # 负现金流（现金流出）
    outflow_types = {
        BusinessType.BUY.code,
        BusinessType.DIVIDEND_REINVEST.code,
    }
    # 正现金流（现金流入）
    inflow_types = {
        BusinessType.SELL.code,
        BusinessType.DIVIDEND_CASH.code,
    }

    for txn in transactions:
        # 日期处理
        txn_date = txn.confirm_date
        if isinstance(txn_date, dt.datetime):
            txn_date = txn_date.date()
        if txn_date is None:
            continue
        txn_asset_type = getattr(txn, 'asset_type', None)
        if not include_cash_equivalents and txn_asset_type in EXCLUDED_ASSET_TYPES:
            continue

        # 金额处理
        amount_raw = getattr(txn, 'amount', None)
        if amount_raw is None:
            continue
        try:
            amount = Money.cents_to_yuan(int(amount_raw))  # 分 → 元
        except (TypeError, ValueError):
            continue

        # 根据交易类型确定方向
        txn_type = txn.txn_type  # Transaction 模型字段
        if txn_type in outflow_types:
            cashflows.append((txn_date, -amount))
        elif txn_type in inflow_types:
            cashflows.append((txn_date, amount))

    # 虚拟卖出
    if current_value > 1e-8:
        cashflows.append((end_date, current_value))

    cashflows.sort(key=lambda x: x[0])
    return cashflows


def _exclude_internal_transfers(
    transfer_candidates: list[dict],
    portfolio_ledger_names: set[str],
) -> set[int]:
    """
    识别并返回应排除的内部划转交易索引集合。

    配对条件：同日、金额相等（分精度）、方向相反、分属本组合内不同账户。
    """
    excluded = set()
    deposit_code = BusinessType.DEPOSIT.code
    withdraw_code = BusinessType.WITHDRAW.code

    for i, a in enumerate(transfer_candidates):
        if i in excluded:
            continue
        for j, b in enumerate(transfer_candidates):
            if j <= i or j in excluded:
                continue
            if a['date'] != b['date']:
                continue
            if a['amount_cents'] != b['amount_cents']:
                continue
            if a['account_name'] == b['account_name']:
                continue
            # 方向相反
            a_out = a['txn_type'] == deposit_code and b['txn_type'] == withdraw_code
            b_out = b['txn_type'] == deposit_code and a['txn_type'] == withdraw_code
            if not (a_out or b_out):
                continue
            if a['account_name'] not in portfolio_ledger_names or b['account_name'] not in portfolio_ledger_names:
                continue
            excluded.update([i, j])
            logger.debug(f'内部划转已排除: {a["date"]} {a["account_name"]}↔{b["account_name"]} 金额={a["amount"]:.2f}')
            break
    return excluded


def generate_portfolio_cashflows(
    db_session,
    portfolio_id: int,
    current_value: float = 0.0,
    end_date: Optional[dt.date] = None,
    family_id: int = 1,
    include_cash_equivalents: bool = False,
) -> List[Tuple[dt.date, float]]:
    """为指定投资组合生成 XIRR 现金流列表，过滤内部划转与非投资资产。"""
    if end_date is None:
        end_date = dt.date.today()
    elif isinstance(end_date, dt.datetime):
        end_date = end_date.date()

    # 1. 校验组合存在且未删除，获取关联账户名（家庭维度）
    portfolio = (
        db_session.query(Portfolio)
        .filter(
            Portfolio.id == portfolio_id,
            Portfolio.is_deleted.is_(False),
            Portfolio.family_id == family_id,
        )
        .first()
    )
    if not portfolio:
        raise ValueError(f'投资组合不存在: {portfolio_id}')

    ledger_names = [
        row[0]
        for row in db_session.query(Ledger.name)
        .filter(Ledger.portfolio_id == portfolio_id, Ledger.family_id == family_id)
        .all()
    ]
    if not ledger_names:
        return []

    ledger_set = set(ledger_names)

    # 2. 查询所有相关交易
    transactions = (
        db_session.query(Transaction)
        .filter(Transaction.account_name.in_(ledger_names), Transaction.family_id == family_id)
        .all()
    )

    # 3. 分类交易
    outflow_types = {BusinessType.BUY.code, BusinessType.DIVIDEND_REINVEST.code}
    inflow_types = {BusinessType.SELL.code, BusinessType.DIVIDEND_CASH.code}

    investment_cf: List[Tuple[dt.date, float]] = []
    transfer_candidates: List[dict] = []

    for txn in transactions:
        txn_date = txn.confirm_date
        if isinstance(txn_date, dt.datetime):
            txn_date = txn_date.date()
        if txn_date is None:
            continue

        if not include_cash_equivalents and getattr(txn, 'asset_type', None) in EXCLUDED_ASSET_TYPES:
            continue

        amount = getattr(txn, 'amount', None)
        if amount is None:
            continue
        try:
            amount_f = float(amount)
        except (TypeError, ValueError):
            continue

        txn_type = txn.txn_type
        if txn_type in (BusinessType.DEPOSIT.code, BusinessType.WITHDRAW.code):
            transfer_candidates.append(
                {
                    'date': txn_date,
                    'amount': amount_f,
                    'amount_cents': round(amount_f * 100),
                    'txn_type': txn_type,
                    'account_name': txn.account_name,
                }
            )
        elif txn_type in outflow_types:
            investment_cf.append((txn_date, -amount_f))
        elif txn_type in inflow_types:
            investment_cf.append((txn_date, amount_f))

    # 4. 剔除内部划转
    _ = _exclude_internal_transfers(transfer_candidates, ledger_set)

    # 5. 添加虚拟卖出
    if current_value > 1e-8:
        investment_cf.append((end_date, current_value))

    investment_cf.sort(key=lambda x: x[0])
    return investment_cf
