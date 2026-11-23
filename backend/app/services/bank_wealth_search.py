# -*- coding: utf-8 -*-
"""银行理财搜索源（#931 / D121）。

## 为什么独立成文件

聚合搜索的 Provider 注册表在 `asset_search.py`，但那个文件有 256 行的冻结基线
（`scripts/guard_service_size.py`，存量服务「只减不增」）。把带完整口径说明的
Provider 塞进去会让它涨到 307 行。正确做法是**下沉成独立模块**，主文件只留
一行 import 与两个注册项——而不是去放宽基线。

## 数据源的口径

中国理财网无面向个人/第三方的公开 API（`docs/spec/importer-architecture.md` §5.1），
全市场产品目录不可得。所以这里是「**本地已知产品库**」——用户自己录过的产品，
用于加仓 / 跨账户录入时按产品名直接选中；**首次录入仍需手填登记编码与名称**。
不做全市场目录是刻意的边界：避开无授权抓取与无 SLA 的爬虫。

## 契约

与其它 Provider 一致：`(db, q) -> list[dict]`，信封 `{code, name, asset_type,
market, venue, extra}`；`market` / `venue` 空串表示无市场实体（NO_VENUE 约定）。
"""

from typing import Dict, List

from sqlalchemy import or_
from sqlalchemy.orm import Session

# 与 asset_search._PER_PROVIDER_LIMIT 同值（单源条数上限，避免单源刷屏淹没其它品种）。
# 不在模块级从 asset_search 导入它：那会形成循环导入（asset_search 反过来要导本模块）。
_LIMIT = 10


def search_bank_wealth(db: Session, q: str) -> List[Dict]:
    """按产品名或登记编码搜用户已录入的银行理财（#931 / D121）。

    `code` 取 `positions.symbol`，即理财登记编码（银登中心全市场唯一）——**不取产品名**：
    同名不同期 / 不同渠道的产品名字会撞，拿它当身份会让两笔钱合并成一条持仓。
    大小写归一不需要在这里做，落库时 `_fill_position_symbol_norm` 的 `symbol_identity`
    已按 `NO_VENUE:{大写编码}` 生成身份键。

    不过滤 `ownership_status`：清仓后持仓行保留（D117 不替用户删持仓），
    用户回购同一产品时仍应能搜到。family 过滤与读侧一致，避免跨家庭搜到别人的产品名。
    """
    from app.core.auth import get_family_id
    from app.domains.positions.models import Position

    rows = (
        db.query(Position.symbol, Position.name)
        .filter(
            Position.family_id == get_family_id(),
            Position.asset_type == 'bank_wealth',
            or_(Position.symbol.ilike(f'%{q}%'), Position.name.ilike(f'%{q}%')),
        )
        .distinct()
        .limit(_LIMIT)
        .all()
    )
    return [
        {
            'code': symbol,
            'name': name or '',
            'asset_type': 'bank_wealth',
            # 银行理财在银行渠道销售、不在交易所撮合，无市场与场所归属（core/venues）
            'market': '',
            'venue': '',
        }
        for symbol, name in rows
    ]
