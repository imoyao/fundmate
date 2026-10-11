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
        name = getattr(model, '__name__', '')
        if name == 'Fund':
            return fund_q
        if name == 'MoneyFundDailyWorth':
            return money_q
        if name == 'DailyWorth':
            return dw_q
        return MagicMock()

    db.query.side_effect = _query
    return db


def test_build_not_found():
    assert build_fund_performance(_fake_db(None), '999999') is None


def test_build_money_fund():
    # 货基：返回万份收益 + 七日年化，不进净值算法（无回撤口径）
    db = _fake_db(_Fund('货币型'), money_row=_MoneyRow())
    result = build_fund_performance(db, '000001')
    assert result is not None
    assert result['fund_kind'] == 'money'
    assert result['applicable'] is True
    assert result['annual_return_7d'] == 1.5
    assert result['nav_per_10k'] == 0.5
    assert result['source'] == '天天基金'


def test_build_open_fund(monkeypatch):
    # 场外基金：构造 48 个月度净值（含一次回撤），验证结构与同源口径。
    # 序列必须**锚定到 today**（末点落在 today 所在月），否则「近1年」窗口内点数
    # 不足 3 → volatility_1y 恒为 None，测不到真实分支。
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    # 从 today 所在月往前推 48 个月，再反转为「最早在前」
    months = []
    y, m = today.year, today.month
    for _ in range(48):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months.reverse()
    rows = []
    for i, (y, m) in enumerate(months):
        # 增长率本身要波动：若净利严格单调（如恒定 1.005^i），日收益全同 → 方差 0 → 波动率恒为 0，
        # 测不到真实数值分支。这里用 ±1% 交替偏离做确定性噪声（不引入随机源，保证可复现）。
        growth = 1.005 + (0.01 if i % 2 == 0 else -0.01)
        nav = 1.0 * (growth**i)
        if i == 30:
            nav *= 0.8  # 中途 -20% 回撤（落在近 3 年窗口内）
        rows.append(_DailyWorth(date(y, m, 1), round(nav, 6)))
    db = _fake_db(_Fund('股票型'), daily_rows=rows)
    result = build_fund_performance(db, '110020')
    assert result is not None
    assert result['fund_kind'] == 'fund'
    assert result['applicable'] is True
    assert result['basis'] == 'acc_nav'
    assert len(result['intervals']) == 10
    # 4 年历史覆盖所有窗口（近5年 起点晚于首点 → 退化为首点）→ 区间值均非空
    assert all(iv['value'] is not None for iv in result['intervals'])
    # 含回撤 → 最大回撤为负且非 None，口径 fixed_3y
    assert result['max_drawdown'] is not None
    assert result['max_drawdown'] < 0
    assert result['max_drawdown_basis'] == 'fixed_3y'
    # 近 1 年窗口内 ≥3 个月度点 → 波动率可算（月度间距不代表真实年化，仅验证分支可达）
    assert result['volatility_1y'] is not None
    assert result['volatility_1y'] > 0
    assert result['source'] == '天天基金'


def test_build_open_fund_stale_series_no_volatility(monkeypatch):
    """数据陈旧（末点远早于 today）→ 近1年窗口点数不足，波动率降级为 None 而非报错。

    这条守护的是「序列锚点写错」这类测试自身 bug：实现对陈旧数据必须诚实地返回 None。
    """
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    # 末点 2025-12，距 today 10 个月 → 近1年窗口内只有 1 个点
    rows = [_DailyWorth(date(2025, 11, 1), 1.0), _DailyWorth(date(2025, 12, 1), 1.05)]
    result = build_fund_performance(_fake_db(_Fund('股票型'), daily_rows=rows), '110020')
    assert result['applicable'] is True
    assert result['volatility_1y'] is None
    assert result['max_drawdown'] is None
    assert result['max_drawdown_basis'] == 'insufficient'
