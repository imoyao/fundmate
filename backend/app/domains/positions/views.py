# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/7 21:19
# File : views.py
"""持仓相关 API."""

from apiflask import APIBlueprint
from flask import abort

from app.core.database import get_db
from app.domains.positions.models import Position
from app.domains.positions.schemas import PositionCreate, PositionOut, PositionUpdate

bp = APIBlueprint('positions', __name__, url_prefix='/api/positions')


@bp.get('/')
@bp.output(PositionOut, status_code=200)
def list_positions():
    """获取所有持仓记录."""
    with get_db() as db:
        positions = db.query(Position).order_by(Position.updated_at.desc()).all()
        return positions


@bp.post('/')
@bp.input(PositionCreate)
@bp.output(PositionOut, status_code=201)
def create_position(json_data):
    """新增一条持仓记录."""
    with get_db() as db:
        position = Position(**json_data.model_dump())
        position.current_price = position.avg_price
        db.add(position)
        db.commit()
        db.refresh(position)
        return position


@bp.patch('/<int:id>')
@bp.input(PositionUpdate)
@bp.output(PositionOut, status_code=200)
def update_position(id, json_data):
    """使用 PATCH 语义仅更新修改过的字段 (例如 current_price)."""
    with get_db() as db:
        position = db.query(Position).filter_by(id=id).first()
        if not position:
            abort(404, description='Position not found')

        # model_dump(exclude_unset=True) 仅返回用户实际发送的字段
        # 例如，用户仅提供 {"current_price": 160.5}，则返回 {"current_price": 160.5}
        update_data = json_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(position, field, value)

        db.commit()
        db.refresh(position)
        return position


@bp.delete('/<int:id>')
@bp.output({}, status_code=204)
def delete_position(id):
    """删除某条持仓记录."""
    with get_db() as db:
        position = db.query(Position).filter_by(id=id).first()
        if not position:
            abort(404, description='Position not found')
        db.delete(position)
        db.commit()
        return ''
