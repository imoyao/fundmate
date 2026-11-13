# -*- coding: utf-8 -*-
"""持仓再平衡「客观参考」信号的纯计算规则（Q3 v1 + v2，源 #3049 §10 / D112）。

铁律（D19 + L1 数据真实性）：本模块只做确定性计算，不接 DB、不调模型、
不生成任何方向性建议。所有数值来自调用方传入的已取数事实，算不出的一律进
``missing_signals`` 并写明原因，**绝不补 0、绝不近似、绝不让模型自由发挥**。

v2（2026-11-12，D112）把 v1 硬钉为缺口的两类信号改成「有数据就算、没数据就声明」：

- ``industry_concentration``：口径为**证监会门类（csrc）+ 已穿透部分 HHI + 覆盖率**。
  基金侧没有申万一级，设计 §4 的「申万一级」不可实现；按穿透模块硬口径禁止跨体系相加。
- ``deviation_from_mean``：当前占比 vs 近 90 天 as-of 采样均值（不回填快照，D62）。
- ``fund_valuation_percentile``：个基历史估值分位。A′ 口径未落库 ⇒ 恒定缺口；
  接入点已备好，落库后自动生效，绝不拿宽基分位冒充个基。

阈值均为 owner 裁定后的正式口径（D112）：只影响 ``level`` 标注，不改变任何数值，
也不引入「买 / 卖」语义。

信号按类拆成小函数，主入口只做编排 —— 守住 services 层软闸门
（``guard_service_size.py``：新增文件最长函数 ≤120 行 / 圈复杂度 ≤20）。
"""

from typing import Any, Dict, List, Optional

DISCLAIMER = '客观参考，非投资建议'

#: 单一标的占比关注 / 警示线（%）。
WATCH_WEIGHT_PCT = 20.0
CAUTION_WEIGHT_PCT = 35.0
#: 最多列出几个权重最高 / 偏离最大的标的，避免长尾刷屏。
TOP_N = 5
#: 估值分位带（%）。
PERCENTILE_HIGH = 80.0
PERCENTILE_LOW = 20.0
#: v2：历史占比偏离与行业集中度的关注 / 警示线（百分点 / %）。
DEVIATION_WATCH_PCT = 5.0
DEVIATION_CAUTION_PCT = 10.0
INDUSTRY_WATCH_SHARE_PCT = 40.0
INDUSTRY_CAUTION_SHARE_PCT = 60.0
HISTORY_MIN_SAMPLES = 2

LEVEL_INFO = 'info'
LEVEL_WATCH = 'watch'
LEVEL_CAUTION = 'caution'
VALID_LEVELS = frozenset({LEVEL_INFO, LEVEL_WATCH, LEVEL_CAUTION})

#: 数据底座仍恒定算不出的信号（防止把「没算」伪装成「算出来没问题」）。
#: v1 的行业集中度 / 历史均值偏离已改为动态判定，见 ``_v2_signals``。
UNAVAILABLE_SIGNALS: tuple[tuple[str, str], ...] = (
    ('fund_valuation_percentile', '本地无个基历史估值分位落库（A′ 口径未落地，不拿宽基分位替代）'),
)

GAP_INDUSTRY = '本地无可用行业穿透数据（覆盖率 0），不编造行业占比'
GAP_HISTORY = '近 90 天无足够历史价格与份额样本，as-of 现算不可用，不回填快照'
GAP_WEIGHT = '无可用持仓市值（总额不可算，不补 0）'
GAP_VALUATION = '本地无该基准指数的估值分位记录'


def _threshold_level(value: float, watch: float, caution: float) -> str:
    """阈值 → 档位；偏离取绝对值，占比取原值。档位不含操作含义。"""
    magnitude = abs(value)
    if magnitude >= caution:
        return LEVEL_CAUTION
    if magnitude >= watch:
        return LEVEL_WATCH
    return LEVEL_INFO


def weight_level(weight_pct: float) -> str:
    """单一标的占比 → 档位。阈值只做标注，不含操作含义。"""
    return _threshold_level(weight_pct, WATCH_WEIGHT_PCT, CAUTION_WEIGHT_PCT)


def valuation_label(pe_percentile: float) -> str:
    """估值分位 → 中性描述。>80 偏高 / <20 偏低 / 其余正常。"""
    if pe_percentile > PERCENTILE_HIGH:
        return '估值偏高'
    if pe_percentile < PERCENTILE_LOW:
        return '估值偏低'
    return '估值正常'


def _positive_positions(positions: Any) -> List[Dict[str, Any]]:
    """只保留市值可取正值的行；None / 非数值 / 非正值一律不算进分母也不造 0。"""
    rows: List[Dict[str, Any]] = []
    for p in positions or []:
        if not isinstance(p, dict):
            continue
        mv = p.get('market_value')
        if isinstance(mv, bool) or not isinstance(mv, (int, float)) or mv <= 0:
            continue
        rows.append({'symbol': str(p.get('symbol') or ''), 'name': str(p.get('name') or ''), 'market_value': float(mv)})
    return rows


def _weights_and_names(rows, total: float):
    """当前占比与名称索引；总额不可算时两个都为空。"""
    if total <= 0:
        return {}, {}
    weights = {r['symbol']: r['market_value'] / total * 100 for r in rows}
    names = {r['symbol']: r['name'] for r in rows}
    return weights, names


def _weight_signals(rows, total: float):
    """v1：单一标的占比（Top-N，超阈优先）。"""
    if total <= 0:
        return [], {'type': 'single_position_weight', 'reason': GAP_WEIGHT}
    ranked = sorted(rows, key=lambda r: r['market_value'], reverse=True)[:TOP_N]
    ranked = [{'row': r, 'pct': round(r['market_value'] / total * 100, 2)} for r in ranked]
    # 有超阈标的就只列超阈的；一个都没有时仍留 Top1 的 info，避免空 signals 被误读成没查
    shown = [x for x in ranked if x['pct'] >= WATCH_WEIGHT_PCT] or ranked[:1]
    signals = [
        {
            'type': 'single_position_weight',
            'symbol': item['row']['symbol'],
            'name': item['row']['name'],
            'weight_pct': item['pct'],
            'note': '单一标的占比，越高越集中',
            'level': weight_level(item['pct']),
        }
        for item in shown
    ]
    return signals, None


def _valuation_signal(valuation: Optional[Dict[str, Any]]):
    """v1：宽基估值分位；缺失返回缺口，不补 0。"""
    percentile = (valuation or {}).get('pe_percentile')
    if isinstance(percentile, bool) or not isinstance(percentile, (int, float)):
        return None, {'type': 'valuation_context', 'reason': GAP_VALUATION}
    p = float(percentile)
    extreme = p > PERCENTILE_HIGH or p < PERCENTILE_LOW
    signal = {
        'type': 'valuation_context',
        'index': str((valuation or {}).get('index') or ''),
        'pe_percentile': p,
        'valuation_date': (valuation or {}).get('valuation_date'),
        'note': valuation_label(p),
        'level': LEVEL_WATCH if extreme else LEVEL_INFO,
    }
    return signal, None


def _industry_signal(fact: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """csrc 已穿透部分的 Top 行业占比 + HHI；无可用事实返回 None。"""
    if not fact:
        return None
    items = [i for i in fact.get('industries') or [] if float(i.get('value_cny') or 0) > 0]
    total = sum(float(i['value_cny']) for i in items)
    if not items or total <= 0:
        return None
    shares = [float(i['value_cny']) / total for i in items]
    top_item, top_share = max(zip(items, shares), key=lambda pair: pair[1])
    share_pct = round(top_share * 100, 2)
    return {
        'type': 'industry_concentration',
        'scheme': fact.get('scheme') or 'csrc',
        'scheme_label': fact.get('scheme_label') or '',
        'top_industry': str(top_item.get('name') or top_item.get('code') or ''),
        'share_pct': share_pct,
        'hhi': round(sum(s * s for s in shares), 4),
        'coverage_pct': round(float(fact.get('penetrated_ratio') or 0) * 100, 2),
        'note': '已穿透部分的行业占比；未穿透部分不含在内，覆盖率见 coverage_pct',
        'level': _threshold_level(share_pct, INDUSTRY_WATCH_SHARE_PCT, INDUSTRY_CAUTION_SHARE_PCT),
    }


def _deviation_signals(
    fact: Optional[Dict[str, Any]], weights: Dict[str, float], names: Dict[str, str]
) -> List[Dict[str, Any]]:
    """当前占比 vs 历史采样均值；只对当前仍持有的标的出信号，最多 TOP_N 条。"""
    if not fact or int(fact.get('sample_days') or 0) < HISTORY_MIN_SAMPLES:
        return []
    out: List[Dict[str, Any]] = []
    for symbol, mean in (fact.get('means') or {}).items():
        current = weights.get(symbol)
        if current is None or isinstance(mean, bool) or not isinstance(mean, (int, float)):
            continue
        delta = round(float(current) - float(mean), 2)
        out.append(
            {
                'type': 'deviation_from_mean',
                'symbol': symbol,
                'name': names.get(symbol, ''),
                'current_pct': round(float(current), 2),
                'mean_pct': round(float(mean), 2),
                'delta_pct': delta,
                'sample_days': int(fact.get('sample_days') or 0),
                'note': '当前占比与近 90 天 as-of 采样均值的差；正值表示比历史更集中',
                'level': _threshold_level(delta, DEVIATION_WATCH_PCT, DEVIATION_CAUTION_PCT),
            }
        )
    out.sort(key=lambda s: abs(s['delta_pct']), reverse=True)
    return out[:TOP_N]


def _fund_valuation_signals(fact: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A′ 落库后才会有数据；分位缺失的行跳过，不补 0。"""
    out: List[Dict[str, Any]] = []
    for item in (fact or {}).get('items') or []:
        pct = item.get('pe_percentile')
        if isinstance(pct, bool) or not isinstance(pct, (int, float)):
            continue
        p = float(pct)
        out.append(
            {
                'type': 'fund_valuation_percentile',
                'symbol': str(item.get('symbol') or ''),
                'pe_percentile': p,
                'valuation_date': item.get('valuation_date'),
                'note': valuation_label(p),
                'level': LEVEL_WATCH if p > PERCENTILE_HIGH or p < PERCENTILE_LOW else LEVEL_INFO,
            }
        )
    return out[:TOP_N]


def _v2_signals(industry, history, fund_valuation, weights, names):
    """三类 v2 信号与对应缺口：有事实出数、没事实声明原因，二者互斥。"""
    signals: List[Dict[str, Any]] = []
    missing: List[Dict[str, str]] = []
    industry_signal = _industry_signal(industry)
    if industry_signal is None:
        missing.append({'type': 'industry_concentration', 'reason': GAP_INDUSTRY})
    else:
        signals.append(industry_signal)
    deviation_signals = _deviation_signals(history, weights, names)
    if not deviation_signals:
        missing.append({'type': 'deviation_from_mean', 'reason': GAP_HISTORY})
    else:
        signals.extend(deviation_signals)
    fund_signals = _fund_valuation_signals(fund_valuation)
    if not fund_signals:
        missing.extend({'type': t, 'reason': r} for t, r in UNAVAILABLE_SIGNALS)
    else:
        signals.extend(fund_signals)
    return signals, missing


def build_rebalance_report(
    *,
    positions: Any,
    as_of: str,
    scope: str,
    valuation: Optional[Dict[str, Any]] = None,
    industry: Optional[Dict[str, Any]] = None,
    history: Optional[Dict[str, Any]] = None,
    fund_valuation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """组装 Q3 输出（设计文档 §5 schema + ``missing_signals`` / ``coverage``）。

    ``positions``：[{symbol, name, market_value(元)}]，来自 ``list_position_pnl`` 同款口径。
    ``valuation``：宽基 {index, pe_percentile, valuation_date?} 或 None。
    ``industry`` / ``history`` / ``fund_valuation``：v2 取数层事实，None = 算不出。
    """
    rows = _positive_positions(positions)
    total = sum(r['market_value'] for r in rows)
    weights, names = _weights_and_names(rows, total)
    signals: List[Dict[str, Any]] = []
    missing: List[Dict[str, str]] = []

    weight_signals, weight_gap = _weight_signals(rows, total)
    signals.extend(weight_signals)
    if weight_gap:
        missing.append(weight_gap)

    valuation_signal, valuation_gap = _valuation_signal(valuation)
    if valuation_signal:
        signals.append(valuation_signal)
    else:
        missing.append(valuation_gap)

    v2_signals, v2_missing = _v2_signals(industry, history, fund_valuation, weights, names)
    signals.extend(v2_signals)
    missing.extend(v2_missing)

    return {
        'disclaimer': DISCLAIMER,
        'as_of': as_of,
        'scope': scope,
        'signals': signals,
        'missing_signals': missing,
        'coverage': {
            'position_count': len(rows),
            'total_market_value_yuan': round(total, 2),
            'excluded_count': len(positions or []) - len(rows),
        },
    }


__all__ = [
    'CAUTION_WEIGHT_PCT',
    'DEVIATION_CAUTION_PCT',
    'DEVIATION_WATCH_PCT',
    'DISCLAIMER',
    'INDUSTRY_CAUTION_SHARE_PCT',
    'INDUSTRY_WATCH_SHARE_PCT',
    'UNAVAILABLE_SIGNALS',
    'VALID_LEVELS',
    'WATCH_WEIGHT_PCT',
    'build_rebalance_report',
    'valuation_label',
    'weight_level',
]
