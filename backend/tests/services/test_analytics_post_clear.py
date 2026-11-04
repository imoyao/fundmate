# -*- coding: utf-8 -*-
"""清仓后涨跌幅（analytics/cleared_cycles.py · #2773）测试。

覆盖两层：

1. 纯函数 `attach_post_clear_performance` —— 口径判断全在这里，故把状态矩阵钉死在
   这一层；
2. `count_unrealized_losses` —— 胜率的样本选择偏差对冲。它要查持仓与净值，故用
   `make_position` 造数据、monkeypatch 净值查询，只验「哪些持仓该被数进来」。

关键约束（这几条就是本卡的验收口径）：
- 算不出一律 `post_clear_pct is None` + 状态码，**禁止回 0**；
- 前后两点必须同口径（都 acc 或都 unit），混用宁可不给数；
- 同一标的多轮清仓，各轮的锚点按 (code, 末卖日) 分开，不会被后一轮覆盖；
- `ok` 必须带 `post_clear_as_of`（否则用户会把旧数当实时值）；
- 浮亏数只数「能定价的活跃 nav 持仓」，取不到价**不回落成 0**。
"""

from datetime import date

import pytest

from app.services.analytics.cleared_cycles import (
    POST_CLEAR_NO_AFTER,
    POST_CLEAR_NO_ANCHOR,
    POST_CLEAR_NOT_SUPPORTED,
    POST_CLEAR_OK,
    attach_post_clear_performance,
    count_unrealized_losses,
    summarize_cycles,
)


def _cycle(identity='OTC:001937', sold='2026-05-20'):
    """一个已清仓周期的最小形态（只带本函数用到的字段）。"""
    return {'identity': identity, 'symbol': 'SZ001937', 'last_sell_date': sold}


def test_ok_computes_pct_from_aligned_acc_nav():
    """两边都有 acc_nav 时用 acc：2.75 / 2.5 - 1 = 10%。"""
    cycles = [_cycle()]
    anchors = {('OTC:001937', '2026-05-20'): (2.0, 2.5, date(2026, 5, 20))}
    latest = {'OTC:001937': (2.2, 2.75, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_OK
    assert cycles[0]['post_clear_pct'] == 10.0


def test_unit_nav_used_when_acc_missing_on_both_sides():
    """两边都没有 acc → 退到 unit 口径：2.4 / 2.0 - 1 = 20%。"""
    cycles = [_cycle()]
    anchors = {('OTC:001937', '2026-05-20'): (2.0, None, date(2026, 5, 20))}
    latest = {'OTC:001937': (2.4, None, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_OK
    assert cycles[0]['post_clear_pct'] == 20.0


def test_mixed_nav_basis_is_never_guessed():
    """锚点只有 acc、最新只有 unit → **不混口径**，降级而不是硬算。

    这是本函数最容易写错的地方：拿 acc 当分母、unit 当分子，中间分过红就会
    凭空多出一截涨幅。宁可给 None。
    """
    cycles = [_cycle()]
    anchors = {('OTC:001937', '2026-05-20'): (None, 2.5, date(2026, 5, 20))}
    latest = {'OTC:001937': (2.4, None, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_NO_ANCHOR
    assert cycles[0]['post_clear_pct'] is None


def test_missing_anchor_reports_no_nav_at_sell():
    """卖出日及之前没有任何净值（#2343 前清仓的典型形态）。"""
    cycles = [_cycle()]

    attach_post_clear_performance(cycles, {}, {})

    assert cycles[0]['post_clear_status'] == POST_CLEAR_NO_ANCHOR
    assert cycles[0]['post_clear_pct'] is None


def test_latest_not_after_anchor_is_no_nav_after():
    """最新净值没越过卖出日：恒等于 0 涨幅是「没数据」，不是「没涨」。"""
    cycles = [_cycle()]
    same_day = date(2026, 5, 20)
    anchors = {('OTC:001937', '2026-05-20'): (2.0, 2.0, same_day)}
    latest = {'OTC:001937': (2.0, 2.0, same_day)}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_NO_AFTER
    assert cycles[0]['post_clear_pct'] is None


def test_exchange_traded_uses_adj_close_basis():
    """场内用前复权收盘价，且 basis 必须标 adj_close（#2773 场内收口）。"""
    cycles = [{'identity': 'EXCHANGE:SH600519', 'symbol': 'SH600519', 'last_sell_date': '2026-05-20'}]
    anchors = {('EXCHANGE:SH600519', '2026-05-20'): (10.0, None, date(2026, 5, 20))}
    latest = {'EXCHANGE:SH600519': (12.0, None, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_OK
    assert cycles[0]['post_clear_pct'] == 20.0
    assert cycles[0]['post_clear_basis'] == 'adj_close'


def test_exchange_without_adj_close_is_not_guessed():
    """场内缺前复权价 → 「算不出」，**不回落**未复权 close（会把除权算成亏损）。"""
    cycles = [{'identity': 'EXCHANGE:SH600519', 'symbol': 'SH600519', 'last_sell_date': '2026-05-20'}]
    # 备位（原本留给 close）即便给了值也不能被采用
    anchors = {('EXCHANGE:SH600519', '2026-05-20'): (None, 10.0, date(2026, 5, 20))}
    latest = {'EXCHANGE:SH600519': (None, 12.0, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_NO_ANCHOR
    assert cycles[0]['post_clear_pct'] is None


def test_no_venue_entity_is_not_supported():
    """无交易场所的实体（经理 / 投顾组合 / 指数）：没有可信市价，不假装能算。"""
    cycles = [{'identity': 'NO_VENUE:MGR_001', 'symbol': 'MGR_001', 'last_sell_date': '2026-05-20'}]
    anchors = {('NO_VENUE:MGR_001', '2026-05-20'): (10.0, None, date(2026, 5, 20))}
    latest = {'NO_VENUE:MGR_001': (12.0, None, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_NOT_SUPPORTED
    assert cycles[0]['post_clear_pct'] is None


def test_multi_round_same_code_uses_per_date_anchor():
    """同一标的两轮清仓：各用各的锚点，不能被后一轮覆盖。

    这正是 `anchors` 的键要带日期、而不是只用身份键的原因。
    """
    cycles = [_cycle(sold='2026-03-10'), _cycle(sold='2026-07-15')]
    anchors = {
        ('OTC:001937', '2026-03-10'): (1.0, 1.0, date(2026, 3, 10)),
        ('OTC:001937', '2026-07-15'): (2.0, 2.0, date(2026, 7, 15)),
    }
    latest = {'OTC:001937': (2.4, 2.4, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    by_sell_date = {c['last_sell_date']: c['post_clear_pct'] for c in cycles}
    assert by_sell_date['2026-03-10'] == 140.0  # 2.4 / 1.0 - 1
    assert by_sell_date['2026-07-15'] == 20.0  # 2.4 / 2.0 - 1


def test_returns_same_objects_for_chaining():
    """原地写入 + 返回同一批 dict（便于 build 层链式调用）。"""
    cycles = [_cycle()]

    out = attach_post_clear_performance(cycles, {}, {})

    assert out[0] is cycles[0]


def test_ok_reports_as_of_date_and_basis():
    """算出来的必须一起给出「截至哪一天」与「用了哪个口径」。

    不给 `as_of`，一个停在几个月前的数会被当实时值读；不给 `basis`，
    同一列里 acc / unit 混着也看不出为什么某行和别人不一样（#2773 验收口径）。
    """
    cycles = [_cycle()]
    anchors = {('OTC:001937', '2026-05-20'): (2.0, 2.5, date(2026, 5, 20))}
    latest = {'OTC:001937': (2.2, 2.75, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_as_of'] == '2026-10-30'
    assert cycles[0]['post_clear_basis'] == 'acc_nav'


def test_unit_basis_is_reported_when_acc_missing():
    """退到 unit 口径时 basis 必须标 unit_nav，不能默认写 acc。"""
    cycles = [_cycle()]
    anchors = {('OTC:001937', '2026-05-20'): (2.0, None, date(2026, 5, 20))}
    latest = {'OTC:001937': (2.4, None, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_basis'] == 'unit_nav'


def test_unsolved_statuses_never_carry_as_of_or_basis():
    """算不出时 as_of / basis 必须为空：留一个日期会让「--」看起来像有数据。"""
    cycles = [
        _cycle(identity='OTC:001937'),  # 无锚点
        {'identity': 'EXCHANGE:SH600519', 'symbol': 'SH600519', 'last_sell_date': '2026-05-20'},  # 场内无锚点
    ]

    attach_post_clear_performance(cycles, {}, {})

    for c in cycles:
        assert c['post_clear_pct'] is None
        assert c['post_clear_as_of'] is None
        assert c['post_clear_basis'] is None


def test_no_nav_after_keeps_anchor_but_reports_no_as_of():
    """净值停更：有锚点但没有「之后的点」，故 as_of 仍为空、状态如实标 no_nav_after。"""
    same_day = date(2026, 5, 20)
    cycles = [_cycle()]
    anchors = {('OTC:001937', '2026-05-20'): (2.0, 2.0, same_day)}

    attach_post_clear_performance(cycles, anchors, {'OTC:001937': (2.0, 2.0, same_day)})

    assert cycles[0]['post_clear_status'] == POST_CLEAR_NO_AFTER
    assert cycles[0]['post_clear_as_of'] is None


# ── 浮亏标的数（#2773 样本选择偏差对冲）──────────────────────────────────


@pytest.fixture
def nav_stub(monkeypatch):
    """把批量净值查询换成一个可控字典，隔离 nav 取数细节，只测筛选口径。"""

    def _stub(db, fund_codes, target_date):
        return {code: (nav, nav, date(2026, 10, 30)) for code, nav in _stub.data.items() if code in fund_codes}

    _stub.data = {}
    monkeypatch.setattr(
        'app.services.nav_service.NavService.get_navs_at_or_before',
        staticmethod(_stub),
    )
    return _stub


def test_counts_otc_position_underwater(db, make_position, nav_stub):
    """场外持仓：净值低于成本 → 计入 1 只。"""
    make_position(symbol='000001', asset_type='fund', name='浮亏基', quantity=1000, avg_price=1.0)
    nav_stub.data = {'000001': 0.9}

    assert count_unrealized_losses(db) == 1


def test_profitable_position_is_not_counted(db, make_position, nav_stub):
    """净值高于成本 → 不算浮亏（这个数只数亏的）。"""
    make_position(symbol='000002', asset_type='fund', name='盈利基', quantity=1000, avg_price=1.0)
    nav_stub.data = {'000002': 1.2}

    assert count_unrealized_losses(db) == 0


def test_missing_nav_is_skipped_not_treated_as_loss(db, make_position, nav_stub):
    """取不到净值 → 跳过，**不能**当成 0 市值算成满仓浮亏。

    这是最容易埋假数据的一条：current_price 缺省为 0，若直接拿它当市价，
    每只没同步过净值的持仓都会变成「浮亏」，数字凭空翻几倍。
    """
    make_position(symbol='000003', asset_type='fund', name='无净值', quantity=1000, avg_price=1.0)
    nav_stub.data = {}

    assert count_unrealized_losses(db) == 0


def test_cleared_position_is_excluded(db, make_position, nav_stub):
    """已清仓行不进这里——它已经由周期口径统计，再数一次会重复暴露。"""
    make_position(
        symbol='000004', asset_type='fund', name='已清仓', quantity=0, avg_price=1.0, ownership_status='cleared'
    )
    nav_stub.data = {'000004': 0.5}

    assert count_unrealized_losses(db) == 0


def test_same_product_across_ledgers_counted_once(db, make_position, nav_stub):
    """同一标的在两个账户各一笔 → 产品级口径数 1 只（与 product_count 一致）。"""
    make_position(symbol='000005', asset_type='fund', name='同一只', quantity=500, avg_price=1.0, account_name='A')
    make_position(symbol='000005', asset_type='fund', name='同一只', quantity=500, avg_price=1.0, account_name='B')
    nav_stub.data = {'000005': 0.8}

    assert count_unrealized_losses(db) == 1


def test_balance_mode_is_excluded(db, make_position, nav_stub):
    """balance 模式（人工录入市值）没有可核验市价，不参与浮亏判断。"""
    make_position(
        symbol='MGR_001',
        asset_type='fund',
        name='投顾组合',
        quantity=1000,
        avg_price=1.0,
        valuation_mode='balance',
        market_value_override=50000,
    )

    assert count_unrealized_losses(db) == 0


def test_cash_equivalents_excluded_by_default(db, make_position, nav_stub):
    """货基默认剔除（与 build_cleared_cycles 同口径），开启后才数。"""
    make_position(symbol='000006', asset_type='money_fund', name='货基', quantity=1000, avg_price=1.0)
    nav_stub.data = {'000006': 0.9}

    assert count_unrealized_losses(db) == 0
    assert count_unrealized_losses(db, include_cash_equivalents=True) == 1


# ── 汇总里「没算」与「算了是 0」必须可分辨 ──────────────────────────────


def test_summary_distinguishes_not_computed_from_zero():
    """`unrealized_count=None`（没查）≠ `0`（查了，一只都不亏）。

    混成 0 会让「没实现/没查」在界面上显示成「持仓全部健康」——那是编数字。
    """
    assert summarize_cycles([])['unrealized_count'] is None
    assert summarize_cycles([], unrealized_count=0)['unrealized_count'] == 0
    assert summarize_cycles([], unrealized_count=3)['unrealized_count'] == 3
