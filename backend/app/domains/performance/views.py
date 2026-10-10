# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/12 19:29
# File : views.py
# app/domains/performance/views.py

from apiflask import APIBlueprint
from flask import abort, jsonify
from loguru import logger

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.validation import parse_query
from app.domains.performance.schemas import MoneyFundIncomeRequest, XirrRequest
from app.services.money_fund_income import calculate_money_fund_income, resolve_money_fund_scope
from app.services.performance import XirrScopeParameterError, calculate_xirr_by_scope

bp = APIBlueprint('performance', __name__, url_prefix='/api/performance')


@bp.get('/xirr/')
def get_xirr():
    """查询年化收益率（scope=position / portfolio / symbol，分派下沉 services）"""
    query_data: XirrRequest = parse_query(XirrRequest)

    with get_db() as db:
        # scope 校验 / 分派 / 归属校验全部下沉 services（#1929 / #1972）：
        # XirrScopeParameterError 必须排在 ValueError 之前捕获（它是其子类），
        # 否则「参数缺失」会被归属校验的 404 分支吃掉。
        try:
            result = calculate_xirr_by_scope(
                db,
                scope=query_data.scope,
                position_id=query_data.position_id,
                portfolio_id=query_data.portfolio_id,
                symbol=query_data.symbol,
                family_id=get_family_id(),
                include_cash_equivalents=query_data.include_cash_equivalents,
            )
        except XirrScopeParameterError as e:
            abort(400, str(e))
        except ValueError as e:
            abort(404, str(e))
        except Exception as e:
            logger.exception('年化收益率计算异常')
            abort(500, f'年化收益率计算失败，请稍后重试: {str(e)}')

    logger.info(
        f'年化收益率计算完成(scope={query_data.scope}, position_id={query_data.position_id}, '
        f'portfolio_id={query_data.portfolio_id}, symbol={query_data.symbol}): {result}'
    )
    return jsonify({'data': result, 'message': 'ok'})


@bp.get('/money-fund-income/')
def get_money_fund_income():
    """查询货币基金每日收益（账本/家庭/组合维度）"""
    q: MoneyFundIncomeRequest = parse_query(MoneyFundIncomeRequest)

    with get_db() as db:
        # scope 校验 / 归属校验 / 组合→账户解析全部下沉 services（视图只做 HTTP 编排，#1606 / #1929）
        try:
            resolved = resolve_money_fund_scope(db, q.scope, q.ledger_id, q.portfolio_id, get_family_id())
        except ValueError as e:
            abort(400, str(e))
        if resolved is None:
            abort(404, '投资组合不存在或无权访问' if q.scope == 'portfolio' else '账户不存在或无权访问')
        ledger_id, ledger_ids = resolved
        try:
            result = calculate_money_fund_income(
                db,
                start_date=q.start_date,
                end_date=q.end_date,
                scope=q.scope,
                ledger_id=ledger_id,
                ledger_ids=ledger_ids,
                family_id=get_family_id(),
            )
        except ValueError as e:
            abort(400, str(e))
        except Exception as e:
            logger.exception('货币基金收益计算异常')
            abort(500, f'货币基金收益计算失败，请稍后重试: {str(e)}')

    logger.info(f'货币基金收益计算完成(scope={q.scope}, portfolio_id={q.portfolio_id}): {result}')
    return jsonify({'data': result, 'message': 'ok'})
