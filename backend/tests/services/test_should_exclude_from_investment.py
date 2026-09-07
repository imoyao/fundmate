# -*- coding: utf-8 -*-
"""should_exclude_from_investment 单一真理源单元测试（#1354 决策 #7）。

覆盖：非类现金永不排除 / cash 永远排除 / 货基默认排除+覆盖 / 逆回购按 maturity_date
动态判定 + override 覆盖 / maturity_date 缺失默认算投资。
"""

from datetime import date

from app.services.fund_utils import should_exclude_from_investment


class _FakePos:
    def __init__(self, asset_type, count_as_investment=None, maturity_date=None, is_money_fund=None):
        self.asset_type = asset_type
        self.count_as_investment = count_as_investment
        self.maturity_date = maturity_date
        self.is_money_fund = is_money_fund


def test_non_cash_like_never_excluded():
    for at in ('stock', 'etf', 'fund', 'bond', 'crypto', None, 'index'):
        assert should_exclude_from_investment(_FakePos(at)) is False


def test_cash_always_excluded():
    assert should_exclude_from_investment(_FakePos('cash')) is True


def test_money_fund_default_excluded_but_override_includes():
    # 默认（未覆盖）→ 排除
    assert should_exclude_from_investment(_FakePos('money_fund')) is True
    # 显式纳入 → 不排除
    assert should_exclude_from_investment(_FakePos('money_fund', count_as_investment=True)) is False
    # 显式排除 → 排除
    assert should_exclude_from_investment(_FakePos('money_fund', count_as_investment=False)) is True
    # is_money_fund 标记（asset_type 非货基但被判定货基）→ 同样适用
    assert should_exclude_from_investment(_FakePos('fund', is_money_fund=True)) is True
    assert should_exclude_from_investment(_FakePos('fund', is_money_fund=True, count_as_investment=True)) is False


def test_reverse_repo_override_takes_precedence():
    assert should_exclude_from_investment(_FakePos('reverse_repo', count_as_investment=True)) is False
    assert should_exclude_from_investment(_FakePos('reverse_repo', count_as_investment=False)) is True


def test_reverse_repo_maturity_dynamic():
    # 未到期 → 算投资（不排）
    assert (
        should_exclude_from_investment(
            _FakePos('reverse_repo', maturity_date=date(2026, 9, 10)), as_of_date=date(2026, 9, 7)
        )
        is False
    )
    # 已到期 → 自动变现金（排除）
    assert (
        should_exclude_from_investment(
            _FakePos('reverse_repo', maturity_date=date(2026, 9, 5)), as_of_date=date(2026, 9, 7)
        )
        is True
    )


def test_reverse_repo_missing_maturity_defaults_included():
    # 决策#7：maturity_date 缺失默认算投资（不排）；导入层应校验必填
    assert should_exclude_from_investment(_FakePos('reverse_repo')) is False


def test_reverse_repo_maturity_day_is_excluded():
    # 到期当日即算现金（排除）：effective = as_of < maturity 为 False（设计 §3.7，
    # 对应旧实现 as_of > maturity 改为 >= 的修复点）。
    assert (
        should_exclude_from_investment(
            _FakePos('reverse_repo', maturity_date=date(2026, 9, 7)), as_of_date=date(2026, 9, 7)
        )
        is True
    )
    # 到期次日仍排除
    assert (
        should_exclude_from_investment(
            _FakePos('reverse_repo', maturity_date=date(2026, 9, 7)), as_of_date=date(2026, 9, 8)
        )
        is True
    )
