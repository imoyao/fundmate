# -*- coding: utf-8 -*-
"""行情回补深度口径：以「该标的自己的首笔流水日」为准（#2860）。

## 为什么不能用固定年数

`price_history` 的起点此前由「抓取那一刻 − 365 天」决定，于是起点落成几个**批次日期**。
本机实测（2026-11-03，19,147 行 / 81 标的）：17 个标的起 2025-08-29、17 个起 2025-09-22、
21 个起 2025-11-03（前一天刚入库，365 天前正是这天），而它们的首笔流水分布在
2023-02 ~ 2025-09。58 个有流水的场内标的里 **19 个的行情起点晚于首笔**，最长缺 2.7 年
（SH113649：首笔 2023-02-17 / 行情起 2025-11-03）。

后果不是「少画几天」：产品详情页的「建仓」档从首笔买入日画起，前半段直接空白；
买卖点也落不到轴上（#2857 的 `markerData` 按 `trend.dates` 查不到就 `continue`）。

把 1 年换成 3 年 / 5 年只是把同一个**静态阈值**换个数字：今天够了，2030 年导入 2015 年
对账单时又缺一次，而且同样无声。标的自何时被买入是每只自己的量，不随时间漂移。

## 两个上界，取更早的那个

- **首笔流水日 − 缓冲**：建仓档的起点、买卖点与成本线的锚点都在这一天；
- **今天 − `BASELINE_HISTORY_YEARS` 年**：走势卡最长档位是 5Y。不足 5 年意味着那个档位
  **点得到却永远降级**（`available_days` 会把档位收敛掉，诚实但本可修）。

无流水的自选标的只吃第二项 ⇒ 近 5 年。比改之前的 1 年贵，但那是 5Y 档能被点开的
唯一办法；5 年 × 300 标的约 36 万行，对 SQLite 仍是一次性可忽略的量级。

## 缓冲天数

`confirm_date` 是确认日，可能落在周末 / 停牌日；`trade_date` 是 T 日，也可能与记账日
不同。留 14 天只为「首笔那天恰好取不到那一行」时不至于从空白起画——缓冲只会多抓几行，
不会少抓。
"""

import datetime as dt
from typing import Dict, Iterable, Optional

from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.constants import CASH_SYMBOL
from app.core.symbol_utils import symbol_identity
from app.domains.transactions.models import Transaction
from app.services.job_base import IN_CHUNK_SIZE

# 首笔流水日往前的缓冲（天）。理由见模块 docstring。
FIRST_TXN_BUFFER_DAYS = 14

# 走交易所行情（`price_history`）的资产类型。
# 用**白名单**而不是 `EXCLUDED_ASSET_TYPES` 的补集：后者会把 manager / portfolio /
# index / bank_wealth 一并放进来，而这些同样没有连续行情。场外基金（fund）走净值
# （funds / daily_worth），逆回购（reverse_repo）与现金（cash）没有行情。
HELD_EXCHANGE_ASSET_TYPES: tuple[str, ...] = ('stock', 'etf', 'bond')

# 无流水标的的保底历史年数，**对齐走势卡最长档位 5Y**（`useProductTrend.ts`
# 的 RANGE_BASE_OPTIONS）。新增更长档位时同步改这里，否则新档位对老标的一律降级。
BASELINE_HISTORY_YEARS = 5


def _years_before(day: dt.date, years: int) -> dt.date:
    """`day` 往前 `years` 年。2/29 落到 2/28（平年），不抛 ValueError。"""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, month=2, day=28)


def desired_start(first_txn: Optional[dt.date], today: dt.date) -> dt.date:
    """该标的应该回补到哪一天：`min(首笔流水日 − 缓冲, 今天 − BASELINE 年)`。

    取更早的那个：有老流水的标的按流水走，流水很新的标的仍保底 5 年（否则 5Y 档
    永远降级）。`first_txn` 为空（纯自选 / 无流水）时只剩后一项。
    """
    floor = _years_before(today, BASELINE_HISTORY_YEARS)
    if first_txn is None:
        return floor
    return min(first_txn - dt.timedelta(days=FIRST_TXN_BUFFER_DAYS), floor)


# ── 谁需要行情：「持有过」的真相源是流水，不是持仓行 ──────────────────────


def held_symbols(db: Session) -> list[str]:
    """流水里出现过的场内标的（含已清仓、含持仓行已被物理删除的历史遗留）。

    ## 为什么不能只认 positions ∪ watchlist

    同步目标池此前只取这两张表（`sync/orchestrator._load_codes_from_database`）。
    而 #2343（2026-10-18）之前清仓走的是 `db.delete(position)`：持仓行连同它的
    symbol 一起消失，流水因为不级联还在库里。于是标的**两张表都不在** ⇒ 永远
    进不了同步 ⇒ 永远零行情，产品详情页是空图（用户读成「数据丢了」）。

    本机实测（2026-11-03，`invest.db`）：流水里 213 个场内标的，143 个零行情，
    其中 **136 个不在池**；**637 条流水的 `position_id` 已悬空**（指向不存在的
    持仓行）——这就是「清仓删行」留下的疤，也是「明明买过却查不到行情」的根。

    ## 为什么真相源是流水，而不是「补建持仓行」

    清仓周期（`analytics/cleared_cycles.py`）本来就从流水现算、不依赖持仓行；
    补行则要多决定账本归属、快照锚点与 `uq_positions_ledger_symbol` 唯一约束，
    风险远大于收益。「我买过它」这件事，流水是唯一不会丢的证据。

    ## 为什么是白名单

    见 `HELD_EXCHANGE_ASSET_TYPES`：场外基金走净值、逆回购/现金没有行情，
    用「排除 EXCLUDED_ASSET_TYPES」的补集会放进没有行情的 manager/portfolio。

    Returns:
        去重后的 `transactions.symbol` 字面量（场内带交易所前缀，与
        `price_history.symbol` 同形态）；空串与 `__CASH__` 已排除。
    """
    rows = (
        db.query(Transaction.symbol)
        .filter(
            Transaction.symbol.isnot(None),
            Transaction.symbol != '',
            Transaction.symbol != CASH_SYMBOL,
            Transaction.asset_type.in_(HELD_EXCHANGE_ASSET_TYPES),
        )
        .distinct()
        .all()
    )
    return [s for (s,) in rows if s]


def _as_date(value) -> Optional[dt.date]:
    """宽松转 date：SQLite 的 coalesce(min(...)) 可能回传字符串 / datetime。"""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def first_transaction_dates(db: Session, symbols: Iterable[str]) -> Dict[str, dt.date]:
    """`{传入的 symbol 写法: 首笔流水日}`（`COALESCE(trade_date, confirm_date)`）。

    ## 为什么不能直接 join

    `price_history.symbol` 是 `SH600383` 形态，`transactions.symbol_norm` 是
    `EXCHANGE:SH600383` 形态（场外是 `OTC:004369`）。两者直接相比**一条都命中不了**——
    本机实测按字面量 join 会把 58 个场内标的全判成「无流水」，进而给它们全部退回
    「近 5 年」保底，看起来没有报错，只是老标的的深度永远补不上。故先把调用方的
    写法归一成身份键，建反查表后再比对。

    字面量 `Transaction.symbol` 一并 OR 上：`symbol_norm` 是 #1662 之后才回填的，
    早期行可能是空串（本机 543 行），字面量是它们唯一的可归因线索。

    查不到的标的**不出现在返回值里**，由调用方按「无流水」处理。
    """
    wanted = [s for s in dict.fromkeys(symbols) if s]
    if not wanted:
        return {}

    ident_to_symbol: Dict[str, str] = {}
    for symbol in wanted:
        try:
            # 三种 venue 身份一并纳入（与 `symbol_scope.build_transaction_symbol_conditions`
            # 同一套判据）：`price_history.symbol` 是 `SH600383` 形态，但调用方也可能只拿
            # 到裸码；只按默认 venue 归一，会漏掉另一侧的写法。
            idents = {
                symbol_identity(symbol),
                symbol_identity(symbol, venue='EXCHANGE'),
                symbol_identity(symbol, venue='OTC'),
            }
        except Exception as e:  # noqa: BLE001 — 归一失败只影响该标的的深度，不阻断同步
            logger.warning(f'{symbol} 归一失败，按无流水处理: {e}')
            continue
        for ident in idents:
            if ident:
                ident_to_symbol.setdefault(ident, symbol)
    if not ident_to_symbol:
        return {}

    out: Dict[str, dt.date] = {}
    idents = list(ident_to_symbol.keys())
    literal_set = set(ident_to_symbol.values())
    for i in range(0, len(idents), IN_CHUNK_SIZE):
        ident_chunk = idents[i : i + IN_CHUNK_SIZE]
        literal_chunk = [ident_to_symbol[k] for k in ident_chunk]
        rows = (
            db.query(
                Transaction.symbol,
                Transaction.symbol_norm,
                func.min(func.coalesce(Transaction.trade_date, Transaction.confirm_date)),
            )
            .filter(
                or_(
                    Transaction.symbol_norm.in_(ident_chunk),
                    Transaction.symbol.in_(literal_chunk),
                )
            )
            .group_by(Transaction.symbol, Transaction.symbol_norm)
            .all()
        )
        for raw_symbol, raw_norm, first in rows:
            symbol = ident_to_symbol.get(raw_norm)
            if symbol is None and raw_symbol in literal_set:
                symbol = raw_symbol
            day = _as_date(first)
            if not symbol or day is None:
                continue
            current = out.get(symbol)
            if current is None or day < current:
                out[symbol] = day
    return out
