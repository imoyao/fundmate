# -*- coding: utf-8 -*-
"""策略域的查询 / 展示行组装服务（#1642 B 块，从 views 下沉，承 #1606）。

WHY 下沉
    `get_strategy_overview` 长在视图里（98 行）：4 张表的家庭隔离查询 + 持仓/资产合并组装
    + 关联映射构建，属纯读组装，却只能挂在 HTTP 栈下测。本模块收口，视图只做调服务 + 组响应。

边界
    - 不碰 ``g`` / ``request``：family_id 由调用方显式传入，可脱离请求上下文单测；
    - 只读组装：不写库、不提交事务；
    - 对外 API 契约零变更（``conventions.md`` §2.4）：返回字段名、嵌套结构与下沉前逐字一致。
"""

from app.core.constants import ASSET_CATEGORY_LABELS, TYPE_LABELS
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.positions.models import Position
from app.domains.strategy.models import PositionStrategyTag, StrategyTag


def build_strategy_overview(db, family_id: int) -> dict:
    """策略视图全部数据：持仓、资产、标签、关联（#1642 B 块，从视图层下沉）。

    与下沉前逐字段一致：持仓（quantity>0）与资产（非负债、amount>0）合并为 holdings
    （资产 id+100000 偏移）；标签按创建时间升序；关联映射 {position_id: [tag_name]}。
    """
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
        .filter(Position.family_id == family_id, Position.quantity > 0)
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
            Asset.family_id == family_id,
            Asset.major_category != 'liability',
            Asset.amount > 0,
        )
        .all()
    )

    # 3. 所有策略标签（家庭隔离）
    tags = (
        db.query(StrategyTag)
        .filter(StrategyTag.family_id == family_id)
        .order_by(StrategyTag.created_at.asc())
        .all()
    )

    # 4. 所有持仓-标签关联，构建映射
    rows = (
        db.query(PositionStrategyTag.position_id, StrategyTag.name)
        .join(StrategyTag, PositionStrategyTag.strategy_tag_id == StrategyTag.id)
        .filter(StrategyTag.family_id == family_id)
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
                'current_price': Money.price_units_to_yuan(p.current_price),
                'avg_price': Money.price_units_to_yuan(p.avg_price),
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
                'type_label': ASSET_CATEGORY_LABELS.get(a.major_category, a.major_category or '其他'),
                'quantity': 1,
                'current_price': a.amount,
                'avg_price': a.amount,
                'account_name': a.account_name,
            }
        )

    tag_list = [{'id': t.id, 'name': t.name} for t in tags]

    return {
        'holdings': holdings,
        'tags': tag_list,
        'relations': relations,
    }
