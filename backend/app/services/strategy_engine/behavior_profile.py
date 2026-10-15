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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
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
) -> BehaviorProfile:
    """构建单个标的的行为画像。纯函数：无 DB、无 IO。"""
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

    classified_as, classified_label = 'unknown', '样本不足，暂不判定'
    if avg_hold is not None:
        for limit, code, label in _CLASSIFY_RULES:
            if avg_hold < limit:
                classified_as, classified_label = code, label
                break
        else:
            classified_as, classified_label = _LONG_HOLD

    return BehaviorProfile(
        symbol=symbol,
        trade_count=len(trades),
        avg_hold_days=avg_hold,
        chase_buy_ratio=chase_ratio,
        profitable_sell_ratio=profit_ratio,
        early_exit_cost=early_cost,
        classified_as=classified_as,
        classified_label=classified_label,
        evidence={
            'buy_count': len(buys),
            'sell_count': len(sells),
            'closed_pairs': len(pairs),
            'last_nav': round(last_nav, 6) if last_nav is not None else None,
            'last_nav_date': last_date.isoformat() if last_date else None,
            'chase_lookback_days': _CHASE_LOOKBACK,
        },
    )
