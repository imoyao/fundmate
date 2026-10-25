# -*- coding: utf-8 -*-
"""账户级资金流动（#2616）：把 L1 分层落成「账户页能直接画」的数据。

## 这个模块解决什么

账户详情页此前只有持仓与占比，用户回答不了「这个账户我一共投进去多少、取出来多少、
现在值多少、到底赚了多少」。收益率回答不了这个问题（收益率高不代表投入规模合适），
只有资金流动能回答。

## 三层事实，别混

| 指标 | 来源 | 口径 |
|---|---|---|
| 累计入金 / 出金 / 净投入 | `cashflow_layers` 的 L1（`deposit` / `withdraw`） | **自开户以来**（累计语义不随区间变） |
| 逐笔流水 / 月度柱状 | 同上，按 `start_date`~`end_date` 过滤 | 区间视图 |
| 期末市值 | `pnl_calendar.build_daily_pnl_series` 的日净资产末值 | 与收益日历同源，不另算 |
| 现金残差 | `cashflow_layers.totals['cash_residual']` | **推导值**（不是对账单） |
| 累计收益 | `期末资产 − 净投入` | 期末资产 = 期末市值 + 现金残差 |

**为什么「累计」不跟着区间走**：带着区间算「累计入金」，用户把时间切到本月就会看到
「累计入金 0」，那不是他要的「我一共投了多少」。区间只影响列表与月度柱状，累计永远自
开户以来——这一点必须在页面上写明，否则同一屏两个「累计」会打架。

**为什么净值线不含现金残差**：`pnl_calendar` 的净资产是持仓市值口径（现金不落表，见
#2616 边界）。曲线加不上它，故现金残差单列在 totals 里，页面必须注明「净值线为持仓
市值，现金残差 XX 元未计入曲线」——两线差额（净投入线 vs 净值线）不等于累计收益时，
差额恰好是现金残差 + 未实现盈亏的口径差，说清楚比强行对齐更重要。
"""

import datetime as dt
from collections import OrderedDict
from typing import Optional

from app.core.time_utils import today_shanghai
from app.domains.ledgers.models import Ledger
from app.services.performance import cashflow_layers
from app.services.pnl_calendar import build_daily_pnl_series

#: 缺省区间长度（天）：与 pnl-calendar 的缺省口径保持一致的量级（近一年）
DEFAULT_RANGE_DAYS = 365


def _parse_date(value: Optional[str]) -> Optional[dt.date]:
    """YYYY-MM-DD → date；None / 空串 → None。格式错抛出 ValueError（由视图层转 400）。"""
    if value in (None, ''):
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f'日期格式应为 YYYY-MM-DD，收到 {value!r}') from exc


def _flow_payload(flow: dict) -> dict:
    """L1 流水 → 页面消费形态（金额已是元，方向用 `in` / `out` 不用符号）。"""
    direction = 'in' if flow['txn_type'] == 'deposit' else 'out'
    return {
        'date': flow['date'].isoformat(),
        'direction': direction,
        'amount': round(flow['amount'], 2),
        'asset_type': flow.get('asset_type'),
        'symbol': flow.get('symbol'),
    }


def _monthly(l1_flows: list, start: dt.date, end: dt.date) -> list:
    """按月上卷入金 / 出金（只出现在区间内的月份，缺月不补 0——补 0 会被读成「当月没动」）。"""
    buckets: 'OrderedDict[str, dict]' = OrderedDict()
    month = dt.date(start.year, start.month, 1)
    while month <= end:
        key = month.strftime('%Y-%m')
        buckets[key] = {'month': key, 'deposit': 0.0, 'withdraw': 0.0, 'net': 0.0}
        month = dt.date(month.year + (month.month == 12), (month.month % 12) + 1, 1)

    for flow in l1_flows:
        key = flow['date'].strftime('%Y-%m')
        if key not in buckets:
            continue
        if flow['txn_type'] == 'deposit':
            buckets[key]['deposit'] += flow['amount']
        else:
            buckets[key]['withdraw'] += flow['amount']

    result = []
    for item in buckets.values():
        item['deposit'] = round(item['deposit'], 2)
        item['withdraw'] = round(item['withdraw'], 2)
        item['net'] = round(item['deposit'] - item['withdraw'], 2)
        result.append(item)
    return result


def _net_worth_series(days: list, inception_flows: list) -> list:
    """日净资产 + 累计净投入阶梯线（同一天多条流水先合并，避免同 x 多点）。"""
    by_day: dict = {}
    for flow in inception_flows:
        delta = flow['amount'] if flow['txn_type'] == 'deposit' else -flow['amount']
        by_day[flow['date']] = by_day.get(flow['date'], 0.0) + delta

    series = []
    cumulative = 0.0
    for day in days:
        day_date = dt.date.fromisoformat(day['date'])
        cumulative += by_day.get(day_date, 0.0)
        series.append(
            {
                'date': day['date'],
                'net_worth': day.get('net_worth'),
                'cum_net_invested': round(cumulative, 2),
                'state': day.get('state'),
            }
        )
    return series


def build_ledger_cash_flow(
    db,
    family_id: int,
    ledger_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """账户级资金流动汇总（口径见 `docs/spec/cashflow-layers.md`）。

    Args:
        ledger_id: 必填，且必须属于当前家庭（跨家庭直接 `ValueError`，不泄漏存在性）。
        start_date / end_date: 区间视图（逐笔流水 / 月度柱状 / 净值曲线）；累计指标不受影响。
            缺省 end = 今日（上海），start = end − 365 天。

    返回（金额均为元）::

        {'ledger_id', 'start_date', 'end_date',
         'totals': {'deposit','withdraw','net_invested','cash_residual',
                    'market_value','end_asset','total_return','has_deposit_record'},
         'external_flows': [{'date','direction','amount','asset_type','symbol'}],
         'monthly': [{'month','deposit','withdraw','net'}],
         'net_worth_series': [{'date','net_worth','cum_net_invested','state'}]}
    """
    ledger = db.query(Ledger).filter(Ledger.id == ledger_id, Ledger.family_id == family_id).first()
    if ledger is None:
        raise ValueError('账户不存在')

    end = _parse_date(end_date) or today_shanghai()
    start = _parse_date(start_date) or (end - dt.timedelta(days=DEFAULT_RANGE_DAYS))
    if start > end:
        raise ValueError('start_date 不能晚于 end_date')

    # 累计口径：自开户以来（只截到 end，避免把未来的流水算进来）
    inception = cashflow_layers.build_layers(db, [ledger_id], family_id=family_id, end_date=end)
    # 区间口径：列表与月度柱状
    ranged = cashflow_layers.build_layers(db, [ledger_id], family_id=family_id, start_date=start, end_date=end)

    totals_raw = inception['totals']
    has_deposit = any(flow['txn_type'] == 'deposit' for flow in inception['l1'])

    series = build_daily_pnl_series(db, family_id, start.isoformat(), end.isoformat(), ledger_id)
    days = series.get('days') or []
    market_value = 0.0
    for day in reversed(days):
        if day.get('net_worth') is not None:
            market_value = float(day['net_worth'])
            break

    cash_residual = float(totals_raw['cash_residual'])
    net_invested = float(totals_raw['net_invested'])
    end_asset = round(market_value + cash_residual, 2)

    return {
        'ledger_id': ledger_id,
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'totals': {
            'deposit': float(totals_raw['deposit']),
            'withdraw': float(totals_raw['withdraw']),
            'net_invested': net_invested,
            # 推导值：缺流水会偏，页面须注明「推导」
            'cash_residual': cash_residual,
            'market_value': round(market_value, 2),
            'end_asset': end_asset,
            'total_return': round(end_asset - net_invested, 2),
            # 没有入金流水 ⇒ 净投入恒 0，页面不能把「0」当成「没赚钱」，要提示补录
            'has_deposit_record': has_deposit,
        },
        'external_flows': [_flow_payload(flow) for flow in ranged['l1']],
        'monthly': _monthly(ranged['l1'], start, end),
        'net_worth_series': _net_worth_series(days, inception['l1']),
        'coverage': {
            'has_any_price': series.get('has_any_price'),
            'days': len(days),
            'missing_nav_days': sum(1 for day in days if day.get('net_worth') is None),
            'amount_unit': 'yuan',
            'cash_residual_is_derived': True,
        },
    }
