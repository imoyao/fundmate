# -*- coding: utf-8 -*-
"""自选提醒判据的纯函数回归（无 DB 夹具）。

重点守「正负号 / 除零 / 边界」这三类容易在重构中翻车的地方。
"""

from datetime import date

import pytest

from app.services.alerts import rules


def test_normalize_type_rejects_unknown():
    assert rules.normalize_alert_type(' change_pct ') == 'CHANGE_PCT'
    with pytest.raises(ValueError):
        rules.normalize_alert_type('PRICE')


@pytest.mark.parametrize(
    ('alert_type', 'value', 'expected'),
    [
        ('PRICE_UP', 1800.456, 1800.456),
        ('CHANGE_PCT', 5, 5.0),
        ('DRAWDOWN', 12.345, 12.35),
    ],
)
def test_validate_threshold_accepts_in_range(alert_type, value, expected):
    assert rules.validate_threshold(alert_type, value) == expected


@pytest.mark.parametrize(
    ('alert_type', 'value'),
    [
        ('PRICE_UP', 0),
        ('PRICE_UP', -10),
        ('CHANGE_PCT', 0.1),
        ('CHANGE_PCT', 51),
        ('DRAWDOWN', 0.5),
        ('DRAWDOWN', 91),
        ('CHANGE_PCT', float('nan')),
    ],
)
def test_validate_threshold_rejects_out_of_range(alert_type, value):
    with pytest.raises(ValueError):
        rules.validate_threshold(alert_type, value)


def test_validate_window_bounds():
    assert rules.validate_window(None) is None
    assert rules.validate_window(60) == 60
    with pytest.raises(ValueError):
        rules.validate_window(1)
    with pytest.raises(ValueError):
        rules.validate_window(300)


def test_price_triggered_equality_counts():
    """等于阈值也算「到价」——用户设的是「到」。"""
    assert rules.price_triggered('PRICE_UP', 100.0, 100.0)
    assert rules.price_triggered('PRICE_DOWN', 100.0, 100.0)
    assert not rules.price_triggered('PRICE_UP', 99.9, 100.0)
    assert not rules.price_triggered('PRICE_DOWN', 100.1, 100.0)


def test_change_pct_guards_division_by_zero():
    assert rules.change_pct(110.0, 100.0) == pytest.approx(10.0)
    assert rules.change_pct(90.0, 100.0) == pytest.approx(-10.0)
    assert rules.change_pct(100.0, None) is None
    assert rules.change_pct(100.0, 0) is None
    assert rules.change_pct(None, 100.0) is None


def test_pct_triggered_reports_drops_only():
    assert rules.pct_triggered(-5.0, 5.0)
    assert rules.pct_triggered(-5.1, 5.0)
    assert not rules.pct_triggered(-4.9, 5.0)
    assert not rules.pct_triggered(5.2, 5.0)  # 涨不报
    assert not rules.pct_triggered(None, 5.0)


def test_drawdown_math_and_guard():
    assert rules.drawdown_pct(80.0, 100.0) == pytest.approx(20.0)
    assert rules.drawdown_pct(100.0, 100.0) == pytest.approx(0.0)
    assert rules.drawdown_pct(100.0, 0) is None
    assert rules.drawdown_pct(None, 100.0) is None
    assert rules.drawdown_triggered(11.0, 10.0)
    assert not rules.drawdown_triggered(9.9, 10.0)


def test_weekly_anchor_is_monday():
    assert rules.weekly_anchor(date(2026, 11, 8)) == date(2026, 11, 2)  # Sunday → 本周一
    assert rules.weekly_anchor(date(2026, 11, 9)) == date(2026, 11, 9)  # Monday → 自己


def test_messages_state_facts_without_advice():
    """文案只陈述事实 + 引用用户自己设的线，不出现方向性建议。"""
    title, body = rules.price_message('贵州茅台', 'PRICE_UP', 1800.0, 1750.0)
    assert '到价提醒' in title and '1750.000' in title
    assert '自动关闭' in body

    title, body = rules.pct_message('贵州茅台', -6.2, 5.0, date(2026, 11, 7))
    assert '单日跌幅' in title and '6.20%' in title
    assert '只提醒一次' in body

    title, body = rules.drawdown_message('贵州茅台', 15.0, 10.0, 60, date(2026, 11, 7))
    assert '回撤提醒' in title and '60' in title
    for text in (title, body):
        assert '建议' not in text
        assert '买入' not in text and '卖出' not in text
