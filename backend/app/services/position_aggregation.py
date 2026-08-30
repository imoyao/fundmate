# -*- coding: utf-8 -*-
"""持仓跨账本聚合通用范式（#1101 场外基金 / #1132 场内证券 共用）。

把家族内某类资产的全部持仓（ownership_status='active'）按维度聚合成统一视图，
供资产概览聚合卡片与下钻页（/funds、/stocks）使用。

设计要点（#1133 结论）：
- **零 schema 迁移**：聚合视图是「品类维度」的虚拟视图，不新建物理账本、不加列。
  产品信息（快照日期 / 管理人 / 分红方式 / 基金账户等）全部来自 #1012 已建的
  `position_import_meta` 表，本服务只负责 join 出来。
- **数据日期口径**：取持仓快照日（`position_import_meta.snapshot_date`，即导入
  对账日期 / Excel「份额日期」），**不取**「持仓最新更新日期」——用户可能手动改过，
  两边必须拉平到同一时间基准。页面顶部展示最早的一笔（最滞后、最诚实）。
- **市值口径（#1133 修复）**：
  基金/货基用 **NavService 最新净值** 计算市值（与 ledger_service 口径一致）；
  其他类型仍用快照价。响应体新增 ``nav_date`` 字段表示净值日期，
  与 ``snapshot_date``（份额日期）分叉时前端可双日期展示。
- **净值获取统一入口**：通过 :mod:`app.services.nav_service.NavService` 批量取值，
  禁止再各自实现查 DailyWorth / 调 xalpha 的逻辑。
  （见 NavService 模块 docstring 的迁移指引表）
- **维度**：`product`（按产品）/ `institution`（按销售机构）。
  原 `app`（按交易前端）维度已于 #1133 收敛去掉——其本质就是销售机构，属重复维度。

两品类共享本文件，避免 fund_aggregation / securities_aggregation 两份逻辑漂移。
"""

from __future__ import annotations

from typing import Dict

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta, SalesInstitution

# 🔄 NavService 统一入口：替代此前分散在各处的净值取数逻辑
# （见 nav_service.py 模块 docstring 的迁移指引表）
from app.services.nav_service import NavService

# 🔄 市值口径收口（#1174）：三处派生计算统一委托此唯一入口，禁止再各写一套
from app.services.position_valuation import market_value_cents

# 合法聚合维度（app 维度已废弃，见模块 docstring）
AGGREGATION_DIMENSIONS = ('product', 'institution')

# 排序字段白名单：禁止前端传入任意列名拼进排序键
SORT_FIELDS = ('market_value', 'quantity', 'name', 'symbol')

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


def _position_market_value_cents(
    position: Position,
    *,
    effective_nav_yuan: float | None = None,
) -> int:
    """单笔持仓市值（分）。

    🔄 口径收口（#1174）：实际计算已委托 position_valuation.market_value_cents，
    此处仅保留签名以兼容既有调用方。新增市值逻辑一律改到唯一口径里，禁止在此另开分支。

    Args:
        position: 持仓记录
        effective_nav_yuan: 有效净值（元）。基金/货基传 NavService 最新净值；
            其他类型或无净值时为 None（回退到快照价 current_price）。
    """
    # 聚合口径需折算成 CNY（total_*_cny），故显式传汇率；明细口径则不传（本币直算）
    return market_value_cents(
        position,
        effective_nav_yuan=effective_nav_yuan,
        rate=EXCHANGE_RATES.get(position.currency, 1.0),
    )


def _iso_date(value) -> str | None:
    """date → 'YYYY-MM-DD'；None 安全穿透。"""
    return value.isoformat() if value is not None else None


def _collect_rows(session, family_id: int, asset_types: tuple) -> list[dict]:
    """取出该类资产的全部在管持仓，并 join 出展示所需的溯源字段。

    一次批量查 `position_import_meta`（position_id IN ...）后再内存映射，
    避免逐笔查询造成 N+1。

    🔄 市值口径（#1133 修复）：基金/货基通过 NavService 取最新净值计算市值，
       与 ledger_service / XIRR 口径一致，消除「账本页和聚合页显示不同市值」的 bug。
    """
    positions = (
        session.query(Position)
        .filter(
            Position.family_id == family_id,
            Position.asset_type.in_(asset_types),
            Position.ownership_status == 'active',
        )
        .all()
    )
    if not positions:
        return [], None

    # ── 批量取溯源元数据（快照日期 / 管理人 / 分红方式 / 平台账号）──
    metas: dict[int, PositionImportMeta] = {}
    position_ids = [p.id for p in positions]
    for meta in session.query(PositionImportMeta).filter(PositionImportMeta.position_id.in_(position_ids)).all():
        metas[meta.position_id] = meta

    # ── 批量取账户与销售机构（补全「按机构」维度的机构名）──
    ledger_ids = {p.ledger_id for p in positions if p.ledger_id}
    ledgers: dict[int, Ledger] = {}
    if ledger_ids:
        ledgers = {led.id: led for led in session.query(Ledger).filter(Ledger.id.in_(ledger_ids)).all()}

    institution_ids = {led.sales_institution_id for led in ledgers.values() if led.sales_institution_id}
    # 机构名与别名分开存：主展示用 **AMAC 权威全称**（真实、完整、专业），
    # 别名（支付宝/天天基金等）仅作辅助提示，不替代全称。
    institutions: dict[int, str] = {}
    institution_aliases: dict[int, str] = {}
    if institution_ids:
        for inst in session.query(SalesInstitution).filter(SalesInstitution.id.in_(institution_ids)).all():
            institutions[inst.id] = inst.org_name or inst.display_name
            if inst.display_name and inst.display_name != inst.org_name:
                institution_aliases[inst.id] = inst.display_name

    # ── 🔄 NavService：批量取基金/货基最新净值（与 ledger_service 口径统一）──
    # 注意：聚合接口是用户触发的同步请求，必须 allow_remote=False 避免阻塞。
    # 远程净值拉取由定时任务（grab.job fund_nav）异步完成。
    fund_symbols = [p.symbol for p in positions if p.symbol and p.asset_type in ('fund', 'money_fund')]
    latest_navs: Dict[str, float] = {}
    nav_date_global: str | None = None
    if fund_symbols:
        latest_navs = NavService.get_latest_navs(session, fund_symbols, allow_remote=False)
        # 记录净值日期（用于响应体的 nav_date 字段）
        # 取所有有净值的基金中最大的日期作为全局 nav_date
        if latest_navs:
            try:
                from sqlalchemy import func as _func

                from app.domains.funds.models import DailyWorth as _DW

                max_date_row = (
                    session.query(_func.max(_DW.date)).filter(_DW.fund_code.in_(list(latest_navs.keys()))).first()
                )
                nav_date_global = max_date_row[0].isoformat() if max_date_row and max_date_row[0] else None
            except Exception:
                nav_date_global = None

    rows: list[dict] = []
    for p in positions:
        ledger = ledgers.get(p.ledger_id)
        meta = metas.get(p.id)
        institution_id = ledger.sales_institution_id if ledger else None

        # 🔄 有效净值：基金/货基从 NavService 取，其他类型为 None（回退快照价）
        effective_nav = latest_navs.get(p.symbol) if (p.symbol and p.asset_type in ('fund', 'money_fund')) else None

        rows.append(
            {
                'symbol': p.symbol,
                'name': p.name,
                'ledger_id': p.ledger_id,
                'ledger_name': ledger.name if ledger else None,
                'institution_id': institution_id,
                # 主展示：AMAC 权威全称（真实、完整）；别名单列，供前端作辅助提示
                'institution_name': institutions.get(institution_id) if institution_id else None,
                'institution_alias': institution_aliases.get(institution_id) if institution_id else None,
                # 🔄 使用 NavService 最新净值计算市值（而非快照价 current_price）
                'market_value_cents': _position_market_value_cents(p, effective_nav_yuan=effective_nav),
                'quantity': p.quantity,
                # 参考净值：优先 NavService 最新值，无则回退快照价
                'nav_yuan': effective_nav if effective_nav else Money.price_units_to_yuan(p.current_price),
                # ── 以下来自 position_import_meta，无快照记录时全为 None ──
                'snapshot_date': _iso_date(meta.snapshot_date) if meta else None,
                'fund_manager': meta.fund_manager if meta else None,
                'dividend_preference': meta.dividend_preference if meta else None,
                'fund_account': meta.fund_account if meta else None,
                'trade_account': meta.trade_account if meta else None,
                'source_broker': meta.source_broker if meta else None,
            }
        )
    return rows, nav_date_global


def _group_by_dimension(rows: list[dict], dimension: str) -> list[dict]:
    """按维度分组。product 按代码聚合并带 sources 明细；institution 按销售机构聚合。"""
    if dimension == 'institution':
        grouped: dict = {}
        for r in rows:
            key = r['institution_id'] or 'unknown'
            g = grouped.setdefault(
                key,
                {
                    'key': key,
                    # 机构中文名：此前前端只能显示「销售机构 #3」，此处直接给出现成文案
                    'institution_name': r['institution_name'] or ('未关联机构' if key == 'unknown' else f'机构 #{key}'),
                    'market_value_cents': 0,
                    'items': [],
                },
            )
            g['market_value_cents'] += r['market_value_cents']
            g['items'].append(r)
        return list(grouped.values())

    # product（默认）
    grouped = {}
    for r in rows:
        g = grouped.setdefault(
            r['symbol'],
            {
                'symbol': r['symbol'],
                'name': r['name'],
                'market_value_cents': 0,
                'quantity': 0,
                # 同一 symbol 各渠道净值一致，取首个非空值即可
                'nav_yuan': r['nav_yuan'],
                'snapshot_date': r['snapshot_date'],
                'fund_manager': r['fund_manager'],
                'dividend_preference': r['dividend_preference'],
                'sources': [],
            },
        )
        g['market_value_cents'] += r['market_value_cents']
        g['quantity'] += r['quantity']
        # 分组级快照日期取「最早」的一笔：代表该数据最滞后的部分，对外展示最诚实
        if r['snapshot_date'] and (not g['snapshot_date'] or r['snapshot_date'] < g['snapshot_date']):
            g['snapshot_date'] = r['snapshot_date']
        if not g['fund_manager']:
            g['fund_manager'] = r['fund_manager']
        if not g['dividend_preference']:
            g['dividend_preference'] = r['dividend_preference']
        g['sources'].append(
            {
                'ledger_id': r['ledger_id'],
                'ledger_name': r['ledger_name'],
                'institution_name': r['institution_name'],
                'institution_alias': r['institution_alias'],
                'market_value_cents': r['market_value_cents'],
                'quantity': r['quantity'],
                'snapshot_date': r['snapshot_date'],
                'fund_manager': r['fund_manager'],
                'nav_yuan': r['nav_yuan'],
            }
        )
    return list(grouped.values())


def _sort_groups(groups: list[dict], sort: str, order: str, dimension: str) -> list[dict]:
    """分组排序。默认按市值降序（用户最高频的诉求：先看最大的持仓）。"""
    if sort not in SORT_FIELDS:
        sort = 'market_value'
    reverse = str(order).lower() != 'asc'

    if sort == 'quantity':
        key = lambda g: g.get('quantity') or 0  # noqa: E731
    elif sort == 'name':
        key = lambda g: g.get('name') or ''  # noqa: E731
    elif sort == 'symbol':
        key = lambda g: str(g.get('symbol') if g.get('symbol') else g.get('key') or '')  # noqa: E731
    else:  # market_value
        key = lambda g: g.get('market_value_cents') or 0  # noqa: E731

    return sorted(groups, key=key, reverse=reverse)


def aggregate_positions(
    session,
    family_id: int,
    asset_types: tuple,
    dimension: str = 'product',
    sort: str = 'market_value',
    order: str = 'desc',
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """聚合某类资产的持仓（#1101 / #1132 共用入口）。

    Args:
        asset_types: 纳入聚合的 `Position.asset_type` 集合（如 fund/money_fund）。
        dimension: 'product' | 'institution'。
        sort: 'market_value'（默认）| 'quantity' | 'name' | 'symbol'。
        order: 'desc'（默认）| 'asc'。
        page: 页码，从 1 开始。
        page_size: 每页条数；传 0 或负数表示不分页（返回全量）。

    Returns:
        {
            total_market_value_cents, dimension, groups,
            total, page, page_size, total_pages,
            snapshot_date, snapshot_date_latest
        }
        其中 `snapshot_date` 为全部持仓中**最早**的快照日（数据最滞后的一笔），
        供页面顶部「数据日期」展示；`snapshot_date_latest` 为最近的一笔，供区间提示。
    """
    if dimension not in AGGREGATION_DIMENSIONS:
        dimension = 'product'

    rows, nav_date_global = _collect_rows(session, family_id, asset_types)

    # 汇总市值与快照区间：基于全量 rows，先于分页计算（分页不应改变汇总口径）
    total_mv = sum(r['market_value_cents'] for r in rows)
    snapshot_dates = [r['snapshot_date'] for r in rows if r['snapshot_date']]

    groups = _group_by_dimension(rows, dimension)
    groups = _sort_groups(groups, sort, order, dimension)

    total = len(groups)
    # 分页：page_size<=0 视为不分页（向后兼容旧调用方）
    if page_size and page_size > 0:
        page_size = min(int(page_size), MAX_PAGE_SIZE)
        page = max(1, int(page))
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        groups = groups[start : start + page_size]
    else:
        page, page_size, total_pages = 1, total, 1

    return {
        'total_market_value_cents': total_mv,
        'dimension': dimension,
        'groups': groups,
        # ── 分页元信息 ──
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        # ── 数据日期：最早 / 最近快照日（无快照记录时为 None）──
        'snapshot_date': min(snapshot_dates) if snapshot_dates else None,
        'snapshot_date_latest': max(snapshot_dates) if snapshot_dates else None,
        # 🔄 净值日期（NavService 取到的最新净值日期；与 snapshot_date 分叉时前端可双日期展示）
        'nav_date': nav_date_global,
    }
