# -*- coding: utf-8 -*-
"""投资组合域的查询 / 展示行组装服务（#1642 B 块，从 views 下沉，承 #1606）。

WHY 下沉
    `get_portfolio_holdings` 长在视图里（104 行），含组合校验、关联账户推导、持仓/资产
    联合查询、类现金排除与逐行市值/盈亏组装——属纯读组装，却只能挂在 HTTP 栈下测。
    本模块把这部分收口，视图只做归属校验 + 调服务 + 组响应信封。

边界
    - 不碰 ``g`` / ``request``：family_id 由调用方显式传入，可脱离请求上下文单测；
    - 只读组装：不写库、不提交事务；
    - 对外 API 契约零变更（``conventions.md`` §2.4）：返回字段名、嵌套结构与下沉前逐字一致。
"""

from sqlalchemy import and_, or_

from app.core.constants import ASSET_CATEGORY_LABELS, TYPE_LABELS
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position
from app.services.fund_utils import should_exclude_from_investment


def build_portfolio_holdings(db, family_id: int, portfolio_id: int) -> list[dict]:
    """组合下所有关联账户的持仓/资产明细（#1642 B 块，从视图层下沉）。

    与下沉前逐字段一致：
    - 组合不存在 / 已删除 / 非本家庭 → 抛 ``ValueError('投资组合不存在')``，由视图转 404；
    - 主路径 ``positions.portfolio_id == portfolio_id``；继承路径仅当持仓未显式指定组合时
      继承其账户(ledger)的默认组合（显式 portfolio_id 必须覆盖 ledger 继承）；
    - 类现金由 ``should_exclude_from_investment`` 排除（尊重 count_as_investment 覆盖）；
    - 账户级资产（现金，非负债）并入同一 holdings 列表，以 ``asset.id + 100000`` 区分。
    """
    portfolio = (
        db.query(Portfolio)
        .filter(
            Portfolio.id == portfolio_id,
            Portfolio.is_deleted.is_(False),
            Portfolio.family_id == family_id,
        )
        .first()
    )
    if not portfolio:
        raise ValueError('投资组合不存在')

    # 关联账户 ID 列表（组合 = 默认组合指向本组合的账户集合）
    ledger_ids = [
        row[0]
        for row in db.query(Ledger.id)
        .filter(Ledger.portfolio_id == portfolio_id, Ledger.family_id == family_id)
        .all()
    ]
    if not ledger_ids:
        return []

    # 查询持仓（仅用 portfolio_id / ledger_id 关联，杜绝 account_name 字符串匹配）
    #   - 主路径：持仓显式归属本组合（positions.portfolio_id == P）
    #   - 继承路径：仅当持仓未显式指定组合时，继承其账户(ledger)的默认组合
    #   注意：显式 portfolio_id 必须覆盖 ledger 继承，否则改派后会同时出现在账户默认组合
    pos_conds = [
        Position.portfolio_id == portfolio_id,
        and_(
            Position.portfolio_id.is_(None),
            Position.ledger_id.in_(ledger_ids),
        ),
    ]
    positions = (
        db.query(Position)
        .filter(
            or_(*pos_conds),
            Position.quantity > 0,
        )
        .all()
    )
    # 类现金排除改由统一函数判定（决策 #7：尊重 count_as_investment 覆盖 + 逆回购到期自动转现金）
    positions = [p for p in positions if not should_exclude_from_investment(p)]

    # 账户级资产仍按 ledger_id 关联（现金不进持仓级组合，沿用账户归属）
    assets = (
        db.query(Asset)
        .filter(
            Asset.ledger_id.in_(ledger_ids),
            # 排除负债
            Asset.major_category != 'liability',
        )
        .all()
    )

    # 构造持仓列表（包含市值和盈亏）
    holdings = []
    for pos in positions:
        market_value = Money.multiply_price_quantity(pos.current_price, pos.quantity)
        pnl = Money.multiply_price_quantity(pos.current_price - pos.avg_price, pos.quantity) if pos.avg_price else 0

        holdings.append(
            {
                'id': pos.id,
                'symbol': pos.symbol,
                'name': pos.name,
                'type': pos.asset_type,
                'type_label': TYPE_LABELS.get(pos.asset_type, pos.asset_type),
                'account_name': pos.account_name,
                'quantity': Money.min_unit_to_shares(pos.quantity),
                'current_price': Money.price_units_to_yuan(pos.current_price),
                'avg_price': Money.price_units_to_yuan(pos.avg_price),
                'market_value': Money.cents_to_yuan(market_value),
                'pnl': Money.cents_to_yuan(pnl),
                'pnl_rate': round((pos.current_price - pos.avg_price) / pos.avg_price * 100, 2)
                if pos.avg_price
                else 0.0,
            }
        )

    for asset in assets:
        holdings.append(
            {
                'id': asset.id + 100000,
                'symbol': asset.major_category or 'asset',
                'name': asset.name or asset.major_category,  # 使用 name 字段
                'type': asset.major_category,
                'type_label': ASSET_CATEGORY_LABELS.get(asset.major_category, asset.major_category or '其他'),
                'account_name': asset.account_name,
                'ledger_id': asset.ledger_id,
                'quantity': 1,
                'current_price': Money.cents_to_yuan(asset.amount),
                'avg_price': Money.cents_to_yuan(asset.amount),
                'market_value': Money.cents_to_yuan(asset.amount),
                'pnl': 0.0,
                'pnl_rate': 0.0,
            }
        )

    return holdings
