# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/12 19:25
# File : __init__.py
# app/services/performance/__init__.py
from loguru import logger

from app.services.performance.calculators import (
    XirrScopeParameterError,
    calculate_portfolio_xirr,
    calculate_position_xirr,
    calculate_symbol_xirr,
    calculate_xirr_by_scope,
)
from app.services.performance.twr import calculate_twr, calculate_twr_by_scope

__all__ = [
    'calculate_position_xirr',
    'calculate_portfolio_xirr',
    'calculate_symbol_xirr',
    'calculate_xirr_by_scope',
    'calculate_return_by_scope',
    'calculate_twr',
    'calculate_twr_by_scope',
    'XirrScopeParameterError',
]

# method 白名单（#871）。twr 走日因子引擎（pnl_calendar 的 daily_pnl 连乘，
# #2133 实现 + #871 组合级扩展），不共享现金流管线，由本门面转派，
# 视图层因此只见一个入口。
_METHODS = ('xirr', 'twr', 'dietz')


def calculate_return_by_scope(
    db,
    method: str = 'xirr',
    scope: str = 'portfolio',
    family_id: int = 1,
    position_id: int | None = None,
    portfolio_id: int | None = None,
    symbol: str | None = None,
    include_cash_equivalents: bool = False,
    end_date=None,
) -> dict:
    """收益率统一入口：method=xirr|twr|dietz（#871）。

    放包门面而不是视图：分派属 service 职责（#1929 / #1972），且 twr 模块
    import calculators 的异常类——若在 calculators 里反 import twr 会成环，
    门面按「先 calculators 后 twr」的顺序导入天然无环。

    `include_cash_equivalents` 仅对 xirr / dietz 生效：TWR 的日净资产序列
    天然含全部 active 持仓（`pnl_calendar._positions` 不过滤 asset_type），
    是总资产口径；要剔除现金等价物需引擎层加过滤，另行处理。
    """
    if method not in _METHODS:
        raise XirrScopeParameterError(f'不支持的 method: {method!r}，应为 xirr / twr / dietz 之一')
    if method == 'twr':
        result = calculate_twr_by_scope(
            db,
            scope=scope,
            family_id=family_id,
            position_id=position_id,
            portfolio_id=portfolio_id,
            symbol=symbol,
            end_date=end_date,
        )
    else:
        result = calculate_xirr_by_scope(
            db,
            scope=scope,
            family_id=family_id,
            position_id=position_id,
            portfolio_id=portfolio_id,
            symbol=symbol,
            include_cash_equivalents=include_cash_equivalents,
            method=method,
        )
    # 成功日志跟计算同生命周期：下沉到这里，视图层因此只剩 HTTP 编排（#1606 基线冻结）
    logger.info(
        f'收益率计算完成(method={method}, scope={scope}, position_id={position_id}, '
        f'portfolio_id={portfolio_id}, symbol={symbol}): {result}'
    )
    return result
