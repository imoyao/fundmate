# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : product_identity.py
# app/services/product_identity.py
"""产品身份解析服务（#1963 · 详情页汇总卡 #1962 的 A1 子卡）。

产品详情页需要一个**后端权威**的「这个 symbol 到底是什么产品」判定：
前端路径上的 `asset_type` 只是**入口提示**（用户可手输 URL、收藏夹可能过期），
一律以后端返回为准（设计 §3.3，见
`docs/working-notes/product-detail-page-design-2026-10-08.md`）。

两步法 + 双域会话（跨域 SQL 无法 JOIN，见 :mod:`app.services.cross_domain`）
-------------------------------------------------------------------------
1. **user 域判身份**：自选行 / 持仓行自带 ``asset_type`` 语义——是用户自己录入的，
   最可信，优先于任何形态推断；
2. **market 域取实体**：按定下的 ``asset_type`` 回查展示名，复用
   :func:`~app.services.watchlist_service.resolve_display_name` 这条**单一反查链**
   （历史教训：同一展示需求两处实现必然漂移，见该函数 docstring）。

⚠️ **必须接两个 Session**（`docs/dev/db-data-domain.md` §2 的硬规则）：
``watchlist`` / ``positions`` 属 **user 域**（含 family_id、随用户数膨胀），
``funds`` / ``securities`` / ``index_catalog`` / ``managers`` / ``advisor_portfolios``
属 **market 域**（公开读多写少）。生产下两者是**独立引擎**（Turso / Supabase），
拿 user 域 session 查 market 表会直接 ``no such table``。业务层读市场数据必须且只能
经 ``db_factory.market_session_factory()``，本模块因此由调用方注入两个会话。

两步全部收口本模块，**禁止视图层手写 N+1**（守卫
`scripts/check_cross_domain_query.py`）。

asset_type 判定优先级（设计 §3.3：symbol 前缀不能单独当判据）
--------------------------------------------------------------
``自选行 → 持仓行 → 调用方提示（路径段，仅供核对）→ 目录反查``。
四者都拿不到时返回 ``None``，由视图转 404 空态（设计 §8），而不是让前端白屏。

隐私口径
--------
``in_watchlist`` / ``has_position`` 是**家庭私有状态**：未登录时
（``include_user_state=False``）一律返回 ``None`` 且**不查**这两张表——
既避免泄露他家持仓，也让匿名探查不产生多余查询。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.asset_types import is_valid_asset_type
from app.core.markets import market_aliases, to_contract_market
from app.domains.funds.models import AdvisorPortfolio, Fund
from app.domains.indices.models import IndexCatalog
from app.domains.positions.models import Position
from app.domains.securities.models import ConvertibleBondTerm, Security
from app.domains.watchlist.models import WatchlistItem
from app.services.watchlist_service import (
    bare_code_of,
    looks_like_exchange_code,
    lookup_manager,
    resolve_display_name,
)

# 市场归一（交易所前缀 → 契约市场、读侧别名）收口在 `app.core.markets`：
# **写入侧**（`watchlist_service.normalize_and_infer_venue`）与本**出口**共用同一份
# 真相源，避免「两处各写一份归一表」再把口径写分叉——这正是 #1969 P0 的成因
# （watchlist 存 SH、positions 存 CN_A，详情页拿 SH 过滤持仓恒为空）。


# 「指数 / 场内」形态（带市场前缀或纯数字）：**裸码反查只对这些形态开放**——
# 平台原生码（投顾 ZHxxxx / 经理 MGR_xxx）里的数字与市场码无关（ZH000001 的裸码 000001
# 就是上证指数）。判据收口在 `watchlist_service.looks_like_exchange_code`（与 `bare_code_of`
# 成对）：此处曾独立存过一份实现，而 `resolve_display_name` 那边没有闸门 → #2029 的
# 「远足」被同裸码基金劫持。**判据只此一处，勿再复制**。


def _resolve_market_venue(
    symbol: str,
    asset_type: str,
    market: Optional[str],
    venue: Optional[str],
) -> tuple[str, str]:
    """补全 market / venue（**读取**口径：拿不到就留空，绝不抛错）。

    与写入路径的 :func:`~app.services.watchlist_service.normalize_and_infer_venue`
    **有意不同**：后者是「创建自选」的前置校验，缺 venue 必须报错，否则唯一键
    ``(family_id, symbol, market, venue)`` 会缺一块；而本 resolver 是只读入口——
    用户手输 ``/stock/600519`` 时压根不会带 venue，这里若照搬那套校验就会把
    「读一下这是什么产品」变成 400。缺值一律留空，由前端按需消歧。
    """
    resolved_venue = venue or ''
    if not resolved_venue and asset_type == 'fund':
        resolved_venue = 'OTC'
    # 出口只说**契约市场**：库里两套词表（watchlist 存 SH/SZ、positions 存 CN_A），
    # 消费方不该猜是哪套（详见 _to_contract_market）
    resolved_market = to_contract_market(market, symbol)
    return resolved_market, resolved_venue


# securities.type 的取值可直接当 asset_type 用（取值见 securities/models.py）；
# future 等非持仓品类不在枚举内，此时回落 'stock'，由上层按需纠正。
_SECURITY_TYPE_AS_ASSET_TYPE = frozenset({'stock', 'etf', 'bond', 'crypto'})


def _infer_asset_type_from_catalog(market_db: Session, symbol: str) -> Optional[str]:
    """目录反查兜底：按各域实体是否存在判定品类，命中即返回。

    全部查 **market 域**表。顺序按「形态独特性」排，避免同码歧义：

    - 经理（MGR_ 前缀）/ 投顾组合（平台原生码）形态独有，先判、不会误命中；
    - 指数**必须**先于基金判：本库 ``index_catalog`` 与 ``funds`` 裸码重叠 258 条
      且撞的是主流码（#1497：000300 指数=沪深300 / funds=德邦德利货币A），
      顺序反了会把指数错标成一只无关的货币基金；
    - 可转债名称/条款在 ``convertible_bond_terms``，``securities`` 只装股票（#1499）。
    """
    if lookup_manager(symbol, market_db) is not None:
        return 'manager'
    if market_db.query(AdvisorPortfolio.id).filter(AdvisorPortfolio.code == symbol).first() is not None:
        return 'portfolio'

    # **精确形态优先**：securities 存「带市场前缀」形态（``SZ000001``）。带前缀的场内
    # 代码必须先在这里命中——否则下面的裸码兜底会把 ``SZ000001`` 判成上证指数
    # （``index_catalog.index_code`` 里 ``000001`` 就是它），把一只股票错标成指数。
    # 裸码输入（``000001``）则命中不了 securities，会正确落到下面的指数分支。
    sec = market_db.query(Security).filter(Security.symbol == symbol).first()
    if sec is not None:
        sec_type = (sec.type or '').strip().lower()
        return sec_type if sec_type in _SECURITY_TYPE_AS_ASSET_TYPE else 'stock'

    bare = bare_code_of(symbol)
    # 裸码反查**仅适用于「指数 / 场内」形态**（带市场前缀或纯数字）：平台原生码里的
    # 数字与市场码无关——``ZH000001``（投顾组合）的裸码 ``000001`` 恰好就是上证指数，
    # 不限定形态就会把一只投顾组合错判成指数。
    allow_bare = looks_like_exchange_code(symbol)
    # 指数按**裸码**存（#1497：本库 index_catalog 与 funds 裸码重叠 258 条且撞主流码，
    # 故命中即返回，不回退 funds——错标成一只无关的货币基金比退回显示代码更糟）
    if allow_bare and bare and market_db.query(IndexCatalog.id).filter(IndexCatalog.index_code == bare).first():
        return 'index'

    if market_db.query(ConvertibleBondTerm.id).filter(ConvertibleBondTerm.symbol == symbol).first() is not None:
        return 'bond'

    if market_db.query(Fund.id).filter(Fund.fund_code == symbol).first() is not None:
        return 'fund'
    # 场内 ETF 的 symbol 带 SH/SZ 前缀，而 funds.fund_code 存裸码（#1497）
    if allow_bare and bare and bare != symbol and market_db.query(Fund.id).filter(Fund.fund_code == bare).first():
        return 'fund'
    return None


def resolve_product_identity(
    user_db: Session,
    market_db: Session,
    symbol: str,
    market: Optional[str] = None,
    venue: Optional[str] = None,
    asset_type_hint: Optional[str] = None,
    family_id: Optional[int] = None,
    include_user_state: bool = False,
) -> Optional[Dict[str, Any]]:
    """解析产品的权威身份（详情页所有入口共用的单一 resolver）。

    Args:
        user_db: **user 域**会话（读 watchlist / positions）。
        market_db: **market 域**会话（读 funds / securities / index_catalog /
            managers / advisor_portfolios / convertible_bond_terms）。生产下与
            ``user_db`` 是不同引擎，混用会 ``no such table``。
        symbol: 产品代码（大小写不敏感，内部归一为大写）。
        market: 可选，市场消歧（同品类跨市场同码，如 000001）。
        venue: 可选，交易场所消歧（``EXCHANGE`` / ``OTC``）。
        asset_type_hint: 可选，**入口提示**（前端路径段传来的 asset_type）。
            仅参与「后端自行判定」；与后端结论不一致时以本函数返回为准
            （设计 §3.3：不信任手输路径）。
        family_id: 家庭 ID，用于判「该家庭是否已自选 / 持有」。
        include_user_state: 是否回家庭私有状态。**未登录必须传 False**，
            此时不查 watchlist / positions，``in_watchlist`` 与 ``has_position``
            恒为 ``None``。

    Returns:
        解析结果 dict；**无法判定品类时返回 None**（调用方转 404 空态）。

    Raises:
        ValueError: ``symbol`` 为空。
    """
    symbol = (symbol or '').strip().upper()
    if not symbol:
        raise ValueError('缺少 symbol 参数')

    wl: Optional[WatchlistItem] = None
    pos: Optional[Position] = None
    if include_user_state:
        # 入参 market 同样走「契约市场 + 别名」匹配：存量 watchlist.market 混着
        # SH/SZ 与 CN_A 两套词表，只比契约值会静默漏行，归一后「已自选」反而被判成
        # 未自选（#1969 P0 的连带面，详见 _market_aliases）
        market_in = market_aliases(to_contract_market(market, symbol)) if market else ()
        wl_query = user_db.query(WatchlistItem).filter(
            WatchlistItem.family_id == family_id,
            WatchlistItem.symbol == symbol,
        )
        if market_in:
            wl_query = wl_query.filter(WatchlistItem.market.in_(market_in))
        if venue:
            wl_query = wl_query.filter(WatchlistItem.venue == venue)
        wl = wl_query.first()

        pos_query = user_db.query(Position).filter(
            Position.family_id == family_id,
            Position.symbol == symbol,
        )
        if market_in:
            pos_query = pos_query.filter(Position.market.in_(market_in))
        pos = pos_query.first()

    # ── 1. 品类判定：用户行内语义 > 入口提示 > 目录反查 ──
    asset_type: Optional[str] = None
    source: Optional[str] = None
    if wl is not None and is_valid_asset_type(wl.asset_type):
        asset_type, source = wl.asset_type, 'watchlist'
    elif pos is not None and is_valid_asset_type(pos.asset_type):
        asset_type, source = pos.asset_type, 'position'
    else:
        # 目录反查**优先于**入口提示：设计 §3.3 明令「不信任手输路径，以后端返回为准」，
        # 目录能核实就必须核实；提示只在目录查不到时兜底（如平台原生码的投顾组合）。
        asset_type = _infer_asset_type_from_catalog(market_db, symbol)
        if asset_type is not None:
            source = 'catalog'
        elif is_valid_asset_type(asset_type_hint):
            asset_type, source = asset_type_hint, 'hint'

    if asset_type is None:
        return None

    # ── 2. market / venue：行内快照优先，其次按品类 / 前缀补全（只读口径，不抛错）──
    wl_market = (wl.market if wl is not None else '') or ''
    wl_venue = (wl.venue if wl is not None else '') or ''
    pos_market = (pos.market if pos is not None else '') or ''
    resolved_market, resolved_venue = _resolve_market_venue(
        symbol,
        asset_type,
        wl_market or pos_market or market,
        wl_venue or venue,
    )

    # ── 3. 展示名：自选快照优先（#1508），否则走 market 域单一反查链 ──
    display_name = ((wl.name if wl is not None else '') or '').strip()
    if not display_name:
        display_name = resolve_display_name(symbol, market_db, asset_type)

    return {
        'symbol': symbol,
        'asset_type': asset_type,
        'market': resolved_market,
        'venue': resolved_venue,
        'display_name': display_name,
        # 家庭私有状态：未登录为 None（且上面根本没查这两张表）
        'in_watchlist': (wl is not None) if include_user_state else None,
        'has_position': (pos is not None) if include_user_state else None,
        # 判定来源，供前端排查「为什么判成这个品类」；catalog 表示目录反查兜底
        'source': source,
    }
