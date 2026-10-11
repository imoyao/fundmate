# -*- coding: utf-8 -*-
"""任职年限 / 规模 / 回报的展示换算（#1970 扩展· 转换层）。

重点覆盖「**换算本身会不会说谎**」：

1. **口径文本必须与天天基金 F10 一致** —— 实测张坤 F10 显示「14 年又 15 天」，
   与5125 天算出的结果完全相同。不一致会让同一数据在两个页面显示不同；
2. **天数不是随时间冻结的** —— 展示年数要随基准日自然增长，而存储的起始日不变；
3. **脏输入/ 异常区间必须降级None**，而不是产出「200 年从业」这种假事实；
4. **换算层不返回颜色** —— 配色是前端 design.md 的事，服务层给颜色会导致色板分裂。
"""

from datetime import date

from app.services.tenure_display import (
    build_return_display,
    build_scale_display,
    build_tenure_display,
    format_tenure_days,
)

TODAY = date(2026, 10, 10)


# ── 天数 → 文本：与 F10 口径逐字对齐 ─────────────────────────


def test_format_matches_eastmoney_f10_wording():
    """张坤 5125 天→ 「14 年又 15 天」，与 F10 实测文本逐字相同。

    F10 显示的是「14 年又 15 天」而非「14.04 年」，故中文口径才是对齐目标。
    """
    assert format_tenure_days(5125) == '14 年又 15 天'


def test_format_whole_years_without_extra_day():
    """整年时不该出现「又 0 天」。"""
    assert format_tenure_days(365 * 3) == '3 年'
    assert format_tenure_days(365) == '1 年'


def test_format_days_only_under_one_year():
    """不足一年只显示天数，不显示「0 年又 87 天」。"""
    assert format_tenure_days(87) == '87 天'
    assert format_tenure_days(364) == '364 天'


def test_format_zero_and_negative():
    """0 / 负数不编造「-3 天」，统一降级文案。"""
    assert format_tenure_days(0) == '不足 1 天'
    assert format_tenure_days(-10) == '不足 1 天'


# ── 年限 dict：基准日语义 ────────────────────────────────────


def test_tenure_display_grows_with_as_of_but_start_stays():
    """展示年数随基准日增长，而**起始日不变** —— 这是存日期而非天数的核心收益。"""
    start = date(2012, 9, 28)

    early = build_tenure_display(start, 'em_days_derived', as_of=date(2026, 1, 1))
    late = build_tenure_display(start, 'em_days_derived', as_of=TODAY)

    assert early['years'] < late['years']  # 时间在走，数字在长
    assert early['start_date'] == late['start_date'] == '2012-09-28'  # 但事实不变
    assert late['text'] == '14 年又 15 天'


def test_tenure_display_carries_basis_and_raw():
    """口径元数据必须齐：没有 basis 的年限数字等于假数字。"""
    got = build_tenure_display(date(2012, 9, 28), 'em_days_derived', as_of=TODAY, raw=5125.0)
    assert got['basis'] == 'em_days_derived'
    assert got['raw'] == 5125.0  # 溯源线索，不是展示值
    assert got['as_of'] == '2026-10-10'


def test_tenure_display_has_both_years_and_text():
    """同时给 years（供排序比较）与 text（供展示），前端不解析中文。"""
    got = build_tenure_display(date(2012, 9, 28), 'em_days_derived', as_of=TODAY)
    assert got['years'] == 14.0
    assert got['text'] == '14 年又 15 天'


def test_tenure_display_returns_none_without_start():
    """无起始日 → None，前端降级「—」。"""
    assert build_tenure_display(None, 'em_days_derived', as_of=TODAY) is None


def test_tenure_display_rejects_future_start():
    """起始日晚于基准日 = 上游脏数据，降级而非返回负年限。"""
    assert build_tenure_display(date(2030, 1, 1), 'em_days_derived', as_of=TODAY) is None


def test_tenure_display_rejects_absurdly_old_start():
    """起始日过于久远（>80 年）判为脏数据，不展示「200 年从业」。"""
    assert build_tenure_display(date(1900, 1, 1), 'em_days_derived', as_of=TODAY) is None


# ── 规模 / 回报 ──────────────────────────────────────────────


def test_scale_display_formats_yuan_yi():
    """管理规模固定用「亿元」，不做自动进位（全行业都在亿~千亿量级）。"""
    got = build_scale_display(307.94)
    assert got['text'] == '307.94 亿元'
    assert got['unit'] == '亿元'
    assert got['value'] == 307.94
    assert got['basis'] == 'em_yi'


def test_scale_display_none_when_missing():
    """缺失 → None（不是 0.0，0.00 亿元会被读成「规模为零」）。"""
    assert build_scale_display(None) is None


def test_return_display_always_signed():
    """显式带符号：前端按正负选色，不靠猜。"""
    assert build_return_display(43.59)['text'] == '+43.59%'
    assert build_return_display(-18.52)['text'] == '-18.52%'
    assert build_return_display(0)['text'] == '+0.00%'


def test_return_display_none_when_missing():
    """缺失 → None，不返回 '+0.00%'（那会被读成「回报为零」）。"""
    assert build_return_display(None) is None


def test_display_layers_do_not_return_color():
    """换算层不得返回颜色字段 —— 配色统一由前端 design.md 令牌决定。

    服务层返回颜色会导致色板分裂成两套，是设计文档明令禁止的。
    """
    for got in (
        build_tenure_display(date(2012, 9, 28), 'em_days_derived', as_of=TODAY),
        build_scale_display(307.94),
        build_return_display(43.59),
    ):
        assert not any(k in got for k in ('color', 'tone', 'rise', 'fall', 'trend')), got