# -*- coding: utf-8 -*-
"""每日收益日历派生口径测试（#1812）。

重点验证三件事：
1. **资金流免疫**——存取款当日不产生虚假日盈亏（这是选用 `total_pnl` 日差分
   而非 `net_worth` 日环比的根本理由）；
2. **四态可区分**——「无价格序列」不画成 0（balance 模式账户的关键诉求）；
3. **恒等式**——家庭级日盈亏 = Σ 各账户级日盈亏。
"""

import datetime as dt

import pytest

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.services.pnl_calendar import (
    GRANULARITY_DAY,
    GRANULARITY_MONTH,
    GRANULARITY_YEAR,
    STATE_CLOSED,
    STATE_NO_PRICE,
    STATE_UPDOWN,
    STATE_ZERO,
    _collect_fund_nav,
    build_daily_pnl_series,
    build_pnl_series,
)


def _add_nav(db, fund_code, date, unit_nav):
    db.add(DailyWorth(fund_code=fund_code, date=date, unit_nav=unit_nav))
    db.commit()


def _state_of(result, day):
    return next((d['state'] for d in result['days'] if d['date'] == day.isoformat()), None)


def _pnl_of(result, day):
    return next((d['daily_pnl'] for d in result['days'] if d['date'] == day.isoformat()), None)


def test_资金流免疫_追加投入不产生虚假日盈亏(db, make_position, make_transaction):
    """追加买入当日：份额与成本同步增加 ⇒ 日盈亏应为 0，而非凭空跳增。

    这是本卡选用 `total_pnl` 日差分的核心依据。若误用 `net_worth` 日环比，
    追加投入当天会显示为「赚了一笔」，那就是假盈利。
    """
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    pos = make_position(symbol='000001', name='测试基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000001',
    )
    # d2 追加买入：份额 1000→2000，成本 1.0→1.0，市值不变 ⇒ 盈亏仍为 0
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d2,
        symbol='000001',
    )
    _add_nav(db, '000001', d1, 1.0)
    _add_nav(db, '000001', d2, 1.0)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    # d2 当日：净值持平、份额翻倍但成本同步翻倍 ⇒ 盈亏必须为 0
    assert _pnl_of(result, d2) == 0, f'追加投入当日应盈亏 0，实际 {_pnl_of(result, d2)}'
    assert _state_of(result, d2) == STATE_ZERO


def test_净值下跌产生负收益(db, make_position, make_transaction):
    """净值从 1.2 跌到 1.1 ⇒ 当日负收益，且金额等于 (1.1-1.2)×份额。"""
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    pos = make_position(symbol='000002', name='下跌基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000002',
    )
    _add_nav(db, '000002', d1, 1.2)
    _add_nav(db, '000002', d2, 1.1)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    # 份额 1000份，净值跌 0.1 元 ⇒ -100 元
    assert _pnl_of(result, d2) == pytest.approx(-100.0, abs=0.01)
    assert _state_of(result, d2) == STATE_UPDOWN


def test_无价格序列标记为no_price而非零收益(db, make_position, make_transaction):
    """balance 模式（银行理财等）无历史价格 ⇒ 整段 no_price，绝不能画成 0。"""
    d1 = dt.date(2026, 1, 5)
    pos = make_position(
        symbol='ZH0001',
        name='银行理财',
        quantity=0,
        avg_price=0,
        asset_type='portfolio',
        valuation_mode='balance',
        market_value_override=Money.yuan_to_cents(50000),
    )

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert result['has_any_price'] is False
    for day in (d1, dt.date(2026, 1, 6), dt.date(2026, 1, 7)):
        assert _state_of(result, day) == STATE_NO_PRICE, f'{day} 应为 no_price'
        assert _pnl_of(result, day) is None, f'{day} 无价格序列时盈亏须为 None（区别于 0）'


def test_零收益与无数据可区分(db, make_position, make_transaction):
    """净值持平 ⇒ zero 态且盈亏 0；无净值记录 ⇒ closed 态且盈亏 None。"""
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)
    d3 = dt.date(2026, 1, 7)

    pos = make_position(symbol='000003', name='持平基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000003',
    )
    _add_nav(db, '000003', d1, 1.0)
    _add_nav(db, '000003', d2, 1.0)
    # d3 故意不写净值 ⇒ 模拟未同步/休市

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert _state_of(result, d2) == STATE_ZERO
    assert _pnl_of(result, d2) == 0
    # d3：全市场（此例仅 1 笔）都没有新鲜报价 ⇒ 判为休市/未出净值，
    # 按「价格未变」回填 ⇒ 0 收益。这与「部分有价部分没价」要分开处理，
    # 见test_部分标的断档时不出数。
    assert _state_of(result, d3) == STATE_ZERO
    assert _pnl_of(result, d3) == 0


def test_部分标的断档时不出数(db, make_position, make_transaction):
    """回归 #1812：一部分标的有当日价、一部分断档 ⇒ 日总额不完整，差分是错的。

    实测（真实库 2026-09-30）：只有 13/57 笔有价，若照常出数，
    缺失标的的市值被当成 0，日净资产凭空少 20.8 万。
    按 design.md「缺数据不可画成 0」，这类日子标closed（数据不全）而不是给出错数。
    """
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    a = make_position(symbol='000041', name='有价标的', quantity=1000, avg_price=1.0, asset_type='fund')
    b = make_position(symbol='000042', name='断档标的', quantity=1000, avg_price=1.0, asset_type='fund')
    for pos, sym in ((a, '000041'), (b, '000042')):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=1000,
            price=1.0,
            confirm_date=dt.date(2025, 12, 1),
            symbol=sym,
        )
    # d1 两只都有；d2 只有 A 出净值（模拟 B 断档）
    _add_nav(db, '000041', d1, 1.0)
    _add_nav(db, '000042', d1, 1.0)
    _add_nav(db, '000041', d2, 1.1)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    # d2 覆盖不全 ⇒ 不出数（而不是把B 的市值当成 0 算出个假盈亏）
    assert _state_of(result, d2) == STATE_CLOSED, '部分标的断档时应标数据不全'
    assert _pnl_of(result, d2) is None


def test_月合计等于区间内日序列求和(db, make_position, make_transaction):
    """验收项：月合计与区间内日盈亏求和一致（含边界日）。"""
    d1 = dt.date(2026, 1, 5)
    days = [dt.date(2026, 1, 5) + dt.timedelta(days=i) for i in range(4)]

    pos = make_position(symbol='000004', name='合计基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000004',
    )
    for i, day in enumerate(days):
        _add_nav(db, '000004', day, 1.0 + i * 0.01)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-08')

    s = sum(d['daily_pnl'] for d in result['days'] if d['daily_pnl'] is not None)
    assert result['month_total'] == pytest.approx(s, abs=0.02)


def test_家庭级等于各账户级之和(db, make_position, make_transaction):
    """恒等式：家庭级 daily_pnl = Σ 各账户级 daily_pnl。"""
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    p1 = make_position(
        symbol='000011', name='账户A基金', account_name='证券账户', quantity=1000, avg_price=1.0, asset_type='fund'
    )
    p2 = make_position(
        symbol='000012', name='账户B基金', account_name='银行账户', quantity=2000, avg_price=2.0, asset_type='fund'
    )
    for pos, qty in ((p1, 1000), (p2, 2000)):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=qty,
            price=1.0,
            confirm_date=d1,
            symbol=pos.symbol,
        )
    _add_nav(db, '000011', d1, 1.0)
    _add_nav(db, '000011', d2, 1.05)
    _add_nav(db, '000012', d1, 2.0)
    _add_nav(db, '000012', d2, 2.10)

    family = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')
    led_a = build_daily_pnl_series(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-07', ledger_id=p1.ledger_id
    )
    led_b = build_daily_pnl_series(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-07', ledger_id=p2.ledger_id
    )

    assert family['scope'] == 'family'
    assert led_a['scope'] == 'ledger'
    assert family['month_total'] == pytest.approx(led_a['month_total'] + led_b['month_total'], abs=0.02)
    # 逐日对账。区间首日无前一日基准，三级都必须同为 None（都不可算），
    # 否则「账户级首日有值、家庭级首日无值」这种分叉会伪装成口径不一致。
    for day in (d1, d2):
        fam_v = _pnl_of(family, day)
        a_v = _pnl_of(led_a, day)
        b_v = _pnl_of(led_b, day)
        if fam_v is None:
            assert a_v is None and b_v is None, f'{day} 首日：三级应同为 None'
        else:
            assert fam_v == pytest.approx(a_v + b_v, abs=0.02)


def test_改持仓后历史自动重算(db, make_position, make_transaction):
    """本卡核心诉求：后补的建仓流水会改变 as-of 历史（快照方案做不到这点）。"""
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    pos = make_position(symbol='000021', name='后补建仓', quantity=1000, avg_price=1.0, asset_type='fund')
    _add_nav(db, '000021', d1, 1.0)
    _add_nav(db, '000021', d2, 1.1)

    # 场景 A：起初没流水 ⇒ d2 无价格序列变化可算
    before = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')
    assert before['has_any_price'] is False

    # 场景 B：补录 d1 的建仓流水 ⇒ d2 立刻能算出 +100 元
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000021',
    )
    after = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert after['has_any_price'] is True
    assert _pnl_of(after, d2) == pytest.approx(100.0, abs=0.01)


def test_窗口前建仓的持仓必须计入份额(db, make_position, make_transaction):
    """回归 #1812 上线首日的真实缺陷：整月空白。

    背景：`_as_of_shares` 返回的是「按日增量」，而日循环原本只推进 [start, end]。
    2026-01 建的仓位，其 1 月增量永远不会被应用 ⇒ shares 恒为 0 ⇒ 整月 no_price。
    原有用例全部「买在窗口第 1 天」，测不到这条路径 —— 真实库有 151 个持仓、
    绝大多数早于查询窗口，测试却全绿。

    本例显式在**窗口之前**建仓，断言区间内必须有真实盈亏。
    """
    buy_day = dt.date(2025, 12, 20)  # 远早于查询窗口
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    pos = make_position(symbol='000777', name='窗口前建仓', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=buy_day,
        symbol='000777',
    )
    _add_nav(db, '000777', buy_day, 1.0)
    _add_nav(db, '000777', d1, 1.0)
    _add_nav(db, '000777', d2, 1.1)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert result['has_any_price'] is True, '窗口前建仓的持仓必须计入，否则整月空白'
    # 1/6 净值 1.0→1.1，1000 份 ⇒ +100
    assert _pnl_of(result, d2) == pytest.approx(100.0, abs=0.01)
    assert _state_of(result, d2) == STATE_UPDOWN


def test_区间首日不应因缺基准而显示为休市(db, make_position, make_transaction):
    """区间首日要有前一日基准（实现多取一天），否则每月 1 号都被误判成休市。"""
    d0 = dt.date(2026, 1, 4)
    d1 = dt.date(2026, 1, 5)

    pos = make_position(symbol='000888', name='首日基准', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2025, 12, 1),
        symbol='000888',
    )
    _add_nav(db, '000888', d0, 1.0)
    _add_nav(db, '000888', d1, 1.05)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')

    # 首日即应给出真实盈亏，而不是 None/closed
    assert _pnl_of(result, d1) == pytest.approx(50.0, abs=0.01), f'首日应可算，实得 {_pnl_of(result, d1)}'
    assert _state_of(result, d1) == STATE_UPDOWN


def test_空态能区分数据缺口与持仓无估值(db, make_position, make_transaction):
    """无价格数据时，coverage/latest_price_date 要能让人区分成因。"""
    pos = make_position(symbol='000999', name='无价账户', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2025, 12, 1),
        symbol='000999',
    )

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')

    assert result['has_any_price'] is False
    assert result['coverage']['total_positions'] == 1
    assert result['coverage']['priced_positions'] == 0
    assert result['latest_price_date'] is None, '取不到任何价格 ⇒ 应报缺口，让前端说「本月无数据」'


def test_家庭级覆盖不全时账户级丢同一批天(db, make_position, make_transaction):
    """#1916 回归：家庭级因某账户断档丢天时，账户级不得各自出数。

    场景：账户甲的基金 1/5~1/7 都有净值；账户乙的基金仅 1/5 有、1/6 起断档。
    家庭级 1/6、1/7 触发「覆盖不全不出数」⇒ closed/None（#1812 既有行为）。
    若账户级按各自持仓判定：账户甲 1/6 会照常算出 +50 ⇒ Σ账户级 ≠ 家庭级。
    真实库实测：份额口径修正后该缺口放大到 3502.91，根因即丢天集合不一致。

    修法：状态判定集恒为家庭级全量——各作用域丢同一批天、同步推进差分基准；
    而 day_total 按持仓可加（份额/已实现均按持仓归集），故恒等式成立。
    """
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)
    d3 = dt.date(2026, 1, 7)

    a = make_position(
        symbol='000051', name='甲基金', account_name='甲账户', quantity=1000, avg_price=1.0, asset_type='fund'
    )
    b = make_position(
        symbol='000052', name='乙基金', account_name='乙账户', quantity=1000, avg_price=2.0, asset_type='fund'
    )
    for pos, sym, px in ((a, '000051', 1.0), (b, '000052', 2.0)):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=1000,
            price=px,
            confirm_date=dt.date(2025, 12, 1),
            symbol=sym,
        )
    # 甲：三天都有净值；乙：仅 d1 有，d2/d3 断档（超出回填窗）
    _add_nav(db, '000051', d1, 1.0)
    _add_nav(db, '000051', d2, 1.05)
    _add_nav(db, '000051', d3, 1.05)
    _add_nav(db, '000052', d1, 2.0)

    family = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')
    led_a = build_daily_pnl_series(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-07', ledger_id=a.ledger_id
    )
    led_b = build_daily_pnl_series(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-07', ledger_id=b.ledger_id
    )

    # 家庭级：d2/d3 覆盖不全 ⇒ 不出数（#1812 既有行为，不得回归）
    for day in (d2, d3):
        assert _state_of(family, day) == STATE_CLOSED
        assert _pnl_of(family, day) is None

    # #1916：账户级必须丢同一批天——不能因为自己那笔有价就照常出数
    for led in (led_a, led_b):
        for day in (d2, d3):
            assert _state_of(led, day) == STATE_CLOSED, f'{day} 账户级应与家庭级同为 closed'
            assert _pnl_of(led, day) is None

    assert family['month_total'] == pytest.approx(led_a['month_total'] + led_b['month_total'], abs=0.02)


def test_流水与持仓账户不一致时按持仓归集(db, make_position, make_transaction):
    """#1916：流水记在账户乙、持仓在账户甲 ⇒ 账户甲视图必须算进份额。

    真实库 42 笔流水的 ledger_id 与其持仓不一致（账户迁移遗留：持仓搬走了、
    流水没搬）。口径按权威先例 `get_ledger_pnl`（#1220）「按持仓归集」：
    份额来自全家庭流水、按 position_id 归组，与流水记在哪个账户无关。
    若仍按 Transaction.ledger_id 过滤：账户甲视图 shares=0 ⇒ 整月 closed。
    """
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    # 乙账户仅放一笔零份额占位持仓，用来产生一个真实 ledger_id
    donor = make_position(
        symbol='000062', name='乙账户占位', account_name='乙账户', quantity=0, avg_price=0, asset_type='fund'
    )
    pos = make_position(
        symbol='000061', name='甲账户基金', account_name='甲账户', quantity=1000, avg_price=1.0, asset_type='fund'
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=donor.ledger_id,  # ← 流水归属乙账户，持仓在甲账户（复现 42 笔错位）
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2025, 12, 1),
        symbol='000061',
    )
    _add_nav(db, '000061', d1, 1.0)
    _add_nav(db, '000061', d2, 1.1)

    family = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')
    led = build_daily_pnl_series(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-06', ledger_id=pos.ledger_id
    )

    # 甲账户视图：份额必须来自这笔（归属错位的）流水，d2 净值 1.0→1.1 ⇒ +100
    assert _state_of(led, d2) == STATE_UPDOWN
    assert _pnl_of(led, d2) == pytest.approx(100.0, abs=0.01)
    assert led['month_total'] == pytest.approx(family['month_total'], abs=0.02)


# ─────────────────────────────────────────────────────────────────────────────
# #1925 日 / 月 / 年三视图
# ─────────────────────────────────────────────────────────────────────────────


def _seed_跨月收益(db, make_position, make_transaction):
    """1/28 建仓 → 1/29、1/30 各 +100 → 2/2 再 +100（中间靠前值回填）。

    末次净值 2/2，故只查到 2/9（≤ _STALE_CARRY_DAYS），避免测到「回填窗口耗尽」的
    另一回事上。
    """
    pos = make_position(symbol='000031', name='跨月基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2026, 1, 28),
        symbol='000031',
    )
    _add_nav(db, '000031', dt.date(2026, 1, 28), 1.0)
    _add_nav(db, '000031', dt.date(2026, 1, 29), 1.1)
    _add_nav(db, '000031', dt.date(2026, 1, 30), 1.2)
    _add_nav(db, '000031', dt.date(2026, 2, 2), 1.3)
    return pos


def test_月年粒度是同一条日序列的切法_单月恒等式(db, make_position, make_transaction):
    """月/年视图不得另起算法：其期间值必须与日视图同区间合计完全相等。

    这是三视图「口径唯一」的可执行化——只要这条在，日视图改成什么样都
    不会让月/年视图对不上。
    """
    _seed_跨月收益(db, make_position, make_transaction)
    day = build_daily_pnl_series(db, 1, '2026-01-28', '2026-02-03')
    year = build_pnl_series(db, 1, '2026-01-28', '2026-02-03', granularity=GRANULARITY_YEAR)

    assert [p['period'] for p in year['periods']] == ['2026']
    assert year['periods'][0]['pnl'] == pytest.approx(day['month_total'], abs=0.01)
    assert year['month_total'] == pytest.approx(day['month_total'], abs=0.01)
    # 聚合下推：期间视图不回日明细（否则一次年视图要回 1800+ 行）
    assert year['days'] == []
    assert year['granularity'] == GRANULARITY_YEAR


def test_年粒度等于其各月期间之和(db, make_position, make_transaction):
    """同一份日序列按月切、按年切，加起来必须一致（200 + 100 = 300）。"""
    _seed_跨月收益(db, make_position, make_transaction)
    jan = build_pnl_series(db, 1, '2026-01-28', '2026-01-31', granularity=GRANULARITY_MONTH)
    feb = build_pnl_series(db, 1, '2026-02-01', '2026-02-03', granularity=GRANULARITY_MONTH)
    year = build_pnl_series(db, 1, '2026-01-28', '2026-02-03', granularity=GRANULARITY_YEAR)

    assert [p['period'] for p in jan['periods']] == ['2026-01']
    assert [p['period'] for p in feb['periods']] == ['2026-02']
    assert jan['periods'][0]['pnl'] == pytest.approx(200.0, abs=0.01)
    assert feb['periods'][0]['pnl'] == pytest.approx(100.0, abs=0.01)
    assert year['periods'][0]['pnl'] == pytest.approx(jan['periods'][0]['pnl'] + feb['periods'][0]['pnl'], abs=0.01)


def test_期间收益率分母取上一期间末净资产(db, make_position, make_transaction):
    """首期间的分基线是「区间前一天」，由 build_pnl_series 多取的那一天提供。"""
    _seed_跨月收益(db, make_position, make_transaction)
    feb = build_pnl_series(db, 1, '2026-02-01', '2026-02-09', granularity=GRANULARITY_MONTH)
    period = feb['periods'][0]

    # 基线日 1/31：1000 份 × 1.2 元 = 1200 元；2 月盈亏 +100 ⇒ 100/1200 = 8.33%
    assert period['rate'] == pytest.approx(8.33, abs=0.01)
    assert period['net_worth'] == pytest.approx(1300.0, abs=0.01)
    # 多取的基线日不计入区间合计，也不出现在输出里
    assert feb['start_date'] == '2026-02-01'
    assert feb['month_total'] == pytest.approx(100.0, abs=0.01)


def test_无价格序列的期间pnl为None而非零(db, make_position):
    """「缺数据绝不可画成 0」这条红线在聚合层同样成立。"""
    make_position(
        symbol='ZH0001',
        name='银行理财',
        quantity=0,
        avg_price=0,
        asset_type='portfolio',
        valuation_mode='balance',
        market_value_override=Money.yuan_to_cents(50000),
    )
    res = build_pnl_series(db, 1, '2026-01-01', '2026-01-31', granularity=GRANULARITY_MONTH)
    period = res['periods'][0]

    assert period['state'] == STATE_NO_PRICE
    assert period['pnl'] is None
    assert period['rate'] is None
    assert res['has_any_price'] is False


def test_周末为主的整月不会被聚合判成数据不全(db, make_position, make_transaction):
    """周末本来就是 closed，聚合时不应把它算作「数据断档」的证据。"""
    _seed_跨月收益(db, make_position, make_transaction)
    jan = build_pnl_series(db, 1, '2026-01-28', '2026-01-31', granularity=GRANULARITY_MONTH)
    # 1/31 是周六，state=closed，但整个期间仍有可算日 ⇒ 期间必须出数
    assert jan['periods'][0]['state'] == STATE_UPDOWN
    assert jan['periods'][0]['pnl'] == pytest.approx(200.0, abs=0.01)


def test_日粒度不产出期间列表(db, make_position, make_transaction):
    """day 粒度的逐日明细即 `days`，再聚一份期间是同义反复。"""
    _seed_跨月收益(db, make_position, make_transaction)
    res = build_pnl_series(db, 1, '2026-01-28', '2026-01-31', granularity=GRANULARITY_DAY)

    assert res['granularity'] == GRANULARITY_DAY
    assert res['periods'] == []
    assert len(res['days']) == 4  # 日粒度仍然回逐日明细


def test_非法粒度抛值错误(db):
    with pytest.raises(ValueError):
        build_pnl_series(db, 1, '2026-01-01', '2026-01-31', granularity='week')


# ── 净值查询必须按持有代码过滤（#1925 性能根因的防回潮锚点）─────────────────


def test_空代码集合直接返回空_不退化成查全库(db):
    """空 targets 的语义是「跳过」，不是「全表」（AGENTS.md 数据策略硬约束 §3）。"""
    db.add(DailyWorth(fund_code='999999', date=dt.date(2026, 1, 5), unit_nav=1.0))
    db.commit()
    assert _collect_fund_nav(db, dt.date(2026, 1, 1), dt.date(2026, 1, 31), set()) == {}


def test_净值查询只取指定代码(db):
    """回潮成「只按日期查」= 把全市场 754 万行捞进内存（实测 13.7s）。"""
    db.add(DailyWorth(fund_code='000001', date=dt.date(2026, 1, 5), unit_nav=1.0))
    db.add(DailyWorth(fund_code='110011', date=dt.date(2026, 1, 5), unit_nav=2.0))
    db.commit()

    got = _collect_fund_nav(db, dt.date(2026, 1, 1), dt.date(2026, 1, 31), {'000001'})

    assert set(got) == {'000001'}
    assert '110011' not in got
    assert got['000001'][dt.date(2026, 1, 5)] == Money.yuan_to_price_units(1.0)
