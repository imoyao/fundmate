# -*- coding: utf-8 -*-
"""行为画像编排层集成测试（#2382）——behavior_profiles 端到端。

用 conftest 内存双库：user 域（positions/transactions）+ market 域（funds/daily_worth）。
"""

from datetime import date, datetime, timedelta

import pytest

from app.services.strategy_engine.data_provider import DataProvider
from app.services.strategy_engine.diagnosis import behavior_profiles

D0 = date(2025, 1, 1)


def _mk_fund_type(db, name: str) -> int:
    from app.domains.funds.models import FundType

    ft = FundType(name=name)
    db.add(ft)
    db.flush()
    return ft.id


def _mk_fund(db, code: str, type_id: int) -> None:
    from app.domains.funds.models import Fund

    db.add(Fund(fund_code=code, name=f'基金{code}', fund_type_id=type_id))
    db.flush()


def _mk_worth(db, code: str, day: date, nav: float) -> None:
    from app.domains.funds.models import DailyWorth

    db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav))
    db.flush()


def _seed_holding(db, make_position, make_transaction, symbol: str = '000001', name: str = '华夏成长'):
    pos = make_position(
        symbol=symbol,
        name=name,
        asset_type='fund',
        quantity=1000.0,
        avg_price=1.0,
        account_name='测试账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        symbol=symbol,
        quantity=1000.0,
        price=1.0,
        trade_date=datetime(2025, 1, 1),
        confirm_date=date(2025, 1, 1),
    )
    return pos


def test_behavior_profiles_includes_buy_side_metrics(app, db, make_position, make_transaction):
    """端到端：forward_return 有值；同类不足 20 只时 buy_percentile 诚实 None。"""
    type_id = _mk_fund_type(db, '股票型')
    _mk_fund(db, '000001', type_id)
    for i in range(150):
        _mk_worth(db, '000001', D0 + timedelta(days=i), 1.0 + i * 0.01)
    _seed_holding(db, make_position, make_transaction)

    data = behavior_profiles(DataProvider(db), family_id=1)
    assert data['profiles'], '应有画像'
    profile = data['profiles'][0]

    # 买点质量：day0 买 1.0，h20 净值 1.20 → +20%
    assert profile['forward_return'] is not None
    assert profile['forward_return']['h20']['mean'] == pytest.approx(20.0, abs=0.01)
    assert profile['forward_return']['h20']['sample_count'] == 1

    # 同类仅 1 只 < 20 → 分位 None（诚实降级）
    assert profile['buy_percentile'] is None

    # 账户层：只买不卖 → 实际与持有同解（末值 2.49 → +149%）
    summary = data['summary']
    assert summary['actual_vs_hold'] is not None
    assert summary['actual_vs_hold']['actual_return_pct'] == pytest.approx(149.0, abs=0.5)
    assert summary['actual_vs_hold']['hold_to_end_pct'] == pytest.approx(149.0, abs=0.5)
    assert summary['actual_vs_hold']['diff_pct'] == pytest.approx(0.0, abs=0.5)
    assert summary['avg_buy_percentile'] is None


def test_behavior_profiles_buy_percentile_with_enough_peers(app, db, make_position, make_transaction):
    """同类补足 20 只 → buy_percentile 有值且可复算。

    序列 260 天（自 D0-200 起，买入日 D0 位于序列中段）；回看 365 天窗口含序列
    前段，自身收益可复算。
    """
    type_id = _mk_fund_type(db, '股票型')
    _mk_fund(db, '000001', type_id)
    # 自身净值：D0-200 → D0+59 共 260 点，线性 1.0 → 2.59
    for i in range(260):
        _mk_worth(db, '000001', D0 - timedelta(days=200) + timedelta(days=i), 1.0 + i * (1.59 / 259))
    # 同类 19 只：买入日 D0 的回看窗口内收益 0% ~ +18%（全部低于自身）
    for n in range(2, 21):
        code = f'{n:06d}'
        _mk_fund(db, code, type_id)
        _mk_worth(db, code, D0 - timedelta(days=100), 1.0)
        _mk_worth(db, code, D0, 1.0 + (n - 2) * 0.01)
    _seed_holding(db, make_position, make_transaction)

    data = behavior_profiles(DataProvider(db), family_id=1)
    profile = data['profiles'][0]
    assert profile['buy_percentile'] is not None
    # 自身窗口收益（D0-200 的 1.0 → D0 的 ≈2.227）远高于全部 19 个同类（≤18%）
    # → 分位 = (19 严格小于 + 0.5 自身) / 20 = 97.5
    assert profile['buy_percentile'] == pytest.approx(97.5, abs=0.1)
    assert data['summary']['avg_buy_percentile'] == pytest.approx(97.5, abs=0.1)


def test_behavior_profiles_sell_side_flow(app, db, make_position, make_transaction):
    """买入后卖出：账户层 diff 为负（卖了后继续涨，实际操作跑输拿着）。"""
    type_id = _mk_fund_type(db, '混合型')
    _mk_fund(db, '000001', type_id)
    for i in range(150):
        _mk_worth(db, '000001', D0 + timedelta(days=i), 1.0 + i * 0.01)
    pos = _seed_holding(db, make_position, make_transaction)
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='sell',
        symbol='000001',
        quantity=1000.0,
        price=1.20,
        trade_date=datetime(2025, 1, 21),
        confirm_date=date(2025, 1, 21),
    )

    data = behavior_profiles(DataProvider(db), family_id=1)
    avh = data['summary']['actual_vs_hold']
    assert avh is not None
    # 实际：回款 1200 − 成本 1000 → +20%
    assert avh['actual_return_pct'] == pytest.approx(20.0, abs=0.5)
    # 拿着：期末 2.49×1000 → +149%
    assert avh['hold_to_end_pct'] == pytest.approx(149.0, abs=0.5)
    assert avh['diff_pct'] == pytest.approx(-129.0, abs=0.6)
    # 卖出侧原字段不受影响
    profile = data['profiles'][0]
    assert profile['profitable_sell_ratio'] == pytest.approx(100.0)
    assert profile['evidence']['closed_pairs'] == 1


def test_behavior_profiles_empty_family_returns_degraded(app, db):
    """无持仓家庭：空画像 + summary 全降级字段（含 actual_vs_hold=None）。"""
    data = behavior_profiles(DataProvider(db), family_id=999)
    assert data['profiles'] == []
    assert data['summary']['actual_vs_hold'] is None
    assert data['summary']['symbol_count'] == 0


def test_behavior_profiles_nav_window_covers_earliest_buy(app, db, make_position, make_transaction):
    """#2637 端到端回归：净值窗口必须回溯到最早买入日之前，否则 h 日定位整体错位。

    布点：400 个净值日（D0-300 → D0+99），买入在 D0-250（序列下标 50，净值 1.05）。
    只看「近 260 条」只能覆盖 D0-160 之后，买入日早于窗口起点 —— 修复前该笔会被
    错位索引成「窗口第 20 个点」，产出一个不报错的错值。
    """
    type_id = _mk_fund_type(db, '股票型')
    _mk_fund(db, '000001', type_id)
    start = D0 - timedelta(days=300)
    for i in range(400):
        _mk_worth(db, '000001', start + timedelta(days=i), 1.0 + i * 0.001)
    buy_day = start + timedelta(days=50)
    pos = make_position(
        symbol='000001',
        name='华夏成长',
        asset_type='fund',
        quantity=1000.0,
        avg_price=1.0,
        account_name='测试账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        symbol='000001',
        quantity=1000.0,
        price=1.05,
        trade_date=datetime.combine(buy_day, datetime.min.time()),
        confirm_date=buy_day,
    )

    data = behavior_profiles(DataProvider(db), family_id=1)
    profile = data['profiles'][0]
    forward = profile['forward_return']
    assert forward is not None
    # 买入后第 20 个净值日 = 下标 70 → 1.07；(1.07-1.05)/1.05 = +1.90%
    assert forward['h20']['mean'] == pytest.approx((1.07 - 1.05) / 1.05 * 100, abs=0.01)
    # 第 120 个净值日 = 下标 170 → 1.17 → +11.43%
    assert forward['h120']['mean'] == pytest.approx((1.17 - 1.05) / 1.05 * 100, abs=0.01)
    assert forward['h20']['missing_count'] == 0
    assert profile['evidence']['forward_uncovered_buys'] == 0
    assert profile['evidence']['first_nav_date'] == start.isoformat()
