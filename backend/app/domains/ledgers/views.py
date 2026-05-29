# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : views.py
"""资金容器 API — 基本 CRUD"""

import json

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.constants import ALLOCATION_LABELS
from app.core.database import get_db
from app.domains.ledgers.models import Ledger

ledgers_bp = APIBlueprint('ledgers', __name__, url_prefix='/api/ledgers')


def _ledger_to_dict(ledger: Ledger) -> dict:
    """将 Ledger 模型实例转为字典"""
    # 处理 fee_config：数据库中是字符串，需要反序列化
    fee_config = None
    if ledger.fee_config:
        try:
            fee_config = json.loads(ledger.fee_config)
        except (json.JSONDecodeError, TypeError):
            fee_config = None  # 非法 JSON 视为空

    return {
        'id': ledger.id,
        'name': ledger.name,
        'ledger_type': ledger.ledger_type,
        'default_allocation': ledger.default_allocation,
        'default_allocation_label': ALLOCATION_LABELS.get(ledger.default_allocation, '未配置'),
        'fee_config': fee_config,
        'notes': ledger.notes,
        'created_at': ledger.created_at.isoformat() if ledger.created_at else None,
        'updated_at': ledger.updated_at.isoformat() if ledger.updated_at else None,
    }


@ledgers_bp.post('/')
def create_ledger():
    """创建新账户"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        abort(400, '账户名称不能为空')

    with get_db() as db:
        ledger = Ledger(
            name=name,
            ledger_type=data.get('ledger_type', 'general'),
            default_allocation=data.get('default_allocation', 'longterm'),
            notes=data.get('notes', ''),
        )

        # 处理 fee_config JSON 字段
        fee_config = data.get('fee_config')
        if fee_config is not None:
            # 前端传入的可能是一个 dict，直接序列化；也可以是字符串
            if isinstance(fee_config, dict):
                ledger.fee_config = json.dumps(fee_config, ensure_ascii=False)
            elif isinstance(fee_config, str):
                ledger.fee_config = fee_config  # 信任前端传的 JSON 字符串
            else:
                abort(400, 'fee_config 格式无效')
        # 未传则保持 None

        db.add(ledger)
        db.commit()
        db.refresh(ledger)

        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.get('/')
def list_ledgers():
    """获取所有账户"""
    with get_db() as db:
        ledgers = db.query(Ledger).order_by(Ledger.created_at.asc()).all()
        return jsonify({'data': [_ledger_to_dict(leg) for leg in ledgers], 'message': 'ok'})


@ledgers_bp.get('/<int:ledger_id>/')
def get_ledger(ledger_id: int):
    """获取单个账户详情"""
    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.patch('/<int:ledger_id>/')
def update_ledger(ledger_id: int):
    """更新账户信息"""
    data = request.get_json() or {}
    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')

        # 更新基本字段
        if 'name' in data:
            name = data['name'].strip()
            if not name:
                abort(400, '账户名称不能为空')
            ledger.name = name
        if 'ledger_type' in data:
            ledger.ledger_type = data['ledger_type']
        if 'default_allocation' in data:
            ledger.default_allocation = data['default_allocation']
        if 'notes' in data:
            ledger.notes = data['notes']

        # 更新 fee_config
        if 'fee_config' in data:
            fee_config = data['fee_config']
            if fee_config is None:
                ledger.fee_config = None
            elif isinstance(fee_config, dict):
                ledger.fee_config = json.dumps(fee_config, ensure_ascii=False)
            elif isinstance(fee_config, str):
                ledger.fee_config = fee_config
            else:
                abort(400, 'fee_config 格式无效')

        db.commit()
        db.refresh(ledger)
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.delete('/<int:ledger_id>/')
def delete_ledger(ledger_id: int):
    """删除账户"""
    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        db.delete(ledger)
        db.commit()
        return jsonify({'data': {}, 'message': 'ok'})
