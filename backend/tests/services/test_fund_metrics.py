# -*- coding: utf-8 -*-
"""测试最大回撤计算（#1285 / §3.10）。"""

from datetime import date, timedelta

from app.services.fund_metrics import compute_max_drawdown, load_nav_points

D0 = date(2025, 1, 1)


def _series(values):
    return [(D0 + timedelta(days=i), v) for i, v in enumerate(values)]


def test_drawdown_peak_to_trough():
    # 1.0 → 1.2（峰）→ 0.9（谷）→ 1.1：回撤 = (0.9-1.2)/1.2 = -25%
    r = compute_max_drawdown(_series([1.0, 1.2, 0.9, 1.1]))
    assert r is not None
    assert round(r.max_drawdown, 2) == -25.0
    assert r.peak_date == D0 + timedelta(days=1)
    assert r.trough_date == D0 + timedelta(days=2)
    assert r.sample_size == 4
    assert r.as_of == D0 + timedelta(days=3)


def test_resets_peak_on_new_high():
    # 1.0 → 1.1 → 1.05 → 1.3（新高）→ 1.04：最深回撤应相对 1.3 计（-20%），
    # 而非相对区间首日 1.0（-5.5%）——这是「区间首日为基准」错误写法的关键差异
    r = compute_max_drawdown(_series([1.0, 1.1, 1.05, 1.3, 1.04]))
    assert r is not None
    assert round(r.max_drawdown, 2) == -20.0
    assert r.peak_date == D0 + timedelta(days=3)


def test_monotonic_no_drawdown():
    r = compute_max_drawdown(_series([1.0, 1.1, 1.2]))
    assert r is not None
    assert r.max_drawdown == 0.0


def test_insufficient_points():
    assert compute_max_drawdown([]) is None
    assert compute_max_drawdown(_series([1.0])) is None


def test_invalid_values_skipped():
    r = compute_max_drawdown([(D0, 1.0), (D0 + timedelta(days=1), None), (D0 + timedelta(days=2), 0.8)])
    assert r is not None
    assert round(r.max_drawdown, 2) == -20.0
    assert r.sample_size == 2  # 无效点不计入样本


def test_load_nav_points_prefers_acc_nav():
    class Row:
        def __init__(self, d, unit, acc):
            self.date = d
            self.unit_nav = unit
            self.acc_nav = acc

    rows = [Row(D0, 1.0, 2.0), Row(D0 + timedelta(days=1), 1.1, None)]
    pts = load_nav_points(rows)
    assert pts[0][1] == 2.0  # 优先累计净值
    assert pts[1][1] == 1.1  # 缺失时回退单位净值
