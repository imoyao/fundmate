# -*- coding: utf-8 -*-
"""manager_style 判据纯函数测试（#2044）。

覆盖：三维度档位边界（下界含本档）、缺失值 / 越界 / NaN 的诚实降级、
basis 文本格式、标签顺序确定性、阈值注入、StyleLabel 无颜色字段。
"""

import dataclasses
import math

import pytest

from app.services.manager_style import (
    DEFAULT_THRESHOLDS,
    DIM_CONCENTRATION,
    DIM_INDUSTRY,
    DIM_SIZE,
    FundStyleMetrics,
    StyleLabel,
    judge_style,
)


def _full(top10=55.0, top1=70.0, coverage=90.0, large=60.0, holding_basis='full', **kw):
    """构造一份「数据齐全」的典型指标（默认值落在各维度中档）。"""
    return FundStyleMetrics(
        fund_code='005827',
        top10_ratio=top10,
        holding_basis=holding_basis,
        top_industry_ratio=top1,
        size_covered_pct=coverage,
        size_large_share=large,
        report_period='2026Q2',
        **kw,
    )


def _by_dim(labels):
    return {lb.dim: lb for lb in labels}


# ── 降级：缺失 / 越界 ──────────────────────────────────────


def test_all_missing_returns_empty():
    """只有 fund_code、其余全缺 → 空列表（issue 问题 3：不猜、不填充）。"""
    assert judge_style(FundStyleMetrics(fund_code='110022')) == []


def test_partial_data_only_available_dims():
    """只有一维数据 → 只出一个标签，缺席维度不是 null 占位而是不存在。"""
    m = FundStyleMetrics(fund_code='x', top10_ratio=66.0)
    labels = judge_style(m)
    assert [lb.dim for lb in labels] == [DIM_CONCENTRATION]


@pytest.mark.parametrize('bad', [-1.0, 101.0, float('nan'), float('inf'), 'abc', True])
def test_invalid_top10_treated_as_missing(bad):
    """越界 / NaN / 非法类型 → 视为缺失，集中度维度不出标签。"""
    m = FundStyleMetrics(fund_code='x', top10_ratio=bad)
    assert judge_style(m) == []


def test_pure_missing_all_dims():
    """三项指标全缺 → 三维度全缺席。"""
    m = FundStyleMetrics(
        fund_code='x',
        top10_ratio=None,
        top_industry_ratio=None,
        size_covered_pct=None,
        size_large_share=None,
    )
    assert judge_style(m) == []


# ── 集中度档位边界（lo=50 / hi=65，下界含本档）──────────────


@pytest.mark.parametrize(
    'value,expect',
    [
        (0.10, 'concentration_low'),  # 全库真实 min
        (49.9, 'concentration_low'),
        (50.0, 'concentration_mid'),  # 下界含本档
        (64.9, 'concentration_mid'),
        (65.9, 'concentration_mid'),
        (66.0, 'concentration_high'),  # 下界含本档（P80=65.83→66）
        (85.95, 'concentration_high'),  # 全库真实 max
        (100.0, 'concentration_high'),
    ],
)
def test_concentration_bands(value, expect):
    labels = judge_style(_full(top10=value))
    assert _by_dim(labels)[DIM_CONCENTRATION].key == expect


def test_concentration_top10_basis_extra_note():
    """季报前十大口径必须在 basis 里注明口径强度（full 口径不加）。"""
    base = judge_style(_full(top10=66.0, holding_basis='full'))[0]
    top10 = judge_style(_full(top10=66.0, holding_basis='top10'))[0]
    assert '季报前十大口径' in top10.basis
    assert '季报前十大口径' not in base.basis


# ── 行业集中度档位边界（lo=60 / hi=81）─────────────────────


@pytest.mark.parametrize(
    'value,expect',
    [
        (0.12, 'industry_low'),  # 全库真实 min
        (59.9, 'industry_low'),
        (60.0, 'industry_mid'),  # 下界含本档
        (80.9, 'industry_mid'),
        (81.0, 'industry_high'),  # 下界含本档
        (94.77, 'industry_high'),  # 全库真实 max
    ],
)
def test_industry_bands(value, expect):
    labels = judge_style(_full(top1=value))
    assert _by_dim(labels)[DIM_INDUSTRY].key == expect


# ── 市值风格：覆盖率门 + 档位边界 ───────────────────────────


@pytest.mark.parametrize(
    'coverage,expect_count',
    [
        (None, 2),  # 覆盖率缺失 → 不判定 size（只剩集中度+行业）
        (0.0, 2),  # 全未覆盖（重仓港股）→ 不判定
        (59.9, 2),  # 门下 → 不判定
        (60.0, 3),  # 门边界含本档 → 判定
        (80.5, 3),  # 全库 P50
    ],
)
def test_size_coverage_gate(coverage, expect_count):
    m = _full(coverage=coverage, large=50.0)
    assert len(judge_style(m)) == expect_count


@pytest.mark.parametrize(
    'share,expect',
    [
        (0.0, 'size_small'),
        (36.4, 'size_small'),
        (36.5, 'size_balanced'),  # 统一约定「下界含本档」：lo 归中档（与集中度 50→mid 同规）
        (36.6, 'size_balanced'),
        (67.3, 'size_balanced'),
        (67.4, 'size_large'),  # 下界含本档（P75）
        (100.0, 'size_large'),
    ],
)
def test_size_bands(share, expect):
    labels = judge_style(_full(coverage=80.0, large=share))
    assert _by_dim(labels)[DIM_SIZE].key == expect


def test_size_share_missing_no_label():
    """覆盖率够但占比缺失 → 同样不判定（半个输入不猜另一半）。"""
    m = FundStyleMetrics(
        fund_code='x',
        top10_ratio=66.0,
        size_covered_pct=80.0,
        size_large_share=None,
    )
    assert [lb.dim for lb in judge_style(m)] == [DIM_CONCENTRATION]


# ── 输出形状 / 文本约定 ─────────────────────────────────────


def test_order_deterministic_and_keys():
    labels = judge_style(_full())
    assert [lb.dim for lb in labels] == [DIM_CONCENTRATION, DIM_INDUSTRY, DIM_SIZE]
    assert [lb.key for lb in labels] == [
        'concentration_mid',
        'industry_mid',
        'size_balanced',
    ]


def test_basis_format_and_no_color():
    """basis = `{指标} {值:.1f}%，{分位注记}`；StyleLabel 无颜色字段（硬约束）。"""
    # 65.78 落在 [50,66) 中档（P80 阈值为 66），注记为「全库 P50–P80」
    label = judge_style(_full(top10=65.78, top1=80.75, large=72.48))[0]
    assert label.basis == '前十大重仓占净值 65.8%，全库 P50–P80'
    fields = {f.name for f in dataclasses.fields(StyleLabel)}
    assert fields == {'dim', 'key', 'label', 'basis'}
    for forbidden in ('color', 'colour', 'style', 'hex'):
        assert forbidden not in label.as_dict()


def test_full_label_texts():
    """三维度三档中文文案齐全（前端 Badge 直接消费 label）。"""
    high = _by_dim(judge_style(_full(top10=80, top1=90, large=80)))
    assert (high[DIM_CONCENTRATION].label, high[DIM_INDUSTRY].label, high[DIM_SIZE].label) == (
        '持仓高集中',
        '行业集中',
        '偏大盘',
    )
    low = _by_dim(judge_style(_full(top10=30, top1=40, large=20)))
    assert (low[DIM_CONCENTRATION].label, low[DIM_INDUSTRY].label, low[DIM_SIZE].label) == (
        '持仓分散',
        '行业分散',
        '偏中小盘',
    )


# ── 阈值注入 ────────────────────────────────────────────────


def test_custom_thresholds_injected():
    """测试不依赖 DEFAULT 占位：注入极窄阈值即可在任意值上翻档。"""
    th = DEFAULT_THRESHOLDS
    custom = dataclasses.replace(th, concentration=dataclasses.replace(th.concentration, lo=10.0, hi=20.0))
    labels = judge_style(_full(top10=15.0), thresholds=custom)
    assert _by_dim(labels)[DIM_CONCENTRATION].key == 'concentration_mid'
    # 同一值用默认阈值应为 low
    labels_default = judge_style(_full(top10=15.0))
    assert _by_dim(labels_default)[DIM_CONCENTRATION].key == 'concentration_low'


def test_default_thresholds_shape():
    """默认阈值的形状锁定（改数字须同步标定文档，改结构须迁移）。"""
    th = DEFAULT_THRESHOLDS
    assert (th.concentration.lo, th.concentration.hi) == (50.0, 66.0)
    assert (th.industry.lo, th.industry.hi) == (60.0, 81.0)
    assert (th.size.min_coverage, th.size.lo, th.size.hi) == (60.0, 36.5, 67.4)


def test_real_distribution_spots():
    """全库真实极值点抽查（数据快照见标定文档 §2）。"""
    # 集中度 min=0.10（债基）→ 分散；max=85.95 → 高集中
    assert _by_dim(judge_style(_full(top10=0.10)))[DIM_CONCENTRATION].key == 'concentration_low'
    assert _by_dim(judge_style(_full(top10=85.95)))[DIM_CONCENTRATION].key == 'concentration_high'
    # 全库「前十大 = 0.10」与 math 边界一致
    assert math.isfinite(DEFAULT_THRESHOLDS.concentration.lo)
