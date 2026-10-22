# -*- coding: utf-8 -*-
"""行为反推（#2225）——「你以为的 vs 你实际做的」。

WHY 这是首批里最该做的一件
    它**不需要用户先选策略**：直接用已有的交易记录 + 净值序列，反推用户过去
    **实际**在用什么策略，并量化其代价。成本几乎为零（库内数据 + 本地计算），
    却是唯一能让用户立刻「看见自己」的功能。

合规
    输出只陈述**用户自己的历史事实**（「你的实际行为接近波段交易」），
    不对未来给出任何倾向性意见。这不是投资建议。

算法口径（诚实标注）
    - 成本配对用 **FIFO**（与本仓其它盈亏口径一致，避免移动加权带来的二次分叉）；
    - 「提前卖出代价」= 卖出的份额若持有到**最后一个净值日**能多赚多少，
      为**机会成本**而非已实现亏损，负数表示提前卖出反而躲过了下跌（同样如实呈现）；
    - 分类为**启发式规则**（持有天数 + 追涨比例），阈值集中在 `_CLASSIFY_RULES` 便于校准。

买入侧指标（#2382 补齐）
    原实现只量化了「卖早了亏多少」，没有「买贵了亏多少」——后者对收益率的破坏
    通常更大。本文件提供三个纯函数补齐（均不碰 DB、不发起外部请求）：
    - `forward_return_metrics`：买点质量。每笔买入持有到第 20/60/120 个**净值日**
      的收益率，输出均值 / 中位数 / 胜率。口径：买入价取**成交价**（用户真实付出），
      期末取**买入日之后**第 h 个净值日（「买入后持有 h 个净值日」语义）；
      未来净值不足 h 个的买入不计入该窗口，计入 `missing_nav_count`，不插值。
    - `percentile_rank`：买入时点该基金近 1 年收益率在同类基金中的分位
      （中位秩，ties 折半）。同类样本 < `_PERCENTILE_MIN_PEERS` 返回 None（诚实降级）。
    - `account_actual_vs_hold`：账户层实际收益 vs「每笔买入后持有到期末」的差额。
      用**成本口径**（盈利 / 累计买入成本，与持有对照同分母可比、赎回鲁棒）；
      与 `early_exit_cost` 的口径差异：后者是**单笔**机会成本的金额求和（元），
      前者是**账户层**收益率的百分比对照，两者回答不同问题，不应互相替代。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Mapping, Sequence

from app.services.strategy_engine.contracts import SeriesPoint

#: 分类阈值（天 / %）。集中在此，便于后续用真实数据校准。
_CLASSIFY_RULES = (
    # (最长持有天数, 策略标识, 说明)
    (20, 'frequent', '短线频繁交易'),
    (90, 'swing', '波段交易'),
    (250, 'trend', '趋势交易'),
)
_LONG_HOLD = ('long_hold', '长期持有')
_CHASE_LOOKBACK = 20  # 判定「追涨」的回看交易日数

#: 买点质量前瞻窗口（净值日个数，#2382）
_FORWARD_HORIZONS = (20, 60, 120)
#: 同类分位的最小同类样本数；不足则诚实降级为 None（#2382）
_PERCENTILE_MIN_PEERS = 20
#: 买入时点「近 1 年」窗口（自然日，#2382）
_YEAR_WINDOW_DAYS = 365


@dataclass(frozen=True)
class TradeRecord:
    """归一化交易记录（份额单位：份；价格单位：元）。"""

    symbol: str
    trade_date: date
    side: str  # 'buy' | 'sell'
    quantity: float
    price: float


@dataclass(frozen=True)
class BehaviorProfile:
    """单个标的的行为画像。所有字段都可能为 None（数据不足时诚实降级）。"""

    symbol: str
    trade_count: int = 0
    avg_hold_days: float | None = None
    chase_buy_ratio: float | None = None  # 追涨买入占比 %
    profitable_sell_ratio: float | None = None  # 盈利卖出占比 %
    early_exit_cost: float | None = None  # 提前卖出的机会成本（元，可为负）
    forward_return: Mapping[str, object] | None = None  # 买点质量（#2382）：{'h20': {...}, ...}
    buy_percentile: float | None = None  # 买入时点同类分位（#2382，编排层填充）
    classified_as: str = 'unknown'
    classified_label: str = '样本不足，暂不判定'
    evidence: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            'symbol': self.symbol,
            'trade_count': self.trade_count,
            'avg_hold_days': self.avg_hold_days,
            'chase_buy_ratio': self.chase_buy_ratio,
            'profitable_sell_ratio': self.profitable_sell_ratio,
            'early_exit_cost': self.early_exit_cost,
            'forward_return': dict(self.forward_return) if self.forward_return is not None else None,
            'buy_percentile': self.buy_percentile,
            'classified_as': self.classified_as,
            'classified_label': self.classified_label,
            'evidence': dict(self.evidence),
        }


def _nav_lookup(series: Sequence[SeriesPoint]) -> tuple[dict[date, float], float | None, date | None]:
    """序列 → (日期→净值映射, 最后净值, 最后日期)。"""
    mapping = {p.date: p.value for p in series}
    last_nav = series[-1].value if series else None
    last_date = series[-1].date if series else None
    return mapping, last_nav, last_date


def _return_pct_before(mapping: Mapping[date, float], target: date, lookback: int) -> float | None:
    """target 之前 lookback 个交易日的累计涨幅（%）；数据不足返回 None。"""
    dates = sorted(d for d in mapping if d <= target)
    if len(dates) < 2:
        return None
    idx = len(dates) - 1
    start_idx = max(0, idx - lookback)
    start_val, end_val = mapping[dates[start_idx]], mapping[dates[idx]]
    if start_val == 0:
        return None
    return (end_val - start_val) / start_val * 100.0


# ── 买入侧指标（#2382） ──


def forward_return_metrics(
    buys: Sequence[TradeRecord],
    mapping: Mapping[date, float],
    horizons: Sequence[int] = _FORWARD_HORIZONS,
) -> dict[str, dict[str, object]] | None:
    """买点质量：每笔买入持有到第 h 个净值日的收益率统计（#2382）。

    口径（可手工复算）
        - 买入价取**成交价** `buy.price`（用户真实付出的成本，可能与当日净值有折溢价）；
        - 期末取**买入日之后**第 h 个净值日（`d > buy_date` 中第 h 个），
          即「买入后持有 h 个净值日」的语义；
        - 未来净值不足 h 个的买入**不计入**该窗口统计，汇总到 `missing_count`，
          不插值、不用最近值兜底；
        - 收益率为 %；胜率 = 收益率 > 0 的占比（%）。

    返回 `{'h20': {...}, 'h60': {...}, 'h120': {...}}`；某窗口零样本则**不出现该键**
    （调用方按缺失降级），完全无买入返回 None。
    """
    if not buys:
        return None
    sorted_dates = sorted(mapping)
    out: dict[str, dict[str, object]] = {}
    for horizon in horizons:
        returns: list[float] = []
        missing = 0
        for b in buys:
            future = [d for d in sorted_dates if d > b.trade_date]
            if len(future) < horizon:
                missing += 1
                continue
            end_nav = mapping[future[horizon - 1]]
            if b.price == 0 or end_nav is None:
                missing += 1
                continue
            returns.append((end_nav - b.price) / b.price * 100.0)
        if not returns:
            continue
        out[f'h{horizon}'] = {
            'mean': round(statistics.fmean(returns), 2),
            'median': round(statistics.median(returns), 2),
            'win_rate': round(sum(1 for r in returns if r > 0) / len(returns) * 100.0, 1),
            'sample_count': len(returns),
            'missing_count': missing,
        }
    return out or None


def percentile_rank(
    value: float | None,
    peers: Sequence[float] | None,
    min_peers: int = _PERCENTILE_MIN_PEERS,
) -> float | None:
    """`value` 在同类 `peers` 中的分位（0–100，中位秩，#2382）。

    - 中位秩口径：严格小于者全额计入，相等者折半（`(below + 0.5*equal) / n`），
      避免大量并列时把所有相同值压到同一端；
    - `peers` 应**包含自身**（由取数侧保证，见 `DataProvider.peer_year_returns`）；
    - 同类样本 < `min_peers` 返回 None——样本不足时硬算分位是伪精确，诚实降级。
    """
    if value is None or peers is None or len(peers) < min_peers:
        return None
    below = sum(1 for p in peers if p < value)
    equal = sum(1 for p in peers if p == value)
    return round((below + 0.5 * equal) / len(peers) * 100.0, 1)


def year_return(
    start_nav: float | None,
    end_nav: float | None,
) -> float | None:
    """区间收益率（%）；任一端缺失或起点为 0 返回 None。"""
    if start_nav is None or end_nav is None or start_nav == 0:
        return None
    return (end_nav - start_nav) / start_nav * 100.0


def _year_window_navs(
    mapping: Mapping[date, float],
    target: date,
    window_days: int = _YEAR_WINDOW_DAYS,
) -> tuple[float | None, float | None]:
    """target 当日回看 window_days 窗口的（起点净值, 终点净值）。

    终点 = target 及之前最后一个净值日；起点 = 窗口中（target - window_days 起）
    第一个净值日。用于「买入时点近 1 年收益率」的自身值（#2382）。
    """
    dates = sorted(d for d in mapping if d <= target)
    if not dates:
        return None, None
    end_nav = mapping[dates[-1]]
    window_start = target - timedelta(days=window_days)
    start_candidates = [d for d in dates if d >= window_start]
    start_nav = mapping[start_candidates[0]] if start_candidates else None
    return start_nav, end_nav


def account_actual_vs_hold(
    trades: Sequence[TradeRecord],
    series_by_symbol: Mapping[str, Sequence[SeriesPoint]],
) -> dict[str, object] | None:
    """账户层：实际收益 vs「每笔买入后持有到期末」的差额（#2382）。

    口径（两者都是**账户层收益率**、同分母可比，可手工复算）
        - `actual_return_pct`：**成本口径**的账户实际收益率。
          `盈利 = 期末持仓市值 + 累计回款 − 累计买入成本`，
          `实际收益率 = 盈利 / 累计买入成本`（现金回款不再投资的简化假设）。
        - `hold_to_end_pct`：假设**没有任何卖出**，全部买入份额持有到最后净值日：
          `(Σ qty_i·nav_end − Σ qty_i·price_i) / Σ qty_i·price_i`。
        - `diff_pct = actual_return_pct − hold_to_end_pct`：**买卖择时**对收益率的净影响
          （百分点）。为负表示实际操作跑输了「无脑拿着」。

    为何不用链式 TWR / IRR（口径选型留痕）
        - 链式 TWR：全额赎回后因子乘 0，组合收益塌到 −100%，恰恰在最需要
          回答「卖早了亏多少」的场景失效；
        - IRR（资金加权）：早落袋在时点上占优，与用户「少赚了」的直觉相反，
          且短窗口年化数值爆炸；
        - 成本口径与 `hold_to_end_pct` **同分母同量纲**，diff 直接可读，
          代价是不做时间加权（早期与近期投入同权）——docstring 如实标注。

    与 `early_exit_cost` 的口径差异（勿混用）
        `early_exit_cost` 是**单笔**卖出「持有到最后一个净值日」的机会成本**金额求和**（元），
        回答「这笔卖出让我少赚多少钱」；本函数是**账户层**收益率**百分比**对照，
        回答「整体买卖操作比拿着不动差多少」。前者不随时间加权、后者不给出单笔归因。

    数据不足（无交易 / 无净值 / 零买入成本）返回 None，不伪造 0。
    """
    dated = [t for t in trades if t.side in ('buy', 'sell') and t.price > 0 and t.quantity > 0]
    if not dated:
        return None

    nav_by_symbol: dict[str, dict[date, float]] = {}
    for sym, series in series_by_symbol.items():
        if series:
            nav_by_symbol[sym] = {p.date: p.value for p in series}
    if not nav_by_symbol:
        return None

    dated = sorted(dated, key=lambda x: x.trade_date)
    last_day = max(max(nav) for nav in nav_by_symbol.values())

    # 期末持仓份额（全量流水 FIFO 记账：买加卖减）
    shares: dict[str, float] = {}
    for t in dated:
        shares[t.symbol] = shares.get(t.symbol, 0.0) + (t.quantity if t.side == 'buy' else -t.quantity)

    buy_cost = sum(t.quantity * t.price for t in dated if t.side == 'buy')
    sell_proceeds = sum(t.quantity * t.price for t in dated if t.side == 'sell')
    end_value = sum(
        q * nav_by_symbol[s][last_day]
        for s, q in shares.items()
        if s in nav_by_symbol and q > 0 and last_day in nav_by_symbol[s]
    )
    if buy_cost <= 0:
        return None

    actual_ret = (end_value + sell_proceeds - buy_cost) / buy_cost * 100.0
    hold_value = sum(
        t.quantity * nav_by_symbol[t.symbol][last_day]
        for t in dated
        if t.side == 'buy' and last_day in nav_by_symbol.get(t.symbol, {})
    )
    hold_ret = (hold_value - buy_cost) / buy_cost * 100.0

    return {
        'actual_return_pct': round(actual_ret, 2),
        'hold_to_end_pct': round(hold_ret, 2),
        'diff_pct': round(actual_ret - hold_ret, 2),
        'sample': {
            'trade_count': len(dated),
            'symbol_count': len({t.symbol for t in dated}),
            'buy_cost': round(buy_cost, 2),
            'end_value': round(end_value + sell_proceeds, 2),
            'window_end': last_day.isoformat(),
        },
    }


def _fifo_pairs(trades: Sequence[TradeRecord]) -> list[tuple[TradeRecord, TradeRecord]]:
    """FIFO 配对买卖：返回 [(buy, sell), ...]，未平仓的买入不出现在结果里。"""
    queue: list[TradeRecord] = []
    pairs: list[tuple[TradeRecord, TradeRecord]] = []
    for t in sorted(trades, key=lambda x: (x.trade_date, 0 if x.side == 'buy' else 1)):
        if t.side == 'buy':
            queue.append(t)
            continue
        remaining = t.quantity
        while remaining > 0 and queue:
            buy = queue[0]
            used = min(buy.quantity, remaining)
            pairs.append((buy, t))
            remaining -= used
            if used >= buy.quantity:
                queue.pop(0)
            else:
                # 买入部分成交：把余量放回队首（不可变对象 → 重建）
                queue[0] = TradeRecord(
                    symbol=buy.symbol,
                    trade_date=buy.trade_date,
                    side='buy',
                    quantity=buy.quantity - used,
                    price=buy.price,
                )
    return pairs


def build_behavior_profile(
    symbol: str,
    trades: Sequence[TradeRecord],
    series: Sequence[SeriesPoint],
    today: date | None = None,
    peer_year_returns: Mapping[date, Sequence[float]] | None = None,
) -> BehaviorProfile:
    """构建单个标的的行为画像。纯函数：无 DB、无 IO。

    `peer_year_returns`（#2382）：`{买入日: 同类近 1 年收益率集合}` 的映射
    （集合应含自身，由取数侧 `DataProvider.peer_year_returns` 保证）。
    传入即逐笔计算 `buy_percentile` 后取均值；不传、买入日无同类数据或同类样本
    不足则字段留 None（诚实降级）。
    """
    if not trades:
        return BehaviorProfile(symbol=symbol)

    mapping, last_nav, last_date = _nav_lookup(series)
    buys = [t for t in trades if t.side == 'buy']
    sells = [t for t in trades if t.side == 'sell']
    pairs = _fifo_pairs(trades)

    # 1) 平均持有天数：已配对按 (卖 − 买)；未平仓按 (今天/最后净值日 − 买)
    hold_days: list[int] = [(s.trade_date - b.trade_date).days for b, s in pairs]
    reference_day = today or last_date
    if reference_day:
        hold_days += [(reference_day - b.trade_date).days for b in buys if not any(b is pb for pb, _ in pairs)]
    avg_hold = round(sum(hold_days) / len(hold_days), 1) if hold_days else None

    # 2) 追涨买入占比：买入日前 _CHASE_LOOKBACK 日涨幅 > 0 视为追涨
    chase_flags = []
    for b in buys:
        pct = _return_pct_before(mapping, b.trade_date, _CHASE_LOOKBACK)
        if pct is not None:
            chase_flags.append(pct > 0)
    chase_ratio = round(sum(chase_flags) / len(chase_flags) * 100.0, 1) if chase_flags else None

    # 3) 盈利卖出占比（处置效应的镜像：越高说明「赚一点就跑」越明显）
    profit_flags = [s.price > b.price for b, s in pairs]
    profit_ratio = round(sum(profit_flags) / len(profit_flags) * 100.0, 1) if profit_flags else None

    # 4) 提前卖出的机会成本：卖出的份额持有到最后一个净值日能多赚/少亏多少
    early_cost = None
    if last_nav is not None:
        early_cost = round(sum((last_nav - s.price) * s.quantity for _, s in pairs), 2)

    # 5) 买点质量（#2382）：各前瞻窗口的收益统计
    forward = forward_return_metrics(buys, mapping)

    # 6) 买入时点同类分位（#2382）：逐笔买入算自身近 1 年收益在同类中的分位，再取均值
    buy_pct = None
    if peer_year_returns:
        pcts: list[float] = []
        for b in buys:
            peers = peer_year_returns.get(b.trade_date)
            own = year_return(*_year_window_navs(mapping, b.trade_date))
            p = percentile_rank(own, peers)
            if p is not None:
                pcts.append(p)
        if pcts:
            buy_pct = round(statistics.fmean(pcts), 1)

    classified_as, classified_label = 'unknown', '样本不足，暂不判定'
    if avg_hold is not None:
        for limit, code, label in _CLASSIFY_RULES:
            if avg_hold < limit:
                classified_as, classified_label = code, label
                break
        else:
            classified_as, classified_label = _LONG_HOLD

    missing_forward = 0
    if forward:
        missing_forward = sum(int(w.get('missing_count', 0)) for w in forward.values())

    return BehaviorProfile(
        symbol=symbol,
        trade_count=len(trades),
        avg_hold_days=avg_hold,
        chase_buy_ratio=chase_ratio,
        profitable_sell_ratio=profit_ratio,
        early_exit_cost=early_cost,
        forward_return=forward,
        buy_percentile=buy_pct,
        classified_as=classified_as,
        classified_label=classified_label,
        evidence={
            'buy_count': len(buys),
            'sell_count': len(sells),
            'closed_pairs': len(pairs),
            'last_nav': round(last_nav, 6) if last_nav is not None else None,
            'last_nav_date': last_date.isoformat() if last_date else None,
            'chase_lookback_days': _CHASE_LOOKBACK,
            'forward_missing_count': missing_forward,
        },
    )
