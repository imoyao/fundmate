# -*- coding: utf-8 -*-
"""资产统一聚合搜索（#1286）。

设计要点（决策留档见 issue #1286 2026-09-08 评论）：
- 前端全局搜索唯一后端入口 `GET /api/search/assets/`，五类源扇出：
  场内证券 / 场外基金 / 指数名录 / 投顾组合 / 基金经理。
- Provider 注册表模式：新增品种 = 在 SEARCH_PROVIDERS 注册一个函数即可，
  响应信封与前端消费方零改动（未来「组合购买」记账录入复用同一端点）。
- 单源失败不阻断整体（Partial failure 容忍，与 useAssetSearch 既有语义一致）。
- 基金源是唯一带外部兜底（akshare）的源：兜底准入受 #2218 条件跳过约束——
  其它本地源已有命中即不打外部（见 _search_funds / _other_local_providers_hit）。
- 统一信封 {code, name, asset_type, market, venue, extra}：
  - code 即 watchlist.symbol 的取值（经理 MGR_ 前缀、组合平台原生码）；
  - market/venue 为 '' 表示无市场实体（经理/组合，SQLite UNIQUE 空串约定）；
  - extra 为品种差异化展示字段（#1285 消费），可选。
"""

import re
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
    """场外基金（funds 表，FundService 内含 akshare 外部兜底）。

    外部兜底带准入判定（#2218）：只有「本地 funds 零命中 **且** 其它本地源也全空」
    （= 真正的基金名检索）才打 3MB/14s 的 akshare fund_name_em；用户搜的是股票 /
    指数 / 组合 / 经理时，其它本地源必先命中，直接跳过外部源。
    """
    from app.services.fund_service import FundService

    rows = FundService.search_funds(
        db,
        q,
        # 延迟求值：search_funds 仅在本地零命中、即将打外部源时才调用本回调，
        # 本地命中路径零额外开销（判据实现见 _other_local_providers_hit）。
        external_gate=lambda: not _other_local_providers_hit(db, q),
    )
    return [
        {
            'code': r.get('code') or r.get('fund_code'),
            'name': r.get('name'),
            'asset_type': 'fund',
            'market': 'CN_A',
            'venue': 'OTC',
        }
        for r in rows[:_PER_PROVIDER_LIMIT]
        if r.get('code') or r.get('fund_code')
    ]


def _search_indices(db: Session, q: str) -> List[Dict]:
    """指数名录（index_catalog 表，三源合并：sina/中证/国证 #1365 + 万得系静态名录 #2217）。

    code 归一化：exchange 作为命名空间前缀——SH000300 / SZ399001（交易所）、
    CSI930950（中证）、CNI399303（国证），与场内证券 SH600519 形态同构；
    万得系（881001 万得全A 等）无交易所/命名空间前缀 → 返回裸码
    （exchange 为 NULL 时 market 落回 CN_A，venue 为空串，与加入自选的约定一致）。
    """
    from app.domains.indices.models import INDEX_PUBLISHER_LABELS, IndexCatalog

    # 同时匹配「裸码」「名称」与「命名空间前缀码」：聚合搜索返回的 code 是
    # 前缀形态（SH000300 / CSI930950），用户若直接搜前缀码也能命中（#1362 评审 #5）。
    # exchange 可能为空串/None，用 COALESCE 兜底再拼接 index_code。
    prefixed_code = func.coalesce(IndexCatalog.exchange, '').concat(IndexCatalog.index_code)
    conditions = [
        IndexCatalog.index_code.ilike(f'%{q}%'),
        IndexCatalog.name.ilike(f'%{q}%'),
        prefixed_code.ilike(f'%{q}%'),
    ]
    # 查询空白归一化（#2217）：库内名「万得全A」无空格，用户输入「万得全 A」（带空格）
    # 时原样 ilike 必落空。补一条「去空白」变体，原样与 compact 双路任一命中即返回。
    # 只压查询侧即可覆盖该场景：库内名取各源公示简称为准、普遍不含空格。
    q_compact = re.sub(r'\s+', '', q)
    if q_compact and q_compact != q:
        conditions.extend(
            [
                IndexCatalog.index_code.ilike(f'%{q_compact}%'),
                IndexCatalog.name.ilike(f'%{q_compact}%'),
                prefixed_code.ilike(f'%{q_compact}%'),
            ]
        )
    rows = (
        db.query(IndexCatalog)
        .filter(or_(*conditions))
        # 核心白名单置顶（人工策展，#1365），其余按代码稳定排序
        .order_by(IndexCatalog.is_core.desc(), func.coalesce(IndexCatalog.core_rank, 999), IndexCatalog.index_code)
        .limit(_PER_PROVIDER_LIMIT)
        .all()
    )
    out = []
    for r in rows:
        prefix = r.exchange if r.exchange in ('SH', 'SZ', 'CSI', 'CNI') else ''
        market = 'CN_A' if prefix in ('SH', 'SZ') else (r.exchange or 'CN_A')
        # 编制/发布机构（#1425）：读名录表存储的机构代码（三源作业按来源回填，
        # 万得系静态行 #2217 直接写 WIND），映射为中文展示名下发；未知/未回填（NULL）
        # 时不下发该字段——前端据「字段缺失」降级不展示，与「错误的发布方比没有更糟」
        # 的取舍一致。
        publisher = INDEX_PUBLISHER_LABELS.get(r.publisher)
        extra = {
            'exchange': r.exchange,
            'is_core': r.is_core,
            'core_rank': r.core_rank,
        }
        if publisher:
            extra['publisher'] = publisher
        out.append(
            {
                'code': f'{prefix}{r.index_code}',
                'name': r.name,
                'asset_type': 'index',
                'market': market,
                'venue': 'EXCHANGE' if prefix in ('SH', 'SZ') else '',
                'extra': extra,
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

    # 支持按 MGR_ 前缀码搜索（#1491 评审）：先剥前缀再匹配 mgr_code，与其它 Provider
    # 同时匹配 code/name 的行为一致；否则用户粘贴 'MGR_xxx' 永远搜不到。
    mgr_code_q = q[4:] if q.upper().startswith('MGR_') else q
    rows = (
        db.query(Manager)
        .filter(or_(Manager.mgr_code.ilike(f'%{mgr_code_q}%'), Manager.name.ilike(f'%{q}%')))
        .limit(_PER_PROVIDER_LIMIT)
        .all()
    )
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


# 除 funds 外的四类**本地**源（#2218）：全部是本地表查询、毫秒级，
# 供基金外部兜底的有条件跳过判定复用（不含 _search_funds 自身，防自引用）。
_OTHER_LOCAL_PROVIDERS: List[Callable[[Session, str], List[Dict]]] = [
    _search_securities,
    _search_indices,
    _search_advisor_portfolios,
    _search_managers,
]


def _other_local_providers_hit(db: Session, q: str) -> bool:
    """其它四类本地源是否已有命中（#2218「有条件跳过外部兜底」的判据）。

    直接复用 Provider 本体，而非另写一份等价快查：判据与实际返回若分两处实现必然漂移。
    仅在本地 funds 零命中时才被求值（search_funds 的 external_gate 延迟求值），
    命中即短路；每次最多 4 条带 limit 的本地查询，代价可忽略——对比它拦掉的
    3MB / 14s akshare 全量拉取。

    单源异常**按未命中处理**：预检失败宁可多打一次外部源，也不能把真正的基金名检索
    拦在门外（外部兜底就是为它设计的）。
    """
    for provider in _OTHER_LOCAL_PROVIDERS:
        try:
            if provider(db, q):
                return True
        except Exception as e:  # 预检失败不阻断兜底准入（保守放行）
            logger.warning(f'外部兜底预检源 {provider.__name__} 失败（按未命中处理）: {e}')
    return False


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
