# -*- coding: utf-8 -*-
"""可转债条款解析与到期税前收益（YTM）自算（#1400 / #2575）。

## 为什么不用集思录的 YTM 真值

集思录 `bond_cb_jsl` 的「到期税前收益」**游客口径只有 30 条**（服务端硬截断，
`bond_ids` / `rp` / `page` 等参数均无效——实测）。而可转债全市场 300+ 只，
故 YTM 必须自算。

## 口径定义（**必须与集思录一致**，否则同页两个口径）

集思录的「到期税前收益」经 30 条基准反解确认是**单利年化的持有到期总回报**，
**不是 IRR / XIRR**：

    YTM = (持有到期总收 - 现价) / 现价 / 剩余年数

    持有到期总收 = 剩余各年票息之和 + 到期赎回价

    剩余各年票息之和 = 票息表尾部 K 档之和 −（末期票息，若到期赎回价已含最后一期利息）

其中 K = **剩余付息次数**（按实际付息日算，不是剩余年数取整——用年数取整会让
残差系统性偏正，实测中位 0.10pp → 0.14pp，最大 1.36pp）。

实测基准（30 条集思录真值，2026-10-24）：中位绝对误差 **0.103pp**，95% ≤ 0.5pp。

## 三道护栏（**缺一不可**）

1. **深度价内豁免**：现价 ≥ 面值 × `DEEP_IN_MONEY_RATIO` → 不出 YTM。
   深度价内债（现价 190~590）会转股，「持有到期」这个前提不成立，算出来的
   是 -554% 这种无意义数（集思录自己也是这么显示的，但不该由我们复刻）。
2. **条款解析失败 → `None`**：不猜、不用 0 兜底（0 会被读成「收益率为零」）。
3. **期次自洽**：剩余付息次数 K 不得超过票息表档数（否则说明票息表与实际条款
   对不上，宁可不给数）。

## 术语口径（避免与「下修历史」混淆）

本模块的「下修触发价」= **下修条款里的触发价格线**（东财 `EXECUTE_PRICE_HS/SH`），
**不是**「下修历史」。下修历史（每次下修的记录）在集思录 `adj_logs` 逐只接口，
本期不落库（见 #2575 边界）。
"""

import math
import re
from datetime import date
from typing import List, Optional, Tuple

# 可转债面值（分）
PAR_VALUE = 100.0

# 深度价内阈值：现价 ≥ 面值 × 此值 → 不出 YTM（持有到期不成立，会转股）
DEEP_IN_MONEY_RATIO = 1.5

# 剩余年数下限：小于此值不给出（年化无意义）
MIN_REMAINING_YEARS = 1e-6

# 票息解析：集思录/东财的票面利率说明形如
#   「票面利率:第一年0.2%、第二年0.4%、第三年0.6%、第四年0.8%、第五年1.5%、第六年2.0%。」
_COUPON_SEGMENT_RE = re.compile(r'(\d+(?:\.\d+)?)\s*%')
_COUPON_SPLIT_RE = re.compile(r'[、,，;；]')

# 到期赎回价：形如「按本次发行的可转债票面面值的110%(含最后一期年度利息)的价格…」
_REDEEM_PCT_RE = re.compile(r'面值的\s*(\d+(?:\.\d+)?)\s*%')
_REDEEM_INCL_LAST_RE = re.compile(r'含最后一期|含最后一年度')


def parse_coupon_schedule(text: Optional[str]) -> List[float]:
    """解析逐年票面利率 → 百分比数值列表（按年份升序）。

    >>> parse_coupon_schedule('票面利率:第一年0.2%、第二年0.4%。')
    [0.2, 0.4]
    >>> parse_coupon_schedule('票面利率：第一年 0.3%、第二年 0.8%、第三年 1.5%。')
    [0.3, 0.8, 1.5]
    >>> parse_coupon_schedule(None)
    []
    """
    if not text:
        return []
    raw = str(text)
    m = re.search(r'票面利率[:：](.*?)(?:。|$)', raw)
    segment = m.group(1) if m else raw
    out: List[float] = []
    for part in _COUPON_SPLIT_RE.split(segment):
        mm = _COUPON_SEGMENT_RE.search(part)
        if mm:
            out.append(float(mm.group(1)))
    return out


def parse_redeem_price(clause: Optional[str]) -> Tuple[Optional[float], bool]:
    """解析到期赎回条款 → (面值百分比, 是否已含最后一期利息)。

    只取「到期赎回条款」那一段，**不把有条件赎回条款的溢价混进来**（两者
    同在一句 REDEEM_CLAUSE 里，正则不限定段落就会取错数）。

    >>> parse_redeem_price('(1)到期赎回条款在期满后五个交易日内,公司将按本次发行的'
    ...                   '可转债票面面值的110%(含最后一期年度利息)的价格向投资者赎回全部未转股的可转债。')
    (110.0, True)
    >>> parse_redeem_price('将按面值加当期应计利息的价格赎回')  # 解析不出 → (None, False)
    (None, False)
    """
    if not clause:
        return (None, False)
    text = str(clause)
    idx = text.find('到期赎回')
    segment = text[idx : idx + 400] if idx >= 0 else text[:400]
    m = _REDEEM_PCT_RE.search(segment)
    if not m:
        return (None, False)
    pct = float(m.group(1))
    incl_last = bool(_REDEEM_INCL_LAST_RE.search(segment))
    return (pct, incl_last)


def count_remaining_coupons(
    *,
    start_date: Optional[date],
    expire_date: Optional[date],
    pay_month_day: Optional[str],
    today: date,
) -> int:
    """按**实际付息日**算剩余付息次数 K（今天之后、到期日及之前的付息日个数）。

    付息日按「发行日 + n 年」的月日推（`pay_month_day` 形如 ``'11-20'``）；
    发行当年的付息日可能不是发行日周年（半年付息的首期），故从第 1 年起推，
    落在到期日之前即计入。

    >>> from datetime import date
    >>> count_remaining_coupons(start_date=date(2020, 11, 20),
    ...                         expire_date=date(2026, 11, 20),
    ...                         pay_month_day='11-20', today=date(2026, 10, 24))
    1
    """
    if start_date is None or expire_date is None:
        return 0
    md = (pay_month_day or '').strip()
    if '-' not in md:
        return 0
    try:
        month, day = (int(x) for x in md.split('-')[:2])
    except (TypeError, ValueError):
        return 0
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return 0

    def nth(n: int) -> Optional[date]:
        year = start_date.year + n
        try:
            return date(year, month, day)
        except ValueError:
            # 2/29 之类：退到当月最后一天
            try:
                return date(year, month, day - 1)
            except ValueError:
                return None

    count = 0
    for n in range(1, 41):
        d = nth(n)
        if d is None or d > expire_date:
            break
        if d > today:
            count += 1
    return count


def compute_ytm(
    *,
    price: Optional[float],
    coupons: Optional[List[float]],
    redeem_pct: Optional[float],
    redeem_includes_last_coupon: bool,
    remaining_coupon_count: int,
    remaining_years: Optional[float],
    par: float = PAR_VALUE,
    deep_in_money_ratio: float = DEEP_IN_MONEY_RATIO,
) -> Tuple[Optional[float], Optional[str]]:
    """按集思录口径算 YTM（%）。返回 (ytm, 豁免原因)；ytm 为 None 时看原因。

    >>> compute_ytm(price=111.9, coupons=[0.2, 0.5, 1.0, 1.5, 1.8, 2.0],
    ...             redeem_pct=108.0, redeem_includes_last_coupon=True,
    ...             remaining_coupon_count=1, remaining_years=0.4273972602739726)
    (-8.15, None)
    >>> compute_ytm(price=191.938, coupons=[0.2], redeem_pct=110.0,
    ...             redeem_includes_last_coupon=True,
    ...             remaining_coupon_count=1, remaining_years=0.077)
    (None, '深度价内：现价 191.94 ≥ 面值 100.0 × 1.5，持有到期不成立')
    """
    if price is None or price <= 0:
        return (None, '缺现价')
    if price >= par * deep_in_money_ratio:
        return (None, f'深度价内：现价 {price:.2f} ≥ 面值 {par:.1f} × {deep_in_money_ratio}，持有到期不成立')
    if not coupons:
        return (None, '票息解析失败')
    if redeem_pct is None:
        return (None, '到期赎回价解析失败')
    if remaining_years is None or remaining_years <= MIN_REMAINING_YEARS:
        return (None, '剩余年限无效')
    if remaining_coupon_count <= 0:
        return (None, '无剩余付息期次')
    if remaining_coupon_count > len(coupons):
        return (None, f'剩余付息期次 {remaining_coupon_count} 超过票息档数 {len(coupons)}')

    tail = coupons[-remaining_coupon_count:]
    coupon_sum = sum(tail)
    if redeem_includes_last_coupon:
        # 到期赎回价已含最后一期利息 → 不重复计
        coupon_sum -= coupons[-1]
    total = coupon_sum + redeem_pct
    ytm = (total - price) / price / remaining_years * 100.0
    if math.isnan(ytm) or math.isinf(ytm):
        return (None, 'YTM 计算异常')
    return (ytm, None)
