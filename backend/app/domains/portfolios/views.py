# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 18:04
# File : views.py
# -*- coding: utf-8 -*-
"""
投资组合 API — CRUD + 软删除
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from loguru import logger
from sqlalchemy import update

from app.core.auth import get_family_id, get_owned_or_404
from app.core.database import get_db
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.portfolios.schemas import PortfolioCreate, PortfolioUpdate
from app.services.portfolio_service import build_portfolio_holdings

portfolios_bp = APIBlueprint('portfolios', __name__, url_prefix='/api/portfolios')


def _portfolio_to_dict(portfolio: Portfolio) -> dict:
    """将 Portfolio 模型实例转为字典"""
    return {
        'id': portfolio.id,
        'name': portfolio.name,
        'description': portfolio.description,
        'purpose': portfolio.purpose,
        'target_return': float(portfolio.target_return) if portfolio.target_return else None,
        'target_amount': float(portfolio.target_amount) if portfolio.target_amount else None,
        'target_date': portfolio.target_date.isoformat() if portfolio.target_date else None,
        'benchmark': portfolio.benchmark,
        'is_deleted': portfolio.is_deleted,
        'created_at': portfolio.created_at.isoformat() if portfolio.created_at else None,
        'updated_at': portfolio.updated_at.isoformat() if portfolio.updated_at else None,
    }


@portfolios_bp.post('/')
def create_portfolio():
    """创建投资组合"""
    data = request.get_json() or {}
    schema = PortfolioCreate(**data)  # Pydantic 自动校验

    with get_db() as db:
        try:
            portfolio = Portfolio(
                name=schema.name,
                description=schema.description,
                purpose=schema.purpose,
                target_return=schema.target_return,
                target_amount=schema.target_amount,
                target_date=schema.target_date,
                benchmark=schema.benchmark,
                family_id=get_family_id(),
            )
            db.add(portfolio)
            db.flush()
            db.refresh(portfolio)
            return jsonify({'data': _portfolio_to_dict(portfolio), 'message': 'ok'})
        except Exception as e:
            db.rollback()
            logger.exception('创建投资组合失败')
            abort(500, description=str(e))


@portfolios_bp.get('/')
def list_portfolios():
    """获取所有投资组合（不含已删除）"""
    with get_db() as db:
        portfolios = (
            db.query(Portfolio)
            .filter(Portfolio.is_deleted.is_(False), Portfolio.family_id == get_family_id())
            .order_by(Portfolio.created_at.asc())
            .all()
        )
        # MVP 列表返回: id, name, purpose, created_at
        result = [
            {
                'id': p.id,
                'name': p.name,
                'purpose': p.purpose,
                'created_at': p.created_at.isoformat() if p.created_at else None,
            }
            for p in portfolios
        ]
        return jsonify({'data': result, 'message': 'ok'})


@portfolios_bp.get('/<int:portfolio_id>/')
def get_portfolio(portfolio_id: int):
    """获取单个投资组合详情"""
    with get_db() as db:
        portfolio = get_owned_or_404(db, Portfolio, portfolio_id)
        if not portfolio:
            abort(404, '投资组合不存在')
        return jsonify({'data': _portfolio_to_dict(portfolio), 'message': 'ok'})


@portfolios_bp.patch('/<int:portfolio_id>/')
def update_portfolio(portfolio_id: int):
    """更新投资组合"""
    data = request.get_json() or {}
    schema = PortfolioUpdate(**data)

    with get_db() as db:
        portfolio = get_owned_or_404(db, Portfolio, portfolio_id)
        if not portfolio:
            abort(404, '投资组合不存在')

        # 仅更新传入的字段
        if schema.name is not None:
            portfolio.name = schema.name
        if schema.description is not None:
            portfolio.description = schema.description
        if schema.purpose is not None:
            portfolio.purpose = schema.purpose
        if schema.target_return is not None:
            portfolio.target_return = schema.target_return
        if schema.target_amount is not None:
            portfolio.target_amount = schema.target_amount
        if schema.target_date is not None:
            portfolio.target_date = schema.target_date
        if schema.benchmark is not None:
            portfolio.benchmark = schema.benchmark

        db.flush()
        db.refresh(portfolio)
        return jsonify({'data': _portfolio_to_dict(portfolio), 'message': 'ok'})


@portfolios_bp.delete('/<int:portfolio_id>/')
def delete_portfolio(portfolio_id: int):
    """软删除投资组合，并自动解绑所有关联账户"""
    with get_db() as db:
        portfolio = get_owned_or_404(db, Portfolio, portfolio_id)
        if not portfolio:
            abort(404, '投资组合不存在')

        # 批量解绑关联账户（使用 update 语句，避免逐条加载），限本家庭
        db.execute(
            update(Ledger)
            .where(Ledger.portfolio_id == portfolio_id, Ledger.family_id == get_family_id())
            .values(portfolio_id=None)
        )

        # 软删除组合
        portfolio.is_deleted = True
        db.flush()

        return jsonify({'data': {}, 'message': 'ok'})


# 在文件末尾新增端点
@portfolios_bp.get('/<int:portfolio_id>/holdings/')
def get_portfolio_holdings(portfolio_id: int):
    """获取组合下所有关联账户的持仓明细"""
    with get_db() as db:
        try:
            holdings = build_portfolio_holdings(db, get_family_id(), portfolio_id)
        except ValueError as e:
            abort(404, str(e))
        return jsonify({'data': holdings, 'message': 'ok'})
