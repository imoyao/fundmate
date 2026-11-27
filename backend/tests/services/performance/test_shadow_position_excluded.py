# -*- coding: utf-8 -*-
"""组合级 XIRR 必须排除 E 账户影子持仓（`ownership_status='shadow'`）。

## 修的 bug（线上表现）

投资复盘「收益概览」的**当前市值**比同页「资金流动」的持仓市值高 22 万，累计收益
更是差一倍（42.5 万 vs 21.0 万）。

根因是两条路径对「什么是持仓」判定不一致：

- 收益日历（`pnl_calendar._positions`）只取 `active`，影子行从来不参与 ⇒ 566,749；
- 组合级 XIRR（`calculate_portfolio_xirr`，`scope=portfolio` 且不传组合 id 走这里）
  只过滤 `quantity > 0` ⇒ 把 93 条 E账户镜像行（`ledger_id` 恒 NULL、零流水、
  `snapshot_quantity` 也空）当成了真实持仓 ⇒ 790,431。

镜像行没有买入流水，它的市值在现金流表里只能以「期末虚拟卖出」出现 ⇒ 不是市值虚高，
是**纯收益虚高**：真库实测 93 行 / 214,911.35 元凭空变成收益。

`services/position_scope.exclude_shadow` 的 docstring 早已点名本场景
（「典型是 XIRR 现金流……镜像行既没有自己的流水、也不该贡献市值」），只是
`calculators` 没接线。

## 覆盖

- 家庭级（不传组合 id）市值 / 净投入 / 累计收益都不含影子行；
- `visible_ids` 子组合路径同样排除（`restrict_visible` 对 `ledger_id IS NULL` 是
  **放行**的，影子行恰好全 NULL ⇒ 这条路径漏得更彻底）；
- `include_cash_equivalents=True` 也不含；
- 反向：同一行只把 `ownership_status` 改成 active，市值立刻多出 600 —— 证明被排掉的
  确实只有影子行，不是「误伤没有账户归属的持仓」。
"""

import datetime as dt

import pytest

from app.domains.ledgers.models import Ledger
from app.services.performance.calculators import calculate_portfolio_xirr

ONE_YEAR_AGO = dt.date.today() - dt.timedelta(days=365)


@pytest.fixture
def seeded(db, make_position, make_transaction):
    """一个账户 + 一条 active 持仓（1000 份 × 1.2 = 1,200，买入 1,000）+ 一条影子行。

    市值用 `asset_type='bond'`（走 `current_price`，不依赖 NAV / 行情表），
    与 `test_portfolio_xirr_units.py` 同一约定。
    """
    ledger = Ledger(name='影子口径账户', ledger_type='fund', family_id=1)
    db.add(ledger)
    db.flush()

    active = make_position(
        symbol='AAA',
        name='真实持仓',
        ledger_id=ledger.id,
        asset_type='bond',
        quantity=1000,
        current_price=1.2,
    )
    make_transaction(
        active.id,
        ledger.id,
        txn_type='buy',
        asset_type='bond',
        amount=1000,
        confirm_date=ONE_YEAR_AGO,
        account_name='影子口径账户',
        symbol='AAA',
    )
    shadow = make_position(
        symbol='BBB',
        name='E账户镜像',
        ledger_id=None,
        account_name=None,
        asset_type='bond',
        quantity=500,
        current_price=1.2,
        ownership_status='shadow',
    )
    return db, ledger, active, shadow


def _xirr(db, **kwargs):
    return calculate_portfolio_xirr(db, family_id=1, **kwargs)


def test_影子持仓不计入当前市值(seeded):
    """500 份 × 1.2 = 600 元的镜像行不能进市值。"""
    db, _ledger, _active, _shadow = seeded
    assert _xirr(db)['current_value'] == pytest.approx(1200.0)


def test_影子持仓不虚增累计收益(seeded):
    """镜像行没有买入流水 ⇒ 它的市值过去被整笔算成收益（1,200 − 1,000 = 200 才是真的）。"""
    db, _ledger, _active, _shadow = seeded
    result = _xirr(db)
    assert result['net_invested'] == pytest.approx(1000.0)
    assert result['total_return'] == pytest.approx(200.0)


def test_可见账户子组合也不含影子行(seeded):
    """`restrict_visible` 对 `ledger_id IS NULL` 是放行的，影子行恰全 NULL ⇒ 必须显式排。"""
    db, ledger, _active, _shadow = seeded
    assert _xirr(db, visible_ids={ledger.id})['current_value'] == pytest.approx(1200.0)
    # 空集只留无主行——影子行仍是价格为零贡献的「持仓」，不能被算成 600 元市值
    assert _xirr(db, visible_ids=set())['current_value'] == pytest.approx(0.0)


def test_含现金等价物口径同样排除影子行(seeded):
    db, _ledger, _active, _shadow = seeded
    assert _xirr(db, include_cash_equivalents=True)['current_value'] == pytest.approx(1200.0)


def test_同一行改成active后市值立刻多出镜像行(seeded):
    """反向验证：被排掉的是 shadow 这个状态本身，不是「没有账户归属」的持仓。"""
    db, _ledger, _active, shadow = seeded
    shadow.ownership_status = 'active'
    db.commit()
    assert _xirr(db)['current_value'] == pytest.approx(1800.0)
