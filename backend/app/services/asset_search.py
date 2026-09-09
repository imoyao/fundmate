# -*- coding: utf-8 -*-
"""资产统一聚合搜索（#1286）。

设计要点（决策留档见 issue #1286 2026-09-08 评论）：
- 前端全局搜索唯一后端入口 `GET /api/search/assets/`，五类源扇出：
  场内证券 / 场外基金 / 指数名录 / 投顾组合 / 基金经理。
- Provider 注册表模式：新增品种 = 在 SEARCH_PROVIDERS 注册一个函数即可，
  响应信封与前端消费方零改动（未来「组合购买」记账录入复用同一端点）。
- 单源失败不阻断整体（Partial failure 容忍，与 useAssetSearch 既有语义一致）。
- 统一信封 {code, name, asset_type, market, venue, extra}：
  - code 即 watchlist.symbol 的取值（经理 MGR_ 前缀、组合平台原生码）；
  - market/venue 为 '' 表示无市场实体（经理/组合，SQLite UNIQUE 空串约定）；
  - extra 为品种差异化展示字段（#1285 消费），可选。
"""

from typing import Callable, Dict, List

from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

# 单源返回条数上限（避免单源刷屏淹没其他品种）
_PER_PROVIDER_LIMIT = 10


def _search_securities(db: Session, q: str) -> List[Dict]:
    """场内证券（股票/ETF/可转债/美股/港股等，securities 表）。"""
    from app.core.symbol_utils import get_normalizer
    from app.domains.securities.models import Security

    normalizer = get_normalizer()
    normalized_q, _, _ = normalizer.normalize(q)
    conditions = []
    if normalized_q:
        conditions.append(Security.symbol == normalized_q)
    conditions.append(Security.symbol.ilike(f'%{q}%'))
    conditions.append(Security.name.ilike(f'%{q}%'))
    rows = db.query(Security).filter(or_(*conditions)).limit(_PER_PROVIDER_LIMIT).all()
    return [
        {
            'code': s.symbol,
            'name': s.name,
            'asset_type': s.type,
            'market': s.market,
            'venue': 'EXCHANGE',
        }
        for s in rows
    ]


def _search_funds(db: Session, q: str) -> List[Dict]:
    """场外基金（funds 表，FundService 内含 akshare 外部兜底）。"""
    from app.services.fund_service import FundService

    rows = FundService.search_funds(db, q)[:_PER_PROVIDER_LIMIT]
    return [
        {
            'code': r.get('code') or r.get('fund_code'),
            'name': r.get('name'),
            'asset_type': 'fund',
            'market': 'CN_A',
            'venue': 'OTC',
        }
        for r in rows
        if r.get('code') or r.get('fund_code')
    ]


def _search_indices(db: Session, q: str) -> List[Dict]:
    """指数名录（index_catalog 表，三源合并：sina/中证/国证，#1365）。

    code 归一化：exchange 作为命名空间前缀——SH000300 / SZ399001（交易所）、
    CSI930950（中证）、CNI399303（国证），与场内证券 SH600519 形态同构。
    """
    from app.domains.indices.models import IndexCatalog

    # 同时匹配「裸码」「名称」与「命名空间前缀码」：聚合搜索返回的 code 是
    # 前缀形态（SH000300 / CSI930950），用户若直接搜前缀码也能命中（#1362 评审 #5）。
    # exchange 可能为空串/None，用 COALESCE 兜底再拼接 index_code。
    prefixed_code = func.coalesce(IndexCatalog.exchange, '').concat(IndexCatalog.index_code)
    rows = (
        db.query(IndexCatalog)
        .filter(
            or_(
                IndexCatalog.index_code.ilike(f'%{q}%'),
                IndexCatalog.name.ilike(f'%{q}%'),
                prefixed_code.ilike(f'%{q}%'),
            )
        )
        # 核心白名单置顶（人工策展，#1365），其余按代码稳定排序
        .order_by(IndexCatalog.is_core.desc(), func.coalesce(IndexCatalog.core_rank, 999), IndexCatalog.index_code)
        .limit(_PER_PROVIDER_LIMIT)
        .all()
    )
    out = []
    for r in rows:
        prefix = r.exchange if r.exchange in ('SH', 'SZ', 'CSI', 'CNI') else ''
        market = 'CN_A' if prefix in ('SH', 'SZ') else (r.exchange or 'CN_A')
        out.append(
            {
                'code': f'{prefix}{r.index_code}',
                'name': r.name,
                'asset_type': 'index',
                'market': market,
                'venue': 'EXCHANGE' if prefix in ('SH', 'SZ') else '',
                'extra': {
                    'exchange': r.exchange,
                    'is_core': r.is_core,
                    'core_rank': r.core_rank,
                },
            }
        )
    return out


def _search_advisor_portfolios(db: Session, q: str) -> List[Dict]:
    """投顾组合（advisor_portfolios 表，#1167）。平台原生码（tgcode/ZHxxxx）直接作为 code。"""
    from app.domains.funds.models import AdvisorPortfolio

    rows = (
        db.query(AdvisorPortfolio)
        .filter(
            AdvisorPortfolio.is_active.is_(True),
            or_(AdvisorPortfolio.code.ilike(f'%{q}%'), AdvisorPortfolio.name.ilike(f'%{q}%')),
        )
        .limit(_PER_PROVIDER_LIMIT)
        .all()
    )
    return [
        {
            'code': p.code,
            'name': p.name,
            'asset_type': 'portfolio',
            'market': '',
            'venue': '',
            'extra': {'platform': p.platform, 'risk_level': p.risk_level, 'host': p.host},
        }
        for p in rows
    ]


def _search_managers(db: Session, q: str) -> List[Dict]:
    """基金经理（managers 表）。code 带 MGR_ 前缀（#1286 命名空间约定，防与数字码空间碰撞）。"""
    from app.domains.funds.models import FundCompany, Manager

    rows = db.query(Manager).filter(Manager.name.ilike(f'%{q}%')).limit(_PER_PROVIDER_LIMIT).all()
    # Manager 无 company relationship（仅 company_id 列），公司名走一次批量两步查询
    company_ids = {m.company_id for m in rows if m.company_id}
    company_map = {}
    if company_ids:
        company_map = {c.id: c.name for c in db.query(FundCompany).filter(FundCompany.id.in_(company_ids)).all()}
    return [
        {
            'code': f'MGR_{m.mgr_code}',
            'name': m.name,
            'asset_type': 'manager',
            'market': '',
            'venue': '',
            'extra': {'company': company_map.get(m.company_id)},
        }
        for m in rows
    ]


# Provider 注册表：新增品种在此追加一个 (db, q) -> list[dict] 函数即可
SEARCH_PROVIDERS: List[Callable[[Session, str], List[Dict]]] = [
    _search_securities,
    _search_funds,
    _search_indices,
    _search_advisor_portfolios,
    _search_managers,
]


def search_assets_aggregate(db: Session, q: str) -> List[Dict]:
    """聚合搜索入口：扇出全部 Provider，单源失败仅记日志不阻断。"""
    results: List[Dict] = []
    for provider in SEARCH_PROVIDERS:
        try:
            results.extend(provider(db, q))
        except Exception as e:  # noqa: BLE001 单源失败不阻断其他品种搜索
            logger.warning(f'聚合搜索源 {provider.__name__} 失败: {e}')
    return results
