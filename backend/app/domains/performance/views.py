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
from app.domains.ledgers.models import Ledger
from app.domains.performance.schemas import MoneyFundIncomeRequest, XirrRequest
from app.services.money_fund_income import calculate_money_fund_income
from app.services.performance import calculate_portfolio_xirr, calculate_position_xirr
from app.services.performance.calculators import calculate_portfolio_xirr_by_id

bp = APIBlueprint('performance', __name__, url_prefix='/api/performance')


@bp.get('/xirr/')
def get_xirr():
    """查询年化收益率"""
    query_data: XirrRequest = parse_query(XirrRequest)
    scope = query_data.scope
    position_id = query_data.position_id
    portfolio_id = query_data.portfolio_id

    with get_db() as db:
        try:
            if scope == 'position':
                if not position_id:
                    abort(400, '缺少 position_id 参数')
                result = calculate_position_xirr(db, position_id, family_id=get_family_id())
            elif scope == 'portfolio' and portfolio_id:
                result = calculate_portfolio_xirr_by_id(db, portfolio_id, family_id=get_family_id())
                logger.info(f'组合 XIRR 计算完成(portfolio_id={portfolio_id}): {result}')
            else:
                result = calculate_portfolio_xirr(db, family_id=get_family_id())
                logger.info(f'组合 XIRR 计算完成: {result}')
        except ValueError as e:
            abort(404, str(e))
        except Exception as e:
            logger.exception('年化收益率计算异常')
            abort(500, f'年化收益率计算失败，请稍后重试: {str(e)}')

    return jsonify({'data': result, 'message': 'ok'})


@bp.get('/money-fund-income/')
def get_money_fund_income():
    """查询货币基金每日收益（账本/家庭维度）"""
    query_data: MoneyFundIncomeRequest = parse_query(MoneyFundIncomeRequest)
    scope = query_data.scope
    ledger_id = query_data.ledger_id
    start_date = query_data.start_date
    end_date = query_data.end_date

    if scope not in ('ledger', 'family'):
        abort(400, 'scope 参数非法，仅支持 ledger / family')
    if scope == 'ledger' and not ledger_id:
        abort(400, 'scope=ledger 时必须提供 ledger_id')

    with get_db() as db:
        if scope == 'ledger':
            # 账户归属校验：越权/不存在统一 404（避免泄露存在性）
            ledger = db.query(Ledger).filter(Ledger.id == ledger_id, Ledger.family_id == get_family_id()).first()
            if not ledger:
                abort(404, '账户不存在或无权访问')
        try:
            result = calculate_money_fund_income(
                db,
                start_date=start_date,
                end_date=end_date,
                scope=scope,
                ledger_id=ledger_id,
                family_id=get_family_id(),
            )
        except ValueError as e:
            abort(400, str(e))
        except Exception as e:
            logger.exception('货币基金收益计算异常')
            abort(500, f'货币基金收益计算失败，请稍后重试: {str(e)}')

    logger.info(f'货币基金收益计算完成(scope={scope}, ledger_id={ledger_id}): {result}')
    return jsonify({'data': result, 'message': 'ok'})
