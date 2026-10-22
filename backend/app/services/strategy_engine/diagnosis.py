# -*- coding: utf-8 -*-
"""策略诊断组装（#2225）——把「持仓 + 净值 + 策略」拼成用户能看懂的结果。

设计取向
    - **只读**：不写库、不产生副作用，用户刷新即重算，无状态残留；
    - **诚实降级**：数据不足时返回 WATCH 并说明缺什么，绝不编造信号；
    - 只陈述客观事实（「趋势成立 / 走弱 / 结束」），**不给买卖指令**——这是合规底线。

P0 不落库的原因（避免过度工程）
    诊断场景的消费方式是「用户打开页面时看一眼」，落一张信号日志表既不改善体验、
    又立刻带来迁移 / 数据域登记 / 只写不读的负担（AGENTS.md「数据策略」明确禁止）。
    状态持久化留给 P1 提醒（那时才真正需要「上次是什么状态」）。
"""

from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

from app.services.strategy_engine import strategies  # noqa: F401  —— 导入即完成策略注册
from app.services.strategy_engine.behavior_profile import (
    BehaviorProfile,
    TradeRecord,
    account_actual_vs_hold,
    build_behavior_profile,
)
from app.services.strategy_engine.contracts import SeriesPoint, StrategyContext
from app.services.strategy_engine.data_provider import DataProvider, extract_fund_code
from app.services.strategy_engine.registry import registry

#: 诊断默认只用「数据已具备」的策略：P0 只供 nav，故估值型/配置型策略不会出现在结果里
DEFAULT_DATA_SUPPLY = ('nav',)


def list_strategies(available: Sequence[str] = DEFAULT_DATA_SUPPLY) -> list[dict]:
    """列出当前数据条件下**可运行**的策略及其元信息（供前端策略卡片与文档站引用）。"""
    return [
        {
            'code': s.meta.code,
            'name': s.meta.name,
            'family': s.meta.family.value,
            'summary': s.meta.summary,
            'discipline': s.meta.discipline,
            'params': dict(s.meta.params_schema),
            'required_data': sorted(s.meta.required_data),
        }
        for s in registry.satisfiable(available)
    ]


def diagnose_symbol(
    provider: DataProvider,
    symbol: str,
    name: str = '',
    asset_type: str = '',
    strategy_codes: Sequence[str] | None = None,
    params: Mapping[str, Mapping[str, object]] | None = None,
    limit: int = 260,
) -> dict:
    """诊断单个标的：返回各策略的当前信号。

    `strategy_codes` 为空 → 跑所有「当前数据可满足」的策略。
    """
    series = provider.nav_series(symbol, limit=limit)
    codes = list(strategy_codes) if strategy_codes else [s.code for s in registry.satisfiable(DEFAULT_DATA_SUPPLY)]

    signals = []
    for code in codes:
        strategy = registry.get(code)
        if strategy is None:
            continue
        ctx = StrategyContext(
            symbol=symbol,
            name=name,
            asset_type=asset_type,
            series=series,
            params=(params or {}).get(code, {}),
        )
        signals.append(strategy.evaluate(ctx).to_dict())

    return {
        'symbol': symbol,
        'name': name,
        'asset_type': asset_type,
        'sample_size': len(series),
        'as_of': series[-1].date.isoformat() if series else None,
        'data_sufficient': bool(series),
        'signals': signals,
    }


def diagnose_holdings(
    provider: DataProvider,
    family_id: int,
    strategy_codes: Sequence[str] | None = None,
    limit: int = 260,
) -> dict:
    """对家庭全部在持仓位做诊断。**只读**，不写库。"""
    holdings = provider.holdings(family_id)
    items = [
        diagnose_symbol(
            provider,
            symbol=h.symbol,
            name=h.name,
            asset_type=h.asset_type,
            strategy_codes=strategy_codes,
            limit=limit,
        )
        for h in holdings
    ]
    return {
        'family_id': family_id,
        'holding_count': len(holdings),
        'items': items,
    }


def behavior_profiles(
    provider: DataProvider,
    family_id: int,
    symbols: Sequence[str] | None = None,
    limit: int = 260,
) -> dict:
    """行为反推：用真实流水 + 净值，算出用户**实际**在用什么策略（#2225）。

    输出只陈述用户自己的历史事实，不给出任何未来倾向性意见。

    买入侧指标（#2382）
        - `forward_return`（买点质量）与 `buy_percentile`（是否追高）逐标的计算；
          同类分位需要同类型基金净值，由 provider 分步查询（本地库，无外部请求）；
        - 账户层 `actual_vs_hold` 进 summary：实际收益 vs「每笔买入后持有到期末」。
    """
    holdings = provider.holdings(family_id)
    target_symbols = list(symbols) if symbols else [h.symbol for h in holdings]
    name_by_symbol = {h.symbol: h.name for h in holdings}
    if not target_symbols:
        return {'family_id': family_id, 'profiles': [], 'summary': _empty_summary()}

    trades = provider.trades(family_id, symbols=target_symbols)
    grouped = provider.group_trades_by_symbol(trades)

    profiles: list[dict] = []
    series_by_symbol: dict[str, tuple[SeriesPoint, ...]] = {}
    for symbol in target_symbols:
        series = provider.nav_series(symbol, limit=limit)
        series_by_symbol[symbol] = series
        symbol_trades = grouped.get(symbol, [])
        peer_map = _peer_year_returns_for_symbol(provider, symbol, symbol_trades)
        profile = build_behavior_profile(
            symbol=symbol,
            trades=symbol_trades,
            series=series,
            peer_year_returns=peer_map,
        )
        payload = profile.to_dict()
        payload['name'] = name_by_symbol.get(symbol, '')
        profiles.append(payload)

    summary = _summarize(profiles)
    summary['actual_vs_hold'] = account_actual_vs_hold(
        [t for t in trades if t.symbol in series_by_symbol],
        series_by_symbol,
    )
    return {
        'family_id': family_id,
        'profiles': profiles,
        'summary': summary,
    }


def _peer_year_returns_for_symbol(
    provider: DataProvider,
    symbol: str,
    trades: Sequence[TradeRecord],
) -> dict[date, tuple[float, ...]]:
    """逐**唯一买入日**取同类近 1 年收益率（#2382）。

    去重键 = (symbol, 买入日)：同一 symbol 同一天的多笔买入共享一次查库。
    取数失败（库异常等）按「无同类数据」降级，不阻断画像其余字段。
    """
    code = extract_fund_code(symbol)
    if not code:
        return {}
    buy_dates = sorted({t.trade_date for t in trades if t.side == 'buy'})
    out: dict[date, tuple[float, ...]] = {}
    for day in buy_dates:
        try:
            peers = provider.peer_year_returns(code, day)
        except Exception:  # 取数失败不阻断画像（诚实降级）
            peers = None
        if peers:
            out[day] = peers
    return out


def _empty_summary() -> dict:
    return {
        'symbol_count': 0,
        'total_early_exit_cost': 0.0,
        'avg_hold_days': None,
        'avg_chase_buy_ratio': None,
        'dominant_style': 'unknown',
        'dominant_label': '暂无样本',
        'actual_vs_hold': None,
    }


def _summarize(profiles: Sequence[Mapping[str, object]]) -> dict:
    """汇总画像：给出**整体风格**与代价总量。

    `total_early_exit_cost` 为负表示提前卖出总体上躲过了下跌——如实呈现，不取绝对值。
    """
    scored = [p for p in profiles if p.get('trade_count')]
    if not scored:
        return _empty_summary()

    costs = [float(p['early_exit_cost']) for p in scored if p.get('early_exit_cost') is not None]
    holds = [float(p['avg_hold_days']) for p in scored if p.get('avg_hold_days') is not None]
    chases = [float(p['chase_buy_ratio']) for p in scored if p.get('chase_buy_ratio') is not None]
    pcts = [float(p['buy_percentile']) for p in scored if p.get('buy_percentile') is not None]

    tally: dict[str, int] = {}
    for p in scored:
        tally[str(p['classified_as'])] = tally.get(str(p['classified_as']), 0) + 1
    dominant = max(tally.items(), key=lambda kv: kv[1])[0] if tally else 'unknown'
    label = next((str(p['classified_label']) for p in scored if p['classified_as'] == dominant), '')

    return {
        'symbol_count': len(scored),
        'total_early_exit_cost': round(sum(costs), 2) if costs else None,
        'avg_hold_days': round(sum(holds) / len(holds), 1) if holds else None,
        'avg_chase_buy_ratio': round(sum(chases) / len(chases), 1) if chases else None,
        'avg_buy_percentile': round(sum(pcts) / len(pcts), 1) if pcts else None,
        'dominant_style': dominant,
        'dominant_label': label,
    }


def profile_to_dict(profile: BehaviorProfile) -> dict:
    return profile.to_dict()
