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
from sqlalchemy.exc import IntegrityError

from app.core.auth import get_family_id, get_owned_or_404
from app.core.database import get_db
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.portfolios.schemas import PortfolioCreate, PortfolioUpdate
from app.services.portfolio_service import (
    PortfolioNameConflict,
    PortfolioNameEmpty,
    assert_portfolio_name_available,
    build_portfolio_holdings,
    replace_portfolio_ledger_links,
)

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
    """创建投资组合

    重名一律 409（同家庭内、未删除的组合之间）：卡片标题就是组合名，两个同名卡片
    无法区分。校验在写库**之前**，且库层还有 ``uq_portfolios_family_name_alive``
    部分唯一索引兜住并发/旁路写入——这里捕获它并转成同一句 409，而不是 500。
    """
    data = request.get_json() or {}
    schema = PortfolioCreate(**data)  # Pydantic 自动校验

    with get_db() as db:
        try:
            name = assert_portfolio_name_available(db, get_family_id(), schema.name)
        except PortfolioNameEmpty as e:
            abort(422, description=str(e))
        except PortfolioNameConflict as e:
            abort(409, description=str(e))

        try:
            portfolio = Portfolio(
                name=name,
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
        except IntegrityError as e:
            db.rollback()
            # 走到这里只有一种可能：两个请求同时通过了上面的查询校验（或旁路写入）。
            # 唯一索引是最终判据，把它翻译成与前面一致的 409，别让用户看到 500。
            logger.warning(f'组合创建触发唯一索引冲突（并发重名）: {e}')
            abort(409, description=f'组合「{name}」已存在，请换一个名字')
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
    """更新投资组合

    改名同样要过唯一校验（排除自身，否则「保存时不改名字」会被自己判成重名）。
    只传 description 等其它字段时不做名字检查。
    """
    data = request.get_json() or {}
    schema = PortfolioUpdate(**data)

    with get_db() as db:
        portfolio = get_owned_or_404(db, Portfolio, portfolio_id)

        # 仅更新传入的字段（None = 未传，不动）
        for field in ('description', 'purpose', 'target_return', 'target_amount', 'target_date', 'benchmark'):
            value = getattr(schema, field)
            if value is not None:
                setattr(portfolio, field, value)

        if schema.name is not None:
            try:
                portfolio.name = assert_portfolio_name_available(
                    db, get_family_id(), schema.name, exclude_id=portfolio_id
                )
            except PortfolioNameEmpty as e:
                abort(422, description=str(e))
            except PortfolioNameConflict as e:
                abort(409, description=str(e))

        # 账户关联原子替换（#981）：diff/归属校验/批量写在 service，视图只做「异常 → HTTP」
        if schema.ledger_ids is not None:
            try:
                replace_portfolio_ledger_links(db, portfolio_id, get_family_id(), schema.ledger_ids)
            except ValueError as e:
                abort(404, str(e))

        try:
            db.flush()
        except IntegrityError as e:
            # 与创建路径同理：并发改名撞唯一索引时给 409，别让用户看到 500
            db.rollback()
            logger.warning(f'组合改名触发唯一索引冲突（并发重名）: {e}')
            abort(409, description=f'组合「{schema.name}」已存在，请换一个名字')
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
