# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 17:22
# File : views.py
# -*- coding: utf-8 -*-
"""通用资产 API."""

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from sqlalchemy import func

from app.core.asset_types import INVESTMENT_MINOR_CATEGORIES, normalize_major_category
from app.core.auth import get_family_id, get_owned_or_404
from app.core.constants import ALLOCATION_LABELS, ASSET_CATEGORY_LABELS
from app.core.database import get_db
from app.core.money import Money
from app.core.utils import paginate
from app.core.validation import parse_body
from app.domains.assets.models import Asset
from app.domains.assets.schemas import AssetCreate, AssetOut, AssetUpdate
from app.domains.ledgers.models import Ledger

bp = APIBlueprint('assets', __name__, url_prefix='/api/assets')


def _parse_csv_filter(value: str) -> list[str]:
    """把逗号分隔的多值过滤参数解析为去空白后的非空列表（major/minor 共用）。"""
    return [m.strip() for m in value.split(',') if m.strip()]


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
    minor = request.args.get('minor_category', '')
    exclude = request.args.get('exclude', '')

    with get_db() as db:
        query = db.query(Asset).order_by(Asset.updated_at.desc())
        query = query.filter(Asset.family_id == get_family_id())

        # #1354：支持逗号分隔多值。盘点页「投资理财」需一次取回 investment 及其
        # 历史细分子类（bank_wealth/advisory/trust/private_fund/wealth_insurance）；
        # 仅传 investment 时自动展开为全部子类键，统一「写入收敛 + 读取归一」口径
        # （前端既可能传完整逗号列表，也可能只传 investment，两种都要能命中）。
        major_list = _parse_csv_filter(major)
        if 'investment' in major_list:
            major_list = major_list + [k for k in INVESTMENT_MINOR_CATEGORIES if k not in major_list]
        if len(major_list) == 1:
            query = query.filter(Asset.major_category == major_list[0])
        elif major_list:
            query = query.filter(Asset.major_category.in_(major_list))

        minor_list = _parse_csv_filter(minor)
        if len(minor_list) == 1:
            query = query.filter(Asset.minor_category == minor_list[0])
        elif minor_list:
            query = query.filter(Asset.minor_category.in_(minor_list))

        # 新增：排除指定的大类
        if exclude:
            exclude_list = [e.strip() for e in exclude.split(',') if e.strip()]
            if exclude_list:
                query = query.filter(Asset.major_category.not_in(exclude_list))

        assets, total = paginate(query, page=page, per_page=per_page)
        data = [_enrich_asset_dict(a) for a in assets]
        return jsonify({'data': data, 'total': total, 'page': page, 'per_page': per_page, 'message': 'ok'})


@bp.post('/')
def create_asset():
    json_data = parse_body(AssetCreate)
    data = json_data.model_dump()
    data['amount'] = Money.yuan_to_cents(data.get('amount', 0))

    # 如果传了 ledger_id，确保 account_name 快照正确（家庭维度）
    if data.get('ledger_id'):
        with get_db() as db:
            ledger = db.query(Ledger).filter_by(id=data['ledger_id'], family_id=get_family_id()).first()
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
        asset.user_id = 1
        asset.family_id = get_family_id()
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return jsonify({'data': _enrich_asset_dict(asset), 'message': 'ok'})


@bp.patch('/<int:id>/')
def update_asset(id):
    json_data = parse_body(AssetUpdate)
    with get_db() as db:
        asset = get_owned_or_404(db, Asset, id)
        if not asset:
            abort(404, description='资产不存在')

        update_data = json_data.model_dump(exclude_unset=True)

        # 🔥 修复：新增防御性校验，禁止把已有的资产迁移到错误的账户
        if 'ledger_id' in update_data and update_data['ledger_id'] is not None:
            new_ledger = db.query(Ledger).filter_by(id=update_data['ledger_id'], family_id=get_family_id()).first()
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
        asset = get_owned_or_404(db, Asset, id)
        if not asset:
            abort(404, description='资产不存在')
        db.delete(asset)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


@bp.get('/summary/')
def get_assets_summary():
    """获取各类通用资产的大类汇总金额（自带结构化标签，自解释性API）"""
    from app.core.constants import ASSET_CATEGORY_LABELS  # 确保导入了常量

    with get_db() as db:
        results = (
            db.query(Asset.major_category, func.coalesce(func.sum(Asset.amount), 0).label('total_cents'))
            .filter(Asset.family_id == get_family_id())
            .group_by(Asset.major_category)
            .all()
        )

        # 将数据库结果转为字典方便查找；#1354：投资理财的历史细分子类归一到 investment，
        # 否则盘点页大类金额会把本该合并的投资理财拆散（细分类永远显示「无记录」）。
        db_result_map: dict[str, int] = {}
        for cat, cents in results:
            # normalize 对 NULL 大类返回 None，单独归到 'other' 桶，避免 rest_keys 含 None
            # 触发混合类型排序异常（#1355 AI review）；金额不丢。
            key = normalize_major_category(cat) or 'other'
            db_result_map[key] = db_result_map.get(key, 0) + (cents or 0)

        # 定义一个明确的顺序（按业务逻辑排序，不再是乱序的键值对）
        category_order = ['investment', 'cash', 'fixed', 'liability', 'receivable', 'insurance']
        # 顺序表之外仍有大类（如 real_estate/precious_metal/custom）时一并下发，
        # 避免存量数据被静默丢弃
        rest_keys = [k for k in db_result_map if k not in category_order]

        summary_list = []
        for key in category_order + sorted(rest_keys):
            cents = db_result_map.get(key, 0)
            yuan = Money.cents_to_yuan(cents)
            # 负债处理为负数
            if key == 'liability':
                yuan = -yuan

            summary_list.append(
                {
                    'code': key,  # 分类代码（用于前端匹配）
                    'label': ASSET_CATEGORY_LABELS.get(key, key),  # 分类中文名（自带解释）
                    'value': yuan,  # 汇总金额
                }
            )

        return jsonify({'data': summary_list, 'message': 'ok'})
