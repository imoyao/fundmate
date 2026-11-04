# -*- coding: utf-8 -*-
# Author : imoyao
"""#2620 组合同期基准对比（超额 / 最大回撤 / 相关性）。

账本精灵对话里「我跑赢沪深300了吗」的取数层：`get_portfolio_performance` 只给
绝对收益，没有对照基准，模型只能含糊。本模块把**已有的**基准口径接进对话层，
不新建数据源。

## 口径（复用，不另算一套账）

1. **区间收益与超额**：直接调 `analytics.benchmark_excess.build_scope_excess`
   （#2134）取家庭级 `range_rate` / `excess_return`——区间收益的唯一出口是
   `pnl_calendar.build_daily_pnl_series`，本模块不重算。显式指定基准时只重算
   「基准区间涨跌幅 + 超额」两段，收益侧仍用同一份 `range_rate`。
   ⚠️ `range_rate` 是**简单区间收益率**（区间盈亏 / 区间前一天净资产），不是 TWR：
   区间起点净资产很小时（真库 2024-01-02 基线仅 255.83 元）结果会被放大到
   数学正确但无参考价值的量级；跨大额入金的区间慎用，别把它读成「投资能力」。
2. **最大回撤**：用日收益**连乘**出累计曲线（`r_t = 当日盈亏 / 前一日总资产`，
   即 TWR 链式），`mdd = max(1 − idx_t / peak_t)`。缺数据日（`rate=None`）**跳过、
   不填 0**——填 0 会把缺口读成「平盘」，回撤被系统性低估。
3. **相关系数**：组合与基准**按日期对齐的日收益**做 Pearson（卡面验收要求）；
   交集样本 < 3 或任一侧零波动回 `None`（2 个点恒 ±1，是假信息）。
4. **基准缺失必须显式不可用**：`available=False` + `unavailable_reason` +
   `coverage_gaps`（缺口区间按首/末可得报价与区间边界相减得出），
   **禁止插值或用近似值糊过去**。

## 为什么基准日收益要前扩 30 天

组合首日的 `rate` 是「当日 / 前一日」，而区间首日的基准若只查 `[start, end]`，
第一天没有前收盘可比 ⇒ 对齐时白丢一天、相关性样本偏少。故基准查询起点前扩
`_BENCH_LOOKBACK_DAYS` 天，算完日收益再裁回 `[start, end]`。组合侧无需前扩
（引擎自己带 `start - 1` 的基线）。
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.indices.models import IndexDaily
from app.domains.transactions.models import Transaction
from app.services.analytics.benchmark_excess import (
    build_scope_excess,
    interval_benchmark_return,
)
from app.services.bias.constants import BENCHMARK_INDICES
from app.services.pnl_calendar import build_daily_pnl_series

# 基准日收益的前扩天数（覆盖春节等长假；只为拿到区间首日的前一个收盘）
_BENCH_LOOKBACK_DAYS = 30
# 相关系数最小样本：低于此不做统计（2 个点恒 ±1，是假信息）
_MIN_CORR_SAMPLES = 3


def _max_drawdown_pct(rates: List[Optional[float]]) -> Optional[float]:
    """日收益序列（%）→ 最大回撤（%，正数）。全窗无可算日回 None。

    `rate=None` 的日子跳过：缺口不是 0 收益，填 0 会低估回撤。
    """
    index = 1.0
    peak = 1.0
    worst = 0.0
    seen = False
    for rate in rates:
        if rate is None:
            continue
        index *= 1 + rate / 100
        seen = True
        peak = max(peak, index)
        if peak > 0:
            worst = max(worst, 1 - index / peak)
    return round(worst * 100, 2) if seen else None


def _index_daily_returns(
    db: Session,
    index_code: str,
    start: dt.date,
    end: dt.date,
) -> Dict[dt.date, float]:
    """指数日收益（%）按日期索引，裁剪到 `[start, end]`。

    起点前扩 `_BENCH_LOOKBACK_DAYS` 只为拿到区间首日的前收盘；用 `close` 差分
    而不是 `ret_pct` 列——与 `interval_benchmark_return` 同源同口径
    （`ret_pct` 可能来自不同 source / price_mode，混用会出现两套涨幅）。
    """
    rows = (
        db.query(IndexDaily.trade_date, IndexDaily.close)
        .filter(
            IndexDaily.index_code == index_code,
            IndexDaily.trade_date >= start - dt.timedelta(days=_BENCH_LOOKBACK_DAYS),
            IndexDaily.trade_date <= end,
            IndexDaily.close.isnot(None),
        )
        .order_by(IndexDaily.trade_date)
        .all()
    )
    returns: Dict[dt.date, float] = {}
    for prev, cur in zip(rows, rows[1:]):
        prev_close, cur_close = float(prev.close), float(cur.close)
        if prev_close <= 0:
            continue
        if cur.trade_date >= start:
            returns[cur.trade_date] = (cur_close / prev_close - 1) * 100
    return returns


def _pearson(pairs: List[tuple]) -> Optional[float]:
    """Pearson 相关系数（4 位小数）；样本不足或任一侧零波动回 None。"""
    n = len(pairs)
    if n < _MIN_CORR_SAMPLES:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    return round(cov / (var_x**0.5 * var_y**0.5), 4)


def _as_date(value: Any) -> Optional[dt.date]:
    """payload 里的日期可能是 `date` 也可能是 isoformat 字符串（JSON 风格）。

    对齐故障的典型形态：键类型不一致时 `dict.get` 恒 None、样本数恒 0，
    相关系数静默变 None——**静默降级比报错更难发现**，故此处显式归一。
    """
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and value:
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _coverage_gaps(
    start: dt.date,
    end: dt.date,
    first: Optional[dt.date],
    last: Optional[dt.date],
) -> List[Dict[str, str]]:
    """基准报价未覆盖到的区间（与区间边界相减）；完全无报价 → 整段缺口。"""
    if first is None or last is None:
        return [{'from': start.isoformat(), 'to': end.isoformat()}]
    gaps: List[Dict[str, str]] = []
    if first > start:
        gaps.append({'from': start.isoformat(), 'to': (first - dt.timedelta(days=1)).isoformat()})
    if last < end:
        gaps.append({'from': (last + dt.timedelta(days=1)).isoformat(), 'to': end.isoformat()})
    return gaps


def _earliest_confirm_date(db: Session, family_id: int) -> Optional[str]:
    """本家庭最早一笔流水的确认日（「缺省全期」的起点）。

    用 `confirm_date` 而非 `trade_date`：真库实测 1927 笔中 1211 笔
    `trade_date` 为空，`confirm_date` 100% 填充，且 pnl 引擎按确认日结算。
    """
    earliest = db.query(func.min(Transaction.confirm_date)).filter(Transaction.family_id == family_id).scalar()
    return earliest.isoformat() if earliest else None


def _resolve_dates(
    db: Session,
    family_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple:
    """缺省区间 = 全期；显式传值原样交给下游校验格式。

    ⚠️ 全期起点取**最早确认日的次日**，不是当日：区间收益率的分母是
    「区间前一天净资产」，而首笔交易当天之前还没有任何资产 ⇒ 分母为 0，
    `build_daily_pnl_series` 只能降级 `not_computable`（真库实测 2022-12-23
    起算必然不可用）。从次日起算既拿到有效分母，也不丢收益——建仓日当天的
    盈亏本来就被引擎剔除（#2135 `opening_pnl` 门控）。
    """
    end = end_date or dt.date.today().isoformat()
    if start_date:
        return start_date, end
    earliest = _earliest_confirm_date(db, family_id)
    if not earliest:
        return end, end
    start = dt.date.fromisoformat(earliest) + dt.timedelta(days=1)
    return min(start, dt.date.fromisoformat(end)).isoformat(), end


def build_benchmark_comparison(
    db: Session,
    family_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    benchmark_code: Optional[str] = None,
) -> Dict[str, Any]:
    """家庭组合 vs 基准的区间对比（#2620）。

    Args:
        start_date / end_date: YYYY-MM-DD；缺省为全期（最早确认日 → 今日）。
        benchmark_code: 显式基准（须在 `BENCHMARK_INDICES` 内）；缺省走
            `resolve_benchmark_code`（与非 A 股持仓降级、组合默认基准同一套规则）。

    Returns:
        `available` 为 False 时 `range_rate` / `benchmark_range_return` /
        `excess_return` 中算不出的那个为 None，`unavailable_reason` 与
        `coverage_gaps` 指明缺口——**不插值、不兜底成 0**。

    Raises:
        ValueError: 日期格式非法 / 区间倒挂 / `benchmark_code` 不在白名单。
    """
    if benchmark_code is not None and benchmark_code not in BENCHMARK_INDICES:
        raise ValueError(f'benchmark 仅支持 {"/".join(sorted(BENCHMARK_INDICES))}')

    start_date, end_date = _resolve_dates(db, family_id, start_date, end_date)

    base = build_scope_excess(db, family_id, start_date, end_date)
    bench = base['benchmark']
    excess = base['excess_return']

    if benchmark_code is not None and benchmark_code != bench.get('code'):
        # 只换「基准侧」两段（涨跌幅 + 超额），收益侧仍用 build_scope_excess 的
        # range_rate —— 区间收益的唯一出口是 pnl 引擎，本模块不重算。
        bench = interval_benchmark_return(
            db, benchmark_code, dt.date.fromisoformat(start_date), dt.date.fromisoformat(end_date)
        )
        excess = (
            round(base['range_rate'] - bench['range_return'], 2)
            if base['range_rate'] is not None and bench['range_return'] is not None
            else None
        )

    payload = build_daily_pnl_series(db, family_id, start_date, end_date)
    days = payload.get('days') or []
    portfolio_rates = [d.get('rate') for d in days]
    portfolio_mdd = _max_drawdown_pct(portfolio_rates)

    bench_returns: Dict[dt.date, float] = {}
    if bench.get('code'):
        bench_returns = _index_daily_returns(
            db, bench['code'], dt.date.fromisoformat(start_date), dt.date.fromisoformat(end_date)
        )
    bench_mdd = _max_drawdown_pct(list(bench_returns.values())) if bench_returns else None

    pairs = []
    for day in days:
        rate = day.get('rate')
        if rate is None:
            continue
        day_date = _as_date(day.get('date'))
        if day_date is None:
            continue
        bench_rate = bench_returns.get(day_date)
        if bench_rate is None:
            continue
        pairs.append((rate, bench_rate))

    start = dt.date.fromisoformat(start_date)
    end = dt.date.fromisoformat(end_date)
    unavailable_reason = None
    if base['range_rate'] is None:
        # baseline 为 0 / None ⇒ 区间起点时账户还没有资产（真库 2022-12 起算即是），
        # 收益率没有分母。与 `build_scope_excess` 的组合分支同词（no_baseline），
        # 便于模型区分「算不了」与「没资产可算」。
        if not payload.get('range_baseline'):
            unavailable_reason = 'no_baseline'
        else:
            unavailable_reason = base['range_reason'] or 'portfolio_not_computable'
    elif bench.get('range_return') is None:
        unavailable_reason = bench.get('reason') or 'benchmark_unavailable'

    return {
        'scope': base['scope'],
        'start_date': base['start_date'],
        'end_date': base['end_date'],
        'available': base['range_rate'] is not None and bench.get('range_return') is not None,
        'range_rate': base['range_rate'],
        'range_reason': base['range_reason'],
        'benchmark_code': bench.get('code'),
        'benchmark_name': bench.get('name'),
        'benchmark_range_return': bench.get('range_return'),
        'benchmark_reason': bench.get('reason'),
        'bench_start_date': bench.get('bench_start_date'),
        'bench_end_date': bench.get('bench_end_date'),
        'excess_return': excess,
        'portfolio_max_drawdown_pct': portfolio_mdd,
        'benchmark_max_drawdown_pct': bench_mdd,
        'correlation': _pearson(pairs),
        'correlation_samples': len(pairs),
        'unavailable_reason': unavailable_reason,
        'coverage_gaps': _coverage_gaps(
            start,
            end,
            dt.date.fromisoformat(bench['bench_start_date']) if bench.get('bench_start_date') else None,
            dt.date.fromisoformat(bench['bench_end_date']) if bench.get('bench_end_date') else None,
        ),
    }


__all__ = ['build_benchmark_comparison']
