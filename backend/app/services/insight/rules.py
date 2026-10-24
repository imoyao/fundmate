# -*- coding: utf-8 -*-
# File : rules.py
# app/services/insight/rules.py
"""诊断规则的**唯一登记处**（#1017）。

## 为什么要一张注册表，而不是散落的 if

卡面要求「规则源可配置（避免硬编码散落）」。做成注册表之后：

- 加规则 = 在 `RULES` 里加一项 + 写一个 `check`，**不动取数逻辑、不动视图、不动前端**
  （前端按 `severity` 渲染，不认识具体规则）；
- 阈值与文案都在这一个文件里，改「集中度 25% → 30%」不需要读业务代码；
- 每条规则**只读快照**、不查库，避免「一条规则一次查询」的 N+1，也让单测不必碰数据库。

## 规则与「策略诊断」的分工

`services/strategy_engine/diagnosis.py`（#2225）回答「这只标的该买/持/减」——是**策略信号**；
这里回答「这笔账有什么值得看一眼的风险」——是**静态提示**，零 LLM、零外部调用、不落库。
两者不合并：策略信号的依据是行情与规则组合，提示的依据是账户结构与敞口，混在一起会让
两边都改不动。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# ── 严重度（前端按此上色，顺序即强弱）──────────────────────────────
SEVERITY_INFO = 'info'
SEVERITY_WARN = 'warn'
SEVERITY_RISK = 'risk'

# ── 阈值（改这里就够了）────────────────────────────────────────────
# 单一标的市值占投资持仓总市值的上限
SINGLE_NAME_LIMIT = 0.25
# 主口径下最大行业占「已穿透市值」的上限
INDUSTRY_LIMIT = 0.60
# 行业规则的最低穿透率：穿透率太低时行业占比不可信，宁可不提示
INDUSTRY_MIN_COVERAGE = 0.30
# 少于这个数的持仓视为分散不足
MIN_HOLDINGS = 3
# 组合最近一个交易日的跌幅（百分比，负数）
DAY_DROP_LIMIT_PCT = -2.0


@dataclass(frozen=True)
class Rule:
    """一条诊断规则。

    `check` 收到快照、返回**证据字典**（写入结果的 `evidence`）或 `None`（不触发）。
    证据留原始数值而不是拼好的句子：前端/后续复盘要能看出「凭什么是这条」。
    """

    code: str
    severity: str
    title: str
    rationale: str
    check: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


def _pct(value: float) -> str:
    return f'{value * 100:.1f}%'


def _check_single_name(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """单一标的过度集中：一只标的占到投资持仓的 1/4 以上。"""
    holdings = snapshot.get('holdings') or []
    total = snapshot.get('total_cents') or 0
    if not holdings or total <= 0:
        return None
    top = max(holdings, key=lambda row: row.get('market_value_cents') or 0)
    ratio = (top.get('market_value_cents') or 0) / total
    if ratio < SINGLE_NAME_LIMIT:
        return None
    return {
        'symbol': top.get('symbol'),
        'name': top.get('name'),
        'ratio': round(ratio, 4),
        'limit': SINGLE_NAME_LIMIT,
        'message': (
            f'「{top.get("name") or top.get("symbol")}」占投资持仓 {_pct(ratio)}，'
            f'超过 {_pct(SINGLE_NAME_LIMIT)} 的集中度上限——单一标的波动会直接决定整账表现。'
        ),
    }


def _check_industry(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """行业过度集中：主口径下最大行业占已穿透市值 60% 以上。"""
    industry = snapshot.get('top_industry')
    coverage = snapshot.get('penetration_ratio') or 0
    if not industry:
        return None
    ratio = industry.get('ratio_of_penetrated') or 0
    if coverage < INDUSTRY_MIN_COVERAGE or ratio < INDUSTRY_LIMIT:
        return None
    return {
        'industry': industry.get('name'),
        'ratio': round(ratio, 4),
        'limit': INDUSTRY_LIMIT,
        'penetration_ratio': round(coverage, 4),
        'message': (
            f'行业「{industry.get("name")}」占已穿透持仓 {_pct(ratio)}，超过 {_pct(INDUSTRY_LIMIT)}；'
            f'（行业数据来自基金定期报告，当前穿透率 {_pct(coverage)}）'
        ),
    }


def _check_diversification(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """分散不足：投资持仓少于 MIN_HOLDINGS 只标的。"""
    count = snapshot.get('holding_count') or 0
    total = snapshot.get('total_cents') or 0
    if total <= 0 or count == 0 or count >= MIN_HOLDINGS:
        return None
    return {
        'holding_count': count,
        'limit': MIN_HOLDINGS,
        'message': f'当前只有 {count} 只投资持仓，少于 {MIN_HOLDINGS} 只——单只标的的波动会放大到整账。',
    }


def _check_day_drop(snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """组合最近一个交易日跌幅超阈值。"""
    latest = snapshot.get('latest_day') or {}
    rate = latest.get('rate_pct')
    if rate is None or rate > DAY_DROP_LIMIT_PCT:
        return None
    return {
        'date': latest.get('date'),
        'rate_pct': round(rate, 2),
        'limit_pct': DAY_DROP_LIMIT_PCT,
        'message': (
            f'{latest.get("date")} 组合当日跌幅 {rate:.2f}%，超过 {abs(DAY_DROP_LIMIT_PCT):.0f}% 的提醒线。'
            f'先确认是普跌还是单一标的拖累，再决定要不要动。'
        ),
    }


# ── 注册表：顺序即展示顺序（风险在前）──────────────────────────────
RULES: List[Rule] = [
    Rule(
        code='single_name_concentration',
        severity=SEVERITY_RISK,
        title='单一标的过于集中',
        rationale='一只标的占投资持仓 ≥25%：波动不再是「组合波动」，而是「这只标的的波动」。',
        check=_check_single_name,
    ),
    Rule(
        code='industry_concentration',
        severity=SEVERITY_WARN,
        title='行业集中度偏高',
        rationale='主口径最大行业占已穿透市值 ≥60%，且穿透率 ≥30%（穿透率低时占比不可信，宁可不提示）。',
        check=_check_industry,
    ),
    Rule(
        code='low_diversification',
        severity=SEVERITY_WARN,
        title='持仓分散不足',
        rationale='投资持仓少于 3 只：任何单只标的的异动都会直接改变整账结果。',
        check=_check_diversification,
    ),
    Rule(
        code='portfolio_day_drop',
        severity=SEVERITY_INFO,
        title='组合单日回撤',
        rationale='最近一个交易日跌幅 ≥2%：提示先分辨「普跌」还是「单一标的拖累」，避免情绪化操作。',
        check=_check_day_drop,
    ),
]


def evaluate(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """按注册顺序跑全部规则，返回触发的提示列表。

    单条规则抛异常**不影响其它规则**：一类数据缺列/缺表就把整页提示打空，比不提示更糟。
    """
    from loguru import logger

    tips: List[Dict[str, Any]] = []
    for rule in RULES:
        try:
            evidence = rule.check(snapshot)
        except Exception as e:  # pragma: no cover - 防御性分支，正常数据不会走到
            logger.warning(f'诊断规则 {rule.code} 执行失败，已跳过: {e}')
            continue
        if not evidence:
            continue
        tips.append(
            {
                'code': rule.code,
                'severity': rule.severity,
                'title': rule.title,
                'message': evidence.pop('message'),
                'rationale': rule.rationale,
                'evidence': evidence,
            }
        )
    return tips
