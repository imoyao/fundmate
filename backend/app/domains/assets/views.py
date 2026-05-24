# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 17:22
# File : views.py
# -*- coding: utf-8 -*-
"""通用资产 API."""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.database import get_db
from app.core.enums import ALLOCATION_LABELS, ASSET_CATEGORY_LABELS
from app.core.utils import paginate
from app.domains.assets.models import Asset
from app.domains.assets.schemas import AssetCreate, AssetOut, AssetUpdate

bp = APIBlueprint('assets', __name__, url_prefix='/api/assets')


@bp.get('/')
def list_assets():
    """获取所有通用资产，支持分页和大类筛选."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    major = request.args.get('major_category', '')

    with get_db() as db:
        query = db.query(Asset).order_by(Asset.updated_at.desc())
        # MVP 阶段默认 user_id=1，后续多用户时动态切换
        query = query.filter(Asset.user_id == 1)

        if major:
            query = query.filter(Asset.major_category == major)

        assets, total = paginate(query, page=page, per_page=per_page)

        data = list()
        for asset in assets:
            asset.signed_amount = asset.amount if asset.major_category != 'liability' else -asset.amount
            asset.allocation_label = ALLOCATION_LABELS.get(asset.allocation, asset.allocation or '未配置')
            asset.type_label = ASSET_CATEGORY_LABELS.get(asset.major_category, asset.major_category)
            json_asset = AssetOut.model_validate(asset).model_dump()
            data.append(json_asset)
        return jsonify(
            {
                'data': data,
                'total': total,
                'page': page,
                'per_page': per_page,
                'message': 'ok',
            }
        )


@bp.post('/')
@bp.input(AssetCreate)
def create_asset(json_data):
    """创建一条通用资产记录."""
    with get_db() as db:
        asset = Asset(**json_data.model_dump())
        asset.user_id = 1  # MVP 默认
        db.add(asset)
        db.commit()
        db.refresh(asset)
        asset.allocation_label = ALLOCATION_LABELS.get(asset.allocation, asset.allocation or '未配置')
        asset.signed_amount = asset.amount if asset.major_category != 'liability' else -asset.amount
        asset.type_label = ASSET_CATEGORY_LABELS.get(asset.major_category, asset.major_category)
        return jsonify({'data': AssetOut.model_validate(asset).model_dump(), 'message': 'ok'})


@bp.patch('/<int:id>/')
@bp.input(AssetUpdate)
def update_asset(id, json_data):
    """PATCH 语义更新通用资产."""
    with get_db() as db:
        asset = db.query(Asset).filter_by(id=id).first()
        if not asset:
            abort(404, description='资产不存在')

        update_data = json_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(asset, field, value)

        db.commit()
        db.refresh(asset)
        asset.allocation_label = ALLOCATION_LABELS.get(asset.allocation, asset.allocation or '未配置')
        asset.type_label = ASSET_CATEGORY_LABELS.get(asset.major_category, asset.major_category)
        asset.signed_amount = asset.amount if asset.major_category != 'liability' else -asset.amount
        return jsonify({'data': AssetOut.model_validate(asset).model_dump(), 'message': 'ok'})


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
