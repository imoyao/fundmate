# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : views.py
"""资金容器 API — 基本 CRUD"""

import json

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.constants import ALLOCATION_LABELS, CURRENT_USER_ID, LEDGER_TYPE_LABELS
from app.core.database import get_db
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position

ledgers_bp = APIBlueprint('ledgers', __name__, url_prefix='/api/ledgers')


def _ledger_to_dict(ledger: Ledger) -> dict:
    """将 Ledger 模型实例转为字典"""
    # 处理 fee_config：数据库中是字符串，需要反序列化
    fee_config = None
    if ledger.fee_config:
        try:
            fee_config = json.loads(ledger.fee_config)
        except (json.JSONDecodeError, TypeError):
            fee_config = None

    return {
        'id': ledger.id,
        'name': ledger.name,
        'ledger_type': ledger.ledger_type,
        'default_allocation': ledger.default_allocation,
        'default_allocation_label': ALLOCATION_LABELS.get(ledger.default_allocation, '未配置'),
        'fee_config': fee_config,
        'notes': ledger.notes,
        'portfolio_id': ledger.portfolio_id,
        'linked_cash_ledger_id': ledger.linked_cash_ledger_id,
        'created_at': ledger.created_at.isoformat() if ledger.created_at else None,
        'updated_at': ledger.updated_at.isoformat() if ledger.updated_at else None,
    }


@ledgers_bp.get('/overview/')
def get_ledgers_overview():
    """获取账户资金全景：按类型分组的市值、负债、净资产、已删除账户"""

    with get_db() as db:
        ledgers = db.query(Ledger).all()
        positions = db.query(Position).all()
        assets = db.query(Asset).filter(Asset.user_id == CURRENT_USER_ID).all()

        # 已知账户名及其类型
        known_names = {led.name for led in ledgers}
        name_to_type = {led.name: led.ledger_type for led in ledgers}

        # 按账户名汇总市值
        account_totals: dict[str, dict] = {}  # account_name -> {type, total}
        for pos in positions:
            acc = pos.account_name or '未指定账户'
            if acc not in account_totals:
                account_totals[acc] = {
                    'type': name_to_type.get(acc, 'deleted' if acc not in known_names else 'general'),
                    'total': 0.0,
                }
            value = (pos.quantity or 0) * (pos.current_price or 0)
            account_totals[acc]['total'] += value

        for asset in assets:
            acc = asset.account_name or '未指定账户'
            if acc not in account_totals:
                account_totals[acc] = {
                    'type': name_to_type.get(acc, 'deleted' if acc not in known_names else 'general'),
                    'total': 0.0,
                }
            if asset.major_category != 'liability':
                value = asset.amount or 0
                account_totals[acc]['total'] += value

        # 按类型分组汇总
        type_groups: dict[str, dict] = {}
        for acc, info in account_totals.items():
            t = info['type']
            if t not in type_groups:
                type_groups[t] = {'type': t, 'label': _ledger_type_label(t), 'count': 0, 'total': 0.0}
            type_groups[t]['count'] += 1
            type_groups[t]['total'] += info['total']

        # 负债总额
        liability_total = sum((a.amount or 0) for a in assets if a.major_category == 'liability')

        total_assets = sum(g['total'] for g in type_groups.values())
        net_worth = total_assets - liability_total

        # 排序：stock, fund, cash, general, family, deleted 在最后
        order = ['stock', 'fund', 'cash', 'general', 'family', 'deleted']
        sorted_groups = [type_groups[t] for t in order if t in type_groups]

        # 为“已删除”分组补充特殊 label
        for g in sorted_groups:
            if g['type'] == 'deleted':
                g['label'] = '已删除账户'

        return jsonify(
            {
                'data': {
                    'groups': sorted_groups,
                    'liability_total': round(liability_total, 2),
                    'net_worth': round(net_worth, 2),
                },
                'message': 'ok',
            }
        )


def _ledger_type_label(ledger_type: str) -> str:
    """账户类型中文映射"""
    return LEDGER_TYPE_LABELS.get(ledger_type, ledger_type)


@ledgers_bp.post('/')
def create_ledger():
    """创建新账户"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        abort(400, '账户名称不能为空')

    ledger_type = data.get('ledger_type', 'stock')
    linked_cash_id = data.get('linked_cash_ledger_id')

    # 校验关联的现金账户
    if linked_cash_id is not None:
        if ledger_type not in ('stock', 'fund'):
            return jsonify({'data': None, 'message': '只有证券账户或基金平台可以关联现金账户'}), 400
        with get_db() as db:
            cash_ledger = db.query(Ledger).filter_by(id=linked_cash_id, ledger_type='cash').first()
            if not cash_ledger:
                return jsonify({'data': None, 'message': '关联的现金账户不存在或类型不是现金账户'}), 400

    with get_db() as db:
        ledger = Ledger(
            name=name,
            ledger_type=ledger_type,
            default_allocation=data.get('default_allocation', 'longterm'),
            notes=data.get('notes', ''),
            portfolio_id=data.get('portfolio_id'),
            linked_cash_ledger_id=linked_cash_id,
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
        name = data.get('name')
        if name is not None:
            name = name.strip()
            if not name:
                return jsonify({'data': None, 'message': '账户名称不能为空'}), 400
            ledger.name = name

        ledger_type = data.get('ledger_type')
        if ledger_type is not None:
            ledger.ledger_type = ledger_type

        default_allocation = data.get('default_allocation')
        if default_allocation is not None:
            ledger.default_allocation = default_allocation

        notes = data.get('notes')
        if notes is not None:
            ledger.notes = notes

        # 更新 portfolio_id（允许设置为 None）
        if 'portfolio_id' in data:
            ledger.portfolio_id = data['portfolio_id']

        # 更新 linked_cash_ledger_id（允许设置为 None）
        if 'linked_cash_ledger_id' in data:
            linked_cash_id = data['linked_cash_ledger_id']
            # 如果是设置非空值，必须校验
            if linked_cash_id is not None:
                current_type = ledger_type if ledger_type is not None else ledger.ledger_type
                if current_type not in ('stock', 'fund'):
                    return jsonify({'data': None, 'message': '只有证券账户或基金平台可以关联现金账户'}), 400
                cash_ledger = db.query(Ledger).filter_by(id=linked_cash_id, ledger_type='cash').first()
                if not cash_ledger:
                    return jsonify({'data': None, 'message': '关联的现金账户不存在或类型不是现金账户'}), 400
            # 无论值是否为 None，均更新
            ledger.linked_cash_ledger_id = linked_cash_id

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
                return jsonify({'data': None, 'message': 'fee_config 格式无效'}), 400

        db.commit()
        db.refresh(ledger)
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.delete('/<int:ledger_id>/')
def delete_ledger(ledger_id: int):
    """删除账户，可选择同时删除关联持仓"""
    delete_positions = request.args.get('delete_positions', 'false').lower() == 'true'

    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')

        if delete_positions:
            # 级联删除关联持仓和资产
            db.query(Position).filter(Position.account_name == ledger.name).delete()
            db.query(Asset).filter(Asset.account_name == ledger.name, Asset.user_id == CURRENT_USER_ID).delete()
        else:
            # 检查是否存在关联持仓
            position_count = db.query(Position).filter(Position.account_name == ledger.name).count()
            if position_count > 0:
                return jsonify(
                    {
                        'data': None,
                        'message': f'无法删除：账户「{ledger.name}」下还有 {position_count} 笔持仓，请先清空或勾选"同时删除持仓"',
                    }
                ), 400

        db.delete(ledger)
        db.commit()
        return jsonify({'data': {}, 'message': 'ok'})


@ledgers_bp.post('/<int:ledger_id>/migrations/')
def migrate_positions(ledger_id: int):
    data = request.get_json() or {}
    target_id = data.get('target_ledger_id')
    if not target_id:
        return jsonify({'data': None, 'message': '缺少 target_ledger_id'}), 400

    with get_db() as db:
        source = db.query(Ledger).get(ledger_id)
        target = db.query(Ledger).get(target_id)
        if not source or not target:
            abort(404, '账户不存在')  # 404 可以保留 abort

        if source.ledger_type != target.ledger_type:
            return jsonify({'data': None, 'message': '只能迁移到同类型账户'}), 400

        position_count = (
            db.query(Position).filter(Position.account_name == source.name).update({Position.account_name: target.name})
        )

        asset_count = (
            db.query(Asset)
            .filter(Asset.account_name == source.name, Asset.user_id == CURRENT_USER_ID)
            .update({Asset.account_name: target.name})
        )

        db.commit()

        return jsonify(
            {
                'data': {
                    'position_count': position_count,
                    'asset_count': asset_count,
                    'total': position_count + asset_count,
                },
                'message': f'已将 {position_count + asset_count} 项迁移至「{target.name}」',
            }
        )
