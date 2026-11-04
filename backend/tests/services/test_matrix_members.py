# -*- coding: utf-8 -*-
"""矩阵成员截断规则（#2686）：两张矩阵共用，规则一旦漂移两张表的行列就对不上。

为什么这组用例值钱：固定「12 只」已被真实库证伪（排除个股后 top12 只覆盖 49.6%
市值）。规则现在改成「累计覆盖 ≥90% / 上限 20 / 下限 8」，三个边界都必须钉住——
改任意一个数字都会让某个组合的矩阵结论从「覆盖整体」退化成「只覆盖大仓位」。
"""

from types import SimpleNamespace

import pytest

from app.services.matrix_members import (
    MATRIX_COVERAGE_TARGET,
    MATRIX_MAX_MEMBERS,
    MATRIX_MIN_MEMBERS,
    select_matrix_members,
)


def _funds(*values: int):
    """按传入顺序（即市值降序，调用方负责排序）构造成员。"""
    return [SimpleNamespace(market_value_cents=value, label=index) for index, value in enumerate(values)]


def test_空成员返回空结果而不是崩():
    assert select_matrix_members([]) == ([], 0, 0.0)


def test_成员不足下限时全展开():
    funds = _funds(100, 100, 100)
    members, truncated, pct = select_matrix_members(funds)
    assert [m.label for m in members] == [0, 1, 2]
    assert truncated == 0
    assert pct == 0.0


def test_集中组合至少展开到下限只数():
    """第 1 只占 95%：覆盖率早就够了，但 1 只看不出结构 ⇒ 取满下限。"""
    values = [9500] + [7] * 29
    funds = _funds(*values)
    members, truncated, pct = select_matrix_members(funds)
    assert len(members) == MATRIX_MIN_MEMBERS
    assert truncated == len(values) - MATRIX_MIN_MEMBERS
    expected = round(sum(values[MATRIX_MIN_MEMBERS:]) / sum(values) * 100, 1)
    assert pct == pytest.approx(expected)


def test_覆盖率在上限内达成时按覆盖率停而不是凑满上限():
    """前 10 只合计 90%：只展开 10 只，不是硬凑 20 只。"""
    values = [9] * 10 + [1] * 10
    members, truncated, pct = select_matrix_members(_funds(*values))
    assert len(members) == 10
    assert truncated == 10
    assert pct == pytest.approx(10.0)


def test_分散组合顶到上限并如实给出未覆盖占比():
    """30 只等权：90% 要 27 只，超过上限 ⇒ 截到 20 只，剩 10 只占 33.3%。"""
    members, truncated, pct = select_matrix_members(_funds(*([100] * 30)))
    assert len(members) == MATRIX_MAX_MEMBERS
    assert truncated == 10
    assert pct == pytest.approx(33.3)


def test_恰好等于下限时不多展开():
    """前 8 只刚好 90%（8×1125 + 20×50 = 10000）：取 8 只，不该再多一只。"""
    values = [1125] * 8 + [50] * 20
    members, truncated, pct = select_matrix_members(_funds(*values))
    assert len(members) == MATRIX_MIN_MEMBERS
    assert truncated == len(values) - MATRIX_MIN_MEMBERS
    assert pct == pytest.approx(10.0)


def test_市值全为0时不崩且不给未覆盖占比():
    """估值缺失的脏数据：覆盖率为空谈，按下限展开，``truncated_market_value_pct`` 记 0。"""
    members, _truncated, pct = select_matrix_members(_funds(*([0] * 12)))
    assert len(members) == MATRIX_MIN_MEMBERS
    assert pct == 0.0


def test_负市值按0处理不污染占比():
    funds = _funds(-500, 100, 100)
    members, _truncated, pct = select_matrix_members(funds)
    assert 0.0 <= pct <= 100.0
    assert len(members) == len(funds)


def test_保持调用方给的市值降序顺序():
    """本函数不重排：排序口径（市值降序 + code 兜底）在调用方，两处各排一次必然漂。"""
    funds = _funds(500, 300, 200)
    members, _truncated, _pct = select_matrix_members(funds)
    assert [m.label for m in members] == [0, 1, 2]


def test_默认参数与README口径一致():
    """三个常量是产品口径的一部分，改动必须同步前端文案与卡面。"""
    assert MATRIX_COVERAGE_TARGET == 0.9
    assert MATRIX_MAX_MEMBERS == 20
    assert MATRIX_MIN_MEMBERS == 8
