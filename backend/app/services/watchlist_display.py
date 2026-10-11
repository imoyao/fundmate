# -*- coding: utf-8 -*-
"""自选列表的「展示行组装」层（#1606）。

WHY 独立于 `watchlist_service`
    `watchlist_service` 的职责是**查询 / 写入 / 状态机**（筛选查询、买入即入自选、
    卖出降级状态），而本模块的职责是**把查询结果组装成前端要读的行**——字段别名归一、
    投顾 / 经理 / 可转债 / 指数估值 / 基金回撤 / 跨渠道关联等 enrich、持仓虚拟行构造、
    页内展示字段补算、用户列内排序。两者变化原因不同（改筛选口径 vs 改展示字段），
    故分文件而非并入 `watchlist_service`——否则只是把「1445 行的视图」改名成
    「1600 行的服务」（`conventions.md` §16.2 反对把复杂度搬家）。

WHY 下沉（本模块存在的理由）
    这些函数曾全部长在 `domains/watchlist/views.py`（该文件 1445 行 / 45 次 DB 调用），
    带来两个后果：① 只能在 HTTP 栈里测（`_apply_user_sort` 这类纯函数也被迫挂在视图模块下）；
    ② `tech-debt.md` 记的「自选模块视图层业务逻辑过重 ✅ 已修复」之后仍在原文件里继续生长，
    没有任何边界拦得住（属**债务回潮**）。

边界
    - 本层不碰 `g` / `request`：家庭 ID 由调用方显式传入（与 `watchlist_service` 同规），
      故可脱离请求上下文单测；
    - 只读组装：不提交事务、不写库（`enrich_*` / `list_*` / `build_*` 全为读）；
    - 对外 API 契约零变更（`conventions.md` §2.4）：字段名、嵌套结构与下沉前逐字一致。
"""

from collections import namedtuple
from datetime import date, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy import func, or_, text

from app.core.constants import ALLOCATION_LABELS, MANAGER_SYMBOL_PREFIX, TYPE_LABELS
from app.core.money import Money
from app.domains.funds.models import AdvisorHolding, AdvisorPortfolio, ChannelLink, DailyWorth, Fund, Manager
from app.domains.indices.models import IndexCatalog, IndexValuation
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import ConvertibleBondTerm, Security
from app.domains.watchlist.models import WatchlistGroup, WatchlistItem, WatchlistItemGroup, WatchlistItemTag
from app.domains.watchlist.schemas import WatchlistItemOut
from app.services.fund_metrics import compute_max_drawdown, load_nav_points
from app.services.watchlist_service import (
    _build_quote,
    bare_code_of,
    compute_latest_quote,
    get_filtered_items_query,
    looks_like_exchange_code,
    lookup_manager,
    resolve_display_name,
    resolve_item_display_name,
)

# ── 基金最大回撤（#1285 消费侧「基金」品类 / 设计 §3.10）──
DRAWDOWN_FIXED_WINDOW_DAYS = 365 * 3  # 固定窗口档：近 3 年
DRAWDOWN_FIXED_WINDOW_LABEL = '近3年'
# 样本不足（次新基金/净值稀疏）时不下发数字，只标 basis=insufficient，前端显示 `—`
DRAWDOWN_MIN_SAMPLES = 60


def _to_float(value):
    """Decimal/数值 → float（None 安全）。

    SafeNumeric 落库为 Decimal，若直接塞进响应 dict 会把 Decimal 带进 JSON
    （Flask 默认编码器不认识 Decimal）。统一在此转换。
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_latest_navs(db, fund_codes: list) -> list:
    """批量取每支基金最近 ≤2 条有效净值行，返回 (fund_code, date, unit_nav) 元组列表。

    与逐支 `compute_latest_quote` 的 daily_worth 分支同口径（按 date 降序取 2 条、
    过滤 unit_nav 非空），但把 N 次往返压成 1 条 UNION ALL：
    每个分支走 `idx_daily_worth_code_date_unique` 的降序点查，只碰 2 行；
    窗口函数版会物化 106 支 × ~7000 行净值史（daily_worth 共 754 万行），实测 708ms。
    """
    if not fund_codes:
        return []
    ctes = []
    params: dict = {}
    for i, code in enumerate(fund_codes):
        params[f'c{i}'] = code
        # 每支基金一次索引倒序点查（idx_daily_worth_code_date_unique），只碰 2 行
        ctes.append(
            f't{i} AS (SELECT fund_code, date, unit_nav FROM daily_worth '
            f'WHERE fund_code = :c{i} AND unit_nav IS NOT NULL ORDER BY date DESC LIMIT 2)'
        )
    unions = ' UNION ALL '.join(f'SELECT * FROM t{i}' for i in range(len(fund_codes)))
    sql = text('WITH ' + ', '.join(ctes) + ' ' + unions)
    # raw SQL 不走列类型转换，date 列出来是 'YYYY-MM-DD' 字符串；消费方
    # _build_quote 要求 date 对象（返回的 trade_date 会 .isoformat()），这里统一转。
    # namedtuple 保持与 ORM 行一致的属性访问（消费方用 r.fund_code / r.date）。
    NavRow = namedtuple('NavRow', ['fund_code', 'date', 'unit_nav'])
    out = []
    for fund_code, d, unit_nav in db.execute(sql, params):
        if isinstance(d, str):
            d = date.fromisoformat(d)
        out.append(NavRow(fund_code, d, unit_nav))
    return out


class BatchContext:
    """批量预取上下文：一次性把 enrich 所需的所有 per-symbol 数据按 IN 查齐。

    设计目标：把「158 行 × 8+ 查询」压缩为「~8 条 IN 查询」，与行数无关。
    用法：
        ctx = BatchContext(db, family_id, symbols, need_display_fields=not lite)
        # 后续 enrich_item / _build_holding_row / _enrich_holding_with_watchlist 传 ctx
    """

    def __init__(
        self,
        db,
        family_id: int,
        symbols: list[str],
        need_display_fields: bool = False,
        need_base_fields: bool = True,
    ):
        self.db = db
        self.family_id = family_id
        self.symbols = [s for s in symbols if s]
        self.need_display_fields = need_display_fields
        # need_base_fields=False：只预取展示字段（页级展示 ctx 用，见
        # fill_page_display_fields）——展示段与基础段无数据依赖，可单独跑
        self.need_base_fields = need_base_fields

        # 以下字典均以 symbol 为 key
        self._position_stats: dict[str, dict] = {}
        self._position_market_value: dict[str, float] = {}
        self._avg_current_price: dict[str, float] = {}
        self._position_meta: dict[str, object] = {}
        self._latest_quote: dict[str, dict] = {}
        self._price_at_added: dict[str, Optional[float]] = {}
        self._advisor: dict[str, AdvisorPortfolio] = {}
        self._advisor_ratios: dict[str, list[float]] = {}
        self._manager: dict[str, object] = {}
        self._watchlist_item: dict[str, WatchlistItem] = {}
        # 展示名反查链的名称映射（Security / 可转债 / Fund / IndexCatalog），替代逐行查库
        self._security_names: dict[str, str] = {}
        self._bond_names: dict[str, str] = {}
        self._fund_names: dict[str, str] = {}
        self._index_names: dict[str, str] = {}
        # 分组 / 标签链接（以 item.id 为 key），替代逐 item 的 relationship 懒加载
        self._group_links: dict[int, list[int]] = {}
        self._tag_links: dict[int, list[int]] = {}
        self._group_names: dict[int, str] = {}
        # display fields（仅 need_display_fields=True 时填充）
        self._bond_terms: dict[str, ConvertibleBondTerm] = {}
        self._index_valuations: dict[str, IndexValuation] = {}
        self._fund_drawdowns: dict[str, dict] = {}
        self._channel_links: dict[str, list[ChannelLink]] = {}

        self._prefetch_all()

    def _prefetch_all(self):
        if not self.symbols:
            return
        if not self.need_base_fields:
            # 页级展示 ctx：只跑展示段（与基础段无数据依赖），提前返回
            if self.need_display_fields:
                self._prefetch_display_fields()
            return
        # 1. positions 聚合统计（qty_units, cost_raw, value_raw）
        pos_rows = (
            self.db.query(
                Position.symbol,
                func.sum(Position.quantity).label('qty_units'),
                func.sum(Position.quantity * Position.avg_price).label('cost_raw'),
                func.sum(Position.quantity * Position.current_price).label('value_raw'),
            )
            .filter(Position.symbol.in_(self.symbols), Position.family_id == self.family_id)
            .group_by(Position.symbol)
            .all()
        )
        for r in pos_rows:
            qty_units = r.qty_units
            if not qty_units:
                continue
            qty = Money.min_unit_to_shares(qty_units)
            cost_yuan = Money.cents_to_yuan(Money.multiply_price_quantity(r.cost_raw, 1))
            value_yuan = Money.cents_to_yuan(Money.multiply_price_quantity(r.value_raw, 1))
            cost_price = cost_yuan / qty if qty else 0.0
            pnl = value_yuan - cost_yuan
            pnl_pct = (pnl / cost_yuan * 100) if cost_yuan else 0.0
            self._position_stats[r.symbol] = {
                'quantity': qty,
                'cost_price': cost_price,
                'pnl': pnl,
                'pnl_percent': pnl_pct,
            }
            self._position_market_value[r.symbol] = round(value_yuan, 2)

        # 2. 平均市价
        avg_rows = (
            self.db.query(Position.symbol, func.avg(Position.current_price))
            .filter(Position.symbol.in_(self.symbols), Position.family_id == self.family_id)
            .group_by(Position.symbol)
            .all()
        )
        for sym, avg_units in avg_rows:
            if avg_units:
                self._avg_current_price[sym] = Money.price_units_to_yuan(avg_units)

        # 3. 代表持仓行（market / asset_type / name）：替代 _build_holding_row 里
        #    逐 symbol 的 `Position...first()`。order_by(id) 取首行，与 .first() 的
        #    「任意一行」语义一致（SQLite 默认按 rowid 返回，id 升序即首行）。
        meta_rows = (
            self.db.query(Position.symbol, Position.market, Position.asset_type, Position.name)
            .filter(
                Position.symbol.in_(self.symbols),
                Position.family_id == self.family_id,
                Position.ownership_status == 'active',
            )
            .order_by(Position.id)
            .all()
        )
        for r in meta_rows:
            self._position_meta.setdefault(r.symbol, r)

        # 4. 最新行情：窗口函数一次取每 symbol 最近 2 根，替代逐 symbol 的
        #    compute_latest_quote（每次 1~2 条查询 × 158 行 = 主要残留 N+1）。
        rn = (
            func.row_number()
            .over(partition_by=PriceHistory.symbol, order_by=PriceHistory.trade_date.desc())
            .label('rn')
        )
        ph_sub = (
            self.db.query(PriceHistory.symbol, PriceHistory.trade_date, PriceHistory.close, rn)
            .filter(PriceHistory.symbol.in_(self.symbols), PriceHistory.close.isnot(None))
            .subquery()
        )
        ph_rows = self.db.query(ph_sub.c.symbol, ph_sub.c.trade_date, ph_sub.c.close).filter(ph_sub.c.rn <= 2).all()
        by_sym: dict[str, list] = {}
        for r in ph_rows:
            by_sym.setdefault(r.symbol, []).append(r)
        for sym, rows in by_sym.items():
            rows.sort(key=lambda r: r.trade_date, reverse=True)
            q = _build_quote(rows[0].trade_date, rows[0].close, rows[1].close if len(rows) > 1 else None)
            if q:
                self._latest_quote[sym] = q
        # 4b. 场外基金兜底：6 位纯数字代码且 price_history 无有效行情时查 daily_worth
        #     （与 compute_latest_quote 的分支顺序一致：先场内、再净值）。
        #     每支基金用 (fund_code, date) 唯一索引做「降序 LIMIT 2」点查再 UNION ALL：
        #     daily_worth 有 754 万行（每支基金 ~7000 天净值史），窗口函数会把 106 支
        #     × 7000 行全部物化排序，实测单条 708ms（2026-10-11 profiling），点查版 ~3ms。
        nav_syms = [s for s in self.symbols if s and len(s) == 6 and s.isdigit() and s not in self._latest_quote]
        if nav_syms:
            dw_rows = _fetch_latest_navs(self.db, nav_syms)
            nav_by: dict[str, list] = {}
            for r in dw_rows:
                nav_by.setdefault(r.fund_code, []).append(r)
            for code, rows in nav_by.items():
                rows.sort(key=lambda r: r.date, reverse=True)
                q = _build_quote(rows[0].date, rows[0].unit_nav, rows[1].unit_nav if len(rows) > 1 else None)
                if q:
                    self._latest_quote[code] = q

        # 5. WatchlistItem（自选记录 + 添加日价格 cutoff）
        items = (
            self.db.query(WatchlistItem)
            .filter(WatchlistItem.symbol.in_(self.symbols), WatchlistItem.family_id == self.family_id)
            .all()
        )
        for item in items:
            self._watchlist_item[item.symbol] = item
        # 添加日价格：单条 CTE + 相关子查询（每 cutoff 一次索引 LIMIT 1），替代逐 item 查库。
        # 语义与 _compute_price_at_added 逐字一致：≤ created 的最近一行 close（可为 NULL → None）。
        cutoff_pairs = []
        for item in items:
            created = item.created_at.date() if item.created_at else None
            if created:
                cutoff_pairs.append((item.symbol, created.isoformat()))
        if cutoff_pairs:
            params = {}
            values_sql = []
            for i, (sym, created_iso) in enumerate(cutoff_pairs):
                params[f's{i}'] = sym
                params[f'd{i}'] = created_iso
                values_sql.append(f'(:s{i}, :d{i})')
            sql = text(
                'WITH c(symbol, created) AS (VALUES ' + ','.join(values_sql) + ') '
                'SELECT c.symbol AS sym, ('
                'SELECT p.close FROM price_history p '
                'WHERE p.symbol = c.symbol AND p.trade_date <= c.created '
                'ORDER BY p.trade_date DESC LIMIT 1) AS close FROM c'
            )
            for r in self.db.execute(sql, params):
                if r.close is not None:
                    self._price_at_added[r.sym] = round(float(r.close), 4)

        # 5b. 分组 / 标签链接 + 分组名：替代逐 item 的 group_links / tag_links
        #     relationship 懒加载（每 item 2 条查询 × 158 行）。
        item_ids = [it.id for it in items]
        if item_ids:
            for item_id, group_id in (
                self.db.query(WatchlistItemGroup.item_id, WatchlistItemGroup.group_id)
                .filter(WatchlistItemGroup.item_id.in_(item_ids))
                .all()
            ):
                self._group_links.setdefault(item_id, []).append(group_id)
            for item_id, tag_id in (
                self.db.query(WatchlistItemTag.item_id, WatchlistItemTag.tag_id)
                .filter(WatchlistItemTag.item_id.in_(item_ids))
                .all()
            ):
                self._tag_links.setdefault(item_id, []).append(tag_id)
            group_ids = [g for links in self._group_links.values() for g in links]
            if group_ids:
                for gid, gname in (
                    self.db.query(WatchlistGroup.id, WatchlistGroup.name).filter(WatchlistGroup.id.in_(group_ids)).all()
                ):
                    self._group_names[gid] = gname

        # 5. AdvisorPortfolio + AdvisorHolding
        advisors = self.db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code.in_(self.symbols)).all()
        for adv in advisors:
            self._advisor[adv.code] = adv
            ratios = [
                float(r[0])
                for r in self.db.query(AdvisorHolding.after_ratio).filter_by(portfolio_id=adv.id).all()
                if r[0] is not None
            ]
            if ratios:
                self._advisor_ratios[adv.code] = ratios

        # 6. Manager（watchlist symbol 为 MGR_<mgr_code>，需去前缀；symbol 已在入库时归一为大写）
        manager_codes = []
        for sym in self.symbols:
            if sym.startswith(MANAGER_SYMBOL_PREFIX):
                code = sym[len(MANAGER_SYMBOL_PREFIX) :]
                if code:
                    manager_codes.append(code.upper())  # 归一大写，便于后续按大写 symbol 查
        if manager_codes:
            managers = self.db.query(Manager).filter(func.upper(Manager.mgr_code).in_(manager_codes)).all()
            for m in managers:
                # key 用完整 symbol（MGR_XXX），便于后续直接按 symbol 取
                full_sym = MANAGER_SYMBOL_PREFIX + m.mgr_code.upper()
                self._manager[full_sym] = m

        # 7. 展示名反查链的名称映射（Security / 可转债 / Fund / IndexCatalog）：
        #    resolve_display_name 原本逐行最多 6 条查询，这里一次性按 IN 查齐，
        #    由 ctx.resolve_display_name 按**同一优先级链**纯内存组装（见下方方法）。
        sec_rows = self.db.query(Security.symbol, Security.name).filter(Security.symbol.in_(self.symbols)).all()
        self._security_names = {s: n for s, n in sec_rows if n}
        bond_name_rows = (
            self.db.query(ConvertibleBondTerm.symbol, ConvertibleBondTerm.name)
            .filter(ConvertibleBondTerm.symbol.in_(self.symbols))
            .all()
        )
        self._bond_names = {s: n for s, n in bond_name_rows if n}
        # Fund：精确码（全 symbol）+ 裸码（仅场内形态，#2029 形态闸门——防 ZH/MGR 码空间
        # 的数字撞基金名）。
        fund_lookup_codes = set()
        for s in self.symbols:
            fund_lookup_codes.add(s)
            if looks_like_exchange_code(s):
                bare = bare_code_of(s)
                if bare and bare != s:
                    fund_lookup_codes.add(bare)
        if fund_lookup_codes:
            fund_rows = (
                self.db.query(Fund.fund_code, Fund.name).filter(Fund.fund_code.in_(list(fund_lookup_codes))).all()
            )
            self._fund_names = {c: n for c, n in fund_rows if n}
        # IndexCatalog：只按裸码存名，查询侧仅 asset_type=='index' 时命中（#1497 不回退 funds）
        bare_codes = [b for b in (bare_code_of(s) for s in self.symbols) if b]
        if bare_codes:
            idx_rows = (
                self.db.query(IndexCatalog.index_code, IndexCatalog.name)
                .filter(IndexCatalog.index_code.in_(bare_codes))
                .all()
            )
            self._index_names = {c: n for c, n in idx_rows if n}

        # 8. 展示专用字段（仅 need_display_fields 时；实现抽成独立方法，
        #    供页级展示 ctx 在 need_base_fields=False 时单独执行）
        if self.need_display_fields:
            self._prefetch_display_fields()

    def _prefetch_display_fields(self):
        """展示专用字段预取（section 8，独立成段）。

        与基础段（持仓聚合/行情等）无数据依赖，可单独执行：页级展示 ctx
        （fill_page_display_fields，need_base_fields=False）只跑本段，
        不为 20 行页面重复预取全部 158 行的基础字段。
        """
        # 8a. 可转债条款
        bond_rows = self.db.query(ConvertibleBondTerm).filter(ConvertibleBondTerm.symbol.in_(self.symbols)).all()
        for b in bond_rows:
            self._bond_terms[b.symbol] = b

        # 8b. 指数估值
        bare_codes = [_bare_code(s) for s in self.symbols if _bare_code(s)]
        if bare_codes:
            idx_rows = (
                self.db.query(IndexValuation)
                .filter(IndexValuation.index_code.in_(bare_codes))
                .order_by(IndexValuation.trade_date.desc())
                .all()
            )
            seen = set()
            for row in idx_rows:
                if row.index_code not in seen:
                    self._index_valuations[row.index_code] = row
                    seen.add(row.index_code)

        # 8c. 基金回撤（近 3 年 daily_worth）。口径与 _apply_fund_drawdown_fields
        #     一致：按 asset_type=='fund' 识别基金——真实 symbol 是 6 位裸码
        #     （'001414'），与股票同形，**不能按 'OF.'/'fund_' 前缀猜**（早期版本
        #     按前缀过滤，在真实数据上恒为空 → 全部误报 insufficient）。
        #     从 watchlist + positions 两表反查 asset_type（两条 IN 点查）；
        #     行级 gate 仍以行自身 asset_type 为准，这里按并集多算无害，
        #     少算会让基金行误报 insufficient。
        wl_types = dict(
            self.db.query(WatchlistItem.symbol, WatchlistItem.asset_type)
            .filter(WatchlistItem.family_id == self.family_id, WatchlistItem.symbol.in_(self.symbols))
            .all()
        )
        pos_types = dict(
            self.db.query(Position.symbol, Position.asset_type)
            .filter(Position.family_id == self.family_id, Position.symbol.in_(self.symbols))
            .all()
        )
        fund_syms = {s for s, t in wl_types.items() if (t or '').lower() == 'fund'}
        fund_syms |= {s for s, t in pos_types.items() if (t or '').lower() == 'fund'}
        bare_fund_codes = sorted({c for c in (_bare_code(s) for s in fund_syms) if c})
        if bare_fund_codes:
            since = date.today() - timedelta(days=DRAWDOWN_FIXED_WINDOW_DAYS)
            # 只取计算所需 4 列（load_nav_points 按属性名取值，列元组同样满足），
            # 比整实体少构造 DailyWorth ORM 对象（每基金 ~1095 行/3 年）
            nav_rows = (
                self.db.query(DailyWorth.fund_code, DailyWorth.date, DailyWorth.acc_nav, DailyWorth.unit_nav)
                .filter(DailyWorth.fund_code.in_(bare_fund_codes), DailyWorth.date >= since)
                .order_by(DailyWorth.fund_code, DailyWorth.date)
                .all()
            )
            by_code = {}
            for r in nav_rows:
                by_code.setdefault(r.fund_code, []).append(r)
            for code, rows in by_code.items():
                result = compute_max_drawdown(load_nav_points(rows))
                if result and result.sample_size >= DRAWDOWN_MIN_SAMPLES:
                    self._fund_drawdowns[code] = {
                        'max_drawdown': round(result.max_drawdown, 2),
                        'basis': 'fixed_3y',
                        'window': DRAWDOWN_FIXED_WINDOW_LABEL,
                        'as_of': result.as_of,
                    }

        # 8d. 跨渠道关联
        if bare_codes:
            link_rows = (
                self.db.query(ChannelLink)
                .filter(or_(ChannelLink.from_symbol.in_(bare_codes), ChannelLink.to_symbol.in_(bare_codes)))
                .all()
            )
            for r in link_rows:
                for code in (r.from_symbol, r.to_symbol):
                    self._channel_links.setdefault(code, []).append(r)

    # —— 取数接口（enrich 函数调用）——
    def get_position_stats(self, symbol: str) -> Optional[dict]:
        return self._position_stats.get(symbol)

    def get_position_market_value(self, symbol: str) -> float:
        return self._position_market_value.get(symbol, 0.0)

    def get_avg_current_price(self, symbol: str) -> float:
        return self._avg_current_price.get(symbol, 0.0)

    def get_latest_quote(self, symbol: str) -> Optional[dict]:
        return self._latest_quote.get(symbol)

    def get_price_at_added(self, symbol: str) -> Optional[float]:
        return self._price_at_added.get(symbol)

    def get_advisor(self, symbol: str) -> Optional[AdvisorPortfolio]:
        return self._advisor.get(symbol)

    def get_advisor_ratios(self, symbol: str) -> Optional[list[float]]:
        return self._advisor_ratios.get(symbol)

    def get_manager(self, symbol: str) -> Optional[object]:
        return self._manager.get(symbol)

    def get_watchlist_item(self, symbol: str) -> Optional[WatchlistItem]:
        return self._watchlist_item.get(symbol)

    def get_position_meta(self, symbol: str):
        """代表持仓行（symbol/market/asset_type/name 列），_build_holding_row 构造虚拟行用。"""
        return self._position_meta.get(symbol)

    def get_group_ids(self, item_id: int) -> list[int]:
        return list(self._group_links.get(item_id, []))

    def get_tag_ids(self, item_id: int) -> list[int]:
        return list(self._tag_links.get(item_id, []))

    def get_group_names(self, item_id: int) -> list[str]:
        return [self._group_names[g] for g in self._group_links.get(item_id, []) if g in self._group_names]

    def resolve_display_name(self, symbol: str, asset_type: Optional[str] = None) -> str:
        """展示名反查链的**批量版**——优先级与 watchlist_service.resolve_display_name 逐字一致：
        Manager → Security → 可转债 → AdvisorPortfolio → IndexCatalog(仅 index，不回退 funds，#1497)
        / Fund(精确 + 场内形态裸码回退，#2029) → symbol 兜底。
        ⚠️ 改链序必须同步改原函数，两者禁止漂移。
        """
        mgr = self._manager.get(symbol)
        if mgr and mgr.name:
            return mgr.name
        sec = self._security_names.get(symbol)
        if sec:
            return sec
        bond = self._bond_names.get(symbol)
        if bond:
            return bond
        adv = self._advisor.get(symbol)
        if adv and adv.name:
            return adv.name
        if (asset_type or '').strip().lower() == 'index':
            # 指数语义已确定 → 只认 index_catalog，未命中不回退 funds（#1497）
            idx = self._index_names.get(bare_code_of(symbol))
            if idx:
                return idx
        else:
            fund = self._fund_names.get(symbol)
            if fund:
                return fund
            # 裸码回退带形态闸门（#2029）：只对指数/场内形态开放，防 ZH/MGR 码空间数字撞基金名
            if looks_like_exchange_code(symbol):
                bare = bare_code_of(symbol)
                if bare and bare != symbol:
                    fund = self._fund_names.get(bare)
                    if fund:
                        return fund
        return symbol

    def resolve_item_display_name(self, item: WatchlistItem) -> str:
        """快照优先版展示名（#1508）——与 watchlist_service.resolve_item_display_name 同语义。"""
        snap = (getattr(item, 'name', None) or '').strip()
        if snap:
            return snap
        return self.resolve_display_name(item.symbol, item.asset_type)

    # display fields
    def get_bond_term(self, symbol: str) -> Optional[ConvertibleBondTerm]:
        return self._bond_terms.get(symbol)

    def get_index_valuation(self, symbol: str) -> Optional[IndexValuation]:
        code = _bare_code(symbol)
        return self._index_valuations.get(code) if code else None

    def get_fund_drawdown(self, symbol: str) -> Optional[dict]:
        code = _bare_code(symbol)
        return self._fund_drawdowns.get(code) if code else None

    def get_channel_links(self, symbol: str) -> list[ChannelLink]:
        code = _bare_code(symbol)
        return self._channel_links.get(code, []) if code else []


def _bare_code(symbol: str) -> str:
    """'SH000300' / 'CSI930950' / 'OF000001' → '000300' / '930950' / '000001'。

    指数估值表（index_valuations）与基金净值表（daily_worth）都按**裸代码**存储，
    故统一在此抽取数字部分。
    """
    return ''.join(ch for ch in (symbol or '') if ch.isdigit())


# ────────────────────────── 展示专用 enrich（可延后补算） ──────────────────────────


def _apply_bond_fields(out: dict, symbol: str, db) -> None:
    """可转债条款 enrich（#1285 消费侧 / #1393）。

    仅当 convertible_bond_terms 命中该 symbol 时填充（表未落库/非转债则一律保持
    None，前端据此显示 `—`，不渲染假数据）。
    """
    term = db.query(ConvertibleBondTerm).filter_by(symbol=symbol).first()
    if term is None:
        return
    out['bond_convert_price'] = _to_float(term.convert_price)
    out['bond_convert_value'] = _to_float(term.convert_value)
    out['bond_premium_rate'] = _to_float(term.premium_rate)
    out['bond_force_redeem_price'] = _to_float(term.force_redeem_price)
    out['bond_redeem_count'] = term.redeem_count
    out['bond_redeem_required'] = term.redeem_required
    out['bond_redeem_status'] = term.redeem_status
    out['bond_rating'] = term.rating
    out['bond_maturity_date'] = term.maturity_date
    out['bond_remain_size'] = _to_float(term.remain_size)
    out['bond_issue_size'] = _to_float(term.issue_size)
    out['bond_stock_name'] = term.stock_name


def _apply_index_valuation_fields(out: dict, symbol: str, db) -> None:
    """指数估值 enrich（#1285 消费侧「指数」品类 / #1394）。

    取该指数**最新一期**估值（历史序列留给后续的估值详情页）；表为空或该指数没有
    官方估值文件时保持 None —— 前端显示 `—`，不编造数据。
    """
    code = _bare_code(symbol)
    if not code:
        return
    row = (
        db.query(IndexValuation)
        .filter(IndexValuation.index_code == code)
        .order_by(IndexValuation.trade_date.desc())
        .first()
    )
    if row is None:
        return
    out['index_pe'] = _to_float(row.pe_1)
    out['index_pe_2'] = _to_float(row.pe_2)
    out['index_dividend_yield'] = _to_float(row.dividend_yield_1)
    out['index_valuation_date'] = row.trade_date


def _apply_fund_drawdown_fields(out: dict, symbol: str, asset_type: str, db) -> None:
    """基金最大回撤 enrich（口径见设计 §3.10「存口径元数据，不只存数字」）。

    **本期口径**：固定窗口「近 3 年」，日频，基于 `daily_worth.acc_nav`（累计净值）
    自算，`basis='fixed_3y'`。

    为何不是「现任经理任期」：§3.10 对**主动权益类**要求绑定有效管理人任期，该档位
    依赖经理任期 / 历任任期业绩 / 同类排名数据（均未接入），故本期不产出
    `current_tenure` / `prev_tenure` 两档；字段与前端色板已按 basis 预留，
    数据接入后只需在此处改 `basis` 选择逻辑，算法与服务层无需改动。
    """
    # 仅场外基金：daily_worth 按 6 位基金代码存净值；货基用万份收益口径，不适用本算法
    if (asset_type or '').lower() != 'fund':
        return
    code = _bare_code(symbol)
    if not code:
        return

    since = date.today() - timedelta(days=DRAWDOWN_FIXED_WINDOW_DAYS)
    rows = (
        db.query(DailyWorth)
        .filter(DailyWorth.fund_code == code, DailyWorth.date >= since)
        .order_by(DailyWorth.date)
        .all()
    )
    result = compute_max_drawdown(load_nav_points(rows))
    if result is None or result.sample_size < DRAWDOWN_MIN_SAMPLES:
        out['fund_max_drawdown_basis'] = 'insufficient'
        return

    out['fund_max_drawdown'] = round(result.max_drawdown, 2)
    out['fund_max_drawdown_basis'] = 'fixed_3y'
    out['fund_max_drawdown_window'] = DRAWDOWN_FIXED_WINDOW_LABEL
    out['fund_max_drawdown_as_of'] = result.as_of


def _apply_channel_link_fields(out: dict, symbol: str, db) -> None:
    """跨渠道关联 enrich（#1285 设计 §3.8）：数量角标 + 浮层明细。

    `channel_links` 存**有向**关系（index→etf），但本函数按裸代码**双向查**并对任一端
    都返回「另一侧」清单：指数行看到 ETF、ETF 行看到指数，前端无需判断方向。
    无关联时不写字段（前端渲染 `—`）。
    """
    code = _bare_code(symbol)
    if not code:
        return
    rows = db.query(ChannelLink).filter(or_(ChannelLink.from_symbol == code, ChannelLink.to_symbol == code)).all()
    if not rows:
        return
    links = []
    for r in rows:
        if r.from_symbol == code:
            links.append({'code': r.to_symbol, 'name': r.to_name, 'link_type': r.link_type})
        else:
            links.append({'code': r.from_symbol, 'name': r.from_name, 'link_type': r.link_type})
    out['link_count'] = len(links)
    out['links'] = links


def _apply_bond_fields_cached(out: dict, symbol: str, ctx: BatchContext) -> None:
    term = ctx.get_bond_term(symbol)
    if term is None:
        return
    out['bond_convert_price'] = _to_float(term.convert_price)
    out['bond_convert_value'] = _to_float(term.convert_value)
    out['bond_premium_rate'] = _to_float(term.premium_rate)
    out['bond_force_redeem_price'] = _to_float(term.force_redeem_price)
    out['bond_redeem_count'] = term.redeem_count
    out['bond_redeem_required'] = term.redeem_required
    out['bond_redeem_status'] = term.redeem_status
    out['bond_rating'] = term.rating
    out['bond_maturity_date'] = term.maturity_date
    out['bond_remain_size'] = _to_float(term.remain_size)
    out['bond_issue_size'] = _to_float(term.issue_size)
    out['bond_stock_name'] = term.stock_name


def _apply_index_valuation_fields_cached(out: dict, symbol: str, ctx: BatchContext) -> None:
    row = ctx.get_index_valuation(symbol)
    if row is None:
        return
    out['index_pe'] = _to_float(row.pe_1)
    out['index_pe_2'] = _to_float(row.pe_2)
    out['index_dividend_yield'] = _to_float(row.dividend_yield_1)
    out['index_valuation_date'] = row.trade_date


def _apply_fund_drawdown_fields_cached(out: dict, symbol: str, asset_type: str, ctx: BatchContext) -> None:
    if (asset_type or '').lower() != 'fund':
        return
    dd = ctx.get_fund_drawdown(symbol)
    if not dd:
        out['fund_max_drawdown_basis'] = 'insufficient'
        return
    out['fund_max_drawdown'] = dd['max_drawdown']
    out['fund_max_drawdown_basis'] = dd['basis']
    out['fund_max_drawdown_window'] = dd['window']
    out['fund_max_drawdown_as_of'] = dd['as_of']


def _apply_channel_link_fields_cached(out: dict, symbol: str, ctx: BatchContext) -> None:
    rows = ctx.get_channel_links(symbol)
    if not rows:
        return
    code = _bare_code(symbol)
    links = []
    for r in rows:
        if r.from_symbol == code:
            links.append({'code': r.to_symbol, 'name': r.to_name, 'link_type': r.link_type})
        else:
            links.append({'code': r.from_symbol, 'name': r.from_name, 'link_type': r.link_type})
    out['link_count'] = len(links)
    out['links'] = links


def _apply_advisor_fields(out: dict, symbol: str, db) -> None:
    """投顾品类差异化指标 enrich（#1392）。

    命中 AdvisorPortfolio（按 code=symbol）时补充：平台/主理人/策略类型（#1167）+ 区间收益
    （return_1w/1m/1y/ytd/since_incep，来自天天 SYL_* 实测映射）+ 最大回撤/超额/业绩基准
    （API 不直接提供时为空）+ 持仓集中度（HHI = Σ占比²，由 advisor_holdings.after_ratio 现算）。
    非投顾标的（advisor 为 None）时上述字段一律置 None —— 前端品类列据此渲染 `—`，不编造。
    """
    # #1392 投顾品类列所需字段（区间收益 + 回撤 + 超额），统一先在 out 挂默认 None，
    # 命中 advisor 再覆盖，避免非投顾标的漏字段导致前端 key 缺失
    _ADVISOR_METRIC_KEYS = (
        'return_1d',
        'return_1w',
        'return_1m',
        'return_1q',
        'return_6m',
        'return_1y',
        'return_ytd',
        'return_since_incep',
        'max_drawdown',
        'excess_return',
        # #1468 且慢组合补充指标（GetStrategyDetails 实时抓取）
        'volatility',
        'sharpe_ratio',
    )
    for k in _ADVISOR_METRIC_KEYS:
        out[k] = None
    out['advisor_benchmark'] = None
    out['advisor_holding_count'] = None
    out['advisor_concentration'] = None
    # #1468 且慢策展元数据（配置目标 / 产品类型 / 简介 / 净值 / 官方链接）
    out['advisor_allocation'] = None
    out['advisor_allocation_label'] = None
    out['advisor_product_type'] = None
    out['advisor_strategy_summary'] = None
    out['advisor_nav'] = None
    out['advisor_nav_date'] = None
    out['advisor_source_url'] = None
    # #1167 既有字段默认 None（命中再覆盖）
    out['advisor_platform'] = None
    out['advisor_host'] = None
    out['advisor_strategy_type'] = None
    out['advisor_org_name'] = None

    advisor = db.query(AdvisorPortfolio).filter_by(code=symbol).first()
    if advisor is None:
        return
    out['advisor_platform'] = advisor.platform
    out['advisor_host'] = advisor.host
    out['advisor_strategy_type'] = advisor.strategy_type
    out['advisor_org_name'] = advisor.org_name
    for k in _ADVISOR_METRIC_KEYS:
        out[k] = _to_float(getattr(advisor, k))
    out['advisor_benchmark'] = advisor.benchmark
    # 配置目标（五笔钱）：key 与中文标签都给，前端免于手抄一份词表
    alloc = advisor.allocation
    out['advisor_allocation'] = alloc
    out['advisor_allocation_label'] = ALLOCATION_LABELS.get(alloc, alloc) if alloc else None
    out['advisor_product_type'] = advisor.product_type
    out['advisor_strategy_summary'] = advisor.strategy_summary
    out['advisor_nav'] = _to_float(advisor.nav)
    out['advisor_nav_date'] = advisor.nav_date.isoformat() if advisor.nav_date else None
    out['advisor_source_url'] = advisor.source_url
    # 持仓集中度：HHI = Σ(占比%²)，越高越集中；同时给持仓基金数（信息密度）
    ratios = [
        float(r[0])
        for r in db.query(AdvisorHolding.after_ratio).filter_by(portfolio_id=advisor.id).all()
        if r[0] is not None
    ]
    if ratios:
        out['advisor_holding_count'] = len(ratios)
        out['advisor_concentration'] = round(sum(r * r for r in ratios), 1)
    else:
        out['advisor_holding_count'] = 0
        out['advisor_concentration'] = None


def apply_deferred_display_fields(
    out: dict, symbol: str, asset_type: str, db, ctx: Optional[BatchContext] = None
) -> None:
    """「展示专用」enrich 统一入口（可延后到分页之后补算）。

    这四个 enricher 只填充**展示**字段（可转债条款 / 指数估值 / 基金最大回撤 /
    跨渠道关联），**均不在 `USER_SORTABLE_FIELDS` 白名单内**，即排序不依赖它们；
    而它们各自要按 symbol 查库（基金回撤还需按 fund_code 扫 `daily_worth` 近 3 年序列，
    是本接口最贵的单点，实测占总耗时 ~55%）。

    `list_items` 因此先用 `defer_display=True` 建全量行 → 排序 → 分页 → 只对本页补算，
    避免「页大小 20 却为 164 行全部算回撤」的浪费；`fields=lite` 则完全跳过
    （供前端仅取汇总口径的全量拉取使用，见 useWatchlistData.fetchAllItems）。

    ⚠️ 新增**展示专用**字段请加在此处，并确认未登记进 `USER_SORTABLE_FIELDS`；
    若新增字段需要参与排序，则不能延后，必须留在基础 enrich 内。
    """
    if ctx and ctx.need_display_fields:
        _apply_bond_fields_cached(out, symbol, ctx)
        _apply_index_valuation_fields_cached(out, symbol, ctx)
        _apply_fund_drawdown_fields_cached(out, symbol, asset_type, ctx)
        _apply_channel_link_fields_cached(out, symbol, ctx)
    else:
        # 回退到逐行查库（兼容旧调用 / export_items_rows 等不传 ctx 的场景）
        _apply_bond_fields(out, symbol, db)
        _apply_index_valuation_fields(out, symbol, db)
        _apply_fund_drawdown_fields(out, symbol, asset_type, db)
        _apply_channel_link_fields(out, symbol, db)


# ────────────────────────── 行组装 ──────────────────────────


def enrich_item(
    item: WatchlistItem, db, family_id: int, defer_display: bool = False, ctx: Optional[BatchContext] = None
) -> dict:
    """把自选模型实例组装成前端行（基础字段 + 持仓统计 + 展示专用字段）。"""
    out = WatchlistItemOut.model_validate(item).model_dump()
    # watchlist.asset_type 历史存放大写（STOCK/ETF/...），对外统一归一为小写，
    # 与后端 asset_types 单一来源（stock/etf/fund/bond/index）及 positions 域保持一致（#1171）。
    out['asset_type'] = item.asset_type.lower() if item.asset_type else None
    # 资产类型中文标签：单一来源 app.core.constants.TYPE_LABELS（#1171 枚举一致性），
    # 供前端「资产类型」列（#1332 候选列）直接展示，免前端再映射。
    out['type_label'] = TYPE_LABELS.get(out['asset_type']) or out['asset_type'] or ''
    # 传归一后的 asset_type：裸码跨表不唯一（SH000906 的 000906 同时命中 index_catalog
    # 与 funds），指数须据此优先查 index_catalog，否则会被错标成一只场外基金名（#1497）。
    # #1508 起**优先用 watchlist.name 快照**（创建时随搜索回显落库），快照缺失才走反查链。
    if ctx:
        out['display_name'] = ctx.resolve_item_display_name(item)
        out['group_ids'] = ctx.get_group_ids(item.id)
        out['tag_ids'] = ctx.get_tag_ids(item.id)
        # 所属分组名称列表（#1332 排序用，避免前端再映射 group_ids）
        out['group_names'] = ctx.get_group_names(item.id)
    else:
        out['display_name'] = resolve_item_display_name(item, db)
        out['group_ids'] = [link.group_id for link in item.group_links]
        out['tag_ids'] = [link.tag_id for link in item.tag_links]
        # 所属分组名称列表（#1332 排序用，避免前端再映射 group_ids）
        out['group_names'] = [link.watchlist_group.name for link in item.group_links if link.watchlist_group]

    # 投顾组合补充信息（#1167 / #1392 投顾品类差异化指标）：平台 / 主理人 / 策略类型 +
    # 区间收益 / 回撤 / 超额 / 业绩基准 / 持仓集中度。普通标的字段一律 None，
    # 前端 product 列按需渲染第二行元信息，品类列按 appliesTo=["portfolio"] 显示。
    if ctx:
        advisor = ctx.get_advisor(item.symbol)
        if advisor:
            out['advisor_platform'] = advisor.platform
            out['advisor_host'] = advisor.host
            out['advisor_strategy_type'] = advisor.strategy_type
            out['advisor_org_name'] = advisor.org_name
            _ADVISOR_METRIC_KEYS = (
                'return_1d',
                'return_1w',
                'return_1m',
                'return_1q',
                'return_6m',
                'return_1y',
                'return_ytd',
                'return_since_incep',
                'max_drawdown',
                'excess_return',
                'volatility',
                'sharpe_ratio',
            )
            for k in _ADVISOR_METRIC_KEYS:
                out[k] = _to_float(getattr(advisor, k))
            out['advisor_benchmark'] = advisor.benchmark
            alloc = advisor.allocation
            out['advisor_allocation'] = alloc
            out['advisor_allocation_label'] = ALLOCATION_LABELS.get(alloc, alloc) if alloc else None
            out['advisor_product_type'] = advisor.product_type
            out['advisor_strategy_summary'] = advisor.strategy_summary
            out['advisor_nav'] = _to_float(advisor.nav)
            out['advisor_nav_date'] = advisor.nav_date.isoformat() if advisor.nav_date else None
            out['advisor_source_url'] = advisor.source_url
            ratios = ctx.get_advisor_ratios(item.symbol)
            if ratios:
                out['advisor_holding_count'] = len(ratios)
                out['advisor_concentration'] = round(sum(r * r for r in ratios), 1)
            else:
                out['advisor_holding_count'] = 0
                out['advisor_concentration'] = None
        else:
            _ADVISOR_METRIC_KEYS = (
                'return_1d',
                'return_1w',
                'return_1m',
                'return_1q',
                'return_6m',
                'return_1y',
                'return_ytd',
                'return_since_incep',
                'max_drawdown',
                'excess_return',
                'volatility',
                'sharpe_ratio',
            )
            for k in _ADVISOR_METRIC_KEYS:
                out[k] = None
            out['advisor_benchmark'] = None
            out['advisor_holding_count'] = None
            out['advisor_concentration'] = None
            out['advisor_allocation'] = None
            out['advisor_allocation_label'] = None
            out['advisor_product_type'] = None
            out['advisor_strategy_summary'] = None
            out['advisor_nav'] = None
            out['advisor_nav_date'] = None
            out['advisor_source_url'] = None
            out['advisor_platform'] = None
            out['advisor_host'] = None
            out['advisor_strategy_type'] = None
            out['advisor_org_name'] = None
    else:
        _apply_advisor_fields(out, item.symbol, db)

    # 基金经理补充信息（#1286）：所属基金公司名。
    mgr = ctx.get_manager(item.symbol) if ctx else lookup_manager(item.symbol, db)
    out['manager_company'] = mgr.company.name if mgr and mgr.company else None

    # 展示专用字段（可转债条款 / 指数估值 / 基金最大回撤 / 跨渠道关联）：
    # 排序不依赖它们，故支持延后到分页之后补算（见 apply_deferred_display_fields）。
    if not defer_display:
        apply_deferred_display_fields(out, item.symbol, item.asset_type, db, ctx)

    # 最新价 / 涨跌幅（#1104）：优先「最近交易日收盘价（场内）/ 确认净值（场外基金）」，
    # 二者都没有才兜底到持仓快照 positions.current_price。
    if ctx:
        quote = ctx.get_latest_quote(item.symbol)
        if quote:
            out['current_price'] = round(quote['close'], 4)
            out['change_pct'] = quote['change_pct']
            out['price_as_of'] = quote['trade_date'].isoformat() if quote['trade_date'] else None
        else:
            current_price = ctx.get_avg_current_price(item.symbol)
            out['current_price'] = round(current_price, 2) if current_price else None
            out['change_pct'] = None
            out['price_as_of'] = None
        out['position_market_value'] = ctx.get_position_market_value(item.symbol)

        stats = ctx.get_position_stats(item.symbol)
        if stats:
            out['holding_quantity'] = stats['quantity']
            out['holding_cost_price'] = round(stats['cost_price'], 4)
            out['holding_pnl'] = round(stats['pnl'], 2)
            out['holding_pnl_percent'] = round(stats['pnl_percent'], 2)
        else:
            out['holding_quantity'] = None
            out['holding_cost_price'] = None
            out['holding_pnl'] = None
            out['holding_pnl_percent'] = None

        out['price_at_added'] = ctx.get_price_at_added(item.symbol)
    else:
        position_value = _compute_position_market_value(item.symbol, db, family_id)
        quote = compute_latest_quote(db, item.symbol)
        if quote:
            out['current_price'] = round(quote['close'], 4)
            out['change_pct'] = quote['change_pct']
            out['price_as_of'] = quote['trade_date'].isoformat() if quote['trade_date'] else None
        else:
            current_price = _compute_avg_current_price(item.symbol, db, family_id)
            out['current_price'] = round(current_price, 2) if current_price else None
            out['change_pct'] = None
            out['price_as_of'] = None
        out['position_market_value'] = round(position_value, 2)

        stats = _compute_holding_stats(item.symbol, db, family_id)
        if stats:
            out['holding_quantity'] = stats['quantity']
            out['holding_cost_price'] = round(stats['cost_price'], 4)
            out['holding_pnl'] = round(stats['pnl'], 2)
            out['holding_pnl_percent'] = round(stats['pnl_percent'], 2)
        else:
            out['holding_quantity'] = None
            out['holding_cost_price'] = None
            out['holding_pnl'] = None
            out['holding_pnl_percent'] = None
        out['price_at_added'] = _compute_price_at_added(item, db)

    return out


def _compute_holding_stats(symbol, db, family_id: int) -> dict | None:
    """按 symbol 汇总真实持仓（positions，当前 family）：数量/加权成本/浮动盈亏。

    positions.quantity 以最小单位存储（0.0001 份），avg_price/current_price 以 0.0001元 存储，
    换算统一走 Money（min_unit_to_shares / price_units_to_yuan）。
    """
    row = (
        db.query(
            func.sum(Position.quantity).label('qty_units'),
            func.sum(Position.quantity * Position.avg_price).label('cost_raw'),
            func.sum(Position.quantity * Position.current_price).label('value_raw'),
        )
        .filter(Position.symbol == symbol, Position.family_id == family_id)
        .first()
    )
    if not row or not row.qty_units:
        return None
    quantity = Money.min_unit_to_shares(row.qty_units)  # 最小单位 → 份
    # quantity(×10000) × avg_price(×10000) = ×1e8，multiply_price_quantity ÷1e6 得 分，cents_to_yuan ÷100 得 元
    cost_yuan = Money.cents_to_yuan(Money.multiply_price_quantity(row.cost_raw, 1))
    value_yuan = Money.cents_to_yuan(Money.multiply_price_quantity(row.value_raw, 1))
    cost_price = cost_yuan / quantity if quantity else 0.0  # 加权成本均价（元/份）
    pnl = value_yuan - cost_yuan
    pnl_percent = (pnl / cost_yuan * 100) if cost_yuan else 0.0
    return {'quantity': quantity, 'cost_price': cost_price, 'pnl': pnl, 'pnl_percent': pnl_percent}


def _compute_price_at_added(item: WatchlistItem, db) -> float | None:
    """添加自选日行情：price_history 中 ≤ created_at 的最近一个交易日收盘价（元）。

    数据依赖 price_history 回填覆盖率；早于历史数据起始点或基金未覆盖时返回 None，
    前端对应「添加后涨幅/收益」列降级显示 --（见设计文档「局限」）。
    """
    created = item.created_at.date() if item.created_at else None
    if not created:
        return None
    row = (
        db.query(PriceHistory.close)
        .filter(PriceHistory.symbol == item.symbol, PriceHistory.trade_date <= created)
        .order_by(PriceHistory.trade_date.desc())
        .first()
    )
    return round(row[0], 4) if row and row[0] is not None else None


def _compute_position_market_value(symbol, db, family_id: int):
    """计算持仓市值（元）。

    positions.quantity 存最小单位（0.0001 份）、current_price 存 0.0001元，
    裸乘结果是最小单位·0.0001元，须经 Money.multiply_price_quantity 换算回元（÷1e6 转分、/100 转元）。
    """
    value = (
        db.query(func.sum(Position.quantity * Position.current_price))
        .filter(Position.symbol == symbol, Position.family_id == family_id)
        .scalar()
    )
    if not value:
        return 0.0
    return Money.cents_to_yuan(Money.multiply_price_quantity(value, 1))


def _compute_avg_current_price(symbol, db, family_id: int):
    """计算持仓平均市价（元），用于自选行展示。

    current_price 以 0.0001元 存储，对外换算回元（禁止裸除 float）。
    """
    avg_price_units = (
        db.query(func.avg(Position.current_price))
        .filter(Position.symbol == symbol, Position.family_id == family_id)
        .scalar()
    )
    return Money.price_units_to_yuan(avg_price_units) if avg_price_units else 0.0


def list_holding_items(
    db,
    family_id,
    venue=None,
    search=None,
    asset_types=None,
    defer_display=False,
    lite=False,
    ctx: Optional[BatchContext] = None,
):
    """持仓分组列表：返回 positions 表全部 active 持仓的虚拟行（按 symbol 聚合）。

    与 watchlist.status 快照解耦：一个 symbol 可能多账户多行，distinct 后按 symbol 聚合；
    每行 id=None 表示「无自选记录」，前端据此禁用置顶/关注/标签/移除等行操作。
    """
    rows = (
        db.query(Position.symbol, Position.asset_type, Position.market, Position.name)
        .filter(Position.family_id == family_id, Position.ownership_status == 'active')
        .distinct()
        .all()
    )
    # family 维度 symbol→venue 映射：优先取自选记录里的 venue，缺失时按资产类型推断
    venue_map = dict(
        db.query(WatchlistItem.symbol, WatchlistItem.venue).filter(WatchlistItem.family_id == family_id).all()
    )
    # 收集所有 symbol
    all_symbols = []
    seen_first = set()
    for symbol, asset_type, market, pos_name in rows:
        if symbol in seen_first:
            continue
        seen_first.add(symbol)
        row_venue = venue_map.get(symbol) or ('OTC' if asset_type == 'fund' else 'EXCHANGE')
        if venue and row_venue != venue:
            continue
        if search:
            s = search.lower()
            display = (pos_name or '') or resolve_display_name(symbol, db, asset_type)
            if s not in symbol.lower() and s not in (display or '').lower():
                continue
        all_symbols.append(symbol)

    # 创建或复用 BatchContext。need_display_fields 同 build_all_items 的口径：
    # 仅「完整 enrich 且不延后」（导出路径）才预取展示字段；列表路径的展示字段
    # 由 fill_page_display_fields 的页级 ctx 补算。
    if ctx is None:
        ctx = BatchContext(db, family_id, all_symbols, need_display_fields=not lite and not defer_display)

    data = []
    seen_second = set()
    for symbol, asset_type, market, pos_name in rows:
        if symbol in seen_second:
            continue  # 同一 symbol 多账户行已聚合，跳过重复
        seen_second.add(symbol)
        row_venue = venue_map.get(symbol) or ('OTC' if asset_type == 'fund' else 'EXCHANGE')
        if venue and row_venue != venue:
            continue
        if search:
            s = search.lower()
            display = (pos_name or '') or resolve_display_name(symbol, db, asset_type)
            if s not in symbol.lower() and s not in (display or '').lower():
                continue
        holding_row = _build_holding_row(
            symbol,
            db,
            family_id,
            market=market,
            asset_type=asset_type,
            venue=row_venue,
            defer_display=defer_display,
            ctx=ctx,
        )
        data.append(_enrich_holding_with_watchlist(holding_row, db, family_id, ctx=ctx))
    if asset_types:
        type_set = {t.strip().lower() for t in asset_types.split(',') if t.strip()}
        if type_set:
            data = [r for r in data if (r.get('asset_type') or '').lower() in type_set]
    data.sort(key=lambda r: r['position_market_value'] or 0, reverse=True)
    return data


def _build_holding_row(
    symbol,
    db,
    family_id,
    market=None,
    asset_type=None,
    venue=None,
    defer_display: bool = False,
    ctx: Optional[BatchContext] = None,
):
    """构造持仓虚拟行 dict，字段对齐 WatchlistItemOut/enrich_item 输出（前端直接复用）。

    id=None 是虚拟行约定：该 symbol 可能不在自选表，行操作（置顶/关注/标签/移除）一律禁用。
    """
    if ctx:
        # 批量路径：代表持仓行已由 BatchContext 一次 IN 查齐（对应原 Position.first()）
        pos = ctx.get_position_meta(symbol)
    else:
        pos = (
            db.query(Position)
            .filter(
                Position.symbol == symbol,
                Position.family_id == family_id,
                Position.ownership_status == 'active',
            )
            .first()
        )
    market = market or (pos.market if pos else None)
    asset_type = asset_type or (pos.asset_type if pos else None)
    venue = venue or ('OTC' if asset_type == 'fund' else 'EXCHANGE')
    # 传 asset_type：#1497 裸码跨表不唯一，指数须优先 index_catalog（见 resolve_display_name docstring）
    if ctx:
        display_name = (pos.name if pos and pos.name else None) or ctx.resolve_display_name(symbol, asset_type)
    else:
        display_name = (pos.name if pos and pos.name else None) or resolve_display_name(symbol, db, asset_type)
    # 投顾组合元信息：与 enrich_item 同步，避免虚拟行（持仓聚合无 id 的行）漏字段
    advisor = ctx.get_advisor(symbol) if ctx else db.query(AdvisorPortfolio).filter_by(code=symbol).first()
    mgr = ctx.get_manager(symbol) if ctx else lookup_manager(symbol, db)

    if ctx:
        current_price = ctx.get_avg_current_price(symbol)
        stats = ctx.get_position_stats(symbol)
        position_market_value = ctx.get_position_market_value(symbol)
    else:
        current_price = _compute_avg_current_price(symbol, db, family_id)
        stats = _compute_holding_stats(symbol, db, family_id)
        position_market_value = _compute_position_market_value(symbol, db, family_id)
    row = {
        'id': None,
        'symbol': symbol,
        'market': market,
        'asset_type': (asset_type or '').lower() or None,
        'type_label': TYPE_LABELS.get((asset_type or '').lower()) or (asset_type or '').lower() or '',
        'venue': venue,
        'status': 'HOLDING',
        'favorite': False,
        'favorite_at': None,
        'is_pinned': False,
        'pinned_at': None,
        'add_reason': None,
        'notes': None,
        'cost_price': None,
        'quantity': None,
        'created_at': None,
        'updated_at': None,
        'display_name': display_name,
        'group_ids': [],
        'group_names': [],
        'tag_ids': [],
        'current_price': round(current_price, 2) if current_price else None,
        'change_pct': None,
        'position_market_value': round(position_market_value, 2),
        'holding_quantity': stats['quantity'] if stats else None,
        'holding_cost_price': round(stats['cost_price'], 4) if stats else None,
        'holding_pnl': round(stats['pnl'], 2) if stats else None,
        'holding_pnl_percent': round(stats['pnl_percent'], 2) if stats else None,
        # 与 origin/dev 口径一致：price_at_added 是「自选条目」概念（添加日收盘价），
        # 持仓虚拟行恒 None——即使该 symbol 有自选记录也不回填（_enrich_holding_with_watchlist
        # 同样不覆盖此字段）
        'price_at_added': None,
        # 投顾组合补充信息（与 enrich_item 同源；非投顾为 None）
        'advisor_platform': (advisor.platform if advisor else None),
        'advisor_host': (advisor.host if advisor else None),
        'advisor_strategy_type': (advisor.strategy_type if advisor else None),
        'advisor_org_name': (advisor.org_name if advisor else None),
        'return_1w': (_to_float(advisor.return_1w) if advisor else None),
        'return_1m': (_to_float(advisor.return_1m) if advisor else None),
        'return_1y': (_to_float(advisor.return_1y) if advisor else None),
        'return_ytd': (_to_float(advisor.return_ytd) if advisor else None),
        'return_since_incep': (_to_float(advisor.return_since_incep) if advisor else None),
        'max_drawdown': (_to_float(advisor.max_drawdown) if advisor else None),
        'excess_return': (_to_float(advisor.excess_return) if advisor else None),
        # #1468 且慢补充指标 + 策展元数据（与 _apply_advisor_fields 保持同字段集）
        'return_1d': (_to_float(advisor.return_1d) if advisor else None),
        'return_1q': (_to_float(advisor.return_1q) if advisor else None),
        'return_6m': (_to_float(advisor.return_6m) if advisor else None),
        'volatility': (_to_float(advisor.volatility) if advisor else None),
        'sharpe_ratio': (_to_float(advisor.sharpe_ratio) if advisor else None),
        'advisor_benchmark': (advisor.benchmark if advisor else None),
        'advisor_allocation': (advisor.allocation if advisor else None),
        'advisor_allocation_label': (
            ALLOCATION_LABELS.get(advisor.allocation, advisor.allocation) if advisor and advisor.allocation else None
        ),
        'advisor_product_type': (advisor.product_type if advisor else None),
        'advisor_strategy_summary': (advisor.strategy_summary if advisor else None),
        'advisor_nav': (_to_float(advisor.nav) if advisor else None),
        'advisor_nav_date': (advisor.nav_date.isoformat() if advisor and advisor.nav_date else None),
        'advisor_source_url': (advisor.source_url if advisor else None),
        'advisor_holding_count': 0,
        'advisor_concentration': None,
    }
    # 持仓集中度（HHI）：与 _apply_advisor_fields 同源，避免虚拟行（持仓聚合无 id）漏字段
    if advisor is not None:
        ratios = (
            ctx.get_advisor_ratios(symbol)
            if ctx
            else [
                float(r[0])
                for r in db.query(AdvisorHolding.after_ratio).filter_by(portfolio_id=advisor.id).all()
                if r[0] is not None
            ]
        )
        if ratios:
            row['advisor_holding_count'] = len(ratios)
            row['advisor_concentration'] = round(sum(r * r for r in ratios), 1)
    # 基金经理所属公司（与 enrich_item 同源；非经理为 None）。
    # 复用上方已取的 mgr，避免同一行重复查库（141 行即 141 次多余查询）。
    row['manager_company'] = mgr.company.name if mgr and mgr.company else None
    # 展示专用字段（可转债条款 / 指数估值 / 基金最大回撤 / 跨渠道关联）：支持延后补算
    if not defer_display:
        apply_deferred_display_fields(row, symbol, asset_type, db, ctx)
    return row


def _enrich_holding_with_watchlist(row: dict, db, family_id: int, ctx: Optional[BatchContext] = None) -> dict:
    """持仓虚拟行若存在真实自选记录，回填 id/分组/标签/备注等可编辑字段。

    使「持仓」分组内的产品也能打标签、加备注（#1458 后续：持仓即自选）。
    仅当无自选记录时保持 id=None——前端据此禁用行操作并提示「一键加入自选」。
    「全部」分组天然包含这些真实自选记录，无需在此处理，口径保持一致。
    """
    symbol = row['symbol']
    market = row['market']
    venue = row['venue']
    item = None
    if ctx:
        item = ctx.get_watchlist_item(symbol)
    else:
        item = db.query(WatchlistItem).filter_by(symbol=symbol, market=market, venue=venue, family_id=family_id).first()
        if item is None:
            item = db.query(WatchlistItem).filter_by(symbol=symbol, family_id=family_id).first()
    if item is None:
        return row
    row = dict(row)
    row['id'] = item.id
    if ctx:
        row['group_ids'] = ctx.get_group_ids(item.id)
        row['group_names'] = ctx.get_group_names(item.id)
        row['tag_ids'] = ctx.get_tag_ids(item.id)
    else:
        row['group_ids'] = [g.group_id for g in item.group_links]
        row['group_names'] = [g.watchlist_group.name for g in item.group_links]
        row['tag_ids'] = [t.tag_id for t in item.tag_links]
    row['notes'] = item.notes
    row['is_pinned'] = item.is_pinned
    row['pinned_at'] = item.pinned_at
    row['favorite'] = item.favorite
    row['favorite_at'] = item.favorite_at
    row['add_reason'] = item.add_reason
    row['cost_price'] = item.cost_price
    row['quantity'] = item.quantity
    row['status'] = 'HOLDING'  # 持仓分组恒为 HOLDING
    return row


def build_all_items(
    db,
    family_id,
    venue=None,
    search=None,
    tag_ids_str=None,
    favorite=False,
    group_id=None,
    defer_display=False,
    lite=False,
):
    """「全部」分组数据：自选清单 ∪ 真实持仓补集（同一 symbol 自选记录优先，去重）。

    语义（与分组 count 口径一致，保证「全部 N 条」与分组数字吻合）：
    - 自选条目走 get_filtered_items_query（不传 status），保留置顶排序字段；
    - 补集虚拟行仅当无附加筛选（tag/关注/分组）时追加——附加筛选的语义是
      「自选内的资产」子集，与持仓全集无交集，补行会引入「筛选不到却展示」的条目；
    - 排序：置顶优先，其次持仓市值降序（自选行与虚拟行统一口径）。
    """
    params = {
        'status': None,
        'venue': venue,
        'market': None,
        'group_id': group_id,
        'search': search,
        'favorite': favorite,
        'symbol': None,
        'tag_ids_str': tag_ids_str,
        'tag_id': None,
    }
    query, _ = get_filtered_items_query(db, family_id, **params)
    items = query.order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.updated_at.desc()).all()

    # 收集所有 symbol（自选 + 持仓补集），创建 BatchContext
    all_symbols = [item.symbol for item in items]
    if not (tag_ids_str or favorite or group_id):
        holding_rows_raw = (
            db.query(Position.symbol)
            .filter(Position.family_id == family_id, Position.ownership_status == 'active')
            .distinct()
            .all()
        )
        for (sym,) in holding_rows_raw:
            if sym not in all_symbols:
                all_symbols.append(sym)
    # need_display_fields：仅当「完整 enrich 且不延后」（导出路径）才在建 ctx 时预取
    # 展示字段；列表路径 defer_display=True，展示字段由 fill_page_display_fields 的
    # 页级 ctx 补算（只覆盖本页 ≤per_page 行，避免为全量行预取 3 年净值序列）。
    ctx = BatchContext(db, family_id, all_symbols, need_display_fields=not lite and not defer_display)

    data = [enrich_item(item, db, family_id, defer_display=defer_display, ctx=ctx) for item in items]

    if not (tag_ids_str or favorite or group_id):
        holding_rows = list_holding_items(
            db, family_id, venue=venue, search=search, defer_display=defer_display, lite=lite, ctx=ctx
        )
        watch_symbols = {item['symbol'] for item in data}
        for row in holding_rows:
            if row['symbol'] in watch_symbols:
                continue
            data.append(row)

    data.sort(key=lambda r: (not r['is_pinned'], -(r['position_market_value'] or 0)))
    return data


# ────────────────────────── 用户列内排序 ──────────────────────────

# 用户列内排序白名单（#991）：仅开放行字典中真实存在的数值/日期字段，
# 防止任意字段名注入排序。added_return 为派生值（前端「添加后涨幅」列），
# 由 _user_sort_metric 现算，不在本集合内。
USER_SORTABLE_FIELDS = frozenset(
    {
        # #1331：前端「代码/名称」列（product）标了 sortable:custom 却未开放白名单，
        # 导致点击排序静默失效；映射为 symbol（代码）字典序，稳定且不耦合名称本地化。
        'product',
        'created_at',
        'current_price',
        'change_pct',
        'holding_quantity',
        'holding_cost_price',
        'position_market_value',
        'holding_pnl',
        'holding_pnl_percent',
        'price_at_added',
        # #1332：#993 引入的 4 个候选列放开排序；下列字段均已在 enrich 阶段下发（见 enrich_item），
        # 排序键值由 _user_sort_metric 现算：
        # - holding_cost_price：数值，来自 positions 加权成本（_compute_holding_stats）；
        # - type_label：资产类型中文标签（字符串），单一来源 app.core.constants.TYPE_LABELS（#1171）；
        # - updated_at：ISO 字符串，字典序即时间序；
        # - groups：多值（group_ids），按首个分组 id 字典序、无分组恒排末尾（语义见 _user_sort_metric）。
        'type_label',
        'updated_at',
        'groups',
    }
)


def _user_sort_metric(row: dict, sort_by: str):
    """取排序键值；缺失/不可比较返回 None（恒排末尾）。"""
    if sort_by == 'product':
        # 「代码/名称」列（#1331）：按 symbol（代码）字典序排序，稳定；symbol 缺失则排末尾
        return row.get('symbol')
    if sort_by == 'groups':
        # 所属分组（多值字段，#1332）：排序语义取「首个分组」——优先 group_ids 首个
        # 元素（分组 id）字典序；若无 group_ids 则退化为首个 group_names（分组名）；
        # 无分组恒排末尾。多分组整体顺序按首个分组定，与前端展示首个分组一致。
        ids = row.get('group_ids') or []
        if ids:
            return ids[0]
        names = row.get('group_names') or []
        return names[0] if names else None
    if sort_by == 'added_return':
        # 派生列：添加后收益金额 =（现价 - 添加日收盘价）× 持有数量，
        # 与前端 addedReturnAmount 同口径；三要素缺一则无意义
        cur = row.get('current_price')
        added = row.get('price_at_added')
        qty = row.get('holding_quantity')
        if cur is None or added is None or not qty:
            return None
        try:
            return (float(cur) - float(added)) * float(qty)
        except (TypeError, ValueError):
            return None
    v = row.get(sort_by)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def apply_user_sort(data: list, sort_by, sort_order):
    """用户列内排序（#991）。

    - 未指定 sort_by：维持原顺序（置顶优先 + 更新时间倒序）；
    - 白名单外 sort_by：维持原顺序返回，但明确告警（#1331 消除「点击无反应」式静默失败），
      便于后续新增可排序列漏登记白名单时第一时间暴露，而非毫无提示；
    - 排序稳定且置顶行仍前置：用户排序只改变同优先级内的次序，
      不破坏「置顶恒在顶部」的既有心智；
    - 值缺失（None）的行无论升降序都排在末尾，避免空值干扰阅读。
    """
    if not sort_by:
        return data
    # 白名单外字段（含前端标了排序但后端未开放）：原序返回 + 告警，避免静默失效
    if sort_by not in USER_SORTABLE_FIELDS and sort_by != 'added_return':
        logger.warning(
            'watchlist 排序忽略非白名单字段 sort_by={!r}（前端标了排序但后端未开放，'
            '如确属可排序列请在 USER_SORTABLE_FIELDS 登记）',
            sort_by,
        )
        return data
    reverse = sort_order == 'desc'

    decorated = [(_user_sort_metric(r, sort_by), r) for r in data]
    known = [(m, r) for m, r in decorated if m is not None]
    unknown = [r for m, r in decorated if m is None]
    known.sort(key=lambda t: t[0], reverse=reverse)  # 主排序：用户选的指标
    known.sort(key=lambda t: 0 if t[1].get('is_pinned') else 1)  # 次排序：置顶前置（稳定）
    return [r for _, r in known] + unknown


def fill_page_display_fields(page_data: list, db, lite: bool, family_id: int) -> list:
    """对**已分页**的页内行补算展示专用字段（`fields=lite` 时跳过）。

    放在分页之后是本接口的性能关键：展示专用 enrich 按 symbol 查库，基金回撤还要扫
    3 年 `daily_worth` 序列，实测占本接口总耗时约 55%（全量 164 行 vs 页内 20 行，
    相差一个数量级）。排序不依赖这些字段（均未进 `USER_SORTABLE_FIELDS`），故可安全延后。

    展示字段用**页级** BatchContext 补算：预取只覆盖本页 symbol（≤ per_page 个），
    不复用全量行的 base ctx——base ctx 在列表路径不预取展示字段（见
    need_display_fields=False 的各分支），避免为 158 行预取 3 年净值序列。
    """
    if lite:
        return page_data
    page_symbols: list[str] = []
    seen = set()
    for row in page_data:
        s = row.get('symbol')
        if s and s not in seen:
            seen.add(s)
            page_symbols.append(s)
    if not page_symbols:
        return page_data
    # need_base_fields=False：只跑展示段（8a-8d），不为页内 20 行重复预取
    # 基础字段（行情/持仓聚合等已在列表分支的 base ctx 里做过）
    ctx = BatchContext(db, family_id, page_symbols, need_display_fields=True, need_base_fields=False)
    for row in page_data:
        symbol = row.get('symbol')
        if not symbol:
            continue
        apply_deferred_display_fields(row, symbol, row.get('asset_type') or '', db, ctx)
    return page_data


def list_items_paginated(db, family_id: int, params: dict) -> tuple[list, int]:
    """`list_items` 接口的核心编排（#1642 B 块，从视图层下沉）。

    入参 ``params`` 为视图已解析的查询参数 dict（与下沉前逐字段一致）；本函数按
    ``status`` 分支取数、用户排序、分页并补展示字段，**分支语义与下沉前逐字一致**：

    - ``HOLDING``：全部真实持仓虚拟行（不走 ``watchlist.status`` 快照），``defer_display=True``；
    - 无 status 且无查找型参数：自选 ∪ 持仓补集（``build_all_items``），``defer_display=True``；
    - 其余：``get_filtered_items_query`` 筛选 → 按置顶/更新时间排序 → enrich。

    ``build_all_items`` / ``get_filtered_items_query`` 抛 ``ValueError`` 时透传，由视图转 400。
    返回 ``(page_data, total)``：已分页并补完展示字段的行列表 + 总数。
    """
    lite = params['fields'] == 'lite'
    page = max(params['page'] or 1, 1)
    per_page = max(min(params['per_page'] or 20, 200), 1)
    offset = (page - 1) * per_page
    if params['status'] == 'HOLDING':
        # base ctx：只预取基础字段（行情/持仓聚合等，enrich 阶段消费）；
        # 展示字段由 fill_page_display_fields 的页级 ctx 补算（只覆盖本页 ≤20 行）
        holding_symbols_rows = (
            db.query(Position.symbol)
            .filter(Position.family_id == family_id, Position.ownership_status == 'active')
            .distinct()
            .all()
        )
        holding_symbols = [s for (s,) in holding_symbols_rows]
        ctx = BatchContext(db, family_id, holding_symbols, need_display_fields=False)

        data = list_holding_items(
            db,
            family_id,
            venue=params['venue'],
            search=params['search'],
            asset_types=params['asset_types'],
            defer_display=True,
            lite=lite,
            ctx=ctx,
        )
        data = apply_user_sort(data, params['sort_by'], params['sort_order'])
        total = len(data)
        return fill_page_display_fields(data[offset : offset + per_page], db, lite, family_id), total
    if not params['status'] and not (params['symbol'] or params['market'] or params['tag_id'] or params['asset_types']):
        data = build_all_items(
            db,
            family_id,
            venue=params['venue'],
            search=params['search'],
            tag_ids_str=params['tag_ids_str'],
            favorite=params['favorite'],
            group_id=params['group_id'],
            defer_display=True,
            lite=lite,
        )
        data = apply_user_sort(data, params['sort_by'], params['sort_order'])
        total = len(data)
        return fill_page_display_fields(data[offset : offset + per_page], db, lite, family_id), total
    query, _total = get_filtered_items_query(
        db,
        family_id,
        status=params['status'],
        venue=params['venue'],
        market=params['market'],
        group_id=params['group_id'],
        search=params['search'],
        favorite=params['favorite'],
        symbol=params['symbol'],
        tag_ids_str=params['tag_ids_str'],
        tag_id=params['tag_id'],
        asset_types=params['asset_types'],
    )
    items = query.order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.updated_at.desc()).all()

    # 收集 symbols 创建 base ctx（仅基础字段；展示字段由页级 ctx 补算）
    all_symbols = [item.symbol for item in items]
    ctx = BatchContext(db, family_id, all_symbols, need_display_fields=False)

    data = [enrich_item(item, db, family_id, defer_display=True, ctx=ctx) for item in items]
    data = apply_user_sort(data, params['sort_by'], params['sort_order'])
    total = len(data)
    return fill_page_display_fields(data[offset : offset + per_page], db, lite, family_id), total


def export_items_rows(db, family_id: int, params: dict) -> list:
    """`export_items` 接口的数据取数（#1642 B 块，从视图层下沉）。

    与 ``list_items`` 同口径（HOLDING / 全部 / 筛选）取**全量**行（导出不分页），返回已
    enrich 的行列表供视图组装 CSV。**分支语义与下沉前逐字一致**：HOLDING 与「全部」分支
    不带 ``defer_display``（导出走完整 enrich）；筛选分支透传 ``**params`` 给
    ``get_filtered_items_query``（与下沉前 ``**params`` 一致）。``ValueError`` 透传由视图转 400。
    """
    if params['status'] == 'HOLDING':
        return list_holding_items(db, family_id, venue=params['venue'], search=params['search'])
    if not params['status'] and not (params['symbol'] or params['market'] or params['tag_id'] or params['asset_types']):
        return build_all_items(
            db,
            family_id,
            venue=params['venue'],
            search=params['search'],
            tag_ids_str=params['tag_ids_str'],
            favorite=params['favorite'],
            group_id=params['group_id'],
        )
    query, _total = get_filtered_items_query(
        db,
        family_id,
        status=params['status'],
        venue=params['venue'],
        market=params['market'],
        group_id=params['group_id'],
        search=params['search'],
        favorite=params['favorite'],
        symbol=params['symbol'],
        tag_ids_str=params['tag_ids_str'],
        tag_id=params['tag_id'],
        asset_types=params['asset_types'],
    )
    items = query.all()
    all_symbols = [item.symbol for item in items]
    ctx = BatchContext(db, family_id, all_symbols, need_display_fields=True)
    return [enrich_item(item, db, family_id, defer_display=False, ctx=ctx) for item in items]
