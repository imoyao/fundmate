# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 17:22
# File : views.py
# -*- coding: utf-8 -*-
"""通用资产 API."""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.constants import ALLOCATION_LABELS, ASSET_CATEGORY_LABELS, CURRENT_USER_ID
from app.core.database import get_db
from app.core.money import Money
from app.core.utils import paginate
from app.domains.assets.models import Asset
from app.domains.assets.schemas import AssetCreate, AssetOut, AssetUpdate
from app.domains.ledgers.models import Ledger

bp = APIBlueprint('assets', __name__, url_prefix='/api/assets')


def _enrich_asset_dict(asset: Asset) -> dict:
    """为 Asset 对象附加计算字段，并将金额转为元返回"""
    amount_yuan = Money.cents_to_yuan(asset.amount)
    asset.signed_amount = amount_yuan if asset.major_category != 'liability' else -amount_yuan
    asset.allocation_label = ALLOCATION_LABELS.get(asset.allocation, asset.allocation or '未配置')
    asset.type_label = ASSET_CATEGORY_LABELS.get(asset.major_category, asset.major_category)
    asset.amount = amount_yuan
    return AssetOut.model_validate(asset).model_dump()


@bp.get('/')
def list_assets():
    """获取所有通用资产，支持分页、大类筛选、排除指定类型."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    major = request.args.get('major_category', '')
    exclude = request.args.get('exclude', '')

    with get_db() as db:
        query = db.query(Asset).order_by(Asset.updated_at.desc())
        query = query.filter(Asset.user_id == CURRENT_USER_ID)

        if major:
            query = query.filter(Asset.major_category == major)

        # 新增：排除指定的大类
        if exclude:
            exclude_list = [e.strip() for e in exclude.split(',') if e.strip()]
            if exclude_list:
                query = query.filter(Asset.major_category.not_in(exclude_list))

        assets, total = paginate(query, page=page, per_page=per_page)
        data = [_enrich_asset_dict(a) for a in assets]
        return jsonify({'data': data, 'total': total, 'page': page, 'per_page': per_page, 'message': 'ok'})


@bp.post('/')
@bp.input(AssetCreate)
def create_asset(json_data):
    data = json_data.model_dump()
    data['amount'] = Money.yuan_to_cents(data.get('amount', 0))

    # 如果传了 ledger_id，确保 account_name 快照正确
    if data.get('ledger_id'):
        with get_db() as db:
            ledger = db.query(Ledger).filter_by(id=data['ledger_id']).first()
            if ledger:
                # 🔥 修复：新增防御性校验，禁止将固定资产挂载到银行账户
                if ledger.ledger_type == 'bank' and data.get('major_category') in ('fixed', 'real_estate', 'vehicle'):
                    return jsonify(
                        {
                            'data': None,
                            'message': '错误：固定资产（房产/车辆/固定设备）不能绑定到银行账户下，请选择「实物资产」账户',
                        }
                    ), 400

                data['account_name'] = ledger.name

    with get_db() as db:
        asset = Asset(**data)
        asset.user_id = CURRENT_USER_ID
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return jsonify({'data': _enrich_asset_dict(asset), 'message': 'ok'})


@bp.patch('/<int:id>/')
@bp.input(AssetUpdate)
def update_asset(id, json_data):
    with get_db() as db:
        asset = db.query(Asset).filter_by(id=id).first()
        if not asset:
            abort(404, description='资产不存在')

        update_data = json_data.model_dump(exclude_unset=True)

        # 🔥 修复：新增防御性校验，禁止把已有的资产迁移到错误的账户
        if 'ledger_id' in update_data and update_data['ledger_id'] is not None:
            new_ledger = db.query(Ledger).filter_by(id=update_data['ledger_id']).first()
            if not new_ledger:
                abort(404, description='关联账户不存在')

            # 如果更新请求里没有传 major_category，则沿用资产原本的 major_category
            target_major = update_data.get('major_category', asset.major_category)

            if new_ledger.ledger_type == 'bank' and target_major in ('fixed', 'real_estate', 'vehicle'):
                return jsonify(
                    {'data': None, 'message': '错误：固定资产不能迁移到银行账户下，请选择「实物资产」账户'}
                ), 400

        if 'amount' in update_data:
            update_data['amount'] = Money.yuan_to_cents(update_data['amount'])
        for field, value in update_data.items():
            setattr(asset, field, value)
        db.commit()
        db.refresh(asset)
        return jsonify({'data': _enrich_asset_dict(asset), 'message': 'ok'})


@bp.delete('/<int:id>/')
def delete_asset(id):
    """删除一条通用资产."""
    with get_db() as db:
        asset = db.query(Asset).filter_by(id=id).first()
        if not asset:
            abort(404, description='资产不存在')
        db.delete(asset)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})
