# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 18:04
# File : views.py
"""
投资组合 API — CRUD + 软删除

组合名唯一（2026-10-30）：同家庭内、未删除的组合之间不允许同名。判据全在
``portfolio_service``（名字归一 + 查重 + 并发撞索引的翻译），本文件只做
「异常 → HTTP」——视图层厚度是冻结基线（#1606），业务规则不下沉就会越线。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from sqlalchemy import update

from app.core.auth import get_family_id, get_owned_or_404
from app.core.database import get_db
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.portfolios.schemas import PortfolioCreate, PortfolioUpdate
from app.services.portfolio_service import (
    PortfolioNameConflict,
    PortfolioNameEmpty,
    build_portfolio_holdings,
    create_portfolio_record,
    portfolio_to_dict,
    update_portfolio_record,
)

portfolios_bp = APIBlueprint('portfolios', __name__, url_prefix='/api/portfolios')

#: 命名类异常的 HTTP 状态：空名 = 入参不合法（422），重名 = 冲突（409）。
#: 用表而不是 if/elif：两个分支共用一个 except，视图里只留一行 abort。
_NAME_ERROR_STATUS = {PortfolioNameEmpty: 422, PortfolioNameConflict: 409}


@portfolios_bp.post('/')
def create_portfolio():
    """创建投资组合（同家庭内重名 → 409）"""
    schema = PortfolioCreate(**(request.get_json() or {}))  # Pydantic 自动校验

    with get_db() as db:
        try:
            portfolio = create_portfolio_record(db, get_family_id(), schema)
        except (PortfolioNameEmpty, PortfolioNameConflict) as e:
            abort(_NAME_ERROR_STATUS[type(e)], description=str(e))
        return jsonify({'data': portfolio_to_dict(portfolio), 'message': 'ok'})


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
        return jsonify({'data': portfolio_to_dict(portfolio), 'message': 'ok'})


@portfolios_bp.patch('/<int:portfolio_id>/')
def update_portfolio(portfolio_id: int):
    """更新投资组合（改名同样要过唯一校验，排除自身）"""
    schema = PortfolioUpdate(**(request.get_json() or {}))

    with get_db() as db:
        portfolio = get_owned_or_404(db, Portfolio, portfolio_id)
        try:
            # 传 ledger_ids 即原子替换关联（#981）；不传 = 本次不动关联
            portfolio = update_portfolio_record(db, portfolio, schema, get_family_id())
        except (PortfolioNameEmpty, PortfolioNameConflict) as e:
            abort(_NAME_ERROR_STATUS[type(e)], description=str(e))
        except ValueError as e:
            # 关联账户不存在 / 越权（校验发生在任何写之前，零部分更新）
            abort(404, str(e))
        return jsonify({'data': portfolio_to_dict(portfolio), 'message': 'ok'})


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
