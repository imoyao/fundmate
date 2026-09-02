# -*- coding: utf-8 -*-
"""持仓持有时长（holding_days）派生属性单测（issue #862）。

仅验证模型属性计算，不依赖数据库会话：transient 实例直接赋值 confirm_date。
"""

from datetime import date, timedelta

from app.domains.positions.models import Position


def test_holding_days_from_confirm_date():
    p = Position()
    p.confirm_date = date.today() - timedelta(days=10)
    assert p.holding_days == 10


def test_holding_days_none_when_no_confirm_date():
    p = Position()
    p.confirm_date = None
    assert p.holding_days is None


def test_holding_days_zero_for_today():
    p = Position()
    p.confirm_date = date.today()
    assert p.holding_days == 0
