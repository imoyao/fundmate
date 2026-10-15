# -*- coding: utf-8 -*-
"""趋势跟踪策略（#2224 首个落地策略，用于验证框架端到端）。

规则（双均线，无未来函数）
    - 净值 > 快线 且 快线 > 慢线 → 趋势成立
    - 跌破快线、仍在慢线上 → 趋势走弱
    - 跌破慢线 → 趋势结束

一个重要澄清（关系到合规与诚实）
    P0 诊断是**无状态实时计算**，不落库、不知道用户是否真的持有该标的。
    因此本策略产出的 action 表达的是「**趋势当前支持的方向**」，
    **不是**「对你持仓的买卖指令」。措辞一律是「趋势成立 / 走弱 / 结束」，
    不得写成「建议买入 / 建议卖出」。
"""

from __future__ import annotations

from app.services.strategy_engine.contracts import (
    BaseStrategy,
    PositionState,
    Signal,
    SignalAction,
    StrategyContext,
    StrategyFamily,
    StrategyMeta,
    simple_moving_average,
)


class TrendFollowingStrategy(BaseStrategy):
    """趋势跟踪：势起而动，势在则有，势尽则退；不预判顶底。"""

    meta = StrategyMeta(
        code='trend_following',
        name='趋势跟踪',
        family=StrategyFamily.TIMING,
        required_data=frozenset({'nav'}),
        params_schema={'fast_window': 20, 'slow_window': 60},
        summary='跟随趋势：净值在快慢线之上视为趋势成立，跌破快线走弱，跌破慢线结束。',
        discipline='截断亏损，让利润奔跑。',
    )

    def warmup(self) -> int:
        # 慢线窗口 + 1（首个可判定的点）
        return int(self.meta.params_schema.get('slow_window', 60)) + 1

    def evaluate(self, ctx: StrategyContext) -> Signal:
        fast = int(ctx.params.get('fast_window', 20))
        slow = int(ctx.params.get('slow_window', 60))
        if fast >= slow:
            raise ValueError(f'fast_window({fast}) 必须小于 slow_window({slow})')

        values = ctx.values
        if len(values) < slow:
            return Signal(
                strategy_code=self.code,
                symbol=ctx.symbol,
                action=SignalAction.WATCH,
                state=PositionState.WATCHING,
                reason=f'历史样本 {len(values)} 条，不足 {slow} 条，暂不判定',
                metrics={'sample_size': len(values), 'required': slow},
                as_of=ctx.as_of,
            )

        fast_ma = simple_moving_average(values, fast)
        slow_ma = simple_moving_average(values, slow)
        cur = values[-1]
        f_val, s_val = fast_ma[-1], slow_ma[-1]
        if f_val is None or s_val is None:  # 理论上不可达，兜底防未来改动
            return Signal(
                strategy_code=self.code,
                symbol=ctx.symbol,
                action=SignalAction.WATCH,
                state=PositionState.WATCHING,
                reason='均线数据不足，暂不判定',
                as_of=ctx.as_of,
            )

        metrics = {
            'nav': round(cur, 6),
            f'ma{fast}': round(f_val, 6),
            f'ma{slow}': round(s_val, 6),
            'sample_size': len(values),
        }

        if cur > f_val and f_val > s_val:
            action, state = SignalAction.BUY, PositionState.HOLDING
            reason = f'净值 {cur:.4f} 在快线之上、快线高于慢线，趋势成立'
        elif cur > f_val:
            action, state = SignalAction.HOLD, PositionState.TRIAL
            reason = '净值站上快线，但快线尚未上穿慢线，趋势待确认'
        elif cur > s_val:
            action, state = SignalAction.REDUCE, PositionState.REDUCING
            reason = '净值跌破快线但仍高于慢线，趋势走弱'
        else:
            action, state = SignalAction.SELL, PositionState.CLEARED
            reason = '净值跌破慢线，趋势结束'

        return Signal(
            strategy_code=self.code,
            symbol=ctx.symbol,
            action=action,
            state=state,
            reason=reason,
            metrics=metrics,
            as_of=ctx.as_of,
        )
