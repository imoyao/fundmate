# -*- coding: utf-8 -*-
# File : twr.py
# app/services/performance/twr.py
"""时间加权收益率（TWR）——#2133。

## 为什么不再另起一套现金流

`pnl_calendar` 的 `daily_pnl` **已经剔除当日资金流**（`_compute_days` 里
`diff = day_level - prev_level - day_opening_level`，当日新投入的建仓额被减掉），
所以 `daily_pnl / |前一日净资产|` 就是**日收益因子**：它只反映「资产本身涨跌」，
不受申购/赎回节奏影响——这正是 TWR 的定义。

因此 TWR 不需要重新构造现金流序列，直接把这串日收益因子连乘即可：

    TWR = Π(1 + pnl_i / |net_worth_{i-1}|) - 1

## 为什么不用 `rate` 字段连乘

`rate` 是**保留 2 位小数的百分比**（`round(x, 2)`）。连乘 250 天时，每天 0.005%
的舍入误差会累积成肉眼可见的偏差。这里改用同行输出的 `daily_pnl`（元，2 位小数）
与 `net_worth`（元，2 位小数）现算因子——两者本身就是「分」换算来的，精度更高，
且**不引入第二套口径**：分子分母仍是 pnl_calendar 那套值。

## 与 XIRR 的区别（口径说明，前端 tooltip 用这句）

- **XIRR（资金加权）**：回答「我这些钱投进来，年化赚了多少」，受**投入时点与金额**影响；
- **TWR（时间加权）**：回答「这个组合本身表现如何」，剔除出入金影响，用于评价**资产/策略**；
- 两者并列展示、不相加、不互相替代。同一账户两个数差很大，通常说明「加仓时机」贡献了主要收益或亏损。
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.services.pnl_calendar import build_daily_pnl_series

# 年化基数：与 XIRR 一致用 365 天（非 252 交易日），避免同一页面两个年化口径打架。
DAYS_PER_YEAR = Decimal(365)

# 极端行情保护：单日因子落在 [0, 100] 之外视为脏数据（例如净资产为 1 分钱导致分母塌陷）。
_MIN_FACTOR = Decimal('0')
_MAX_FACTOR = Decimal('100')


def _empty_result(scope: str, ledger_id: Optional[int]) -> Dict[str, Any]:
    """无数据时的标准结构：`twr` 为 None 而不是 0。

    「本期没有收益」和「没有数据」是两件事，前者是 0、后者是 None；前端据 None
    显示 `—`。这与 pnl_calendar「缺数据绝不画成 0」同一条原则。
    """
    return {
        'twr': None,
        'twr_annualized': None,
        'days_used': 0,
        'days_skipped': 0,
        'start_date': None,
        'end_date': None,
        'net_worth_start': None,
        'net_worth_end': None,
        'method': 'daily_chained',
        'scope': scope,
        'ledger_id': ledger_id,
    }


def chain_twr(series: Dict[str, Any]) -> Dict[str, Any]:
    """把 `build_daily_pnl_series` 的输出连乘成 TWR（纯函数，便于单测）。

    参与计算的日必须同时满足：`daily_pnl` 非 None、当日 `net_worth` 非 None、
    **前一交易日**（序列里的前一天）`net_worth` 非 0。缺任一条件的天整日跳过并计入
    `days_skipped`——跳过而不是当 0，否则缺失的一天会被乘成「持平」，把缺失洗成事实。

    年化：`(1 + twr) ** (365 / 计息天数) - 1`，计息天数取**首个到末个有效日**的日历
    天数（含首尾）。有效日不足 2 天时不给年化（单日无法谈年化），返回 None。
    """
    days: List[Dict[str, Any]] = series.get('days') or []
    scope = series.get('scope') or 'family'
    ledger_id = series.get('ledger_id')

    if not days:
        return _empty_result(scope, ledger_id)

    factor = Decimal(1)
    prev_net_worth: Optional[Decimal] = None
    used_dates: List[str] = []
    skipped = 0
    net_worth_start: Optional[float] = None
    net_worth_end: Optional[float] = None

    for day in days:
        raw_pnl = day.get('daily_pnl')
        raw_nw = day.get('net_worth')

        if raw_pnl is None or raw_nw is None or prev_net_worth in (None, Decimal(0)):
            # 缺数据的一天不参与连乘，但**基准仍要推进**：下一天的分母应该是它自己的
            # 前一日净资产，跳过基准会让后面的因子全部错位。
            skipped += 1
        else:
            pnl = Decimal(str(raw_pnl))
            daily_factor = Decimal(1) + pnl / abs(prev_net_worth)
            if _MIN_FACTOR < daily_factor <= _MAX_FACTOR:
                factor *= daily_factor
                if not used_dates:
                    net_worth_start = float(abs(prev_net_worth))
                net_worth_end = float(raw_nw)
                used_dates.append(day.get('date'))
            else:
                # 分母塌陷（净资产接近 0）造成的异常因子：跳过并留痕，绝不写进连乘。
                logger.warning(f'TWR 跳过异常日收益因子: date={day.get("date")} factor={daily_factor}')
                skipped += 1

        if raw_nw is not None:
            prev_net_worth = Decimal(str(raw_nw))

    if not used_dates:
        return _empty_result(scope, ledger_id)

    twr = factor - Decimal(1)
    start_date, end_date = used_dates[0], used_dates[-1]
    annualized: Optional[float] = None
    try:
        span_days = (dt.date.fromisoformat(end_date) - dt.date.fromisoformat(start_date)).days + 1
    except ValueError:
        span_days = 0
    if span_days > 1 and factor > 0:
        # 年化用浮点幂运算：Decimal ** 非整数指数在部分版本不支持，且年化本身是展示值。
        annualized = round(float(factor) ** (float(DAYS_PER_YEAR) / span_days) - 1, 6)

    return {
        'twr': round(float(twr), 6),
        'twr_annualized': annualized,
        'days_used': len(used_dates),
        'days_skipped': skipped,
        'start_date': start_date,
        'end_date': end_date,
        'net_worth_start': net_worth_start,
        'net_worth_end': net_worth_end,
        'method': 'daily_chained',
        'scope': scope,
        'ledger_id': ledger_id,
    }


def calculate_twr(
    db: Session,
    family_id: int = 1,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ledger_id: Optional[int] = None,
) -> Dict[str, Any]:
    """区间 TWR（家庭级 / 账户级）。数据源与收益日历同一条路径（#2133 验收②）。

    刻意**只做家庭级与账户级**：产品级（symbol）/ 单持仓（position）没有独立的
    「每日净资产」序列，硬算会退化成「用家庭净资产当某个标的的分母」，那是错的。
    调用方（视图层）负责拒掉不支持的作用域。
    """
    series = build_daily_pnl_series(
        db,
        family_id=family_id,
        start_date=start_date,
        end_date=end_date,
        ledger_id=ledger_id,
    )
    result = chain_twr(series)
    logger.info(
        f'TWR 计算完成(scope={result["scope"]}, ledger_id={ledger_id}, '
        f'days_used={result["days_used"]}, twr={result["twr"]}): '
        f'{result["start_date"]}~{result["end_date"]}'
    )
    return result
