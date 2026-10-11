# -*- coding: utf-8 -*-
"""测试基金业绩与风险（#2029 卡 B · 详情页业绩与风险卡）。

纯函数（区间收益 / 年化波动率）用合成序列做精确断言；`build_fund_performance`
用 mock 的 db Session 验证分支（货基 / 场外 / 不存在），不依赖真实库。
"""
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services.fund_performance import (
    _annualized_volatility,
    _interval_return,
    build_fund_performance,
)

D0 = date(2025, 1, 1)


def _series(values):
    return [(D0 + timedelta(days=i), v) for i, v in enumerate(values)]


def test_interval_return_basic():
    # 起点=首点，终点=末点 → (1.2/1.0 - 1)*100 = 20.0
    assert _interval_return(_series([1.0, 1.1, 1.2]), D0) == 20.0


def test_interval_return_window_clamps_to_first_ge_start():
    pts = _series([1.0, 1.1, 1.2, 1.5])
    # 起点 = D0+2（≥ 该日首点）→ nav_start=1.2，终点=1.5 → 25.0
    assert _interval_return(pts, D0 + timedelta(days=2)) == 25.0


def test_interval_return_too_few():
    assert _interval_return([(D0, 1.0)], D0) is None


def test_annualized_volatility_known():
    # 100 → 110 → 120：日收益 10% / 9.09%，年化 ≈ 10.20%
    pts = [(D0 + timedelta(days=i), v) for i, v in enumerate([100.0, 110.0, 120.0])]
    vol = _annualized_volatility(pts, date(2000, 1, 1))
    assert vol is not None
    assert round(vol, 2) == 10.20


def test_annualized_volatility_insufficient():
    pts = [(D0, 100.0), (D0 + timedelta(days=1), 101.0)]
    assert _annualized_volatility(pts, D0) is None


class _FundType:
    def __init__(self, name):
        self.name = name


class _Fund:
    def __init__(self, name):
        self.fund_type = _FundType(name)


class _DailyWorth:
    def __init__(self, d, acc_nav):
        self.date = d
        self.acc_nav = acc_nav
        self.unit_nav = None


class _MoneyRow:
    def __init__(self):
        self.annual_return_7d = 1.5
        self.nav_per_10k = 0.5
        self.date = date(2026, 10, 9)


def _fake_db(fund, money_row=None, daily_rows=None):
    db = MagicMock()
    fund_q = MagicMock()
    fund_q.filter.return_value.first.return_value = fund
    money_q = MagicMock()
    money_q.filter.return_value.order_by.return_value.first.return_value = money_row
    dw_q = MagicMock()
    dw_q.filter.return_value.order_by.return_value.all.return_value = daily_rows or []

    def _query(model):
        name = getattr(model, "__name__", "")
        if name == "Fund":
            return fund_q
        if name == "MoneyFundDailyWorth":
            return money_q
        if name == "DailyWorth":
            return dw_q
        return MagicMock()

    db.query.side_effect = _query
    return db


def test_build_not_found():
    assert build_fund_performance(_fake_db(None), "999999") is None


def test_build_money_fund():
    # 货基：返回万份收益 + 七日年化，不进净值算法（无回撤口径）
    db = _fake_db(_Fund("货币型"), money_row=_MoneyRow())
    result = build_fund_performance(db, "000001")
    assert result is not None
    assert result["fund_kind"] == "money"
    assert result["applicable"] is True
    assert result["annual_return_7d"] == 1.5
    assert result["nav_per_10k"] == 0.5
    assert result["source"] == "天天基金"


def test_build_open_fund(monkeypatch):
    # 场外基金：构造 4 年月度净值（含一次回撤），验证结构与同源口径
    monkeypatch.setattr(
        "app.services.fund_performance.today_shanghai", lambda: date(2026, 10, 9)
    )
    rows = []
    base = date(2022, 1, 1)
    for i in range(48):
        y = base.year + (base.month - 1 + i) // 12
        m = ((base.month - 1 + i) % 12) + 1
        nav = 1.0 * (1.005 ** i)
        if i == 30:
            nav *= 0.8  # 中途 -20% 回撤
        rows.append(_DailyWorth(date(y, m, 1), round(nav, 6)))
    db = _fake_db(_Fund("股票型"), daily_rows=rows)
    result = build_fund_performance(db, "110020")
    assert result is not None
    assert result["fund_kind"] == "fund"
    assert result["applicable"] is True
    assert result["basis"] == "acc_nav"
    assert len(result["intervals"]) == 10
    # 4 年历史覆盖所有窗口 → 区间值均非空
    assert all(iv["value"] is not None for iv in result["intervals"])
    # 含回撤 → 最大回撤为负且非 None，口径 fixed_3y
    assert result["max_drawdown"] is not None
    assert result["max_drawdown"] < 0
    assert result["max_drawdown_basis"] == "fixed_3y"
    assert result["volatility_1y"] is not None
    assert result["source"] == "天天基金"
