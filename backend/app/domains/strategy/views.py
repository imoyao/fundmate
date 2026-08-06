# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 19:58
# File : views.py
# -*- coding: utf-8 -*-
"""
策略标签 API — CRUD + 持仓绑定/解绑
"""

from apiflask import APIBlueprint
from flask import abort, jsonify

from app.core.auth import get_family_id, get_owned_or_404
from app.core.constants import TYPE_LABELS
from app.core.database import get_db
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.positions.models import Position
from app.domains.strategy.models import PositionStrategyTag, StrategyTag
from app.domains.strategy.schemas import StrategyTagCreate

strategy_bp = APIBlueprint('strategy', __name__, url_prefix='/api/strategy')


def _tag_to_dict(tag: StrategyTag) -> dict:
    return {
        'id': tag.id,
        'name': tag.name,
        'created_at': tag.created_at.isoformat() if tag.created_at else None,
    }


@strategy_bp.get('/overview/')
def get_strategy_overview():
    """返回策略视图全部数据：持仓、资产、标签、关联（一个请求）"""
    with get_db() as db:
        # 1. 所有持仓（只取必要列），按家庭隔离
        positions = (
            db.query(
                Position.id,
                Position.symbol,
                Position.name,
                Position.asset_type,
                Position.quantity,
                Position.current_price,
                Position.avg_price,
                Position.account_name,
            )
            .filter(Position.family_id == get_family_id(), Position.quantity > 0)
            .all()
        )

        # 2. 所有资产（排除负债）
        assets = (
            db.query(
                Asset.id,
                Asset.major_category,
                Asset.name,
                Asset.amount,
                Asset.account_name,
            )
            .filter(
                Asset.family_id == get_family_id(),
                Asset.major_category != 'liability',
                Asset.amount > 0,
            )
            .all()
        )

        # 3. 所有策略标签（家庭隔离）
        tags = (
            db.query(StrategyTag)
            .filter(StrategyTag.family_id == get_family_id())
            .order_by(StrategyTag.created_at.asc())
            .all()
        )

        # 4. 所有持仓-标签关联，构建映射
        rows = (
            db.query(PositionStrategyTag.position_id, StrategyTag.name)
            .join(StrategyTag, PositionStrategyTag.strategy_tag_id == StrategyTag.id)
            .filter(StrategyTag.family_id == get_family_id())
            .all()
        )
        relations: dict[int, list[str]] = {}
        for pos_id, tag_name in rows:
            relations.setdefault(pos_id, []).append(tag_name)

    # 5. 构造 holdings 列表
    holdings = []
    for p in positions:
        holdings.append(
            {
                'id': p.id,
                'symbol': p.symbol,
                'name': p.name,
                'type': p.asset_type or p.type,
                'type_label': TYPE_LABELS.get(p.asset_type or p.type, p.asset_type or p.type),
                'quantity': Money.min_unit_to_shares(p.quantity),
                'current_price': Money.cents_to_yuan(p.current_price),
                'avg_price': Money.cents_to_yuan(p.avg_price),
                'account_name': p.account_name,
            }
        )
    for a in assets:
        holdings.append(
            {
                'id': a.id + 100000,  # 资产 ID 偏移避免冲突
                'symbol': a.major_category or 'asset',
                'name': a.name or a.major_category,
                'type': a.major_category,
                'type_label': TYPE_LABELS.get(a.major_category, a.major_category or '其他'),
                'quantity': 1,
                'current_price': a.amount,
                'avg_price': a.amount,
                'account_name': a.account_name,
            }
        )

    tag_list = [{'id': t.id, 'name': t.name} for t in tags]

    return jsonify(
        {
            'data': {
                'holdings': holdings,
                'tags': tag_list,
                'relations': relations,
            },
            'message': 'ok',
        }
    )


@strategy_bp.get('/')
def list_tags():
    """获取所有策略标签"""
    with get_db() as db:
        tags = (
            db.query(StrategyTag)
            .filter(StrategyTag.family_id == get_family_id())
            .order_by(StrategyTag.created_at.asc())
            .all()
        )
        return jsonify({'data': [_tag_to_dict(t) for t in tags], 'message': 'ok'})


@strategy_bp.post('/')
@strategy_bp.input(StrategyTagCreate)  # 自动校验，失败返回 422
def create_tag(json_data: StrategyTagCreate):  # 类型注解为模型实例
    with get_db() as db:
        existing = (
            db.query(StrategyTag)
            .filter(StrategyTag.name == json_data.name, StrategyTag.family_id == get_family_id())
            .first()
        )
        if existing:
            return jsonify({'data': None, 'message': '标签名称已存在'}), 409

        tag = StrategyTag(name=json_data.name, family_id=get_family_id())
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return jsonify({'data': _tag_to_dict(tag), 'message': 'ok'})


@strategy_bp.delete('/<int:tag_id>/')
def delete_tag(tag_id: int):
    """删除策略标签（级联删除关联）"""
    with get_db() as db:
        tag = get_owned_or_404(db, StrategyTag, tag_id)
        if not tag:
            abort(404, '标签不存在')
        db.delete(tag)
        db.commit()
        return jsonify({'data': {}, 'message': 'ok'})


@strategy_bp.post('/<int:tag_id>/positions/<int:position_id>/')
def bind_position_tag(tag_id: int, position_id: int):
    """为持仓绑定策略标签"""
    with get_db() as db:
        # 检查标签和持仓存在性（家庭维度）
        get_owned_or_404(db, StrategyTag, tag_id)
        get_owned_or_404(db, Position, position_id)
        # 持仓存在性由 FK 自动校验，但可提前给出友好提示
        existing = (
            db.query(PositionStrategyTag)
            .filter(
                PositionStrategyTag.position_id == position_id,
                PositionStrategyTag.strategy_tag_id == tag_id,
            )
            .first()
        )
        if existing:
            abort(409, '该持仓已绑定此标签')

        bind = PositionStrategyTag(position_id=position_id, strategy_tag_id=tag_id)
        db.add(bind)
        db.commit()
        return jsonify({'data': {}, 'message': 'ok'})


@strategy_bp.delete('/<int:tag_id>/positions/<int:position_id>/')
def unbind_position_tag(tag_id: int, position_id: int):
    """为持仓解绑策略标签"""
    with get_db() as db:
        # 先校验标签/持仓归属（家庭维度），避免越权解绑
        get_owned_or_404(db, StrategyTag, tag_id)
        get_owned_or_404(db, Position, position_id)
        bind = (
            db.query(PositionStrategyTag)
            .filter(
                PositionStrategyTag.position_id == position_id,
                PositionStrategyTag.strategy_tag_id == tag_id,
            )
            .first()
        )
        if not bind:
            abort(404, '绑定关系不存在')
        db.delete(bind)
        db.commit()
        return jsonify({'data': {}, 'message': 'ok'})


@strategy_bp.get('/relations/')
def get_all_position_tags():
    """获取全部持仓的策略标签关联，返回 {position_id: [tag_name, ...]}"""
    with get_db() as db:
        rows = (
            db.query(PositionStrategyTag.position_id, StrategyTag.name)
            .join(StrategyTag, PositionStrategyTag.strategy_tag_id == StrategyTag.id)
            .filter(StrategyTag.family_id == get_family_id())
            .all()
        )
        result: dict[int, list[str]] = {}
        for pos_id, tag_name in rows:
            result.setdefault(pos_id, []).append(tag_name)
        return jsonify({'data': result, 'message': 'ok'})
