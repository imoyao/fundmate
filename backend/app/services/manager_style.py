# -*- coding: utf-8 -*-
# Author : imoyao
"""基金经理风格标签判据（#2044）：可复算纯函数 + 全库分布标定阈值。

## 为什么是纯函数

issue #2044 的验收要求判据「必须给出可复算的数值规则，不能是主观描述」，且阈值
「需用真实分布标定，而不是拍脑袋」。故本模块：**无 DB、无 IO、无网络**——同一份
输入在任何机器上得到同一份标签；阈值全部集中在 `DEFAULT_THRESHOLDS`，其来源与
分位数推导记录在 `docs/working-notes/manager-style-tags-calibration-2026-10-12.md`。

## 三个维度（第四个明确不做，见标定文档 §4/§5）

- `concentration` 持仓集中度：前十大重仓占净值比，按全库 P50/P80 分三档；
- `industry` 行业集中度：证监会门类（csrc）第一大行业占比，按全库 P50/P80 分三档；
- `size` 市值风格：沪深300 成分占**已覆盖**持仓比，覆盖率不足 `min_coverage` 不判定
  （重仓港股的 QDII 等覆盖不全时诚实回空，不拿半截样本猜大盘小盘）。

成长/价值维度**不实现**（穿透只有行业/个股两层，无每股风格属性——数据不足时的
诚实做法是不产出字段，而不是产出恒空字段）；换手率**放弃**（库内无调仓数据）。

## 硬约束

1. **数据不足回空**：指标缺失 / 越界（<0 或 >100）→ 该维度不产出标签，绝不以 0
   或默认值顶替（沿用第一期「回 null、前端显示 —」的降级纪律）。
2. **后端不返回颜色**：`StyleLabel` 只有 `dim/key/label/basis` 四个字段，key 是稳定
   枚举（前端据此映射 Badge 样式），配色由前端令牌决定——与第一期转换层硬约束一致。
3. **basis 必须可解释**：格式 `{指标中文名} {值:.1f}%，{分位注记}`，让用户能判断
   标签可信度（如「前十大重仓占净值 65.8%，全库 P80」）。
4. **边界归属唯一**：下界含本档（`≥` 进高档、`<` 留低档），任意实数恰好命中一档。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ── 维度（稳定枚举，前端按此分流展示）──
DIM_CONCENTRATION = 'concentration'
DIM_INDUSTRY = 'industry'
DIM_SIZE = 'size'


@dataclass(frozen=True)
class StyleLabel:
    """单个风格标签。**不含颜色**——配色是前端令牌的事（硬约束 2）。"""

    dim: str   # 维度枚举
    key: str   # 稳定标签枚举，如 concentration_high（前端映射 Badge 样式）
    label: str # 中文短文案
    basis: str # 可解释依据（指标值 + 分位注记）

    def as_dict(self) -> Dict[str, Any]:
        return {'dim': self.dim, 'key': self.key, 'label': self.label, 'basis': self.basis}


@dataclass(frozen=True)
class FundStyleMetrics:
    """单只基金的风格判定输入（由调用方从既有两张表装配，本模块不查库）。

    全部百分比指标口径见标定文档 §1；`None` = 数据不足，对应维度不产出标签。
    """

    fund_code: str
    top10_ratio: Optional[float] = None        # 前十大重仓合计占净值比（%）
    holding_basis: Optional[str] = None        # 'full' | 'top10'（披露口径，影响 basis 注记）
    top_industry_ratio: Optional[float] = None  # csrc 第一大行业占净值比（%）
    size_covered_pct: Optional[float] = None    # 市值分桶覆盖率（%，已覆盖占全部持仓）
    size_large_share: Optional[float] = None    # 沪深300 成分占已覆盖持仓比（%）
    report_period: Optional[str] = None         # 最新报告期，如 '2026Q2'


# ── 阈值结构 ────────────────────────────────────────────────

@dataclass(frozen=True)
class Band3:
    """三档阈值：`< lo` 低档、`lo ≤ x < hi` 中档、`≥ hi` 高档。

    `note_*` 是 basis 的分位注记（标定文档给出阈值对应的真实分位）。
    """

    lo: float
    hi: float
    note_lo: str
    note_mid: str
    note_hi: str


@dataclass(frozen=True)
class SizeBand:
    """市值风格阈值：先过覆盖率门，再按 300 成分占比三档。"""

    min_coverage: float  # 覆盖率下限（%），不足则不判定
    lo: float
    hi: float
    note_lo: str
    note_mid: str
    note_hi: str


@dataclass(frozen=True)
class Thresholds:
    concentration: Band3
    industry: Band3
    size: SizeBand


#: 默认阈值——全部来自 2026-10-12 全库标定（101 只样本，每只取各自最新报告期）。
#: 分位出处与取整 rationale 见 `docs/working-notes/manager-style-tags-calibration-2026-10-12.md`。
#: 复标时机：持仓多期回填落地后（数据只随报告期缓慢变化，不做高频重标）。
DEFAULT_THRESHOLDS = Thresholds(
    concentration=Band3(
        lo=50.0,    # n=100 P50 = 49.78，四舍五入 50
        hi=66.0,    # n=100 P80 = 65.83，四舍五入 66
        note_lo='全库 P50 以下',
        note_mid='全库 P50–P80',
        note_hi='全库 P80',
    ),
    industry=Band3(
        lo=60.0,    # 全库 P50 = 60.42，取整 60
        hi=81.0,    # 全库 P80 = 80.75，取整 81
        note_lo='全库 P50 以下',
        note_mid='全库 P50–P80',
        note_hi='全库 P80',
    ),
    size=SizeBand(
        min_coverage=60.0,  # ≈ 全库 P25（61.9）向下取整；78/101 只通过
        lo=36.5,            # 全库 P25 = 36.53
        hi=67.4,            # 全库 P75 = 67.38
        note_lo='全库 P25',
        note_mid='全库 P25–P75',
        note_hi='全库 P75',
    ),
)

# ── 档位文案（key 与文案分离：key 稳定，文案可改）──
_SUFFIXES = ('low', 'mid', 'high')
_TEXTS: Dict[str, Dict[str, str]] = {
    DIM_CONCENTRATION: {'low': '持仓分散', 'mid': '持仓中性', 'high': '持仓高集中'},
    DIM_INDUSTRY: {'low': '行业分散', 'mid': '行业中性', 'high': '行业集中'},
    DIM_SIZE: {'low': '偏中小盘', 'mid': '市值均衡', 'high': '偏大盘'},
}
_METRIC_TEXTS: Dict[str, str] = {
    DIM_CONCENTRATION: '前十大重仓占净值',
    DIM_INDUSTRY: '第一大行业占比',
    DIM_SIZE: '沪深300 成分占已覆盖持仓',
}


def _pct(value: Optional[float]) -> Optional[float]:
    """百分比指标消毒：缺失 / bool / NaN / 越界（<0 或 >100）一律回 None（不猜、不填充）。"""
    if value is None or isinstance(value, bool):
        return None
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v) or v < 0 or v > 100:
        return None
    return v


def _band3(value: float, band: 'Band3 | SizeBand') -> str:
    """三档归类，下界含本档：`<lo`→low、`[lo,hi)`→mid、`≥hi`→high。"""
    if value < band.lo:
        return 'low'
    if value < band.hi:
        return 'mid'
    return 'high'


def _note_for(suffix: str, band: 'Band3 | SizeBand') -> str:
    return {'low': band.note_lo, 'mid': band.note_mid, 'high': band.note_hi}[suffix]


def _make_label(
    dim: str, suffix: str, value: float, note: str, extra: str = '', key_suffix: str = ''
) -> StyleLabel:
    """拼标签：`suffix` 索引文案与分位注记，`key_suffix` 缺省与 suffix 相同。"""
    key = f'{dim}_{key_suffix or suffix}'
    basis = f'{_METRIC_TEXTS[dim]} {value:.1f}%，{note}{extra}'
    return StyleLabel(dim=dim, key=key, label=_TEXTS[dim][suffix], basis=basis)


def judge_style(
    metrics: FundStyleMetrics,
    thresholds: Optional[Thresholds] = None,
) -> List[StyleLabel]:
    """按三维度打风格标签。数据不足的维度**不出标签**（issue 问题 3：回 null）。

    Args:
        metrics: 单只基金的指标装配（调用方保证来自同一最新报告期）。
        thresholds: 阈值覆盖（测试注入用）；缺省用全库标定的 `DEFAULT_THRESHOLDS`。

    Returns:
        标签列表，顺序恒为 concentration → industry → size（确定性）。
        输入全缺失时返回 `[]`——前端按「维度缺席」显示 `—`，不显示猜测结果。
    """
    th = thresholds or DEFAULT_THRESHOLDS
    labels: List[StyleLabel] = []

    # 1. 持仓集中度
    top10 = _pct(metrics.top10_ratio)
    if top10 is not None:
        suffix = _band3(top10, th.concentration)
        extra = '（季报前十大口径）' if metrics.holding_basis == 'top10' else ''
        labels.append(
            _make_label(DIM_CONCENTRATION, suffix, top10, _note_for(suffix, th.concentration), extra)
        )

    # 2. 行业集中度（csrc 口径由装配方保证，本函数不辨体系——跨体系混算是上游的错）
    top1 = _pct(metrics.top_industry_ratio)
    if top1 is not None:
        suffix = _band3(top1, th.industry)
        labels.append(_make_label(DIM_INDUSTRY, suffix, top1, _note_for(suffix, th.industry)))

    # 3. 市值风格：覆盖率门不达标即不判定（QDII/重仓港股基金诚实缺席）
    coverage = _pct(metrics.size_covered_pct)
    large_share = _pct(metrics.size_large_share)
    if coverage is not None and large_share is not None and coverage >= th.size.min_coverage:
        suffix = _band3(large_share, th.size)
        # size 的 key 枚举独立命名（small/balanced/large），文案仍按 suffix 取
        size_key = {'low': 'small', 'mid': 'balanced', 'high': 'large'}[suffix]
        labels.append(
            _make_label(
                DIM_SIZE, suffix, large_share, _note_for(suffix, th.size), key_suffix=size_key
            )
        )

    return labels
