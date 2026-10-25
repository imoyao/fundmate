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

# EXCLUDED_ASSET_TYPES 唯一来源为 app.core.asset_types（#1171 枚举一致性）；
# 原 services/performance/constants.py 只是 12 行 re-export 转发层，已删除。
from app.core.asset_types import EXCLUDED_ASSET_TYPES
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.transactions.models import Transaction
from app.services.importer.mappings import BusinessType
from app.services.performance import cashflow_layers


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


def calculate_modified_dietz(cashflows: List[Tuple[dt.date, float]]) -> float:
    """
    Modified Dietz 区间收益率（#871）：线性近似，**不年化**。

    回答「这一段（本月 / 本年）贡献多少」，与 XIRR 的分工见 #796 存档论证：
    XIRR 作主口径（年化、资金加权，对申赎时点敏感），Modified Dietz 作区间
    归因辅助（无需求解、无迭代，权重按持有天数线性折减）。

    标准式：R = (EMV − BMV − C) / (BMV + Σ w_i·C_i)，C_i 为外部流入（正），
    w_i = (T − t_i)/T。换算到本仓现金流约定（支出为负、收入为正，末笔虚拟
    卖出即 EMV，BMV=0 因首笔流前无持仓记录）：

        R = −Σa_i / Σ(w_i·a_i)        （虚拟卖出 w=0，自动出局）

    验证（单利场景必须与直觉一致）：D0 买 100、D365 值 110 ⇒ R=+10%；
    D0/D182 各买 100、D365 值 230 ⇒ R≈+19.97%（同期 XIRR≈19.5%，差异来自
    线性近似本身，属预期）。

    退化处理（不造数字）：
    - 权重分母 ≈ 0（如全部资金最后一天才进仓）：无持续在仓资本即无区间
      收益，返回 0.0；
    - 所有流同一天（T=0）：权重无定义，退化为简单回报（净增益 ÷ 总成本）。
    """
    if not cashflows or len(cashflows) < 2:
        return 0.0

    # 过滤零值现金流并确保按日期升序（与 calculate_xirr 同一前置口径）
    cf = [(d, a) for d, a in cashflows if abs(a) > 1e-8]
    if len(cf) < 2:
        return 0.0
    cf.sort(key=lambda x: x[0])

    d0, d_end = cf[0][0], cf[-1][0]
    total_days = (d_end - d0).days
    net = sum(a for _, a in cf)

    if total_days <= 0:
        cost = -sum(a for _, a in cf if a < 0)
        return _safe_return(net / cost) if cost > 1e-8 else 0.0

    weighted = 0.0
    for d, a in cf:
        weight = (total_days - (d - d0).days) / total_days
        weighted += weight * a
    if abs(weighted) < 1e-8:
        return 0.0
    return _safe_return(-net / weighted)


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
    portfolio_ledger_ids: set[int],
) -> set[int]:
    """兼容入口（历史名）：实现已迁到 `cashflow_layers.pair_internal_transfers`。

    保留别名是因为 `tests/services/performance/test_xirr_engine.py` 有一整套配对用例
    直接打它；真正被消费方使用的是 `cashflow_layers` 里的同名函数。
    """
    return cashflow_layers.pair_internal_transfers(transfer_candidates, portfolio_ledger_ids)


def generate_portfolio_cashflows(
    db_session,
    portfolio_id: int,
    current_value: float = 0.0,
    end_date: Optional[dt.date] = None,
    family_id: int = 1,
    include_cash_equivalents: bool = False,
    basis_sink: Optional[dict] = None,
) -> List[Tuple[dt.date, float]]:
    """为指定投资组合生成 XIRR 现金流列表，过滤内部划转与非投资资产。

    **金额单位必须与 `generate_cashflows` 一致（元）**：`transactions.amount` 存的是
    「分」，本函数曾直接 `float(amount)` 当元用，导致组合级现金流比市值大 100 倍
    （线上表现为总投入 1.68 亿、总收益 -1886 万，XIRR 恒为 0）。改动此处前先看
    `tests/services/performance/test_portfolio_xirr_units.py`。

    口径（#2615）：分类与内部划转判定统一走 `cashflow_layers`，本函数只做「按账户
    口径组装现金流」：

    - 账户有真实外部入金/出金（L1）⇒ **账户口径**：只有 L1 进出算投入/回收，
      买卖属于账户内换形态（L2），不进现金流；
    - 账户只导过交易、没有入金流水 ⇒ **持仓口径**（历史行为，降级）：买入算投入、
      卖出/分红算回收。整组合按账户口径一刀切会让这类老账户丢掉本金（年化 0%）。

    `basis_sink` 传 dict 时回填实际口径：`{'basis': 'account'|'position'|'mixed',
    'by_ledger': {ledger_id: 'account'|'position'}}`，供响应层如实透出「按什么估的」。
    """
    if end_date is None:
        end_date = dt.date.today()
    elif isinstance(end_date, dt.datetime):
        end_date = end_date.date()

    # 1. 校验组合存在且未删除，获取关联账户 ID（家庭维度）
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

    # 组合聚合统一按 ledger_id（外键维度），不用冗余的 account_name —— 同名账户
    # 会造成口径串味（历史 bug）。未归档持仓 ledger_id 为 NULL 自然不计入组合。
    ledger_ids = [
        row[0]
        for row in db_session.query(Ledger.id)
        .filter(Ledger.portfolio_id == portfolio_id, Ledger.family_id == family_id)
        .all()
    ]
    if not ledger_ids:
        return []

    ledger_set = set(ledger_ids)

    # 2. 分层取流水（金额已是元，见 cashflow_layers 的单位纪律）
    flows = cashflow_layers.collect_flows(
        db_session,
        ledger_ids,
        family_id=family_id,
        end_date=end_date,
        include_cash_equivalents=include_cash_equivalents,
    )
    internal = cashflow_layers.pair_internal_transfers(flows, ledger_set)
    basis_map = cashflow_layers.basis_by_ledger(flows, internal)

    # 3. 按账户口径组装现金流（4 类：账户口径只看 L1；持仓口径看 L2/L3）
    investment_cf: List[Tuple[dt.date, float]] = []
    for flow in flows:
        if flow['index'] in internal:
            # 家庭内账户互转：一进一出净额为 0，任何口径都不该出现（#2615 修的正是
            # 此前「配对结果被 `_ =` 丢弃」的空操作）
            continue
        if basis_map.get(flow['ledger_id']) == 'account':
            if flow['layer'] == cashflow_layers.L1_EXTERNAL:
                investment_cf.append((flow['date'], flow['signed_amount']))
            continue
        # 持仓口径（降级）：沿用历史行为
        if flow['layer'] == cashflow_layers.L2_TRANSFER:
            if flow['txn_type'] in (BusinessType.BUY.code, BusinessType.DIVIDEND_REINVEST.code):
                investment_cf.append((flow['date'], -flow['amount']))
            elif flow['txn_type'] == BusinessType.SELL.code:
                investment_cf.append((flow['date'], flow['amount']))
        elif flow['layer'] == cashflow_layers.L3_REALIZED and flow['txn_type'] in (
            BusinessType.DIVIDEND.code,
            BusinessType.DIVIDEND_CASH.code,
            BusinessType.BOND_REDEEM.code,
        ):
            investment_cf.append((flow['date'], flow['amount']))

    if basis_sink is not None:
        used = set(basis_map.values())
        if used == {'account'}:
            overall = 'account'
        elif used <= {'position'}:
            overall = 'position'
        else:
            overall = 'mixed'
        basis_sink['basis'] = overall
        basis_sink['by_ledger'] = dict(basis_map)

    # 4. 添加虚拟卖出（当前市值按元计，与上面同单位）
    if current_value > 1e-8:
        investment_cf.append((end_date, current_value))

    investment_cf.sort(key=lambda x: x[0])
    return investment_cf
