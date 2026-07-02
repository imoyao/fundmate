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
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.positions.views import enrich_position_dict
from app.domains.transactions.models import Transaction
from app.services.ledger_service import LedgerService

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
    with get_db() as db:
        data = LedgerService.get_overview_stats(db)
        return jsonify({'data': data, 'message': 'ok'})


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

    ledger_type = data.get('ledger_type', 'bank')
    linked_cash_id = data.get('linked_cash_ledger_id')

    # 校验关联的现金账户
    if linked_cash_id is not None:
        if ledger_type not in ('stock', 'fund'):
            return jsonify({'data': None, 'message': '只有证券账户或基金平台可以关联现金账户'}), 400
        with get_db() as db:
            cash_ledger = db.query(Ledger).filter_by(id=linked_cash_id, ledger_type='bank').first()
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
    """获取所有账户（含摘要统计）"""
    with get_db() as db:
        ledgers = db.query(Ledger).order_by(Ledger.created_at.asc()).all()
        result = []
        for ledger in ledgers:
            item = _ledger_to_dict(ledger)
            # 附加摘要数据
            item['total_market_value'] = 0.0
            item['pnl'] = 0.0
            item['position_count'] = 0
            item['cash_balance'] = 0.0  # 统一初始化 cash_balance

            if ledger.ledger_type in ('stock', 'fund'):
                stats = LedgerService.get_portfolio_stats(db, ledger.id)
                item['total_market_value'] = stats['total_market_value']
                item['pnl'] = stats['position_pnl']
                item['position_count'] = stats['position_count']
                if ledger.ledger_type == 'stock':
                    item['cash_balance'] = LedgerService.get_cash_balance(db, ledger)

            elif ledger.ledger_type == 'bank':
                stats = LedgerService.get_bank_stats(db, ledger.id)
                item['total_market_value'] = stats['total_market_value']
                item['pnl'] = 0  # bank 不直接显示盈亏
                item['position_count'] = stats.get('position_count', 0)
                item['cash_balance'] = stats['current_balance']
                # 🔥 负债必须从 stats 拿，视图层不做 SQL 聚合
                item['linked_liability'] = stats.get('linked_liability', 0.0)

                # 🔥 货基统计必须在这里写上
                money_fund_stats = LedgerService.get_money_fund_stats(db, ledger.id)
                item['money_fund_amount'] = money_fund_stats.get('money_fund_amount', 0.0)
                item['money_fund_ratio'] = money_fund_stats.get('money_fund_ratio', 0.0)

            elif ledger.ledger_type == 'property':
                stats = LedgerService.get_property_stats(db, ledger.id)
                item['total_market_value'] = stats['total_market_value']
                item['position_count'] = stats['asset_count']
                item['asset_count'] = stats['asset_count']
                item['cash_balance'] = 0.0

            result.append(item)

        return jsonify({'data': result, 'message': 'ok'})


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
                cash_ledger = db.query(Ledger).filter_by(id=linked_cash_id, ledger_type='bank').first()
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
            # 级联删除关联持仓和资产（基于 ledger_id）
            db.query(Position).filter(Position.ledger_id == ledger_id).delete()
            db.query(Asset).filter(Asset.ledger_id == ledger_id, Asset.user_id == CURRENT_USER_ID).delete()
        else:
            # 检查是否存在关联持仓
            position_count = db.query(Position).filter(Position.ledger_id == ledger_id).count()
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
            return jsonify({'data': None, 'message': '账户不存在'}), 404

        if source.ledger_type != target.ledger_type:
            return jsonify({'data': None, 'message': '只能迁移到同类型账户'}), 400

        # 迁移持仓：更新 ledger_id 和 account_name 快照
        position_count = (
            db.query(Position)
            .filter(Position.ledger_id == source.id)
            .update(
                {
                    Position.ledger_id: target.id,
                    Position.account_name: target.name,
                }
            )
        )

        # 迁移资产
        asset_count = (
            db.query(Asset)
            .filter(Asset.ledger_id == source.id, Asset.user_id == CURRENT_USER_ID)
            .update(
                {
                    Asset.ledger_id: target.id,
                    Asset.account_name: target.name,
                }
            )
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


# ────────────────────────────── 账户详情页专用接口 ──────────────────────────────


@ledgers_bp.get('/<int:ledger_id>/summary/')
def get_ledger_summary(ledger_id: int):
    """获取单账户概览卡片数据，根据账户类型返回不同指标"""
    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')

        data = {'ledger_type': ledger.ledger_type, 'ledger_name': ledger.name, 'daily_pnl': None}

        if ledger.ledger_type in ('stock', 'fund'):
            stats = LedgerService.get_portfolio_stats(db, ledger.id)
            data.update(stats)
            data['cumulative_return'] = LedgerService.get_cumulative_return(db, ledger.id)

            if ledger.ledger_type == 'stock':
                data['cash_balance'] = LedgerService.get_cash_balance(db, ledger)
            elif ledger.ledger_type == 'fund':
                # FIX-3: 传入 ledger.id 而非 ledger.name
                money_fund = LedgerService.get_money_fund_stats(db, ledger.id)
                data.update(money_fund)

        elif ledger.ledger_type == 'bank':
            data.update(LedgerService.get_bank_stats(db, ledger.id))

        elif ledger.ledger_type == 'property':
            data.update(LedgerService.get_property_stats(db, ledger.id))

        return jsonify({'data': data, 'message': 'ok'})


@ledgers_bp.get('/<int:ledger_id>/positions/')
def get_ledger_positions(ledger_id: int):
    """获取账户持仓明细，支持分页"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            return jsonify({'data': None, 'message': '账户不存在'}), 404
        items, total = LedgerService.get_positions_paginated(db, ledger.id, page, per_page)
        return jsonify(
            {
                'data': {
                    'items': items,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                },
                'message': 'ok',
            }
        )


@ledgers_bp.get('/<int:ledger_id>/transactions/')
def get_ledger_transactions(ledger_id: int):
    """获取账户交易记录，支持分页"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            return jsonify({'data': None, 'message': '账户不存在'}), 404
        items, total = LedgerService.get_transactions_paginated(db, ledger.id, page, per_page)
        return jsonify(
            {
                'data': {
                    'items': items,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                },
                'message': 'ok',
            }
        )


@ledgers_bp.patch('/<int:ledger_id>/positions/<int:position_id>/')
def update_ledger_position(ledger_id: int, position_id: int):
    """编辑账户内持仓（仅允许修改配置目标、现价、备注等）"""
    data = request.get_json() or {}
    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        pos = (
            db.query(Position)
            .filter(
                Position.id == position_id,
                Position.ledger_id == ledger_id,  # 外键过滤
            )
            .first()
        )
        if not pos:
            abort(404, '持仓不存在或不属于该账户')

        if 'allocation' in data:
            pos.allocation = data['allocation']
        if 'current_price' in data:
            pos.current_price = Money.yuan_to_cents(data['current_price'])
        if 'notes' in data:
            pos.notes = data['notes']
        db.commit()
        db.refresh(pos)
        return jsonify({'data': enrich_position_dict(pos), 'message': 'ok'})


@ledgers_bp.delete('/<int:ledger_id>/positions/<int:position_id>/')
def delete_ledger_position(ledger_id: int, position_id: int):
    """删除账户内持仓"""
    delete_txns = request.args.get('delete_transactions', 'false').lower() == 'true'
    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        pos = (
            db.query(Position)
            .filter(
                Position.id == position_id,
                Position.ledger_id == ledger.id,
            )
            .first()
        )
        if not pos:
            abort(404, '持仓不存在或不属于该账户')

        if delete_txns:
            db.query(Transaction).filter(
                Transaction.position_id == position_id,
                Transaction.ledger_id == ledger.id,
            ).delete()
        db.delete(pos)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


@ledgers_bp.patch('/<int:ledger_id>/transactions/<int:transaction_id>/')
def update_ledger_transaction(ledger_id: int, transaction_id: int):
    """编辑账户内交易（仅允许修改手续费、备注）"""
    data = request.get_json() or {}
    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        txn = (
            db.query(Transaction)
            .filter(
                Transaction.id == transaction_id,
                Transaction.ledger_id == ledger.id,
            )
            .first()
        )
        if not txn:
            abort(404, '交易不存在或不属于该账户')

        if 'fee' in data:
            txn.fee = Money.yuan_to_cents(data['fee'])
        if 'notes' in data:
            txn.notes = data['notes']
        # 禁止修改数量、价格、金额

        db.commit()
        return jsonify(
            {
                'data': {'id': txn.id, 'fee': Money.cents_to_yuan(txn.fee), 'notes': txn.notes},
                'message': 'ok',
            }
        )


@ledgers_bp.delete('/<int:ledger_id>/transactions/<int:transaction_id>/')
def delete_ledger_transaction(ledger_id: int, transaction_id: int):
    """删除账户内交易"""
    with get_db() as db:
        ledger = db.query(Ledger).get(ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        txn = (
            db.query(Transaction)
            .filter(
                Transaction.id == transaction_id,
                Transaction.ledger_id == ledger.id,
            )
            .first()
        )
        if not txn:
            abort(404, '交易不存在或不属于该账户')
        db.delete(txn)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})
