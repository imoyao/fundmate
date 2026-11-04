# -*- coding: utf-8 -*-
"""测试可转债 YTM 自算口径（#1400 / #2575）。

## 这个测试要钉死什么

YTM 是**金融计算**，口径错了比没有更坏（用户会拿它做「值不值拿到期」的判断）。
故本文件同时钉两件事：

1. **口径本身**：集思录的「到期税前收益」是**单利年化持有到期总回报**，不是 IRR /
   XIRR（30 条实测基准反解得出，见 `services/convertible_bond_ytm.py` 的模块
   docstring）。口径写成公式，测它就不只是测「代码没崩」。
2. **与集思录真值的一致性**：用 2026-10-24 实测的 5 组真值做回归，误差 ≤ 0.2pp。

真值来源（集思录游客口径 `bond_cb_jsl` 的「到期税前收益」列，2026-10-24）：

    110077 洪城转债  -576.89   （深度价内 → 豁免，不参与数值比对）
    127120 千红转债    2.15
    123107 温氏转债   -8.10
    111000 起帆转债  -16.30
    113043 财通转债   -5.93
    127040 国泰转债   -8.79

真值是**当时**的（现价会变），故回归用「当时的现价 + 当时的剩余年数」重算，
断言与真值的差 ≤ 0.2pp——**不锁定绝对值**（那会随行情漂移），只锁定「口径一致」。
"""

from datetime import date

from app.services.convertible_bond_ytm import (
    compute_ytm,
    count_remaining_coupons,
    parse_coupon_schedule,
    parse_redeem_price,
)

# ── 条款解析 ──────────────────────────────────────────────────────────────


def test_parse_coupon_schedule():
    assert parse_coupon_schedule('票面利率:第一年0.2%、第二年0.4%、第三年0.6%。') == [0.2, 0.4, 0.6]
    assert parse_coupon_schedule('票面利率：第一年 0.3%、第二年 0.8%、第三年 1.5%。') == [0.3, 0.8, 1.5]
    # 无「票面利率」前缀时也能抓百分数
    assert parse_coupon_schedule('0.2%、0.4%') == [0.2, 0.4]
    assert parse_coupon_schedule(None) == []
    assert parse_coupon_schedule('') == []


def test_parse_redeem_price_parses_face_value_pct():
    clause = (
        '(1)到期赎回条款在本次发行的可转换公司债券期满后五个交易日内,公司将按'
        '本次发行的可转债票面面值的110%(含最后一期年度利息)的价格向投资者赎回全部未转股的可转债。'
    )
    assert parse_redeem_price(clause) == (110.0, True)


def test_parse_redeem_price_ignores_conditional_redeem():
    """只取「到期赎回」段，**不把有条件赎回条款的溢价混进来**。

    两者同在一句 REDEEM_CLAUSE 里，不限定段落就会取错数。
    """
    clause = (
        '(1)到期赎回条款…将按可转债票面面值的108%(含最后一期年度利息)的价格赎回。'
        '(2)有条件赎回条款…公司有权决定按照债券面值加当期应计利息的价格赎回…'
    )
    assert parse_redeem_price(clause) == (108.0, True)


def test_parse_redeem_price_returns_none_when_unparseable():
    """解析不出 → (None, False)，**不猜、不用 0 兜底**。"""
    assert parse_redeem_price('将按面值加当期应计利息的价格赎回') == (None, False)
    assert parse_redeem_price(None) == (None, False)


# ── 剩余付息次数 ──────────────────────────────────────────────────────────


def test_count_remaining_coupons_uses_actual_payment_dates():
    """K = 未来付息日个数（**不是剩余年数取整**）。

    用年数取整会让残差系统性偏正（实测中位 0.10pp → 0.14pp，最大 1.36pp）。
    """
    # 2020-11-20 发行、每年 11-20 付息、2026-11-20 到期；今天 2026-10-24 → 还剩 1 次
    assert (
        count_remaining_coupons(
            start_date=date(2020, 11, 20),
            expire_date=date(2026, 11, 20),
            pay_month_day='11-20',
            today=date(2026, 10, 24),
        )
        == 1
    )
    # 同一只债，若「今天」在首次付息日之前 → 一次都还没付，还剩 6 次
    assert (
        count_remaining_coupons(
            start_date=date(2020, 11, 20),
            expire_date=date(2026, 11, 20),
            pay_month_day='11-20',
            today=date(2021, 6, 1),
        )
        == 6
    )
    # 已付过 1 次（今天在 2021-11-20 之后）→ 还剩 5 次
    assert (
        count_remaining_coupons(
            start_date=date(2020, 11, 20),
            expire_date=date(2026, 11, 20),
            pay_month_day='11-20',
            today=date(2022, 1, 1),
        )
        == 5
    )


def test_count_remaining_coupons_handles_missing_inputs():
    assert (
        count_remaining_coupons(
            start_date=None, expire_date=date(2026, 1, 1), pay_month_day='11-20', today=date(2026, 1, 1)
        )
        == 0
    )
    assert (
        count_remaining_coupons(
            start_date=date(2020, 1, 1), expire_date=date(2026, 1, 1), pay_month_day=None, today=date(2026, 1, 1)
        )
        == 0
    )
    assert (
        count_remaining_coupons(
            start_date=date(2020, 1, 1), expire_date=date(2026, 1, 1), pay_month_day='13-40', today=date(2026, 1, 1)
        )
        == 0
    )


# ── YTM 计算与护栏 ────────────────────────────────────────────────────────


def test_compute_ytm_matches_jsl_truth():
    """与集思录真值一致（误差 ≤ 0.2pp）。

    这组输入取自 2026-10-24 实测：现价、条款原文、剩余年数均为当时的值。
    """
    # 温氏转债 123107：真值 -8.10
    ytm, reason = compute_ytm(
        price=111.9,
        coupons=[0.2, 0.5, 1.0, 1.5, 1.8, 2.0],
        redeem_pct=108.0,
        redeem_includes_last_coupon=True,
        remaining_coupon_count=1,
        remaining_years=0.4273972602739726,
    )
    assert reason is None
    assert abs(ytm - (-8.10)) <= 0.2

    # 财通转债 113043：真值 -5.93
    ytm, _ = compute_ytm(
        price=106.816,
        coupons=[0.2, 0.4, 0.6, 1.0, 2.0, 2.5],
        redeem_pct=106.0,
        redeem_includes_last_coupon=True,
        remaining_coupon_count=1,
        remaining_years=0.132,
    )
    assert abs(ytm - (-5.93)) <= 0.2

    # 国泰转债 127040：真值 -8.79
    ytm, _ = compute_ytm(
        price=115.099,
        coupons=[0.2, 0.4, 0.6, 1.5, 1.8, 2.0],
        redeem_pct=108.0,
        redeem_includes_last_coupon=True,
        remaining_coupon_count=1,
        remaining_years=0.704,
    )
    assert abs(ytm - (-8.79)) <= 0.2

    # 起帆转债 111000：真值 -16.30
    ytm, _ = compute_ytm(
        price=127.088,
        coupons=[0.4, 0.6, 1.0, 1.5, 2.0, 3.0],
        redeem_pct=115.0,
        redeem_includes_last_coupon=True,
        remaining_coupon_count=1,
        remaining_years=0.584,
    )
    assert abs(ytm - (-16.30)) <= 0.2

    # 千红转债 127120：真值 2.15（正收益：现价 100 < 到期总收 113）
    ytm, _ = compute_ytm(
        price=100.0,
        coupons=[0.1, 0.3, 0.6, 1.0, 1.5, 2.0],
        redeem_pct=110.0,
        redeem_includes_last_coupon=True,
        remaining_coupon_count=6,
        remaining_years=6.003,
    )
    assert abs(ytm - 2.15) <= 0.2


def test_compute_ytm_is_simple_interest_not_irr():
    """口径守卫：**单利年化**，不是 IRR。

    构造一个**长周期 + 大幅折价**的样本，让两种口径的差距足够大、断言才有意义：
    现价 50、10 年后拿回 110 元（票息 10 档、末期票息已含在赎回价里）。

    - 单利年化 = (119 - 50) / 50 / 10 = **13.8%**
      （票息 10 档合计 11.0，末期 2.0 已含在赎回价里 → 总收 = 9.0 + 110 = 119.0）
    - 若误用 IRR（复利）→ 约 **8.2%**

    两者差 5.6 个百分点，断言落在单利值上即可锁死口径。
    短周期样本区分度不足（2.25% vs 2.16%），故不用。
    """
    coupons = [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
    ytm, reason = compute_ytm(
        price=50.0,
        coupons=coupons,
        redeem_pct=110.0,
        redeem_includes_last_coupon=True,
        remaining_coupon_count=10,
        remaining_years=10.0,
    )
    assert reason is None
    assert abs(ytm - 13.8) < 1e-6
    # 若实现误用 IRR，结果会落在 8% 附近 → 本断言会失败
    assert abs(ytm - 13.8) < abs(ytm - 8.2)


def test_compute_ytm_guard_deep_in_money():
    """护栏一：深度价内（现价 ≥ 面值×1.5）→ 不出 YTM。

    洪城转债实测：现价 191.938、剩余 0.077 年、兑付 110 → 数学上是 -554%，
    那是「本金全损且倒欠」的荒谬数。持有到期的前提不成立（它会转股）。
    """
    ytm, reason = compute_ytm(
        price=191.938,
        coupons=[0.2, 0.4, 0.6, 0.8, 1.5, 2.0],
        redeem_pct=110.0,
        redeem_includes_last_coupon=True,
        remaining_coupon_count=1,
        remaining_years=0.077,
    )
    assert ytm is None
    assert reason is not None and '深度价内' in reason


def test_compute_ytm_guard_missing_inputs():
    """护栏二：任何一环缺输入 → None（**不用 0 兜底**）。"""
    assert (
        compute_ytm(
            price=None,
            coupons=[0.2],
            redeem_pct=110.0,
            redeem_includes_last_coupon=True,
            remaining_coupon_count=1,
            remaining_years=1.0,
        )[0]
        is None
    )
    assert (
        compute_ytm(
            price=110.0,
            coupons=[],
            redeem_pct=110.0,
            redeem_includes_last_coupon=True,
            remaining_coupon_count=1,
            remaining_years=1.0,
        )[0]
        is None
    )
    assert (
        compute_ytm(
            price=110.0,
            coupons=[0.2],
            redeem_pct=None,
            redeem_includes_last_coupon=True,
            remaining_coupon_count=1,
            remaining_years=1.0,
        )[0]
        is None
    )
    assert (
        compute_ytm(
            price=110.0,
            coupons=[0.2],
            redeem_pct=110.0,
            redeem_includes_last_coupon=True,
            remaining_coupon_count=0,
            remaining_years=1.0,
        )[0]
        is None
    )
    assert (
        compute_ytm(
            price=110.0,
            coupons=[0.2],
            redeem_pct=110.0,
            redeem_includes_last_coupon=True,
            remaining_coupon_count=1,
            remaining_years=0.0,
        )[0]
        is None
    )


def test_compute_ytm_guard_coupon_count_mismatch():
    """护栏三：剩余付息次数 > 票息档数 → 不出数（票息表与实际条款对不上）。"""
    ytm, reason = compute_ytm(
        price=100.0,
        coupons=[0.1, 0.3, 0.6, 1.0, 1.5, 2.0],
        redeem_pct=110.0,
        redeem_includes_last_coupon=True,
        remaining_coupon_count=7,
        remaining_years=6.003,
    )
    assert ytm is None
    assert reason is not None and '票息档数' in reason
