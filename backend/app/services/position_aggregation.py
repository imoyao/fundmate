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
from app.domains.funds.models import Fund, FundType
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
SORT_FIELDS = ('market_value', 'quantity', 'name', 'symbol', 'return_pct')

# fund_type 筛选中「未分类」的占位值（后端约定，前端透传即可）
FUND_TYPE_NONE = '__none__'

# 证券侧资产构成环形图的 asset_type → 中文标签映射（#1264）
ASSET_TYPE_LABELS: dict[str, str] = {'stock': '股票', 'etf': 'ETF', 'bond': '可转债'}

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


def _position_cost_cents(position: Position) -> int:
    """单笔持仓成本（分）：成本均价(0.0001元) × 份额(最小单位)。

    与市值口径（分）同单位，盈亏 = 市值 - 成本。avg_price 缺失（=0）时成本为 0，
    前端对应收益率显示 "--"（不参与收益率排序）。
    """
    return Money.multiply_price_quantity(position.avg_price, position.quantity)


def _matches_fund_type(actual: str | None, wanted: str) -> bool:
    """fund_type 筛选匹配：`FUND_TYPE_NONE` 表示「未分类」占位，其余按小类名精确匹配。"""
    if wanted == FUND_TYPE_NONE:
        return not actual
    return bool(wanted) and actual == wanted


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

    # ── 基金类型（fund_types 小类名：股票型/混合型/债券型/指数型/货币型/基金型）──
    # 供聚合页的类型筛选 Tab。未收录进 funds 名录的产品（手动录入等）为 None，前端归入「未分类」。
    fund_types_by_symbol: Dict[str, str] = {}
    if fund_symbols:
        for fcode, ftype in (
            session.query(Fund.fund_code, FundType.name)
            .join(FundType, Fund.fund_type_id == FundType.id)
            .filter(Fund.fund_code.in_(fund_symbols))
            .all()
        ):
            fund_types_by_symbol[fcode] = ftype
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

        # ── 盈亏派生（分）：成本 = 成本均价×份额；收益 = 市值 - 成本；成本为 0 时收益率 None ──
        mv_cents = _position_market_value_cents(p, effective_nav_yuan=effective_nav)
        cost_cents = _position_cost_cents(p)
        pnl_cents = mv_cents - cost_cents
        return_pct = (pnl_cents / cost_cents) if cost_cents > 0 else None

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
                'market_value_cents': mv_cents,
                'quantity': p.quantity,
                # 参考净值：优先 NavService 最新值，无则回退快照价
                'nav_yuan': effective_nav if effective_nav else Money.price_units_to_yuan(p.current_price),
                # ── 基金类型（来自 funds 名录；未收录为 None）──
                'fund_type': fund_types_by_symbol.get(p.symbol),
                # ── 资产类型（证券侧环形图按此聚类：股票/ETF/可转债）──
                'asset_type': p.asset_type,
                # ── 盈亏（与市值同单位：分）──
                'cost_cents': cost_cents,
                'pnl_cents': pnl_cents,
                'return_pct': return_pct,
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
    """按维度分组。product 按代码聚合并带 sources 明细；institution 按销售机构聚合。

    两维度都汇总成本/盈亏/收益率：product 级是「单只产品」视角，institution 级是「单机构」视角，
    前端卡片与排序（return_pct）统一消费这三个字段。
    """
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
                    # 机构总份额：供「份额」排序（institution 维度此前缺失该字段，
                    # 导致按渠道展示时 quantity/name 排序无效，#1224）
                    'quantity': 0,
                    'cost_cents': 0,
                    'pnl_cents': 0,
                    'return_pct': None,
                    # 「名称」排序键：取机构名（首个非空），缺省空串
                    'name': r['institution_name'],
                    'items': [],
                },
            )
            g['market_value_cents'] += r['market_value_cents']
            g['quantity'] += r['quantity']
            g['cost_cents'] += r['cost_cents']
            g['pnl_cents'] += r['pnl_cents']
            if not g['name']:
                g['name'] = r['institution_name']
            g['items'].append(r)
        for g in grouped.values():
            g['return_pct'] = (g['pnl_cents'] / g['cost_cents']) if g['cost_cents'] > 0 else None
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
                'cost_cents': 0,
                'pnl_cents': 0,
                'return_pct': None,
                # 同一 symbol 各渠道类型一致，取首个非空值即可
                'fund_type': r['fund_type'],
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
        g['cost_cents'] += r['cost_cents']
        g['pnl_cents'] += r['pnl_cents']
        # 分组级快照日期取「最早」的一笔：代表该数据最滞后的部分，对外展示最诚实
        if r['snapshot_date'] and (not g['snapshot_date'] or r['snapshot_date'] < g['snapshot_date']):
            g['snapshot_date'] = r['snapshot_date']
        if not g['fund_type']:
            g['fund_type'] = r['fund_type']
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
                'fund_type': r['fund_type'],
                'cost_cents': r['cost_cents'],
                'pnl_cents': r['pnl_cents'],
                'return_pct': r['return_pct'],
                'snapshot_date': r['snapshot_date'],
                'fund_manager': r['fund_manager'],
                'nav_yuan': r['nav_yuan'],
            }
        )
    for g in grouped.values():
        g['return_pct'] = (g['pnl_cents'] / g['cost_cents']) if g['cost_cents'] > 0 else None
    return list(grouped.values())


def _sort_groups(groups: list[dict], sort: str, order: str, dimension: str) -> list[dict]:
    """分组排序。默认按市值降序（用户最高频的诉求：先看最大的持仓）。

    按渠道（institution）维度：机构分组级排序后，组内 items（单条来源）也按同一排序键
    排列，保证「按渠道展示」下渠道内卡片也有序（修复 #1224：渠道维度 quantity/name 排序无效）。
    """
    if sort not in SORT_FIELDS:
        sort = 'market_value'
    reverse = str(order).lower() != 'asc'

    if sort == 'quantity':
        key = lambda g: g.get('quantity') or 0  # noqa: E731
    elif sort == 'name':
        key = lambda g: g.get('name') or ''  # noqa: E731
    elif sort == 'symbol':
        key = lambda g: str(g.get('symbol') if g.get('symbol') else g.get('key') or '')  # noqa: E731
    elif sort == 'return_pct':
        # 收益率：无成本（return_pct 为 None）的分组恒排最后，不参与值比较
        key = lambda g: (g.get('return_pct') is not None, g.get('return_pct') or 0)  # noqa: E731
    else:  # market_value
        key = lambda g: g.get('market_value_cents') or 0  # noqa: E731

    groups = sorted(groups, key=key, reverse=reverse)
    # 按渠道展示：组内 items 也按同一排序键排列，渠道内卡片有序
    if dimension == 'institution':
        for g in groups:
            g['items'] = sorted(g['items'], key=key, reverse=reverse)
    return groups


def _regroup_page_items(page_items: list[tuple[dict, dict]]) -> list[dict]:
    """按当前页命中的条目重建机构分组（#1265 方案 A 配套）。

    组级汇总（市值/份额/成本/盈亏/收益率）沿用全量口径——它们是「机构」这一层的属性，
    与取哪一页无关；`items` 只保留本页命中的条目，保证前端展平后的卡片数 == 每页条数。

    顺序沿用上游排序（机构间按排序键、机构内 items 同键排序），跨页不重不漏；
    一个机构的 items 可能被分页切开，这是展平分页的预期行为。
    """
    page_groups: list[dict] = []
    index: dict = {}
    for group, item in page_items:
        holder = index.get(group['key'])
        if holder is None:
            holder = {**group, 'items': []}
            index[group['key']] = holder
            page_groups.append(holder)
        holder['items'].append(item)
    return page_groups


def aggregate_positions(
    session,
    family_id: int,
    asset_types: tuple,
    dimension: str = 'product',
    sort: str = 'market_value',
    order: str = 'desc',
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    keyword: str | None = None,
    fund_type: str | None = None,
    breakdown_by: str = 'fund_type',
) -> dict:
    """聚合某类资产的持仓（#1101 / #1132 共用入口）。

    Args:
        asset_types: 纳入聚合的 `Position.asset_type` 集合（如 fund/money_fund）。
        dimension: 'product' | 'institution'。
        sort: 'market_value'（默认）| 'quantity' | 'name' | 'symbol' | 'return_pct'。
        order: 'desc'（默认）| 'asc'。
        page: 页码，从 1 开始。
        page_size: 每页条数；传 0 或负数表示不分页（返回全量）。
        keyword: 名称/代码模糊搜索（大小写不敏感），命中任一即保留。
        fund_type: 基金小类名精确筛选；`FUND_TYPE_NONE` 表示筛选「未分类」。
            过滤在行级执行，对 product / institution 两个维度均生效。
        breakdown_by: 资产构成环形图的聚类维度（#1264）。
            'fund_type'（默认，基金侧按小类名）/ 'asset_type'（证券侧按股票/ETF/可转债）。

    Returns:
        {
            total_market_value_cents, dimension, groups,
            total, page, page_size, total_pages,
            snapshot_date, snapshot_date_latest
        }
        其中 `snapshot_date` 为全部持仓中**最早**的快照日（数据最滞后的一笔），
        供页面顶部「数据日期」展示；`snapshot_date_latest` 为最近的一笔，供区间提示。
        过滤后 `total_market_value_cents` / `snapshot_date` 均基于过滤结果口径。

        `total` 的口径随维度不同（#1265）：
        - product：产品分组数（= 卡片数）；
        - institution：展平后的「产品×渠道」条目数（= 卡片数），
          而非机构分组数——前端按渠道展示时是把组内 items 展平成卡片的。
    """
    if dimension not in AGGREGATION_DIMENSIONS:
        dimension = 'product'

    rows, nav_date_global = _collect_rows(session, family_id, asset_types)

    # ── fund_type 分布统计（基于全量 rows，不受 keyword/fund_type 筛选影响，
    #    供前端动态生成类型 Tab：#1224）──
    fund_type_counts: dict[str, int] = {}
    fund_type_unclassified_count = 0
    # ── 资产构成环形图（基于全量 rows）：按品类维度聚类市值分布（#1264）。
    #    基金侧用 fund_type（小类名），证券侧用 asset_type（股票/ETF/可转债），
    #    二者共用响应字段 fund_type_breakdown，前端 Hero 渲染逻辑无需分叉。
    fund_type_breakdown: dict[str, dict] = {}
    for r in rows:
        ft = r.get('fund_type') or '未分类'
        if ft != '未分类':
            fund_type_counts[ft] = fund_type_counts.get(ft, 0) + 1
        else:
            fund_type_unclassified_count += 1
        raw = r.get(breakdown_by) or '未分类'
        bkey = ASSET_TYPE_LABELS.get(raw, raw) if breakdown_by == 'asset_type' else raw
        item = fund_type_breakdown.setdefault(bkey, {'name': bkey, 'market_value_cents': 0, 'count': 0})
        item['market_value_cents'] += r['market_value_cents']
        item['count'] += 1
    fund_type_breakdown_list = sorted(fund_type_breakdown.values(), key=lambda x: x['market_value_cents'], reverse=True)

    # ── 行级过滤（keyword 模糊 + fund_type 精确）：先于汇总与分页，两维度均生效 ──
    kw = str(keyword or '').strip().lower()
    if kw:
        rows = [r for r in rows if kw in (r.get('name') or '').lower() or kw in (r.get('symbol') or '').lower()]
    if fund_type:
        rows = [r for r in rows if _matches_fund_type(r.get('fund_type'), fund_type)]

    # 汇总市值与快照区间：基于过滤后 rows，先于分页计算（分页不应改变汇总口径）
    total_mv = sum(r['market_value_cents'] for r in rows)
    snapshot_dates = [r['snapshot_date'] for r in rows if r['snapshot_date']]

    groups = _group_by_dimension(rows, dimension)
    groups = _sort_groups(groups, sort, order, dimension)

    # 分页：page_size<=0 视为不分页（向后兼容旧调用方）
    if page_size and page_size > 0:
        page_size = min(int(page_size), MAX_PAGE_SIZE)
        page = max(1, int(page))
    else:
        page, page_size = 1, 0

    if dimension == 'institution':
        # 按渠道展示的分页对象是「展平后的产品×渠道」条目（#1265 方案 A）。
        # 前端把每个机构组内的 items 全量展平成卡片渲染，故分页口径必须与卡片数一致；
        # 此前 total 取的是机构分组数，导致 total_pages 恒为 1 → 分页条被隐藏、卡片一次铺开。
        flattened = [(g, item) for g in groups for item in g['items']]
        total = len(flattened)
        if page_size:
            total_pages = max(1, (total + page_size - 1) // page_size)
            start = (page - 1) * page_size
            groups = _regroup_page_items(flattened[start : start + page_size])
        else:
            total_pages = 1
    else:
        total = len(groups)
        if page_size:
            total_pages = max(1, (total + page_size - 1) // page_size)
            start = (page - 1) * page_size
            groups = groups[start : start + page_size]
        else:
            total_pages = 1

    # 不分页时回传全量条数，保持与既有调用方一致
    if not page_size:
        page_size = total

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
        # 🔄 fund_type 分布：供前端动态生成类型 Tab（只显示有产品的分类）
        'fund_type_counts': fund_type_counts,
        'fund_type_unclassified_count': fund_type_unclassified_count,
        # 🔄 资产构成（按基金类型的市值分布，供环形图/饼图展示占比）
        'fund_type_breakdown': fund_type_breakdown_list,
    }
