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
- **市值口径**：份额(份) × 当前价(元) × 汇率，结果以「分」整数汇总，
  与 summary_service 全局资产计算一致，避免浮点累积误差。
- **维度**：`product`（按产品）/ `institution`（按销售机构）。
  原 `app`（按交易前端）维度已于 #1133 收敛去掉——其本质就是销售机构，属重复维度。

两品类共享本文件，避免 fund_aggregation / securities_aggregation 两份逻辑漂移。
"""

from __future__ import annotations

from decimal import Decimal

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta, SalesInstitution

# 合法聚合维度（app 维度已废弃，见模块 docstring）
AGGREGATION_DIMENSIONS = ('product', 'institution')

# 排序字段白名单：禁止前端传入任意列名拼进排序键
SORT_FIELDS = ('market_value', 'quantity', 'name', 'symbol')

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


def _position_market_value_cents(position: Position) -> int:
    """单笔持仓市值（分），复用 summary_service 口径。"""
    rate = EXCHANGE_RATES.get(position.currency, 1.0)
    yuan = Money.min_unit_to_shares(position.quantity) * Money.price_units_to_yuan(position.current_price) * rate
    return int((Decimal(str(yuan)) * 100).to_integral_value(rounding='ROUND_HALF_UP'))


def _iso_date(value) -> str | None:
    """date → 'YYYY-MM-DD'；None 安全穿透。"""
    return value.isoformat() if value is not None else None


def _collect_rows(session, family_id: int, asset_types: tuple) -> list[dict]:
    """取出该类资产的全部在管持仓，并 join 出展示所需的溯源字段。

    一次批量查 `position_import_meta`（position_id IN ...）后再内存映射，
    避免逐笔查询造成 N+1。
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
        return []

    # ── 批量取溯源元数据（快照日期 / 管理人 / 分红方式 / 平台账号）──
    metas: dict[int, PositionImportMeta] = {}
    position_ids = [p.id for p in positions]
    for meta in session.query(PositionImportMeta).filter(
        PositionImportMeta.position_id.in_(position_ids)
    ).all():
        metas[meta.position_id] = meta

    # ── 批量取账户与销售机构（补全「按机构」维度的机构名）──
    ledger_ids = {p.ledger_id for p in positions if p.ledger_id}
    ledgers: dict[int, Ledger] = {}
    if ledger_ids:
        ledgers = {led.id: led for led in session.query(Ledger).filter(Ledger.id.in_(ledger_ids)).all()}

    institution_ids = {led.sales_institution_id for led in ledgers.values() if led.sales_institution_id}
    institutions: dict[int, str] = {}
    if institution_ids:
        for inst in session.query(SalesInstitution).filter(
            SalesInstitution.id.in_(institution_ids)
        ).all():
            institutions[inst.id] = inst.display_name or inst.org_name

    rows: list[dict] = []
    for p in positions:
        ledger = ledgers.get(p.ledger_id)
        meta = metas.get(p.id)
        institution_id = ledger.sales_institution_id if ledger else None
        rows.append(
            {
                'symbol': p.symbol,
                'name': p.name,
                'ledger_id': p.ledger_id,
                'ledger_name': ledger.name if ledger else None,
                'institution_id': institution_id,
                'institution_name': institutions.get(institution_id) if institution_id else None,
                'market_value_cents': _position_market_value_cents(p),
                # quantity 为 Position.quantity 原始最小单位（份×10000），前端 /10000 转可读份额
                'quantity': p.quantity,
                # 参考净值（元）：positions.current_price 为 0.0001 元单位
                'nav_yuan': Money.price_units_to_yuan(p.current_price),
                # ── 以下来自 position_import_meta，无快照记录时全为 None ──
                'snapshot_date': _iso_date(meta.snapshot_date) if meta else None,
                'fund_manager': meta.fund_manager if meta else None,
                'dividend_preference': meta.dividend_preference if meta else None,
                'fund_account': meta.fund_account if meta else None,
                'trade_account': meta.trade_account if meta else None,
                'source_broker': meta.source_broker if meta else None,
            }
        )
    return rows


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
        if r['snapshot_date'] and (
            not g['snapshot_date'] or r['snapshot_date'] < g['snapshot_date']
        ):
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

    rows = _collect_rows(session, family_id, asset_types)

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
    }
