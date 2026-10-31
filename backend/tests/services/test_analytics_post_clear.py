# -*- coding: utf-8 -*-
"""清仓后涨跌幅（analytics/cleared_cycles.py · #2773）测试。

只覆盖纯函数 `attach_post_clear_performance`：取数在 `_attach_post_clear`（db 层），
但**口径判断全在这里**，所以把状态矩阵钉死在这一层。

关键约束（这几条就是本卡的验收口径）：
- 算不出一律 `post_clear_pct is None` + 状态码，**禁止回 0**；
- 前后两点必须同口径（都 acc 或都 unit），混用宁可不给数；
- 同一标的多轮清仓，各轮的锚点按 (code, 末卖日) 分开，不会被后一轮覆盖。
"""

from datetime import date

from app.services.analytics.cleared_cycles import (
    POST_CLEAR_NO_AFTER,
    POST_CLEAR_NO_ANCHOR,
    POST_CLEAR_NOT_SUPPORTED,
    POST_CLEAR_OK,
    attach_post_clear_performance,
)


def _cycle(identity='OTC:001937', sold='2026-05-20'):
    """一个已清仓周期的最小形态（只带本函数用到的字段）。"""
    return {'identity': identity, 'symbol': 'SZ001937', 'last_sell_date': sold}


def test_ok_computes_pct_from_aligned_acc_nav():
    """两边都有 acc_nav 时用 acc：2.75 / 2.5 - 1 = 10%。"""
    cycles = [_cycle()]
    anchors = {('001937', '2026-05-20'): (2.0, 2.5, date(2026, 5, 20))}
    latest = {'001937': (2.2, 2.75, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_OK
    assert cycles[0]['post_clear_pct'] == 10.0


def test_unit_nav_used_when_acc_missing_on_both_sides():
    """两边都没有 acc → 退到 unit 口径：2.4 / 2.0 - 1 = 20%。"""
    cycles = [_cycle()]
    anchors = {('001937', '2026-05-20'): (2.0, None, date(2026, 5, 20))}
    latest = {'001937': (2.4, None, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_OK
    assert cycles[0]['post_clear_pct'] == 20.0


def test_mixed_nav_basis_is_never_guessed():
    """锚点只有 acc、最新只有 unit → **不混口径**，降级而不是硬算。

    这是本函数最容易写错的地方：拿 acc 当分母、unit 当分子，中间分过红就会
    凭空多出一截涨幅。宁可给 None。
    """
    cycles = [_cycle()]
    anchors = {('001937', '2026-05-20'): (None, 2.5, date(2026, 5, 20))}
    latest = {'001937': (2.4, None, date(2026, 10, 30))}

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
    anchors = {('001937', '2026-05-20'): (2.0, 2.0, same_day)}
    latest = {'001937': (2.0, 2.0, same_day)}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_NO_AFTER
    assert cycles[0]['post_clear_pct'] is None


def test_exchange_traded_is_not_supported():
    """场内标的不假装能算（要另一套价格源 price_history.adj_close）。"""
    cycles = [{'identity': 'SH600519', 'symbol': 'SH600519', 'last_sell_date': '2026-05-20'}]
    anchors = {('600519', '2026-05-20'): (10.0, None, date(2026, 5, 20))}
    latest = {'600519': (12.0, None, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    assert cycles[0]['post_clear_status'] == POST_CLEAR_NOT_SUPPORTED
    assert cycles[0]['post_clear_pct'] is None


def test_multi_round_same_code_uses_per_date_anchor():
    """同一标的两轮清仓：各用各的锚点，不能被后一轮覆盖。

    这正是 `anchor_navs` 的键要带日期、而不是只用 code 的原因。
    """
    cycles = [_cycle(sold='2026-03-10'), _cycle(sold='2026-07-15')]
    anchors = {
        ('001937', '2026-03-10'): (1.0, 1.0, date(2026, 3, 10)),
        ('001937', '2026-07-15'): (2.0, 2.0, date(2026, 7, 15)),
    }
    latest = {'001937': (2.4, 2.4, date(2026, 10, 30))}

    attach_post_clear_performance(cycles, anchors, latest)

    by_sell_date = {c['last_sell_date']: c['post_clear_pct'] for c in cycles}
    assert by_sell_date['2026-03-10'] == 140.0  # 2.4 / 1.0 - 1
    assert by_sell_date['2026-07-15'] == 20.0  # 2.4 / 2.0 - 1


def test_returns_same_objects_for_chaining():
    """原地写入 + 返回同一批 dict（便于 build 层链式调用）。"""
    cycles = [_cycle()]

    out = attach_post_clear_performance(cycles, {}, {})

    assert out[0] is cycles[0]
