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

七态（缺数据绝不能画成 0，见设计文档 §2.3；#1917 加 partial、#1942 拆休市）
--------------------------------------------------------------------------
    updown       真实盈亏（有价格序列且 shares>0）
    zero         有价格序列但当日盈亏恰为 0
    partial      **部分断档**：当天有标的有真报价、也有标的没有 ⇒ 照常出数，
                 但标注「数据不完整」（#1917 的 C 方案，见状态判定处注释）
    no_price     无价格序列 —— `valuation_mode='balance'`（银行理财/投顾/实物），
                 其市值来自 `market_value_override` **单值非序列**，天然无历史；
                 切到这类账户若不区分，用户会以为功能坏了
    no_data      **A 股开盘日**却一个可用价都取不到（净值未出 / 快照任务没跑）
    no_position  当天没有持仓（建仓前 / 清仓后），与「休市」「没数据」都无关
    closed       **非 A 股开盘日**（周末 / 法定节假日 / 调休补班的周末）

`closed` 的判据是 `core/trading_calendar.is_trading_day()`（唯一权威出口，#1217），
**不是**「当天取不到价格」。#1942 之前，凡净值没同步到的交易日都被压成同一种
`closed`、UI 一律显示「休市」，用户看到「9 月一半都是休市」（真实库实测 30 天里
20 天无可用价），与真实开盘日历不符；更糟的是把「数据没同步」（用户该去跑同步任务）
误报成「市场关门」（用户只能干等），无从处置。现在两者必须可辨：
**有值但不全 → `partial`；一个值都没有 → 开盘日 `no_data` / 非开盘日 `closed`。**

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
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.core.trading_calendar import is_trading_day
from app.core.venues import EXCHANGE, OTC, venue_of_row
from app.domains.funds.models import DailyWorth
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.transactions.models import Transaction
from app.services import pnl_snapshot_store
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
# #1942 起与 `STATE_CLOSED` 分家：开盘日**一个可用价都没有** = 数据没同步（no_data），
# 非开盘日 = 休市（closed）。混用会让「同步任务没跑」伪装成「市场关门」。
STATE_NO_DATA = 'no_data'
# 当天没有持仓（建仓前 / 清仓后）。既不是休市，也不是缺数据。
STATE_NO_POSITION = 'no_position'
# 部分断档（#1917 的 C 方案）：当天确有标的有真报价，另有标的当日无报价。
# **照常给出数值**（断档那几笔对 Σmv 与 Σcost 的影响在基准与当日之间对称抵消），
# 但用独立状态告知用户「该日数据不全」。不可与 `closed` 合并——那是「无数据」，
# 与「有数据但不完整」对用户是完全不同的含义。
#
# 与 #1942 的 `no_data` 分工：`partial` = 有真报价、只是不全（**照常出数**）；
# `no_data` = 一条真报价都没有（**不出数**）。两者都不可与 `closed`（真休市）混用。
STATE_PARTIAL = 'partial'

# 某标的当天没价格时，最多向前沿用最近多少天的价格（#1812）。
# 太大：一个月没更新的标的会被当成「价格不变」而画出 0 收益，掩盖数据缺失；
# 太小：单日数据抖动就会让市值归零、差分出现假跳空。7 天覆盖周末与节假日。
_STALE_CARRY_DAYS = 7

# ── 物化新鲜窗（#1926）────────────────────────────────────────────────────────
# `>= 今天 - PRICE_FRESH_DAYS` 的日期**永不落库**、读时恒现算，其行也就从不被写出去。
#
# 为什么这样能免掉「价格同步」的失效钩子：日常增量同步写的是今天 / 近几天的净值，
# 而新到的价格最多被 `_STALE_CARRY_DAYS` 天的前值回填**向前**吃到 7 天——
# 新数据可能改变的日子，正好被这 8 天窗覆盖。于是「同一行先算完、后到新价格」
# 这件事在结构上不可能发生，不必靠钩子去补。
#
# 代价是每次读都要重算末尾 8 天（近 30 天的视图 ≈8/30），远小于整窗重算。
# 例外是**历史回填**（`sync --job fund_nav --full-sync`）：它改的是窗口外的老日期，
# 由 sync 编排器在成功后调 `pnl_snapshot_store.purge_all()` 整表作废。
#
# 取值必须 ≥ `_STALE_CARRY_DAYS + 1`：新价格对 T 日的影响沿前值回填传播到
# T + _STALE_CARRY_DAYS，窗比传播半径短一天就会漏掉尾巴。
PRICE_FRESH_DAYS = _STALE_CARRY_DAYS + 1

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
    """流水生效日：优先 confirm_date，缺失回退 trade_date 的日期部分。

    `trade_date` 列型是 `DateTime`（到分钟），但**flush 之中**读到的未必是方言
    解析后的 `datetime`——`pnl_snapshot_store._before_flush` 在 flush 里读属性，
    拿到的可能是写入时塞进去的 `date` 对象（`.date()` 会 `AttributeError`）。
    日历自身只读已提交的行、拿不到这个形态，故这层判断是**失效钩子接上后**
    才暴露的；两种类型都收，语义不变。
    """
    if txn.confirm_date:
        return txn.confirm_date
    trade = txn.trade_date
    if not trade:
        return None
    return trade.date() if hasattr(trade, 'date') else trade


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
    回填**只保证市值不跳空**，不代表「价格没变」这个事实：周末 / 全市场没同步时
    所有标的都回填不出，差分虽恰为 0，也不出数（状态由 `is_trading_day` 分派成
    `closed` 休市 / `no_data` 没同步，见下方状态判定），不会被填成「0 收益」。
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


# ──────────────────── 物化读路径的辅助件（#1926）────────────────────────────
#
# 这一组函数只解决一件事：让「先算 A 段、再算 B 段、拼起来」与「一次算 A+B 段」
# 逐位相等。任何一条做不到，物化就是静默错数字（#1812 那批 bug 的复刻）。


def _date_range(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    """闭区间逐日迭代——物化读路径要逐日比对「这天有没有行」。"""
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def _fresh_window_start() -> dt.date:
    """物化新鲜窗左端（含）：该日起的日期读时恒现算、永不落库。见 `PRICE_FRESH_DAYS`。"""
    from app.core.time_utils import now_shanghai

    return now_shanghai().date() - dt.timedelta(days=PRICE_FRESH_DAYS)


def _price_code_sets(decision_positions: List[Position]) -> Tuple[set, set]:
    """按场所拆出要查的基金代码 / 场内代码（判定集是家庭级全量）。"""
    otc_codes: set = set()
    ex_symbols: set = set()
    for p in decision_positions:
        symbol = (p.symbol or '').strip()
        if not symbol:
            continue
        venue = venue_of_row(symbol, p.asset_type)
        if venue == OTC:
            otc_codes.add(symbol)
        elif venue == EXCHANGE:
            ex_symbols.add(symbol)
    return otc_codes, ex_symbols


def _price_presence(
    db: Session,
    decision_positions: List[Position],
    start: dt.date,
    end: dt.date,
) -> Tuple[set, Optional[dt.date]]:
    """`(整段无价格序列的持仓 id 集合, 区间内最新价格日)`。

    窗口 = `[start - 1, end]`，与现算取价的 `scan_start..end` **逐字一致**——
    `no_price_ids` 的语义是「这段窗口内有无价格序列」，窗口一变答案就变。

    **为什么不复用 `price_series` 推导**（#1926）：物化读只取尾段的价格行，
    前段的 `price_series` 对它是空的；拿它推会让同一个问题在「缓存命中」与
    「缓存未命中」时给出不同答案。等价性是一行恒等式::

        bool(fund_nav.get(code))  ⟺  该代码在窗口内有行  ⟺  MAX(date) 组存在

    只回 `code -> MAX(date)` 一行/代码，走 `(fund_code, date)` / `(symbol, trade_date)`
    唯一索引，成本 O(代码数) 而非 O(代码数 × 天数)——所以缓存全命中时，
    `coverage` / `latest_price_date` 这两个区间级字段仍能廉价算出来，
    不必为了诊断字段把全量价格行再拉一遍。
    """
    decision_start = start - dt.timedelta(days=1)
    otc_codes, ex_symbols = _price_code_sets(decision_positions)

    otc_latest: Dict[str, dt.date] = {}
    if otc_codes:
        otc_latest = dict(
            db.query(DailyWorth.fund_code, func.max(DailyWorth.date))
            .filter(
                DailyWorth.fund_code.in_(otc_codes),
                DailyWorth.date >= decision_start,
                DailyWorth.date <= end,
            )
            .group_by(DailyWorth.fund_code)
            .all()
        )
    ex_latest: Dict[str, dt.date] = {}
    if ex_symbols:
        ex_latest = dict(
            db.query(PriceHistory.symbol, func.max(PriceHistory.trade_date))
            .filter(
                PriceHistory.symbol.in_(ex_symbols),
                PriceHistory.trade_date >= decision_start,
                PriceHistory.trade_date <= end,
            )
            .group_by(PriceHistory.symbol)
            .all()
        )

    no_price_ids: set = set()
    latest: Optional[dt.date] = None
    for p in decision_positions:
        symbol = (p.symbol or '').strip()
        venue = venue_of_row(symbol, p.asset_type)
        if venue == OTC:
            matched = otc_latest.get(symbol)
        elif venue == EXCHANGE:
            matched = ex_latest.get(symbol)
        else:
            matched = None
        if matched is None:
            no_price_ids.add(p.id)
        elif latest is None or matched > latest:
            latest = matched
    return no_price_ids, latest


def _coverage(positions: List[Position], no_price_ids: set) -> dict:
    """按本作用域自己的持仓报覆盖率（`no_price_ids` 是家庭级全集，须按持仓过滤）。"""
    unpriced = sum(1 for p in positions if p.id in no_price_ids)
    return {
        'total_positions': len(positions),
        'priced_positions': len(positions) - unpriced,
        'unpriced_positions': unpriced,
    }


def _row_meta(row) -> dict:
    """物化行 → 与现算结果同构的中间形态（整数分 / 整数基点）。"""
    return {
        'daily_pnl_cents': row.daily_pnl_cents,
        'net_worth_cents': row.net_worth_cents,
        'rate_bp': row.rate_bp,
        'state': row.state,
    }


def _day_to_api(date: dt.date, meta: dict) -> dict:
    """把**存储形态**（整数分 / 整数基点）还原成 API 形态（元 / 百分比）。

    与现算路径逐字对齐——物化读与现算读必须逐位相等，单位换算是唯一可能引入
    差异的地方，故逐项写明依据：

    - 金额：`round(Money.cents_to_yuan(x), 2)`，与现算同一条 `Money` 出口，整数分
      进出无损；
    - 收益率：现算给的是 2 位小数的 float，存时经 `Decimal(str(v)) * 100` 取整基点
      （`str` 给最短往返表示，故十进制上是精确的），读时 `float(Decimal(bp) / 100)`
      还原到**同一个** IEEE-754 double；
    - 负零：`round(-0.0001, 2)` 得 `-0.0`（大额组合的 1 分钱日盈亏就会命中），
      而整数基点 0 会把这个符号吃掉。故按「基点为 0 且当日盈亏为负」补回 `-0.0`，
      否则前端从 `-0.00%` 变成 `0.00%`——数值相等、字面不同，
      「物化读 ≡ 现算读」就不再逐位成立。
    """
    pnl = meta['daily_pnl_cents']
    rate_bp = meta['rate_bp']
    rate = None
    if rate_bp is not None:
        rate = float(Decimal(rate_bp) / 100)
        if rate_bp == 0 and pnl is not None and pnl < 0:
            rate = -0.0
    return {
        'date': date.isoformat(),
        'daily_pnl': None if pnl is None else round(Money.cents_to_yuan(pnl), 2),
        'net_worth': round(Money.cents_to_yuan(meta['net_worth_cents']), 2),
        'rate': rate,
        'state': meta['state'],
    }


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
          'month_total': float, 'range_rate': float|None, 'has_any_price': bool,
          'days': [{'date','daily_pnl','rate','state'}, ...]}

         `rate` = 当日盈亏 / 前一日总资产；`range_rate` = 区间盈亏 / **区间前一天**总资产
         （两者同分母口径，单位均为 %）。**前端禁止二次计算**，一切数值出口在此。

     恒等式（#1916）：**家庭级 month_total ≡ Σ 各账户级 month_total**，成立条件有三，
    缺一不可：
     1. 份额/已实现按**持仓**归集、流水不按 ledger 过滤（口径先例 `get_ledger_pnl` #1220）；
     2. 状态判定（丢天/覆盖不全/无持仓）恒用**家庭级全量决策集**——各作用域丢同一批天、
        同步推进差分基准，否则 month_total 的差分链错位、不可加（实测差 3502.91）；
     3. day_total 按持仓可加（每笔持仓恰属一个账户）。

    ── 物化读路径（#1926）──────────────────────────────────────────────────────
    以前每次调用都 as-of 现算整段区间（1 年 ≈1.3s、5 年 ≈3.6s，成本随天数线性）。
    现在按日落库、缺哪天补哪天：

    1. 先取物化行（新鲜窗内的行不算数，见 `PRICE_FRESH_DAYS`）；
    2. 区间全命中 ⇒ 直接拼 payload，`coverage` / `latest_price_date` 走
       `_price_presence` 的廉价聚合查询，不取全量价格行；
    3. 有缺失 ⇒ 从 `first_missing` 起**只重算尾段**（其前一天作差分基准），
       前段用物化行拼，随后 upsert 回去，下次命中；
    4. `daily_pnl`/`rate` 为 NULL 的行照原样输出 `None`——**缺数据绝不画成 0**。

    **物化只省时间、不改口径**：拼接结果与「整窗现算」逐位相等由
    `tests/services/test_pnl_snapshot_store.py` 钉住。三条必要条件缺一不可：
    取价窗口前扩 `_STALE_CARRY_DAYS`（首日答案不再取决于查询起点）、
    `no_price_ids`/`latest_price_date` 用固定窗口的存在性聚合查询、
    基准日的水平值与窗口起点无关——`_build_per_pos` 先注入 `scan_start` 之前的
    累计、循环再补 `[scan_start, A]`，故 day A 的份额/已实现恒为 `Σ_{d≤A}`
    （#1917 之后基准无条件推进，也不再有「断档日不能当基准」这回事）。

    物化窗口比 `start` 多带一天 `start - 1`：`range_rate` 的分母是**区间前一天**
    的净资产，全量命中时若不存它，分母就无处可取。
    """
    start, end = _resolve_range(start_date, end_date)
    if start > end:
        return _empty_payload(ledger_id, start, end)

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
    # 覆盖率诊断按**原始窗口**算，缓存命中与否都不影响它（见 `_price_presence`）。
    no_price_ids, latest_dt = _price_presence(db, decision_positions, start, end)
    latest_price_date = latest_dt.isoformat() if latest_dt else None
    # as-of 份额/流水在此取一次：`first_txn_date` 在**全量命中**路径上也要用到，
    # 而那条路根本不进 `_compute_days`；留在里面取会变成命中即白查一次。
    shares, txns = _as_of_shares(db, family_id, end)

    # ── 取物化行（含 `start - 1`：`range_rate` 的分母要区间前一天的净资产）──
    baseline_day = start - dt.timedelta(days=1)
    cached = pnl_snapshot_store.load_days(db, family_id, ledger_id, baseline_day, end)
    fresh_start = _fresh_window_start()
    for d in [d for d in cached if d >= fresh_start]:
        cached.pop(d)  # 新鲜窗内的行即使存量里有也当作没有（读时恒现算）

    first_missing: Optional[dt.date] = None
    for d in _date_range(baseline_day, end):
        if d not in cached:
            first_missing = d
            break

    computed_by_date: Dict[dt.date, dict] = {}
    metas: Dict[dt.date, dict] = {}
    loop_start: Optional[dt.date] = None
    if first_missing is None:
        metas = {d: _row_meta(cached[d]) for d in _date_range(baseline_day, end)}
        recomputed = 0
    else:
        # 起点就是第一个缺口，不必再回退找「可用的基准日」：`_build_per_pos` 先注入
        # `scan_start` 之前的累计、循环再补 `[scan_start, A]`，故 `first_missing - 1`
        # 的水平值与从哪天起算无关（#1917 之后基准也无条件推进，不再有「断档日
        # 不能当基准」这回事）。回退逻辑连同 `baseline_ok` 列一并移除，见 docstring。
        loop_start = first_missing
        computed = _compute_days(
            db,
            family_id,
            positions,
            decision_positions,
            start,
            end,
            ledger_id,
            loop_start,
            no_price_ids,
            shares,
            txns,
        )
        pnl_snapshot_store.save_days(
            db,
            family_id,
            ledger_id,
            computed,
            max_date=fresh_start - dt.timedelta(days=1),
        )
        computed_by_date = {dt.date.fromisoformat(m['date']): m for m in computed}
        metas = {d: _row_meta(cached[d]) for d in _date_range(baseline_day, loop_start) if d in cached}
        recomputed = len(computed)

    def _meta_of(d: dt.date) -> dict:
        """某日的存储形态：缺口之后现算、之前用物化行，与取数窗口无关。"""
        if loop_start is not None and d >= loop_start:
            return computed_by_date[d]
        return metas[d]

    days = [_day_to_api(d, _meta_of(d)) for d in _date_range(start, end)]

    total_cents = sum(int(Decimal(str(d['daily_pnl'])) * 100) for d in days if d['daily_pnl'] is not None)

    # ── 区间收益率（#1942）：分母 = 区间前一天的净资产 ──
    # 与首个期间的 `rate` 同分母口径（不是把日收益率相加——那会算错复利）。
    # `range_baseline` 与 `total_cents` 同为分，比值与单位无关。
    #
    # 三个「不可算」都要回 None，**不能借 0.0 兜底**（「缺数据绝不画成 0」这条红线
    # 在区间层同样成立）：
    #   · 无基准 / 基准为 0（区间首日就无前值）
    #   · 区间内**没有任何可算日**（整段 no_price / no_data / closed），
    #     此时 total_cents 恒为 0，若报 0.00% 会被读成「这段时间没涨没跌」。
    #   · 基准日那行本身取不到（罕见，如落在未物化的新鲜窗内）——宁可不报也不猜。
    baseline_meta = computed_by_date.get(baseline_day, metas.get(baseline_day))
    range_baseline = None if baseline_meta is None else baseline_meta['net_worth_cents']
    has_computable = any(d['daily_pnl'] is not None for d in days)
    range_rate = (
        round(total_cents / abs(range_baseline) * 100, 2)
        if has_computable and range_baseline not in (None, 0)
        else None
    )

    # ── 「投资以来」的起点（#1942 年视图）──
    # 最早一笔**改变份额**的流水（买 / 卖 / 转入 / 转出）的生效日，按本作用域持仓过滤。
    # 年视图要「投资以来每一年占一格」，前端必须知道起点；旧实现写死 3 年窗口
    # （`YEAR_WINDOW`），窗口边界与真实建仓年份无关，年份一多就既看不全也对不上。
    # `shares` 已按 position_id 归组且只含 `eff <= end` 的流水，故取键的最小值即得，
    # 不需要再查一次库。
    scope_position_ids = {p.id for p in positions}
    first_txn = min(
        (day for pid in scope_position_ids for day in shares.get(pid, {})),
        default=None,
    )

    logger.info(
        '收益日历派生完成 scope={} 区间={}~{} 天数={} 合计={} 物化补算={}',
        'ledger' if ledger_id is not None else 'family',
        start,
        end,
        len(days),
        round(Money.cents_to_yuan(total_cents), 2),
        recomputed,
    )

    return {
        'ledger_id': ledger_id,
        'scope': 'ledger' if ledger_id is not None else 'family',
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'month_total': round(Money.cents_to_yuan(total_cents), 2),
        'range_rate': range_rate,
        'has_any_price': any(d['state'] in (STATE_UPDOWN, STATE_ZERO) for d in days),
        # ── 覆盖率诊断（前端据此区分「你的标的无估值」与「这个月没数据」）──
        # 这两件事对用户完全不同的处置：前者是持仓属性（本来就不该有日估值），
        # 后者是数据缺口（该有却没有，多半是每日快照任务没跑）。
        # 不区分就会像 #1812 上线首日那样，一律显示「无历史价格序列」——
        # 而真实原因是当月一条价格数据都没有。
        'coverage': _coverage(positions, no_price_ids),
        'latest_price_date': latest_price_date,
        # 「投资以来」起点：最早一笔改变份额的流水生效日；无持仓 / 无流水时 None
        'first_txn_date': first_txn.isoformat() if first_txn else None,
        'days': days,
    }


def _compute_days(
    db: Session,
    family_id: int,
    positions: List[Position],
    decision_positions: List[Position],
    start: dt.date,
    end: dt.date,
    ledger_id: Optional[int],
    loop_start: dt.date,
    no_price_ids: set,
    shares: Dict[int, Dict[dt.date, int]],
    txns: Dict[int, List[Transaction]],
) -> List[dict]:
    """现算 `[loop_start, end]` 并返回**存储形态**（整数分 / 整数基点，供 `save_days`）。

    `loop_start > start` 时只重算尾段，前段由调用方拿物化行拼（部分重算）。
    `shares` / `txns` 由调用方一次取好传入——`first_txn_date` 在全量命中路径上
    也要用到，留在这里取会变成「命中即白查一次」。
    注意几处**刻意与窗口解耦**的口径：

    - `no_price_ids` 由调用方按**原始窗口** `[start-1, end]` 给入，不在本函数内从
      `price_series` 推导——本函数的取价窗口已前扩，推出来的集合会不一样；
    - 输出条件是 `day >= loop_start` 而非 `>= start`，否则会把 `loop_start - 1`
      也写进结果，与前段的物化行重复。
    """
    # 往前多取一天，**只为给区间首日建立差分基准**。
    # 否则每月 1 号都因「无前一日」而不可算（#1942 起报 no_data，而不是「休市」，
    # 因为成因是基准缺失而非市场关门）。该日不进入输出（见下方 emit 条件）。
    scan_start = loop_start - dt.timedelta(days=1)

    # ── 价格批量取回（跨域两步法：先按键分组，再 in_ 一次取回）──
    # 判定集是家庭级全量，价格按全量取（账户级调用也一样）。
    otc_codes, ex_symbols = _price_code_sets(decision_positions)
    # 价格窗口起点从 `scan_start` 再往前扩 `_STALE_CARRY_DAYS` 天。两条独立理由，
    # 缺一条都会踩到：
    #
    # · #1953（口径）：`scan_start`（区间前一天）当天若无净值行（周末/节假日/基金
    #   当日没出净值），`_price_for` 会向前回溯至多 7 天取前值回填；窗口若从
    #   `scan_start` 起，回溯到的那些日期不在窗口内 ⇒ 取不到价 ⇒ `scan_start`
    #   净资产被低估（甚至按 0 计）⇒ 首个区间日的差分把整笔累计浮盈吞成当日盈亏
    #   （单月合计虚增，违反区间无关性）。
    # · #1926（等价性）：`_price_for` 在某天要回看 `[day-7, day]`，窗口不前扩则
    #   区间首日的回看被窗口起点截断 ⇒ **同一笔持仓换个月份看会算出不同的首日盈亏**
    #   （结果取决于查询区间），物化读与现算读必然分叉。
    #
    # 前扩后回看完整，窗口长度既不再是口径的一部分、也不再是结果的隐含输入。
    # 多取这 7 天只让 SQL 区间加宽 7 天（IN 过滤下增量可忽略）。
    fetch_start = scan_start - dt.timedelta(days=_STALE_CARRY_DAYS)
    fund_nav = _collect_fund_nav(db, fetch_start, end, otc_codes)
    exchange_prices = _collect_price_history(db, ex_symbols, fetch_start, end)

    # ── as-of 份额 / 成本 / 已实现盈亏 ──
    # `shares`/`txns` 已按 `end` 截断后传入（而非按 `scan_start`）：`_as_of_shares`
    # 内部按 `eff > <参数>` 截断，按 `scan_start` 截会把「建仓当天正好落在
    # scan_start 之后」的流水整条丢掉（实测：买在窗口第 1 天 ⇒ 份额恒为 0 ⇒ 整月 closed）。

    # ── 价格序列按持仓解析一次（#1925 性能）──
    # 日循环里每笔持仓每天要问两次「你属于哪个场所 / 你有哪条序列」，每次
    # `venue_of_row` 都要跑正则（实测 3.23µs），5 年窗口 55 万次 ≈ 1.8 秒纯浪费。
    # 持仓集合在整个区间内不变 ⇒ 结果是不变量。判定用家庭级全集
    # （账户级的价值集是它的子集）；coverage 诊断按本作用域报。
    price_series = {p.id: _price_series_of(p, fund_nav, exchange_prices) for p in decision_positions}
    # 整段无价格序列的持仓（balance 模式 / 无场所判定）——整段区间都不可能有日收益。
    # `no_price_ids` 由调用方按**原始窗口**注入（见 `_price_presence`），刻意不在这里
    # 从 `price_series` 推：本函数的取价窗口已前扩 `_STALE_CARRY_DAYS`，推出来的集合
    # 会把前扩进来的行也算成「有序列」，与缓存命中路径的答案分叉。

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
        # 当天**有**真报价的在场标的数。与 day_missing_ids 合起来区分两种「没出报价」：
        #   present==0 ⇒ 全体标的当天都没出真报价：可能是非开盘日（回填后价格未变，
        #     差分恰为 0），也可能是开盘日但净值/快照没同步。**两者必须分开**——
        #     前者是「休市」，后者是「没数据」（#1942）。区分靠
        #     `core/trading_calendar.is_trading_day()`，不靠「有没有价格」。
        #   present>0 且 missing>0 ⇒ **部分断档**：有真报价、只是不全 ⇒ `partial`
        #     照常出数（#1917 的 C 方案，值不能丢），与「一个价都没有」分开。
        day_present_count = 0
        # 当天**持有中**的标的数（含 balance 模式等无价序列的持仓）。
        # 恒为 0 只有一种解释：当天没有持仓（建仓前 / 清仓后）⇒ 与「休市」「缺数据」
        # 都无关，是一种独立状态（no_position）。不单独判的话，建仓前的一个月
        # 会整月显示「休市」，同样是把「不是交易日」错报成「当天没有仓位」。
        #
        # 注：原 `day_complete`（「本日总额是否完整可用于差分基准」）已随 #1917 的
        # A 方案删除——基准无条件推进，见循环末尾。
        day_held_count = 0

        for state in decision_per_pos.values():
            pos: Position = state['pos']
            series = price_series.get(pos.id)
            held = state['shares'] > 0
            # 「当日缺席」= 该标的这一天**没有真报价**（即使回填成功也不算数）。
            # 沿用前值只是让市值不跳空，并不代表「价格没变」这个事实。
            #
            # 新鲜度判定改用预解析的价格序列（#1925）：`no_price_ids` 由调用方按
            # **原始窗口**给出（见 `_price_presence`），与 `series` 非空在整窗现算时
            # 等价；`day in series` 与旧 `_has_fresh_price` 末尾的
            # `bool(series) and day in series` 同义，免去每笔每天的 `venue_of_row`
            # 正则解析（5 年窗口 55 万次 ≈1.8s）。
            #
            # `series or {}`：部分重算时取价窗口只到尾段，某标的可能在原始窗口内
            # 有序列、而尾段窗口里一条都没有（`_price_series_of` 回 None）。
            # 整窗现算下 `not in no_price_ids` 已保证 `series` 非空，加 `or {}`
            # 对它是无操作——只补上窗口变窄后会踩的 `None` 下标。
            if held:
                day_held_count += 1
            if held and pos.id not in no_price_ids:
                if day in (series or {}):
                    day_present_count += 1
                else:
                    day_missing_ids.add(pos.id)

            price = price_of(pos, day)
            if price is None:
                # 按 `no_price_ids` 而非 `not series` 判（#1926）：`series` 是尾段
                # 窗口的，可能因窗口变窄而空，那不等于「这个标的根本没有价格序列」
                # ——整段区间都不可能有日收益的只有后者，判错了会把部分重算的
                # 结果算成 no_price，与缓存命中路径分叉。
                if pos.id in no_price_ids:
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
        #  1. 全部可计价持仓当天都无价、且存在无价格序列的持仓 → no_price
        #     （balance 模式账户的整月空白，必须与「0 收益」区分）
        #  2. 当天没有持仓（建仓前 / 清仓后）→ no_position
        #  3. 当日全部是建仓日 → zero（建仓那一刻浮盈本就是 0）
        #  4. 一个可用价都没有（含「全体都没出真报价、全靠前值回填」）→ 看
        #     **A 股开盘日历**：开盘日 no_data / 非开盘日 closed
        #  5. 部分标的断档 → partial（#1917 C 方案：照常出数，另标不完整）
        #  6. 区间首日无前一日基准 → 同 4（首日不进输出，仅防御）
        #  7. 其余按盈亏正负分 updown / zero
        #
        # 4 与 5 互斥：4 要求 `present == 0`，5 要求 `present > 0`。故「有值但
        # 不完整」永远不会被日历改判成「休市 / 未同步」——丢值就是丢钱。
        if day_priced_count == 0 and day_unpriced_count > 0:
            state_code = STATE_NO_PRICE
            daily_pnl = None
        elif day_held_count == 0 and not day_opening:
            # 当日无任何持仓（尚未建仓 / 已清仓）⇒ 无从计算盈亏。
            # 这里**不能**报「休市」：那天市场可能正常开盘，只是你没有仓位。
            state_code = STATE_NO_POSITION
            daily_pnl = None
        elif day_priced_count == 0 and day_opening:
            # 当日全部是建仓日：水平值已计入，但当日盈亏强制为 0
            # （建仓那一刻浮盈本来就是 0，不是「没数据」）。
            state_code = STATE_ZERO
            daily_pnl = 0
        elif not day_has_price or (day_present_count == 0 and day_missing_ids):
            # 「当天一个可用价都没有」的两种情形（全部标的都取不到价 / 全体标的
            # 当天都没出真报价，全靠前值回填）在这里合流，一律按 **A 股开盘日历**分派：
            #   开盘日   → no_data（净值未发布 / 快照任务没跑 / 断档超出回填窗）
            #   非开盘日 → closed（周末 / 法定节假日 / 调休补班的周末）
            #
            # #1942 的根因就在这一步之前：休市判据原本是「当天取不到价格」，
            # 于是净值同步滞后与市场关门被压成同一种 `closed`，UI 上一律显示
            # 「休市」。用户的直接观感是「9 月一半都是休市，与实际不符」——
            # 日历没错，是判据把「数据没同步」说成了「市场关门」。
            # 判据必须走 `core/trading_calendar.is_trading_day()`（#1217 唯一出口）：
            # 它含「调休补班的周末照常休市」这条修正，绕过它直接调 chinese_calendar
            # 会把 2026-09-20 这类补班日算成开盘日。
            # 成本：只在「拿不到价」的日子调用，正常出数的日子一次都不调。
            state_code = STATE_NO_DATA if is_trading_day(day) else STATE_CLOSED
            daily_pnl = None
        elif day_missing_ids and day_present_count > 0:
            # **部分断档**（当天有标的有真报价、也有标的没有）⇒ 当日总额缺了缺席
            # 那几笔的当日市值（回填只能沿用前值）。
            #
            # 这里刻意**不要求缺席集合相对前一日发生变化**：断档可能连续持续多日
            # （真实库某基金整周未出净值），集合稳定 ≠ 数据完整。
            # 若按「集合是否变化」判，第二、三天就会照常出数，
            # 而那几笔的市值一直靠前值沿用——与断档日根本不是同一口径。
            #
            # #1917 的 C 方案：**照常给出数值**，另用 `partial` 标明完整性。
            # 此前判 `closed`（不出数）会让真实盈亏凭空消失，并被下一个可算日
            # 一次性错位吸收——实测真实库 09-18 的真实盈利 +5,744.06 就这样丢失，
            # 09-19 反而报出一个跨 4 天的假值 4756.40。
            #
            # **本分支不按开 / 闭盘再拆**（#1942 与 #1917 的接缝）：`partial` 是
            # 「有真报价、只是不全」，值必须给出来——若因为「那天是周末」就改成
            # closed 并丢掉这个数，周末那几笔真发生的净值变动就永远不进任何一天。
            # 按日历分派只发生在**一个可用价都没有**的分支（上面那条）。
            state_code = STATE_PARTIAL
        elif daily_pnl is None:
            # 只有**扫描首日**会走到这里（`prev_total_pnl` 尚无值）；它不进输出。
            # #1917 的 A 方案之后基准无条件推进，故后续任何一天都有基准，
            # 不会因为「前一天数据不全」而整段不可算。
            # #1942 起同样按开 / 闭盘分派，不再一律报「休市」。
            state_code = STATE_NO_DATA if is_trading_day(day) else STATE_CLOSED
            daily_pnl = None
        elif daily_pnl > 0 or daily_pnl < 0:
            state_code = STATE_UPDOWN
        else:
            state_code = STATE_ZERO

        rate_pct = None
        if daily_pnl is not None and prev_net_worth not in (None, 0):
            rate_pct = round(daily_pnl / abs(prev_net_worth) * 100, 2)

        # 输出条件用 `loop_start` 而非 `start`（#1926 部分重算）：`loop_start > start`
        # 时若仍按 `start` 判，`loop_start - 1` 会被写进结果、与前段的物化行重复。
        # 两者在整窗现算下等价——`scan_start = start - 1` 本就被原条件排除。
        #
        # `range_baseline`（`range_rate` 的分母 = 区间前一天净资产）刻意**不在这里
        # 捕获**：它要的是 `start - 1` 的净资产，而部分重算的循环是从 `loop_start - 1`
        # 才起的，`loop_start > start` 时首轮 `prev_net_worth` 还是 None——捕出来会
        # 变成 None 或锚到错误的某天。改由 `build_daily_pnl_series` 从物化行取
        # `start - 1` 的 `net_worth_cents`，与取数窗口无关。
        if day >= loop_start:
            # 这里出的是**存储形态**（整数分 / 整数基点），不是 API 形态：
            # `daily_pnl`/`day_net_worth` 本来就是分，`Money` 换算挪到 `_day_to_api`
            # 一次做完——热路径上少一轮 float 往返，物化行与现算结果也就共用同一个
            # 转换出口，不可能各算各的。
            days.append(
                {
                    'date': day.isoformat(),
                    'daily_pnl_cents': daily_pnl,
                    'net_worth_cents': day_net_worth,
                    'rate_bp': None if rate_pct is None else int(Decimal(str(rate_pct)) * 100),
                    'state': state_code,
                }
            )

        # 基准**无条件推进**（#1917 的 A 方案）。
        #
        # 旧行为「数据不全就不写基准」造成**差分基准漂移**：基准冻结在更早的日子，
        # 释放那天的差分就跨越了不连续的多天，把那几天的涨跌一次性算成单日值。
        # 实测（真实库 2026-09，整月区间）：09-15~09-18 等 11 天判数据不全 ⇒ 基准
        # 停在 09-17 ⇒ 09-19（周六，全市场休市）报出 4756.40，而它真实值是 0.00；
        # 同一日在小区间里因起点不同、基准推进次数不同，答案是 0.00。
        # **同一笔数据两个答案，且取决于查询区间** —— 这就是 #1917 要消灭的缺陷。
        #
        # 断档日推进基准不会让后续差分出错：断档那几笔始终缺席，
        # 它们对 Σmv 与 Σcost 的影响在基准与当日之间**对称抵消**，
        # 差分依然只反映「在场标的的市值变动」。
        prev_total_pnl = day_total_pnl
        prev_net_worth = day_net_worth
        day += dt.timedelta(days=1)

    return days


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
    - `state` 由期间盈亏派生，措辞与日粒度同一套（六态）：整天不可算时按**信息量**
      取成因——`no_price`（产品本无日估值）> `no_data`（没同步）> `no_position`
      （当时没仓位）> `closed`（整期非开盘日）。周末休日本来就是 `closed`，
      不参与判定，故一个正常的月份不会因为有周末就被判成「数据不全」；
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
        day_states = {r['state'] for r in rows}

        if computable:
            pnl_cents = sum(int(Decimal(str(r['daily_pnl'])) * 100) for r in computable)
            pnl: Optional[float] = round(Money.cents_to_yuan(pnl_cents), 2)
            state = STATE_ZERO if pnl_cents == 0 else STATE_UPDOWN
        else:
            pnl = None
            # 整期一天都算不出来时，按**信息量从大到小**挑成因：先报「产品本无日估值」
            # （用户改不了），再报「没同步」（用户能处置），最后才是「当时没仓位」与
            # 「整期非开盘日」。顺序写死而不用集合去重，是为了让同一份数据永远得到
            # 同一个标签——前端与测试都按这个优先级断言。
            if STATE_NO_PRICE in day_states:
                state = STATE_NO_PRICE
            elif STATE_NO_DATA in day_states:
                state = STATE_NO_DATA
            elif STATE_NO_POSITION in day_states:
                state = STATE_NO_POSITION
            else:
                state = STATE_CLOSED

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
    # 区间收益率改用**本区间前一天**（scan_start）的净资产做分母。
    # `build_daily_pnl_series` 自己也算了 `range_rate`，但它内部还会再往前挪一天
    # 给首个**日**算差分（= base_start − 2），口径与「期间」不一致，故这里覆盖。
    # 与日粒度同规矩：没有可算日 ⇒ None，不借 0.0 兜底。
    payload['range_rate'] = (
        round(Money.cents_to_yuan(total_cents) / abs(baseline) * 100, 2)
        if baseline not in (None, 0) and any(d['daily_pnl'] is not None for d in in_range)
        else None
    )
    payload['has_any_price'] = any(d['state'] in (STATE_UPDOWN, STATE_ZERO) for d in in_range)
    payload['periods'] = _aggregate_periods(in_range, granularity, baseline)
    payload['days'] = []  # 聚合下推：期间视图不再回日明细
    return payload


def _empty_payload(ledger_id: Optional[int], start: dt.date, end: dt.date) -> dict:
    return {
        'ledger_id': ledger_id,
        'scope': 'ledger' if ledger_id is not None else 'family',
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'month_total': 0.0,
        # 无持仓 / 区间不合法时没有基准可言 ⇒ None（不是 0%，见 build_daily_pnl_series）
        'range_rate': None,
        'has_any_price': False,
        'coverage': {'total_positions': 0, 'priced_positions': 0, 'unpriced_positions': 0},
        'latest_price_date': None,
        'first_txn_date': None,
        'days': [],
    }
