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
    STATE_NO_DATA,
    STATE_NO_POSITION,
    STATE_NO_PRICE,
    STATE_PARTIAL,
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
    """净值持平 ⇒ zero 态且盈亏 0；**开盘日却一条新鲜报价都没有** ⇒ no_data 且盈亏 None。

    #1942 细化：#1917 的 C 方案把这种「全体都没出真报价」的日子按前值回填后
    照常出 0.00。但 0.00 是一句关于收益的断言，而当天的事实是**根本没取到估值**
    ——2026-01-07 是周三（开盘日），把「净值没同步」说成「今天没赚没亏」，
    与把「没同步」说成「休市」是同一类错。故按开盘日历分派：
    开盘日 → `no_data`（用户可去跑同步）/ 非开盘日 → `closed`（只能等开盘）。
    差分恰为 0，不出数不会丢钱；基准仍无条件推进（#1917 的 A 方案不变）。
    """
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
    # d3 故意不写净值 ⇒ 模拟未同步

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert _state_of(result, d2) == STATE_ZERO
    assert _pnl_of(result, d2) == 0
    # d3（周三，A 股开盘日）没有任何新鲜报价 ⇒ 是「没同步」，不是「0 收益」，
    # 更不是「休市」。这与「部分有价部分没价」（partial，见
    # test_部分标的断档时标partial且仍出数）分开处理。
    assert _state_of(result, d3) == STATE_NO_DATA
    assert _pnl_of(result, d3) is None


def test_部分标的断档时标partial且仍出数(db, make_position, make_transaction):
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
    # #1917 的 C 方案：断档日**照常给出数值**，另标 `partial` 告知数据不完整。
    assert _state_of(result, d2) == STATE_PARTIAL, '部分标的断档应标 partial'
    assert _pnl_of(result, d2) == pytest.approx(100.0, abs=0.01)


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


def test_家庭级部分断档时账户级判定天一致(db, make_position, make_transaction):
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

    # #1917 的 A+C：基准无条件推进 ⇒ 断档日**照常出数**（标 partial），不再「丢天」。
    for day in (d2, d3):
        assert _state_of(family, day) == STATE_PARTIAL, f'{day} 应标 partial'
        assert _pnl_of(family, day) is not None, f'{day} 应给出数值'

    # #1916 核心保证不受影响：账户级与家庭级用同一批判定天（decision_positions），
    # 逐日可加 ⇒ 月合计精确相等。
    for day in (d2, d3):
        for led in (led_a, led_b):
            assert _state_of(led, day) == STATE_PARTIAL, f'{day} 账户级判定天须一致'

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
# #1942：休市必须来自交易日历，不能拿「当天取不到价格」当判据
# ─────────────────────────────────────────────────────────────────────────────


def test_非开盘日报道休市_开盘日缺数据报未同步(db, make_position, make_transaction):
    """#1942 核心回归：2026-01-10/11 是周末（休市），01-13 是周二（没同步）。

    旧实现把「当天取不到价」当成休市判据，于是这两天都报同一个「非交易日」态、
    UI 一律显示「休市」。用户的直接观感是「9 月一半都是休市，与实际不符」——
    市场没关门，是每日净值没同步。两者处置方式相反：一个等开盘，一个要去跑同步。
    """
    from app.core.trading_calendar import is_trading_day

    thu = dt.date(2026, 1, 8)
    fri = dt.date(2026, 1, 9)
    sat = dt.date(2026, 1, 10)
    sun = dt.date(2026, 1, 11)
    mon = dt.date(2026, 1, 12)
    tue = dt.date(2026, 1, 13)

    # 前提钉：这三个日期的开闭状态由交易日历给定（本用例的判据基准）
    assert is_trading_day(sat) is False and is_trading_day(sun) is False
    assert is_trading_day(tue) is True, '2026-01-13 是周二，A 股开盘'

    pos = make_position(symbol='000071', name='交易日历基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2025, 12, 1),
        symbol='000071',
    )
    _add_nav(db, '000071', thu, 1.0)
    _add_nav(db, '000071', fri, 1.0)
    _add_nav(db, '000071', mon, 1.05)
    # tue 故意不写净值：开盘日但没同步

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-09', end_date='2026-01-13')

    assert _state_of(result, fri) == STATE_ZERO, '有真净值且持平 ⇒ 真实零收益'
    assert _pnl_of(result, fri) == 0

    for day in (sat, sun):
        assert _state_of(result, day) == STATE_CLOSED, f'{day} 是周末 ⇒ 休市'
        assert _pnl_of(result, day) is None

    assert _state_of(result, mon) == STATE_UPDOWN
    assert _pnl_of(result, mon) == pytest.approx(50.0, abs=0.01)

    assert _state_of(result, tue) == STATE_NO_DATA, '开盘日一条估值都没有 ⇒ 未同步，不是休市'
    assert _pnl_of(result, tue) is None


def test_建仓前的日子报无持仓而不是休市(db, make_position, make_transaction):
    """没有持仓 ≠ 休市，也 ≠ 没数据（#1942）。建仓前的一整段应能自证原因。"""
    buy = dt.date(2026, 1, 8)

    pos = make_position(symbol='000072', name='尚未建仓', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=buy,
        symbol='000072',
    )
    _add_nav(db, '000072', buy, 1.0)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-06', end_date='2026-01-08')

    for day in (dt.date(2026, 1, 6), dt.date(2026, 1, 7)):
        assert _state_of(result, day) == STATE_NO_POSITION, f'{day} 尚无仓位 ⇒ 报无持仓'
        assert _pnl_of(result, day) is None


def test_回报投资以来起点_供年视图取全区间(db, make_position, make_transaction):
    """#1942：年视图要「投资以来每一年占一格」，起点必须来自数据而不是固定年数窗口。

    起点 = 最早一笔**改变份额**的流水生效日（买 / 卖 / 转入 / 转出）；
    无持仓（空态）时为 None，前端据此回落到「今年」。
    """
    buy = dt.date(2024, 3, 15)
    pos = make_position(symbol='000073', name='投资以来', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=buy,
        symbol='000073',
    )
    _add_nav(db, '000073', dt.date(2026, 1, 5), 1.0)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')

    assert result['first_txn_date'] == buy.isoformat()

    # 空态（该家庭没有任何持仓）同样要给字段，保持响应形状一致
    empty = build_daily_pnl_series(db, family_id=99, start_date='2026-01-05', end_date='2026-01-06')
    assert empty['first_txn_date'] is None


def test_整月未同步的期间状态是no_data(db, make_position, make_transaction):
    """整月一条净值都没有 ⇒ 期间报「未同步」，不是「休市」（#1942 聚合层）。"""
    pos = make_position(symbol='000074', name='整月没同步', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2025, 12, 1),
        symbol='000074',
    )
    # 只在窗口第一天（scan_start，1/31 前一天=12/31）有净值，1 月整月全无
    _add_nav(db, '000074', dt.date(2025, 12, 31), 1.0)

    res = build_pnl_series(db, 1, '2026-01-01', '2026-01-31', granularity=GRANULARITY_MONTH)
    period = res['periods'][0]

    assert period['period'] == '2026-01'
    assert period['state'] == STATE_NO_DATA
    assert period['pnl'] is None


def test_建仓前整月的期间状态是无持仓(db, make_position, make_transaction):
    """整月没有仓位 ⇒ 期间报「无持仓」，而不是被周末的 `closed` 盖过去。"""
    pos = make_position(symbol='000075', name='下月才建仓', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2026, 2, 2),
        symbol='000075',
    )
    # 该基金 1 月有净值（用户在看它），但 2 月才建仓
    _add_nav(db, '000075', dt.date(2026, 1, 15), 1.0)

    res = build_pnl_series(db, 1, '2026-01-01', '2026-01-31', granularity=GRANULARITY_MONTH)
    period = res['periods'][0]

    assert period['period'] == '2026-01'
    assert period['state'] == STATE_NO_POSITION
    assert period['pnl'] is None


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


def test_断档日仍推进差分基准(db, make_position, make_transaction):
    """#1917 的 A 方案核心守卫：**基准无条件推进**，与「能否出数」解耦。

    这是消灭「同一日在不同区间得不同盈亏」的唯一关键。旧行为「数据不全就不写基准」
    会让基准冻结在更早的日子 ⇒ 释放那天的差分跨越不连续的几天 ⇒ 实测真实库
    2026-09-19（周六，全市场休市）报出 4756.40，而它真实值是 0.00；同一日在小区间
    里因起点不同、基准推进次数不同，答案是 0.00。

    本例构造「断档两天后恢复」：d4 的盈亏必须只反映 d3→d4 这一天，
    绝不能把断档期间（或更早）的涨跌一次性算进来。
    """
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)
    d3 = dt.date(2026, 1, 7)
    d4 = dt.date(2026, 1, 8)

    a = make_position(symbol='000091', name='全程有价', quantity=1000, avg_price=1.0, asset_type='fund')
    b = make_position(symbol='000092', name='断档两天', quantity=1000, avg_price=1.0, asset_type='fund')
    for pos, sym in ((a, '000091'), (b, '000092')):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=1000,
            price=1.0,
            confirm_date=dt.date(2025, 12, 1),
            symbol=sym,
        )
    # A 逐日有价；B 仅 d1 有，d2/d3 断档，d4 恢复
    _add_nav(db, '000091', d1, 1.0)
    _add_nav(db, '000091', d2, 1.1)
    _add_nav(db, '000091', d3, 1.2)
    _add_nav(db, '000091', d4, 1.2)
    _add_nav(db, '000092', d1, 1.0)
    _add_nav(db, '000092', d4, 1.0)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-09')

    # d2/d3 部分断档 ⇒ partial，且**仍出数**（A 方案：断档那几笔对称抵消）
    for day in (d2, d3):
        assert _state_of(result, day) == STATE_PARTIAL, f'{day} 应标 partial'
        assert _pnl_of(result, day) is not None, f'{day} 应出数'

    # 关键：A 在 d4 的净值与 d3 相同 ⇒ d4 的真实盈亏是 0。
    # 若基准冻结在 d1/d2，d4 就会报出一个累积的假值。
    assert _pnl_of(result, d4) == pytest.approx(0.0, abs=0.01), (
        f'd4 应为 0（净值未变），实得 {_pnl_of(result, d4)} —— 基准可能冻结了'
    )


def test_同一日在不同区间下必须得到相同结果(db, make_position, make_transaction):
    """**核心不变量**（#1917）：日盈亏只依赖该日及其前一日，不依赖查询区间。

    实测缺陷：2026-09-19 在整月区间得 4756.40、在小区间得 0.00——
    同一笔数据的两个答案。根因是「数据不全就不写基准」的旧判据让基准日不推进，
    次日差分跨越不连续的两天，而能推进几步取决于区间起点。
    """
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)
    d3 = dt.date(2026, 1, 7)
    d4 = dt.date(2026, 1, 8)

    a = make_position(symbol='000081', name='稳定有价', quantity=1000, avg_price=1.0, asset_type='fund')
    b = make_position(symbol='000082', name='断档后恢复', quantity=1000, avg_price=1.0, asset_type='fund')
    for pos, sym in ((a, '000081'), (b, '000082')):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=1000,
            price=1.0,
            confirm_date=dt.date(2025, 12, 1),
            symbol=sym,
        )
    _add_nav(db, '000081', d1, 1.0)
    _add_nav(db, '000081', d2, 1.1)
    _add_nav(db, '000081', d3, 1.2)
    _add_nav(db, '000082', d1, 1.0)
    _add_nav(db, '000082', d3, 1.05)

    wide = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-09')
    narrow = build_daily_pnl_series(db, family_id=1, start_date='2026-01-06', end_date='2026-01-09')

    for day in (d2, d3, d4):
        assert _state_of(wide, day) == _state_of(narrow, day), (
            f'{day} 状态随区间变化：整月={_state_of(wide, day)} 小区间={_state_of(narrow, day)}'
        )
        assert _pnl_of(wide, day) == _pnl_of(narrow, day), (
            f'{day} 盈亏随区间变化：整月={_pnl_of(wide, day)} 小区间={_pnl_of(narrow, day)}'
        )


# ─────────────────────────────────────────────────────────────────────────────
# #1942 ②：区间收益率（前端「金额 / 收益率」切换的合计行数据源）
# ─────────────────────────────────────────────────────────────────────────────


def test_区间收益率的分母是区间前一天净资产(db, make_position, make_transaction):
    """#1942 ②：`range_rate` = 区间盈亏 ÷ **区间前一天**净资产，日 / 月两条路径同值。

    区间取 1/30~2/9（跨月）：基准日前一天 1/29 净资产 = 1000 份 × 1.1 = 1100 元，
    区间盈亏 = 1/30 的 +100 与 2/2 的 +100 ⇒ 200/1100 = 18.18%。
    日粒度的 `days` 与月粒度的 `periods` 必须给出同一个数——否则
    「金额 / 收益率」一切换就随粒度变形。

    **前提：基准日（区间前一天）必须取得到价格**。少了它，首个区间日会把
    累计浮盈当成当日盈亏（真实库实测 2026-06 单月合计虚增 8115.71，见 #1953），
    那是另一个缺陷，不在本用例的表达范围内。
    """
    _seed_跨月收益(db, make_position, make_transaction)

    day = build_daily_pnl_series(db, 1, '2026-01-30', '2026-02-09')
    month = build_pnl_series(db, 1, '2026-01-30', '2026-02-09', granularity=GRANULARITY_MONTH)

    assert day['range_rate'] == pytest.approx(18.18, abs=0.01)
    assert month['range_rate'] == pytest.approx(18.18, abs=0.01)
    # 首期间（1/30~1/31，+100）的 `rate` 与区间收益率同分母 ⇒ 也必须一致
    assert month['periods'][0]['rate'] == pytest.approx(9.09, abs=0.01)


def test_无持仓时区间收益率为None(db):
    """空载荷的 `range_rate` 必须是 None——前端据此显示「—」，不能显示 0.00%。"""
    res = build_daily_pnl_series(db, family_id=1, start_date='2026-01-01', end_date='2026-01-31')

    assert res['range_rate'] is None
    assert res['month_total'] == 0.0


def test_整段无可算日时区间收益率为None而非零(db, make_position):
    """#1942 ②：「不可算」与「零收益」必须分开（「缺数据绝不画成 0」的红线）。

    balance 模式持仓有市值、无日估值序列 ⇒ 整段无可算日。此时 `month_total` 本就是
    0 元（无可算日），若再顺手报一个 0.00% 的区间收益率，会被读成
    「这段时间没涨没跌」——而真相是「这段时间算不出来」。
    """
    make_position(
        symbol='ZH0003',
        name='银行理财',
        quantity=0,
        avg_price=0,
        asset_type='portfolio',
        valuation_mode='balance',
        market_value_override=Money.yuan_to_cents(50000),
    )

    res = build_pnl_series(db, 1, '2026-01-01', '2026-01-31', granularity=GRANULARITY_MONTH)

    assert res['periods'][0]['state'] == STATE_NO_PRICE
    assert res['range_rate'] is None


def test_区间前一天为非交易日时单月与宽区间逐日相等(db, make_position, make_transaction):
    """#1953 回归：区间前一天（scan_start）落在非交易日/无净值时，首个区间日不得
    把整笔累计浮盈吞成当日盈亏；同一批日期在「单月区间」与「宽区间」下必须逐日相等。

    构造：基金 1/2 建仓（cost 1.0），5/29 起净值 1.2（已涨 20%），5/31 周日无净值；
    宽区间 scan_start=4/30 补 4/30 nav 使其有价。修复前，单月区间的 scan_start=5/31
    价格窗口不含 5/29，回填取不到价 ⇒ prev_total_pnl 低估 ⇒ 6/1 把累计浮盈当当日盈亏，
    与宽区间 6/1 不一致（单月合计虚增，违反区间无关性）；修复后两者逐日相等。
    """
    pos = make_position(
        symbol='000001', name='测试基金', quantity=1000, avg_price=1.0, asset_type='fund'
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=dt.date(2026, 1, 2),
        symbol='000001',
    )
    # 净值：4/30=1.2（宽区间基准日有价）、5/29=1.2（单月区间可回填到的最后价）、
    # 6/1~6/3=1.2；5/31 周日刻意不加（区间前一天无净值，正是 #1953 触发条件）
    for nav_date in (
        dt.date(2026, 4, 30),
        dt.date(2026, 5, 29),
        dt.date(2026, 6, 1),
        dt.date(2026, 6, 2),
        dt.date(2026, 6, 3),
    ):
        _add_nav(db, '000001', nav_date, 1.2)

    single = build_daily_pnl_series(db, family_id=1, start_date='2026-06-01', end_date='2026-06-03')
    wide = build_daily_pnl_series(db, family_id=1, start_date='2026-05-01', end_date='2026-06-03')

    for day in (dt.date(2026, 6, 1), dt.date(2026, 6, 2), dt.date(2026, 6, 3)):
        s = _pnl_of(single, day)
        w = _pnl_of(wide, day)
        assert s is not None and w is not None, f'{day} 两区间都应可算'
        assert s == w, f'{day} 单月({s})与宽区间({w})应逐日相等（#1953 区间无关性）'
