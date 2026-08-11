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
from app.core.constants import TYPE_LABELS
from app.core.database import get_db
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.portfolios.schemas import PortfolioCreate, PortfolioUpdate
from app.domains.positions.models import Position
from app.services.performance.constants import EXCLUDED_ASSET_TYPES

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
            db.commit()
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

        db.commit()
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
        db.commit()

        return jsonify({'data': {}, 'message': 'ok'})


# 在文件末尾新增端点
@portfolios_bp.get('/<int:portfolio_id>/holdings/')
def get_portfolio_holdings(portfolio_id: int):
    """获取组合下所有关联账户的持仓明细"""
    with get_db() as db:
        # 1. 验证组合存在且未删除（家庭维度）
        portfolio = (
            db.query(Portfolio)
            .filter(
                Portfolio.id == portfolio_id,
                Portfolio.is_deleted.is_(False),
                Portfolio.family_id == get_family_id(),
            )
            .first()
        )
        if not portfolio:
            abort(404, '投资组合不存在')

        # 2. 获取关联账户名称列表
        ledger_names = [
            row[0]
            for row in db.query(Ledger.name)
            .filter(Ledger.portfolio_id == portfolio_id, Ledger.family_id == get_family_id())
            .all()
        ]
        if not ledger_names:
            return jsonify({'data': [], 'message': 'ok'})

        # 3. 查询这些账户下的持仓（排除非投资类型）
        positions = (
            db.query(Position)
            .filter(
                Position.account_name.in_(ledger_names),
                Position.asset_type.not_in(EXCLUDED_ASSET_TYPES),
                Position.quantity > 0,
            )
            .all()
        )

        # 4. 查询这些账户下的资产（取 signed_amount > 0 的资产类，负债通常为负不展示）
        assets = (
            db.query(Asset)
            .filter(
                Asset.account_name.in_(ledger_names),
                # 排除负债
                Asset.major_category != 'liability',
            )
            .all()
        )

        # 5. 构造持仓列表（包含市值和盈亏）
        holdings = []
        for pos in positions:
            market_value = Money.multiply_price_quantity(pos.current_price, pos.quantity)
            pnl = Money.multiply_price_quantity(pos.current_price - pos.avg_price, pos.quantity) if pos.avg_price else 0

            holdings.append(
                {
                    'id': pos.id,
                    'symbol': pos.symbol,
                    'name': pos.name,
                    'type': pos.asset_type,
                    'type_label': TYPE_LABELS.get(pos.asset_type, pos.asset_type),
                    'account_name': pos.account_name,
                    'quantity': Money.min_unit_to_shares(pos.quantity),
                    'current_price': Money.cents_to_yuan(pos.current_price),
                    'avg_price': Money.cents_to_yuan(pos.avg_price),
                    'market_value': Money.cents_to_yuan(market_value),
                    'pnl': Money.cents_to_yuan(pnl),
                    'pnl_rate': round((pos.current_price - pos.avg_price) / pos.avg_price * 100, 2)
                    if pos.avg_price
                    else 0.0,
                }
            )

        for asset in assets:
            holdings.append(
                {
                    'id': asset.id + 100000,
                    'symbol': asset.major_category or 'asset',
                    'name': asset.name or asset.major_category,  # 使用 name 字段
                    'type': asset.major_category,
                    'type_label': TYPE_LABELS.get(asset.major_category, asset.major_category or '其他'),
                    'account_name': asset.account_name,
                    'quantity': 1,
                    'current_price': Money.cents_to_yuan(asset.amount),
                    'avg_price': Money.cents_to_yuan(asset.amount),
                    'market_value': Money.cents_to_yuan(asset.amount),
                    'pnl': 0.0,
                    'pnl_rate': 0.0,
                }
            )

        return jsonify({'data': holdings, 'message': 'ok'})
