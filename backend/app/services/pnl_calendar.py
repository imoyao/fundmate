# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/6
# File : pnl_calendar.py
"""每日收益日历：as-of 派生日盈亏（#1812）。

为什么不用 `asset_snapshots`（issue 原方案）
------------------------------------------
`write_asset_snapshot`（`summary_service.py:752`）的取数链无日期过滤——
`get_distributions(db, family_id)` 不带日期参数、`_load_user_assets` 直接
`db.query(Position).filter(family_id, ownership_status='active').all()`。
它记的是**落库当日那一刻的当前状态**，不是「截至某日」的状态。后果有两条：

1. 历史快照永久冻结：全仓无失效/重算钩子（grep `recompute|invalidate|
   AssetSnapshot.*delete` 零命中），用户改持仓后日历历史数字不动；
2. 回填是**主动写错**而非写旧：今天跑 `write_asset_snapshot(db, fid, '2026-09-01')`
   会把今天的持仓市值贴上 9/1 的标签（docstring 称「用于历史回填」，实现不支持）。

故本模块另起派生路径：从 `transactions` 的 as-of 份额 × 历史价格现算日盈亏。
**持仓一改，历史自动跟着变** —— 这正是 #1812 的核心诉求。

口径（口径唯一，前端不做二次计算）
----------------------------------
    shares_asof(pos, D) = Σ transactions.quantity  (confirm_date <= D, buy/deposit +, sell/withdraw −)
    daily_pnl(D)        = total_pnl_asof(D) − total_pnl_asof(D−1)
                         其中 total_pnl_asof(D) = Σ_pos [ mv_asof(D) − cost_basis_asof(D) + realized_asof(D) ]

**为什么用 `total_pnl` 的日差分而不是 `net_worth` 日环比**：
`total_pnl` 是累计盈亏，买入建仓瞬间 `unrealized = 市值 − 成本 = 0`，追加投入不改变
盈亏总额 ⇒ 它的日差分**天然免疫资金流**。反之 `net_worth` 日环比会被存取款污染
（存入 ¥10,000 当天凭空「赚」10,000）。此约束须写进 UI 口径说明，否则用户看到假盈利。

四态（缺数据绝不能画成 0，见设计文档 §2.3）
-----------------------------------------
    updown  真实盈亏（有价格序列且 shares>0）
    zero    有价格序列但当日盈亏恰为 0
    no_price 无价格序列 —— `valuation_mode='balance'`（银行理财/投顾/实物），
            其市值来自 `market_value_override` **单值非序列**，天然无历史；
            切到这类账户若不区分，用户会以为功能坏了
    closed  非交易日 / 区间外

跨域说明
--------
`positions` / `transactions` 属 user 域，`daily_worth` / `price_history` 属 market 域
（`core/db_factory.py:175-192`），两引擎无法 SQL JOIN。本模块先取键列表再用 `in_`
批量取价（AGENTS.md 数据域硬规则 §3 两步法），**不做 N+1**。
"""

import datetime as dt
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.core.venues import EXCHANGE, OTC, venue_of_row
from app.domains.funds.models import DailyWorth
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.transactions.models import Transaction
from app.services.pnl_service import (
    _DIVEST_TXN_TYPES,
    _INVEST_TXN_TYPES,
)

# 单价精度：场内 adj_close 为「元」浮点，需放大到 0.0001 元整数再喂 Money.multiply_price_quantity
_PRICE_SCALE = Decimal('10000')
_PRICE_QUANTITY_DIVISOR = Decimal('1000000')

# quantize 的目标常量：热路径里每调一次就 `Decimal('1')` 一次实测要 1.8µs，
# 全市场 9.3 万行净值就是 0.16 秒白花，故提到模块级只构造一次。
_PRICE_UNITS_ONE = Decimal('1')

# DailyWorth.unit_nav 是 SafeNumeric(18,6)（元），转 0.0001 元整数单位
_NAV_SCALE = Decimal('10000')

# 日历状态
STATE_UPDOWN = 'updown'
STATE_ZERO = 'zero'
STATE_NO_PRICE = 'no_price'
STATE_CLOSED = 'closed'

# 某标的当天没价格时，最多向前沿用最近多少天的价格（#1812）。
# 太大：一个月没更新的标的会被当成「价格不变」而画出 0 收益，掩盖数据缺失；
# 太小：单日数据抖动就会让市值归零、差分出现假跳空。7 天覆盖周末与节假日。
_STALE_CARRY_DAYS = 7

# 聚合粒度（#1925 三视图）：day=逐日明细回 `days`；month/year=期间聚合回 `periods`。
# 口径唯一出口仍是后端——前端只做呈现，禁止二次盈亏计算（见本文件顶部口径说明）。
GRANULARITY_DAY = 'day'
GRANULARITY_MONTH = 'month'
GRANULARITY_YEAR = 'year'
GRANULARITIES = (GRANULARITY_DAY, GRANULARITY_MONTH, GRANULARITY_YEAR)


def _to_price_units(value) -> int:
    """元（Decimal/float/str）→ 0.0001 元整数单位，与 Position.current_price 同尺度。

    `DailyWorth.unit_nav` 是 `DECIMAL(18,6)`，读出来**已经是 Decimal**——先 `str()`
    再 `Decimal()` 纯属往返（实测 10.19µs → 3.40µs/次），9.3 万行净值差出 6 秒。
    只有 `PriceHistory.adj_close` 那种真 float 才必须走字符串规避二进制误差。
    """
    if value is None:
        return 0
    scaled = value * _PRICE_SCALE if isinstance(value, Decimal) else Decimal(str(value)) * _PRICE_SCALE
    return int(scaled.quantize(_PRICE_UNITS_ONE, rounding=ROUND_HALF_UP))


def _effective_date(txn) -> Optional[dt.date]:
    """流水生效日：优先 confirm_date，缺失回退 trade_date 的日期部分。"""
    if txn.confirm_date:
        return txn.confirm_date
    if txn.trade_date:
        return txn.trade_date.date()
    return None


def _as_of_shares(
    db: Session,
    family_id: int,
    start: dt.date,
    ledger_id: Optional[int] = None,
) -> Tuple[Dict[int, Dict[dt.date, int]], Dict[int, List[Transaction]]]:
    """as-of 份额与原始流水：{position_id: {date: 增量份额}} + {position_id: [txn...]}。

    份额取 `transactions.quantity`（0.0001 份/单位，与 Position.quantity 同尺度）。

    **口径：按持仓归集，流水不按 `ledger_id` 过滤**（#1916）。
    既有权威口径 `get_ledger_pnl`（#1220）就是 `key = p.ledger_id or 0` 按持仓分组，
    而 `realized_pnl_by_position` / `net_invested_by_position` 只按 `family_id` 过滤、
    **不按 ledger 过滤**。本函数曾多此一举按 `Transaction.ledger_id` 过滤，导致：
    持仓在账户 13、流水记在账户 2 时，账户 13 视图「持仓进来、份额没进来」，
    破坏「家庭级 = Σ 账户级」恒等式（真实库实测差 529.90）。

    `ledger_id` 参数**仅用于缩小查询范围做性能优化时也必须保持口径一致**，
    因此这里刻意不使用它过滤——保持与既有 service 完全一致。
    """
    query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.position_id.isnot(None),
    )

    shares: Dict[int, Dict[dt.date, int]] = defaultdict(dict)
    txns: Dict[int, List[Transaction]] = defaultdict(list)

    for txn in query.all():
        eff = _effective_date(txn)
        if eff is None or eff > start:
            continue
        pid = txn.position_id
        if txn.txn_type in _INVEST_TXN_TYPES:
            shares[pid][eff] = shares[pid].get(eff, 0) + (txn.quantity or 0)
        elif txn.txn_type in _DIVEST_TXN_TYPES:
            shares[pid][eff] = shares[pid].get(eff, 0) - (txn.quantity or 0)
        else:
            # 分红 / 手续费等其他类型不改变份额
            continue
        # realized_pnl 存在流水上（清仓删持仓也不丢），as-of 已实现盈亏靠它累计
        txns[pid].append(txn)

    return shares, txns


def _collect_fund_nav(
    db: Session,
    start: dt.date,
    end: dt.date,
    fund_codes: Iterable[str],
) -> Dict[str, Dict[dt.date, int]]:
    """基金单位净值：{fund_code: {date: 0.0001元}}（market 域，按持有代码一次取回本地分组）。

    **必须按 `fund_code` 过滤**（#1925）：`daily_worth` 是全市场表（真实库 7,543,415 行 /
    26,938 只基金），只按日期 `.all()` 等于把全市场当期净值捞进内存再在 Python 里挑，
    现成唯一索引 `idx_daily_worth_code_date_unique (fund_code, date)` 因此完全用不上。
    实测 31 天窗口：**无过滤 13,693 ms → 有过滤 317 ms（43×）**，而家庭持仓只有 114 只 OTC。
    窗口拉到 365 天时差距更致命（无过滤 54.4s，年视图直接不可用）。

    代码集合为空时**直接返回 `{}`，不退化成查全库**——空 targets 的正确语义是「跳过」，
    静默退化是 AGENTS.md 数据策略硬约束 §3 明令禁止的形态（反例 `fund_manager_job.py`）。
    """
    codes = sorted({(c or '').strip() for c in fund_codes if (c or '').strip()})
    if not codes:
        return {}
    # 列投影而非整实体：ORM 把 9.3 万行 DailyWorth 逐个构造 + 塞进 identity map
    # 实测 9,025 ms，投影成元组只要 1,452 ms（6.2×）。热路径上不值得为此建对象。
    rows = (
        db.query(DailyWorth.fund_code, DailyWorth.date, DailyWorth.unit_nav)
        .filter(
            DailyWorth.fund_code.in_(codes),
            DailyWorth.date >= start,
            DailyWorth.date <= end,
        )
        .all()
    )
    nav: Dict[str, Dict[dt.date, int]] = {}
    for code, date, unit_nav in rows:
        nav.setdefault(code, {})[date] = _to_price_units(unit_nav)
    return nav


def _collect_price_history(
    db: Session,
    symbols: Iterable[str],
    start: dt.date,
    end: dt.date,
) -> Dict[str, Dict[dt.date, int]]:
    """场内前复权收盘价：{symbol: {date: 0.0001元}}。

    用 `adj_close` 而非 `close`——除权日`close` 会跳空，用它算的「日收益」是假的
    （除权除息不是收益）。跨域两步法的第二步：先拿键列表，再 `in_` 批量取。
    """
    symbol_list = sorted({s for s in symbols if s})
    if not symbol_list:
        return {}
    # 同 `_collect_fund_nav`：列投影，不为热路径构造 ORM 实体
    rows = (
        db.query(
            PriceHistory.symbol,
            PriceHistory.trade_date,
            PriceHistory.adj_close,
            PriceHistory.close,
        )
        .filter(
            PriceHistory.symbol.in_(symbol_list),
            PriceHistory.trade_date >= start,
            PriceHistory.trade_date <= end,
        )
        .all()
    )
    prices: Dict[str, Dict[dt.date, int]] = {}
    for symbol, trade_date, adj_close, close in rows:
        price = adj_close if adj_close else close
        prices.setdefault(symbol, {})[trade_date] = _to_price_units(price)
    return prices


def _price_series_of(
    pos: Position,
    fund_nav: Dict[str, Dict[dt.date, int]],
    exchange_prices: Dict[str, Dict[dt.date, int]],
) -> Optional[Dict[dt.date, int]]:
    """该持仓的价格序列；`None` = **整段无价格序列**（区别于「有序列但当日无价」）。

    **必须按持仓解析一次、日循环里复用**（#1925）：`venue_of_row` 要跑正则 +
    `strip().upper()`（实测 3.23µs），而日循环里每笔持仓每天要问两次
    （值循环问取价、判定循环问新鲜价），5 年窗口就是 55 万次 ≈ 1.8 秒纯浪费。
    持仓集合在整个区间内不变，故解析结果天然是不变量。
    """
    symbol = (pos.symbol or '').strip()
    venue = venue_of_row(symbol, pos.asset_type)
    if venue == OTC:
        return fund_nav.get(symbol) or None
    if venue == EXCHANGE:
        return exchange_prices.get(symbol) or None
    # 场所判不出（NO_VENUE）：投顾组合 / 基金经理等无价序列标的
    return None


def _price_for(day: dt.date, series: Optional[Dict[dt.date, int]]) -> Optional[int]:
    """该标在 day 的 0.0001 元单价；`series` 为 None/空表示整段无价格序列。

    前值回填（#1812 修复）：某只基金当天没发布净值时，若直接跳过它，
    等价于「市值归零」，日差分会出现巨额假跳空——实测 2026-09-30 只有
    13/57 笔有价，ΔW 假跌 20.8 万。回填让日总额在标的集合不变时可比。
    周末/全市场无数据时所有标的都回填不出 ⇒ 仍判`closed`，不会被填成「0 收益」。
    """
    if not series:
        return None
    price = series.get(day)
    if price is not None:
        return price
    # 当日无价 → 沿用最近一次已知价格（最多回溯 _STALE_CARRY_DAYS 天）
    for back in range(1, _STALE_CARRY_DAYS + 1):
        prev = series.get(day - dt.timedelta(days=back))
        if prev is not None:
            return prev
    return None


def _positions(
    db: Session,
    family_id: int,
    ledger_id: Optional[int],
) -> List[Position]:
    """目标持仓：family 下active；ledger_id 传则限定该账户（账户级），不传=家庭级全量。

    与 `summary_service._load_user_assets` 的 active 过滤口径一致。
    """
    query = db.query(Position).filter(Position.family_id == family_id, Position.ownership_status == 'active')
    if ledger_id is not None:
        query = query.filter(Position.ledger_id == ledger_id)
    return query.all()


def _build_per_pos(
    positions: List[Position],
    shares: Dict[int, Dict[dt.date, int]],
    txns: Dict[int, List[Transaction]],
    scan_start: dt.date,
) -> Dict[int, dict]:
    """每笔持仓的运行态（份额 / 已实现 / 建仓标记），家庭级与账户级共用同一构造。

    `shares` / `txns` 均为全家庭口径（按 position_id 归组，见 `_as_of_shares`），
    传入哪一组持仓就得到哪一组的运行态——这是「家庭级 = Σ 账户级」可加性的前提。
    """
    per_pos: Dict[int, dict] = {}
    for pos in positions:
        rate = EXCHANGE_RATES.get(pos.currency or 'CNY', 1.0)
        day_deltas = shares.get(pos.id, {})
        # **起点之前的累计份额/已实现必须先注入**（#1812 实测缺陷）：
        # `day_deltas` 是「按日的增量」，而日循环只推进 [scan_start, end]，
        # 若不预置，2026-01 建的仓位在 9 月的循环里永远累加不到任何份额
        # ⇒ shares 恒为 0 ⇒ 整月判成 no_price/closed，日历永远空白。
        # 单测买在窗口第 1 天，测不到这条路径；必须显式回归「窗口前建仓」。
        initial_shares = sum(v for d, v in day_deltas.items() if d < scan_start)
        per_pos[pos.id] = {
            'pos': pos,
            'rate': rate,
            'shares': initial_shares,
            'realized': 0,
            'share_days': day_deltas,
            'txn_days': defaultdict(int),
        }
        for txn in txns.get(pos.id, []):
            eff = _effective_date(txn)
            if eff is not None and eff < scan_start:
                per_pos[pos.id]['realized'] += txn.realized_pnl or 0
            elif eff is not None:
                per_pos[pos.id]['txn_days'][eff] += txn.realized_pnl or 0
    return per_pos


def _resolve_range(start_date: Optional[str], end_date: Optional[str]) -> Tuple[dt.date, dt.date]:
    """把 `start_date` / `end_date` 解析成闭区间；end 缺省取上海时区当日，start 缺省为 end−29 天。

    抽出来是因为月/年粒度要在**同一套缺省规则**上把起点再往前挪一天做基线，
    两处各写一份解析就是口径分叉的开始。
    """
    from app.core.time_utils import now_shanghai

    end = dt.datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else now_shanghai().date()
    start = dt.datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else end - dt.timedelta(days=29)
    return start, end


def build_daily_pnl_series(
    db: Session,
    family_id: int = 1,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ledger_id: Optional[int] = None,
) -> dict:
    """逐日盈亏日历序列（家庭级 / 账户级共用同一路径）。

     Args:
         start_date / end_date: YYYY-MM-DD（含）。end 缺省取上海时区当日。
         ledger_id: 传则返回该账户级序列，不传返回家庭级（与 `get_snapshots` 语义一致）。

     Returns:
         {'ledger_id': int|None, 'scope': 'family'|'ledger', 'start_date': ..., 'end_date': ...,
          'month_total': float, 'has_any_price': bool, 'days': [{'date','daily_pnl','rate','state'}, ...]}

     `rate` = 当日盈亏 / 前一日总资产。**前端禁止二次计算**，一切数值出口在此。

     恒等式（#1916）：**家庭级 month_total ≡ Σ 各账户级 month_total**，成立条件有三，
    缺一不可：
     1. 份额/已实现按**持仓**归集、流水不按 ledger 过滤（口径先例 `get_ledger_pnl` #1220）；
     2. 状态判定（丢天/覆盖不全/无持仓）恒用**家庭级全量决策集**——各作用域丢同一批天、
        同步推进差分基准，否则 month_total 的差分链错位、不可加（实测差 3502.91）；
     3. day_total 按持仓可加（每笔持仓恰属一个账户）。
    """
    # 往前多取一天，**只为给区间首日建立差分基准**。
    # 否则每月 1 号都因「无前一日」被判 closed，看着像休市，其实是基准缺失。
    # 该日不进入输出（见下方 emit 条件）。
    start, end = _resolve_range(start_date, end_date)
    if start > end:
        return _empty_payload(ledger_id, start, end)
    scan_start = start - dt.timedelta(days=1)

    positions = _positions(db, family_id, ledger_id)
    if not positions:
        return _empty_payload(ledger_id, start, end)

    # ── 状态判定集恒为家庭级全量（#1916）──
    # 丢天判定（覆盖不全 / 全无价 / 无持仓）若按账户各自计算，家庭级与各账户丢的
    # 天数不同 ⇒ 差分基准（prev_total_pnl）错位 ⇒ month_total 不可加：
    # 真实库实测「家庭级 -11561.76 vs Σ账户 -12091.66，差 529.90」，份额口径修正后
    # 缺口放大到 3502.91。判定集统一取家庭级全量后，各作用域丢同一批天、同步推进
    # 基准；而 day_total 按持仓可加（份额/已实现均按持仓归集），故
    # Σ账户级 month_total ≡ 家庭级 month_total。家庭级调用时两者为同一集合。
    decision_positions = positions if ledger_id is None else _positions(db, family_id, None)

    # ── 价格批量取回（跨域两步法：先按键分组，再 in_ 一次取回）──
    # 判定集是家庭级全量，价格按全量取（账户级调用也一样）。
    otc_codes = {
        (p.symbol or '').strip()
        for p in decision_positions
        if venue_of_row((p.symbol or '').strip(), p.asset_type) == OTC and (p.symbol or '').strip()
    }
    ex_symbols = {
        (p.symbol or '').strip()
        for p in decision_positions
        if venue_of_row((p.symbol or '').strip(), p.asset_type) == EXCHANGE and (p.symbol or '').strip()
    }
    fund_nav = _collect_fund_nav(db, scan_start, end, otc_codes)
    exchange_prices = _collect_price_history(db, ex_symbols, scan_start, end)

    # ── as-of 份额 / 成本 / 已实现盈亏 ──
    # 传 end 而非 scan_start：`_as_of_shares` 内部按 `eff > <参数>` 截断，
    # 传 scan_start 会把「建仓当天正好落在 scan_start 之后」的流水整条丢掉
    # （实测：买在窗口第 1 天 ⇒ 份额恒为 0 ⇒ 整月 closed）。
    shares, txns = _as_of_shares(db, family_id, end)

    # ── 价格序列按持仓解析一次（#1925 性能）──
    # 日循环里每笔持仓每天要问两次「你属于哪个场所 / 你有哪条序列」，每次
    # `venue_of_row` 都要跑正则（实测 3.23µs），5 年窗口 55 万次 ≈ 1.8 秒纯浪费。
    # 持仓集合在整个区间内不变 ⇒ 结果是不变量。判定用家庭级全集
    # （账户级的价值集是它的子集）；coverage 诊断按本作用域报。
    price_series = {p.id: _price_series_of(p, fund_nav, exchange_prices) for p in decision_positions}
    # 整段无价格序列的持仓（balance 模式 / 无场所判定）——整段区间都不可能有日收益。
    no_price_ids = {pid for pid, series in price_series.items() if not series}

    # 当日价缓存：只在**同一天内**复用（值循环与判定循环各查一次），故每天清空。
    # 键取 `pos.id` 而非 `(id, iso日期)`：热路径上每次省掉 2.31µs 的字符串构造，
    # 也不会随区间长度累积出百万级条目（5 年窗口 = 55 万次查价）。
    price_cache: Dict[int, Optional[int]] = {}

    def price_of(pos: Position, day: dt.date) -> Optional[int]:
        key = pos.id
        if key not in price_cache:
            price_cache[key] = _price_for(day, price_series.get(pos.id))
        return price_cache[key]

    # ── 逐日推进：维护每笔持仓的 as-of 份额与累计已实现 ──
    decision_per_pos = _build_per_pos(decision_positions, shares, txns, scan_start)
    value_per_pos = decision_per_pos if ledger_id is None else _build_per_pos(positions, shares, txns, scan_start)

    days: List[dict] = []
    day = scan_start
    prev_net_worth: Optional[int] = None
    prev_total_pnl: Optional[int] = None

    # 账户级调用时决策集（家庭全集）与值集（本账户）是两套；家庭级调用时同一套。
    per_pos_sets = (value_per_pos,) if value_per_pos is decision_per_pos else (decision_per_pos, value_per_pos)

    while day <= end:
        price_cache.clear()
        for per_pos in per_pos_sets:
            for state in per_pos.values():
                # 建仓日标记：份额由 0 变正的那一天。前一日基准是「未持有」，
                # 若当日就计入市值，差额会把整笔成本算成当日盈利（实测 1/5 建仓
                # 当天冒出等于全部市值−成本的假盈亏）。建仓当日不计盈亏。
                prev = state['shares']
                state['shares'] += state['share_days'].get(day, 0)
                state['is_opening'] = prev <= 0 < state['shares']
                state['realized'] += state['txn_days'].get(day, 0)

        # ── 值计算（仅本作用域持仓；家庭级调用时与决策集同一套）──
        day_total_pnl = 0
        day_net_worth = 0
        opening_pnl = 0

        for state in value_per_pos.values():
            pos: Position = state['pos']
            price = price_of(pos, day)
            if price is None:
                continue
            held_shares = state['shares']
            if held_shares <= 0:
                continue
            market_value = Money.multiply_price_quantity(price, held_shares)
            # 成本基数与 pnl_service.cost_basis_cents 同口径：nav 模式用成本均价×份额。
            # as-of 份额变了，故成本也必须按当日份额重算，不能用当下的 avg_price。
            cost = Money.multiply_price_quantity(pos.avg_price or 0, held_shares)
            rate = state['rate']
            if rate != 1.0:
                market_value = int(Decimal(market_value) * Decimal(str(rate)))
                cost = int(Decimal(cost) * Decimal(str(rate)))
            day_total_pnl += market_value - cost + state['realized']
            day_net_worth += market_value + state['realized']
            if state['is_opening']:
                # 建仓持仓的浮盈是「今天新出现的」，不是「今天赚的」。
                # 记进水平值（次日差分的基准要用），但从当日差分里剔掉。
                opening_pnl += market_value - cost + state['realized']

        daily_pnl = None
        if prev_total_pnl is not None:
            daily_pnl = day_total_pnl - prev_total_pnl - opening_pnl

        # ── 状态判定（家庭级决策集，#1916：各作用域丢同一批天、同步推进基准）──
        day_has_price = False
        # 当日参与判定的可计价持仓（balance 模式 / 无场所判定的一律不算）
        day_priced_count = 0
        day_unpriced_count = 0
        day_opening = False
        # 当天**彻底缺席**（连前值回填都取不到价）的标的 id 集合（#1917）。
        #
        # 判据从「当天有无断档」改为「缺席集合相对前一日是否变化」。原因：
        # 同一批标的连续两天都缺席时，它们对 Σmv 与 Σcost 的影响**相互抵消**，
        # 差分仍然正确；只有集合**变了**（某标的从缺席转为出席或反之），
        # 差分里才混入一次性跳变。
        #
        # 旧判据的实测危害：判为数据不全的日子不写入差分基准，基准因而停留在
        # 更早的日子，次日拿跨多天的差分当单日值 ⇒ 同一日的结果取决于查询
        # 区间（实测 2026-09-19 在整月区间得 4756.40、在小区间得 0.00）。
        #
        # 缺席身份在 `decision_per_pos`（家庭级全量，#1922）上统计，与
        # 「值按各作用域持仓算」正交——谁缺席是全局事实，不该随作用域变化。
        day_missing_ids: set = set()
        # 当天**有**真报价的在场标的数。与 day_missing_ids 合起来区分两种「都没价」：
        #   present==0 ⇒ 全体休市/未同步，回填后所有标的价格都未变，差分恰为 0，
        #     这是诚实的，照常出数（zero）；
        #   present>0 且 missing>0 ⇒ **部分断档**，总额缺了那几笔的市值，
        #     任何单日差分都不可信 ⇒ 判数据不全，且不写入差分基准。
        day_present_count = 0
        # 本日总额是否完整可用于差分基准（部分断档时不可用）
        day_complete = True

        for state in decision_per_pos.values():
            pos: Position = state['pos']
            series = price_series.get(pos.id)
            held = state['shares'] > 0
            # 「当日缺席」= 该标的这一天**没有真报价**（即使回填成功也不算数）。
            # 沿用前值只是让市值不跳空，并不代表「价格没变」这个事实。
            #
            # 新鲜度判定改用预解析的价格序列（#1925）：`no_price_ids` 本就由
            # `price_series` 推导（见上方 `no_price_ids = {... if not series}`），
            # 故 `pos.id not in no_price_ids` ≡ `series` 非空；`day in series`
            # 与旧 `_has_fresh_price` 末尾的 `bool(series) and day in series`
            # 同义，免去每笔每天的 `venue_of_row` 正则解析（5 年窗口 55 万次 ≈1.8s）。
            if held and pos.id not in no_price_ids:
                if day in series:
                    day_present_count += 1
                else:
                    day_missing_ids.add(pos.id)

            price = price_of(pos, day)
            if price is None:
                if not series:
                    day_unpriced_count += 1
                continue
            day_has_price = True
            if state['shares'] <= 0:
                continue
            if state['is_opening']:
                # 建仓当日：仍要计入**水平值**（否则次日差分失去基准，
                # 次日会把「建仓日没算的涨跌」一次性算进去），但当日盈亏记 0。
                day_opening = True
            else:
                day_priced_count += 1

        # 状态判定（顺序即优先级）：
        #  1. 全部持仓都无价格序列 → no_price（balance 模式账户的整月空白，必须与「0收益」区分）
        #  2. 有可计价持仓但当日无价（休市/未同步）→ closed
        #  3. 区间首日无前一日基准 → closed（盈亏不可算，不画成 0）
        #  4. 其余按盈亏正负分 updown / zero
        if day_priced_count == 0 and day_unpriced_count > 0:
            state_code = STATE_NO_PRICE
            daily_pnl = None
        elif day_priced_count == 0 and day_unpriced_count == 0 and not day_opening:
            # 当日无任何持仓（尚未建仓/ 已清仓）⇒ 无从计算盈亏
            state_code = STATE_CLOSED
            daily_pnl = None
        elif day_priced_count == 0 and day_opening:
            # 当日全部是建仓日：水平值已计入，但当日盈亏强制为 0
            # （建仓那一刻浮盈本来就是 0，不是「没数据」）。
            state_code = STATE_ZERO
            daily_pnl = 0
        elif not day_has_price:
            state_code = STATE_CLOSED
            daily_pnl = None
        elif day_missing_ids and day_present_count > 0:
            # **部分断档**（当天有标的有真报价、也有标的没有）⇒ 当日总额缺了缺席
            # 那几笔的市值（回填只能沿用前值），任何单日差分都不可信。
            #
            # 这里刻意**不要求缺席集合相对前一日发生变化**：断档可能连续持续多日
            # （真实库某基金整周未出净值），集合稳定 ≠ 数据完整。
            # 若按「集合是否变化」判，第二、三天就会照常出数，
            # 而那几笔的市值一直靠前值沿用——与断档日根本不是同一口径。
            #
            # 与 `day_present_count == 0`（全体休市/未同步）区分：那种情况回填后
            # 所有标的价格都未变，差分恰为 0，是诚实的，不该判成数据不全。
            state_code = STATE_CLOSED
            daily_pnl = None
            day_complete = False
        elif daily_pnl is None:
            state_code = STATE_CLOSED
        elif daily_pnl > 0 or daily_pnl < 0:
            state_code = STATE_UPDOWN
        else:
            state_code = STATE_ZERO

        rate_pct = None
        if daily_pnl is not None and prev_net_worth not in (None, 0):
            rate_pct = round(daily_pnl / abs(prev_net_worth) * 100, 2)

        if day >= start:
            days.append(
                {
                    'date': day.isoformat(),
                    'daily_pnl': None if daily_pnl is None else round(Money.cents_to_yuan(daily_pnl), 2),
                    'net_worth': round(Money.cents_to_yuan(day_net_worth), 2),
                    'rate': rate_pct,
                    'state': state_code,
                }
            )

        # 覆盖不全的日子不写入基准：错值会污染次日的差分
        if day_complete:
            prev_total_pnl = day_total_pnl
            prev_net_worth = day_net_worth
        day += dt.timedelta(days=1)

    total_cents = sum(int(Decimal(str(d['daily_pnl'])) * 100) for d in days if d['daily_pnl'] is not None)
    logger.info(
        '收益日历派生完成 scope={} 区间={}~{} 天数={} 合计={}',
        'ledger' if ledger_id is not None else 'family',
        start,
        end,
        len(days),
        round(Money.cents_to_yuan(total_cents), 2),
    )

    # coverage 按本作用域自己的持仓报（no_price_ids 是家庭级全集，须按持仓过滤）
    scope_unpriced = sum(1 for p in positions if p.id in no_price_ids)
    priced_total = len(positions) - scope_unpriced
    latest_price_date = _latest_price_date(fund_nav, exchange_prices)

    return {
        'ledger_id': ledger_id,
        'scope': 'ledger' if ledger_id is not None else 'family',
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'month_total': round(Money.cents_to_yuan(total_cents), 2),
        'has_any_price': any(d['state'] in (STATE_UPDOWN, STATE_ZERO) for d in days),
        # ── 覆盖率诊断（前端据此区分「你的标的无估值」与「这个月没数据」）──
        # 这两件事对用户完全不同的处置：前者是持仓属性（本来就不该有日估值），
        # 后者是数据缺口（该有却没有，多半是每日快照任务没跑）。
        # 不区分就会像 #1812 上线首日那样，一律显示「无历史价格序列」——
        # 而真实原因是当月一条价格数据都没有。
        'coverage': {
            'total_positions': len(positions),
            'priced_positions': priced_total,
            'unpriced_positions': scope_unpriced,
        },
        'latest_price_date': latest_price_date,
        'days': days,
    }


def _period_key(date_iso: str, granularity: str) -> str:
    """期间键：`month` → `YYYY-MM`，`year` → `YYYY`。

    **键长即粒度**（7=月，4=年），前端据此决定柱标签，不必再传一个可能与数据
    不一致的展示字段。
    """
    if granularity == GRANULARITY_MONTH:
        return date_iso[:7]
    if granularity == GRANULARITY_YEAR:
        return date_iso[:4]
    return date_iso


def _aggregate_periods(
    days: List[dict],
    granularity: str,
    baseline_net_worth: Optional[float] = None,
) -> List[dict]:
    """把逐日序列聚合成期间序列（月收益 / 年收益视图的唯一数据出口，#1925）。

    汇总规则：

    - `pnl` = 该期间内**非 null** 日盈亏之和 ⇒ 单月的期间值恒等于日粒度下该月的
      `month_total`，某年的期间值恒等于其 12 个月之和——**同一条日序列的两种切法**，
      两种视图不可能对不上；
    - 期间内一天都算不出来 ⇒ `pnl=None`（**缺数据绝不画成 0**，与日粒度同一红线）；
    - `state` 由期间盈亏派生，措辞与日粒度同一套：整天不可算时 `no_price` / `closed`，
      否则 `zero` / `updown`。周末休日本来就是 `closed`，不参与判定，
      故一个正常的月份不会因为有周末就被判成「数据不全」；
    - `rate` 分母取**上一期间末净资产**，首期间取调用方多取的基线日。

    注意 `pnl` 可能只覆盖该期间的一部分日子——日粒度的 `month_total` 本来就是
    「非 null 日盈亏之和」（数据断档日不进和），这里保持同一口径，不另起算法。
    """
    if granularity == GRANULARITY_DAY:
        # 日粒度没有「期间」概念：逐日明细已在 `days` 里，再聚一份是同义反复
        return []

    grouped: Dict[str, List[dict]] = {}
    for day in days:
        grouped.setdefault(_period_key(day['date'], granularity), []).append(day)

    periods: List[dict] = []
    prev_net_worth = baseline_net_worth
    for key, rows in grouped.items():
        computable = [r for r in rows if r['daily_pnl'] is not None]
        no_price_count = sum(1 for r in rows if r['state'] == STATE_NO_PRICE)

        if computable:
            pnl_cents = sum(int(Decimal(str(r['daily_pnl'])) * 100) for r in computable)
            pnl: Optional[float] = round(Money.cents_to_yuan(pnl_cents), 2)
            state = STATE_ZERO if pnl_cents == 0 else STATE_UPDOWN
        else:
            pnl = None
            state = STATE_NO_PRICE if no_price_count else STATE_CLOSED

        # 期间末净资产：取最后一日。周末 / 无持仓日会是 0，向前回溯最近一个非零值，
        # 否则下一个期间的收益率分母会莫名变成 0、rate 恒 null。
        net_worth = next(
            (r['net_worth'] for r in reversed(rows) if r['net_worth'] > 0),
            rows[-1]['net_worth'],
        )

        rate = None
        if pnl is not None and prev_net_worth not in (None, 0):
            rate = round(pnl / abs(prev_net_worth) * 100, 2)

        periods.append(
            {
                'period': key,
                'pnl': pnl,
                'net_worth': net_worth,
                'rate': rate,
                'state': state,
            }
        )
        prev_net_worth = net_worth
    return periods


def build_pnl_series(
    db: Session,
    family_id: int = 1,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ledger_id: Optional[int] = None,
    granularity: str = GRANULARITY_DAY,
) -> dict:
    """按粒度取收益序列 —— 日 / 月 / 年三视图的唯一出口（#1925）。

    Args:
        granularity: `day` 逐日明细回 `days`；`month` / `year` 期间聚合回 `periods`。
            非法值抛 `ValueError`，视图层据此回 400（error_code 1001）。

    **为什么月 / 年视图也要走 `build_daily_pnl_series`**：口径唯一。另起一条
    「按月算」的算法就等于两条口径并存，迟早对不上；正确做法是同一条日序列、
    两种切法（见 `_aggregate_periods`）。性能靠 `_collect_fund_nav` 按持有代码过滤
    与**聚合下推**（年视图只回 5 行期间数据，不回 1800+ 条日明细）解决。

    月 / 年粒度会把起点**再往前挪一天**，只为给首个期间算出收益率分母；
    该日不计入 `days` / `month_total`，与日粒度 `scan_start` 的处理完全一致。
    """
    if granularity not in GRANULARITIES:
        raise ValueError(f'不支持的粒度: {granularity}')

    if granularity == GRANULARITY_DAY:
        payload = build_daily_pnl_series(db, family_id, start_date, end_date, ledger_id)
        payload['granularity'] = GRANULARITY_DAY
        payload['periods'] = []
        return payload

    base_start, base_end = _resolve_range(start_date, end_date)
    scan_start = base_start - dt.timedelta(days=1)
    payload = build_daily_pnl_series(
        db,
        family_id,
        scan_start.isoformat(),
        base_end.isoformat(),
        ledger_id,
    )

    # 基线日的净资产 = 首个期间的收益率分母（该日不在输出区间内，先取出再过滤）
    baseline = next(
        (d['net_worth'] for d in payload['days'] if d['date'] == scan_start.isoformat()),
        None,
    )
    in_range = [d for d in payload['days'] if d['date'] >= base_start.isoformat()]
    total_cents = sum(int(Decimal(str(d['daily_pnl'])) * 100) for d in in_range if d['daily_pnl'] is not None)

    payload['granularity'] = granularity
    payload['start_date'] = base_start.isoformat()
    payload['end_date'] = base_end.isoformat()
    # `month_total` 是历史字段名，语义一直是**区间合计**（前端类型注释亦如此写）
    payload['month_total'] = round(Money.cents_to_yuan(total_cents), 2)
    payload['has_any_price'] = any(d['state'] in (STATE_UPDOWN, STATE_ZERO) for d in in_range)
    payload['periods'] = _aggregate_periods(in_range, granularity, baseline)
    payload['days'] = []  # 聚合下推：期间视图不再回日明细
    return payload


def _latest_price_date(
    fund_nav: Dict[str, Dict[dt.date, int]],
    exchange_prices: Dict[str, Dict[dt.date, int]],
) -> Optional[str]:
    """区间内可用的最新价格日（ISO）。前端用它提示「有数据的最后一天」。"""
    latest: Optional[dt.date] = None
    for series in (*fund_nav.values(), *exchange_prices.values()):
        for d in series:
            if latest is None or d > latest:
                latest = d
    return latest.isoformat() if latest else None


def _empty_payload(ledger_id: Optional[int], start: dt.date, end: dt.date) -> dict:
    return {
        'ledger_id': ledger_id,
        'scope': 'ledger' if ledger_id is not None else 'family',
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'month_total': 0.0,
        'has_any_price': False,
        'coverage': {'total_positions': 0, 'priced_positions': 0, 'unpriced_positions': 0},
        'latest_price_date': None,
        'days': [],
    }
