# -*- coding: utf-8 -*-
"""定期复盘报告的**自然周期键**换算纯函数（#875 页面形态第一期）。

「周报 / 月报 / 季报 / 年报」是**自然周期**（有明确起止、可前后翻页），不是
`chartRange.ts` 那种「近 N 天」滚动窗口。本模块负责期间键与起止日的双向换算，
是报告生成、快照落库、翻页导航共用的唯一真相源。

口径（全部已拍板，见 docs/working-notes/periodic-review-report-page-2026-11-27.md §0）：

- ``week``   → ISO 周序键 ``YYYY-Www``（``date.isocalendar()``，跨年周归 ISO 年），
  起止 = 周一 ~ 周日；
- ``month``  → ``YYYY-MM``，起止 = 1 日 ~ 月末；
- ``quarter``→ ``YYYY-Qn``（自然季度 Q1~Q4），起止 = 季首月 1 日 ~ 季末月末；
- ``year``   → ``YYYY``，起止 = 1 月 1 日 ~ 12 月 31 日。

**键长不是粒度判据**：quarter 键 ``2026-Q4`` 与 month 键 ``2026-11`` 都是 7 字符，
前端 / 读侧必须靠 ``period_kind`` 字段（或正则 ``^\\d{4}-\\d{2}$`` 判月键），
绝不能靠「长度 == 7」——那是本功能扩粒度时踩过的撞车点。
"""

from __future__ import annotations

import calendar as _cal
import datetime as dt
from typing import Optional

# 期间类型（与方案文档 §6.1 一致，亦是快照表 period_kind 的合法取值集）。
PERIOD_KINDS = ('week', 'month', 'quarter', 'year')

# 月 → 自然季度（1..12 → 1..4）。
_MONTH_TO_QUARTER = {m: (m - 1) // 3 + 1 for m in range(1, 13)}


def period_key_of(day: dt.date, kind: str) -> str:
    """某一天所属自然周期的期间键。

    Args:
        day: 目标日期（date）。
        kind: 期间类型，见 ``PERIOD_KINDS``。非法值抛 ``ValueError``。

    >>> period_key_of(dt.date(2026, 11, 27), 'week')
    '2026-W48'
    >>> period_key_of(dt.date(2026, 11, 27), 'quarter')
    '2026-Q4'
    """
    if kind == 'week':
        iso = day.isocalendar()
        return f'{iso.year}-W{iso.week:02d}'
    if kind == 'month':
        return f'{day.year:04d}-{day.month:02d}'
    if kind == 'quarter':
        return f'{day.year:04d}-Q{_MONTH_TO_QUARTER[day.month]}'
    if kind == 'year':
        return f'{day.year:04d}'
    raise ValueError(f'非法期间类型：{kind!r}（合法值 {PERIOD_KINDS}）')


def period_bounds(key: str, kind: str) -> tuple[dt.date, dt.date]:
    """期间键 → 闭区间起止日 ``(start, end)``（均为 date，含端点）。

    非法键 / 非法类型抛 ``ValueError``（读侧据此回 400）。
    """
    if kind == 'week':
        # 键 `YYYY-Www`：反解出该 ISO 周的周一。
        year_s, _, week_s = key.partition('-W')
        if not year_s or not week_s:
            raise ValueError(f'非法周键：{key!r}（期望 YYYY-Www）')
        try:
            year = int(year_s)
            week = int(week_s)
        except ValueError as e:
            raise ValueError(f'非法周键：{key!r}') from e
        # ISO 周序下「YYYY-W01」的周一可能落在上一自然年（12 月末），
        # 用 isocalendar 迭代兜底最稳：找「该 ISO 年+周」对应的周一。
        start = _iso_week_monday(year, week)
        return start, start + dt.timedelta(days=6)
    if kind == 'month':
        try:
            year, month = int(key[:4]), int(key[5:7])
        except ValueError as e:
            raise ValueError(f'非法月键：{key!r}（期望 YYYY-MM）') from e
        if not (1 <= month <= 12) or key[4:5] != '-':
            raise ValueError(f'非法月键：{key!r}（期望 YYYY-MM）')
        start = dt.date(year, month, 1)
        return start, dt.date(year, month, _cal.monthrange(year, month)[1])
    if kind == 'quarter':
        # 键 `YYYY-Qn`
        year_s, _, q_s = key.partition('-Q')
        if not year_s or not q_s:
            raise ValueError(f'非法季键：{key!r}（期望 YYYY-Qn）')
        try:
            year = int(year_s)
            q = int(q_s)
        except ValueError as e:
            raise ValueError(f'非法季键：{key!r}') from e
        if not (1 <= q <= 4):
            raise ValueError(f'非法季键：{key!r}（Q 须 1..4）')
        start_month = (q - 1) * 3 + 1
        end_month = q * 3
        start = dt.date(year, start_month, 1)
        end = dt.date(year, end_month, _cal.monthrange(year, end_month)[1])
        return start, end
    if kind == 'year':
        try:
            year = int(key)
        except ValueError as e:
            raise ValueError(f'非法年键：{key!r}（期望 YYYY）') from e
        return dt.date(year, 1, 1), dt.date(year, 12, 31)
    raise ValueError(f'非法期间类型：{kind!r}（合法值 {PERIOD_KINDS}）')


def _iso_week_monday(iso_year: int, iso_week: int) -> dt.date:
    """ISO 周 ``(iso_year, iso_week)`` 对应的周一日期。

    ISO 周 1 的规则：包含该年第一个周四的那一周。用「该年 1 月 4 日」必然落在
    第 1 周（ISO 8601 恒真）→ 回退到周一 → 再 +7*(week-1)。
    """
    jan4 = dt.date(iso_year, 1, 4)
    monday = jan4 - dt.timedelta(days=jan4.weekday())
    return monday + dt.timedelta(weeks=iso_week - 1)


def next_period_key(key: str, kind: str) -> str:
    """期间键的下一期键（用于「向后翻」）。"""
    start, end = period_bounds(key, kind)
    return period_key_of(end + dt.timedelta(days=1), kind)


def prev_period_key(key: str, kind: str) -> str:
    """期间键的上一期键（用于「向前翻」）。"""
    start, end = period_bounds(key, kind)
    return period_key_of(start - dt.timedelta(days=1), kind)


def resolve_last_trading_day(
    end: dt.date,
    is_trading_day,
    max_lookback: int = 7,
) -> Optional[dt.date]:
    """区间 ``[*, end]`` 内最后一个交易日（闭区间含 ``end``，向前回退）。

    周末 / 节假日顺延：月末恰逢周末时，报告边界回退到最后一个实际交易日。
    回退超过 ``max_lookback`` 仍未命中（日历未覆盖 / 异常长假）返回 ``None``。

    Args:
        end: 区间终点（date）。
        is_trading_day: 判定函数 ``(date) -> bool``（由 ``trading_calendar`` 注入，
            便于单测不依赖真日历）。
    """
    for i in range(max_lookback + 1):
        d = end - dt.timedelta(days=i)
        if is_trading_day(d):
            return d
    return None
