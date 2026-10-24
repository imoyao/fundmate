# -*- coding: utf-8 -*-
# File : twr.py
# app/services/performance/twr.py
"""时间加权收益率（TWR）——#2133 引擎 + #871 组合级扩展。

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

## #871：组合级扩展（scope=portfolio）

家庭级 / 账户级的日序列由 `build_daily_pnl_series` 直接给；组合级没有现成序列，
按 #2134 立好的先例（`benchmark_excess` 同款）**Σ 成员账本日序列**：

- 组合 = 成员账本集合（`Ledger.portfolio_id`，与 `compute_range_attribution` /
  `benchmark_excess` 的成员解析同口径）；
- 逐成员取序列后按日**求和**（不是先算各自 TWR 再汇总——TWR 不可加，必须
  在日因子层求和）：组合内转账在各成员自己的 `daily_pnl` 里已各自剔除
  （pnl_calendar 口径），求和天然不重复计入；
- **None 传播**：任一成员某日缺数据 ⇒ 组合该日整体置缺（`chain_twr` 计入
  `days_skipped` 跳过），与 `benchmark_excess`「分母任一成员取不到 ⇒ 整组
  不报」同一条纪律——缺数据绝不借 0 兜底。
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.performance.calculators import XirrScopeParameterError
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


# ──────────────────── 组合级（#871，先例 #2134）────────────────────────────


def _portfolio_member_ledger_ids(db: Session, family_id: int, portfolio_id: int) -> List[int]:
    """组合成员账本 id 列表（`Ledger.portfolio_id`，与 benchmark_excess / 归因同口径）。

    组合不存在 / 非本家庭 / 已删除 ⇒ ValueError（视图转 400/404，与
    `portfolio_service` 同文案）。
    """
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.family_id == family_id, Portfolio.is_deleted.is_(False))
        .first()
    )
    if portfolio is None:
        raise ValueError('投资组合不存在')
    rows = db.query(Ledger.id).filter(Ledger.family_id == family_id, Ledger.portfolio_id == portfolio_id).all()
    return [r[0] for r in rows]


def _merge_member_series(payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Σ 成员日序列 → 组合日序列（纯函数，便于单测）。

    按日期对齐求和 `daily_pnl` / `net_worth`。**None 传播**：某日只要有一个成员
    缺（整天无行，或当日两字段任一为 None），组合该日两字段整体置 None——
    `chain_twr` 会把它计入 `days_skipped` 跳过。这与 `benchmark_excess`
    「分母任一成员取不到 ⇒ 整组不报」是同一条纪律：组合基线宁缺勿假。
    """
    per_date: Dict[str, List[Dict[str, Any]]] = {}
    for payload in payloads:
        for day in payload.get('days') or []:
            per_date.setdefault(day['date'], []).append(day)

    days: List[Dict[str, Any]] = []
    for date in sorted(per_date):
        entries = per_date[date]
        complete = len(entries) == len(payloads) and all(
            e.get('daily_pnl') is not None and e.get('net_worth') is not None for e in entries
        )
        if complete:
            days.append(
                {
                    'date': date,
                    'daily_pnl': round(sum(float(e['daily_pnl']) for e in entries), 2),
                    'net_worth': round(sum(float(e['net_worth']) for e in entries), 2),
                }
            )
        else:
            days.append({'date': date, 'daily_pnl': None, 'net_worth': None})
    return {'scope': 'portfolio', 'ledger_id': None, 'days': days}


def build_portfolio_daily_pnl_series(
    db: Session,
    family_id: int = 1,
    portfolio_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """组合级日序列（#871）：逐成员 `build_daily_pnl_series` 后按日求和。

    无成员账本（空组合）⇒ 空 days（`chain_twr` 转 `twr=None`，不造 0）。
    组合内转账在各成员自己的 `daily_pnl` 里已各自剔除，求和天然干净——
    这正是「Σ 成员」而不「先算 TWR 再平均」的原因（TWR 不可加）。
    """
    if portfolio_id is None:
        raise ValueError('组合级日序列需要 portfolio_id')
    member_ids = _portfolio_member_ledger_ids(db, family_id, portfolio_id)
    if not member_ids:
        return {'scope': 'portfolio', 'ledger_id': None, 'portfolio_id': portfolio_id, 'days': []}
    payloads = [
        build_daily_pnl_series(
            db,
            family_id=family_id,
            start_date=start_date,
            end_date=end_date,
            ledger_id=lid,
        )
        for lid in member_ids
    ]
    merged = _merge_member_series(payloads)
    merged['portfolio_id'] = portfolio_id
    return merged


def calculate_twr_by_scope(
    db: Session,
    scope: str = 'portfolio',
    family_id: int = 1,
    position_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
    symbol: Optional[str] = None,
    ledger_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """TWR 统一入口（#871）：`method=twr` 的包门面转派点。

    支持域与 `calculators.calculate_xirr_by_scope` 的 scope 语义对齐：
    - `portfolio` + `portfolio_id`：组合级（Σ 成员日序列，见模块 docstring）；
    - `portfolio` 无 `portfolio_id`（或家庭级调用）：家庭整体；
    - `ledger_id`：账户级（与 `/twr/` 端点同一条 `calculate_twr` 路径）；
    - `symbol` / `position`：**明确不支持**——产品级与单持仓没有独立的每日
      净资产序列，硬算会把家庭净资产当成某个标的的分母（#2133 立场）。
      抛 `XirrScopeParameterError`（视图映射 400，而不是默默的错数）。

    口径说明：日净资产序列天然含**全部 active 持仓**（`pnl_calendar._positions`
    不过滤 asset_type，货币基金等现金等价物在其中），故 TWR 是总资产口径；
    `include_cash_equivalents` 对本方法不生效（要剔除需引擎层加过滤，另行）。
    """
    if scope in ('symbol', 'position'):
        raise XirrScopeParameterError(
            f'TWR 不支持 scope={scope}：产品级/单持仓没有每日净资产序列，'
            '硬算会把家庭净资产当成某个标的的分母（#2133 立场）'
        )
    if portfolio_id is not None:
        series = build_portfolio_daily_pnl_series(
            db,
            family_id=family_id,
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        result = chain_twr(series)
        logger.info(
            f'TWR 计算完成(scope=portfolio, portfolio_id={portfolio_id}, '
            f'days_used={result["days_used"]}, days_skipped={result["days_skipped"]}, '
            f'twr={result["twr"]}): {result["start_date"]}~{result["end_date"]}'
        )
        return result
    return calculate_twr(db, family_id=family_id, start_date=start_date, end_date=end_date, ledger_id=ledger_id)
