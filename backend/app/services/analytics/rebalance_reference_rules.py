# -*- coding: utf-8 -*-
"""持仓再平衡「客观参考」信号的纯计算规则（Q3 v1，源 #3049 §10 / #3050）。

铁律（D19 + L1 数据真实性）：本模块只做确定性计算，不接 DB、不调模型、
不生成任何方向性建议。所有数值来自调用方传入的已取数事实，算不出的一律进
``missing_signals`` 并写明原因，**绝不补 0、绝不近似、绝不让模型自由发挥**。

为什么 v1 只有两类信号（对设计文档 §3/§4 的实测修正，2026-11-11）：
- ``industry_concentration``：``positions`` 表无行业 / 板块字段，本地也没有
  「用户持仓 → 申万一级行业」的权威映射。``wind_stock`` 的个股行业查询是外部
  调用且未落库，接它等于撞「不新增 MCP / 不查外部」红线 ⇒ v1 标缺口。
- ``deviation_from_mean``：``asset_snapshots`` 只有家庭 / 账户级总资产、负债、
  净资产，**没有逐标的占比**；且模型 docstring 按 D62 明确「snapshot_date 只是
  标签、不是数据时点，禁止回填」，不能当历史序列用 ⇒ v1 标缺口。
- 可算的两类：``single_position_weight``（逐持仓市值 / 总市值）、
  ``valuation_context``（本地 ``market_multi_items`` 的宽基 pe_percentile）。

阈值均为 v1 默认值（对应设计 §10 待裁定 ②③）：owner 可回填调整，但阈值只影响
``level`` 标注，不改变任何权重数值，也不引入「买 / 卖」语义。
"""

from typing import Any, Dict, List, Optional

DISCLAIMER = '客观参考，非投资建议'

#: 单一标的占比关注 / 警示线（%）。见 Q3 设计文档 §10 待裁定 ③。
WATCH_WEIGHT_PCT = 20.0
CAUTION_WEIGHT_PCT = 35.0
#: 最多列出几个权重最高的标的，避免长尾刷屏。
TOP_N = 5
#: 估值分位带（%）。见 Q3 设计文档 §4。
PERCENTILE_HIGH = 80.0
PERCENTILE_LOW = 20.0

LEVEL_INFO = 'info'
LEVEL_WATCH = 'watch'
LEVEL_CAUTION = 'caution'
VALID_LEVELS = frozenset({LEVEL_INFO, LEVEL_WATCH, LEVEL_CAUTION})

#: 现有数据底座算不出的信号，恒定列出（防止把「没算」伪装成「算出来没问题」）。
UNAVAILABLE_SIGNALS: tuple[tuple[str, str], ...] = (
    ('industry_concentration', 'positions 无行业归属字段，本地无「持仓→申万一级行业」权威映射'),
    ('deviation_from_mean', 'asset_snapshots 无逐标的占比，且 D62 判定其不可作时点序列'),
)


def weight_level(weight_pct: float) -> str:
    """单一标的占比 → 档位。阈值只做标注，不含操作含义。"""
    if weight_pct >= CAUTION_WEIGHT_PCT:
        return LEVEL_CAUTION
    if weight_pct >= WATCH_WEIGHT_PCT:
        return LEVEL_WATCH
    return LEVEL_INFO


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


def build_rebalance_report(
    *,
    positions: Any,
    as_of: str,
    scope: str,
    valuation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """组装 Q3 输出（设计文档 §5 schema + ``missing_signals`` / ``coverage``）。

    ``positions``：[{symbol, name, market_value(元)}]，来自 ``list_position_pnl`` 同款口径。
    ``valuation``：{index, pe_percentile, valuation_date?} 或 None（本地无该条记录）。
    """
    rows = _positive_positions(positions)
    total = sum(r['market_value'] for r in rows)
    signals: List[Dict[str, Any]] = []
    missing: List[Dict[str, str]] = [{'type': t, 'reason': r} for t, r in UNAVAILABLE_SIGNALS]

    if total <= 0:
        missing.append({'type': 'single_position_weight', 'reason': '无可用持仓市值（总额不可算，不补 0）'})
    else:
        ranked = sorted(rows, key=lambda r: r['market_value'], reverse=True)[:TOP_N]
        ranked = [{'row': r, 'pct': round(r['market_value'] / total * 100, 2)} for r in ranked]
        # 有超阈标的就只列超阈的；一个都没有时仍留 Top1 的 info，避免空 signals 被误读成没查
        shown = [x for x in ranked if x['pct'] >= WATCH_WEIGHT_PCT] or ranked[:1]
        for item in shown:
            row, pct = item['row'], item['pct']
            signals.append(
                {
                    'type': 'single_position_weight',
                    'symbol': row['symbol'],
                    'name': row['name'],
                    'weight_pct': pct,
                    'note': '单一标的占比，越高越集中',
                    'level': weight_level(pct),
                }
            )

    percentile = (valuation or {}).get('pe_percentile')
    if isinstance(percentile, bool) or not isinstance(percentile, (int, float)):
        missing.append({'type': 'valuation_context', 'reason': '本地无该基准指数的估值分位记录'})
    else:
        p = float(percentile)
        extreme = p > PERCENTILE_HIGH or p < PERCENTILE_LOW
        signals.append(
            {
                'type': 'valuation_context',
                'index': str((valuation or {}).get('index') or ''),
                'pe_percentile': p,
                'valuation_date': (valuation or {}).get('valuation_date'),
                'note': valuation_label(p),
                'level': LEVEL_WATCH if extreme else LEVEL_INFO,
            }
        )

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
    'DISCLAIMER',
    'VALID_LEVELS',
    'WATCH_WEIGHT_PCT',
    'CAUTION_WEIGHT_PCT',
    'build_rebalance_report',
    'valuation_label',
    'weight_level',
]
