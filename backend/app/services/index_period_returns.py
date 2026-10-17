# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/17
# File : index_period_returns.py
# app/services/index_period_returns.py
"""指数阶段性收益（#2278 · 详情页指数区块「过去赚多少、波动多大」）。

按需拉日线序列 → 服务端算区间收益与年化波动 → **算完即弃，不入库**
（#2278 准入前提：不新增任何表/列；L3/L4 口径：按需取 + 缓存 + 可降级）。

数据链（``direct_feeds`` 既有链路，不新建源）：

1. 中证官网 ``fetch_daily_csindex``——0 系 / 9 系（CSI 码族）全覆盖，实测
   931151 / 000300 均可取；接口对未收录码返回空数组、不抛错。
2. 腾讯 ``fetch_daily_tencent`` 兜底——399 系等中证官网无日线的码
   （实测 sh931151 腾讯 0 行、中证官网正常，两源互补，故 csindex 优先；
   裸码前缀映射由 direct_feeds 内部 ``_tencent_symbol`` 兜底处理）。

两源皆空 → 返回 ``None``（整块降级「—」），不编数。

窗口口径（⚠️ 与中证官网抽样核对后如需调整，改 ``compute_period_returns`` 一处即可）：

- 近 1 月 / 3 月 / 1 年 / 2 年 / 3 年：按**自然月**回溯（月末钳位），
  基准 = 目标日**当日或之前最近一个交易日**的收盘（与中证「区间涨跌幅」
  常规口径一致）；
- 今年至今：基准 = 上一自然年最后一个交易日的收盘；
- 收益率 = 最新收盘 / 基准收盘 − 1；
- 历史不足（序列起点晚于基准需求）→ 该窗口 ``null``，不编数；
- 年化波动率（近 1 年）= 近 365 自然日日收益率**样本**标准差 × sqrt(252)，
  样本 < 20 个日收益降级 ``None``（样本太小的波动率没意义）。
"""

from __future__ import annotations

import math
import re
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.services.adapters.direct_feeds import fetch_daily_csindex, fetch_daily_tencent

# 进程内 TTL 缓存：code → (抓取时刻 monotonic, 聚合结果)。
# TTL = 6h：日线在收盘后定型，盘中打开看到的最新收盘一天内不变；
# 6h 足以挡住「同一晚多次打开详情页」的重复请求，又不至于把昨日结果
# 焊死到明天。网络异常/双源空**不进缓存**（下次查看重试——空结果可能是
# 瞬时通道故障，负缓存会把故障焊死，与 #2271 简介缓存同纪律）。
_TTL_SECONDS = 6 * 3600
_returns_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

# 拉取起点：近 3 年窗口 + 40 天余量（月末钳位最大偏差 ~3 天 + 交易日错位）
_SERIES_LOOKBACK_DAYS = 365 * 3 + 40


def _bare_code(symbol: str) -> str:
    """抽裸 6 位指数码（与 index_profile 同款归一，不信任入口形态）。"""
    m = re.search(r'\d{6}', (symbol or '').strip().upper())
    return m.group(0) if m else ''


def _parse_iso(text: str) -> Optional[date]:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _shift_months(d: date, months: int) -> date:
    """日期回溯 N 个自然月（月末钳位：03-31 回 1 个月 → 02-28/29，不越界）。"""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    for day in (d.day, 31, 30, 29, 28):  # 目标月没有 d.day → 取该月最后一天
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 1)  # 理论不可达


def _baseline_on_or_before(series: List[Tuple[str, float]], target: date) -> Optional[float]:
    """目标日**或之前**最近一个交易日的收盘；序列还没到该日 → None。"""
    best: Optional[float] = None
    for d, close in series:
        dd = _parse_iso(d)
        if dd is None or dd > target:
            break  # 升序序列：后面只会更大
        best = close
    return best


def _ytd_baseline(series: List[Tuple[str, float]], year: int) -> Optional[float]:
    """今年至今的基准：上一自然年最后一个交易日收盘。

    序列起点就在今年内（新指数）→ None（今年至今不可算，不从成立日冒充）。
    """
    year_start = date(year, 1, 1)
    best: Optional[float] = None
    for d, close in series:
        dd = _parse_iso(d)
        if dd is None or dd >= year_start:
            break
        best = close
    return best


def _annualized_volatility(series: List[Tuple[str, float]], today: date, days: int = 365) -> Optional[float]:
    """近 N 自然日日收益率年化波动率（× sqrt(252)）；日收益样本 <20 → None。"""
    cutoff = today - timedelta(days=days)
    closes = [c for d, c in series if (_parse_iso(d) or date.min) >= cutoff]
    rets: List[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev <= 0:
            continue
        rets.append(cur / prev - 1)
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)  # 样本方差
    return math.sqrt(var) * math.sqrt(252) * 100  # 年化 → %


def compute_period_returns(series: List[Tuple[str, float]], today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """由日线序列算 6 窗口收益率 + 近 1 年年化波动率（纯函数，便于测试）。

    Args:
        series: ``[(trade_date_iso, close), ...]`` 升序（direct_feeds 输出形态）。
        today: 注入当前日期（测试确定性用）；默认 ``date.today()``。

    Returns:
        ``{'as_of': str, 'windows': {key: float%|None, ...}, 'volatility_1y': float%|None}``；
        序列少于 2 点（算不出任何收益）→ ``None``。
    """
    today = today or date.today()
    if len(series) < 2:
        return None
    latest_date, latest_close = series[-1]
    if latest_close <= 0:
        return None

    last_d = _parse_iso(latest_date) or today

    def _ret(base: Optional[float]) -> Optional[float]:
        if base is None or base <= 0:
            return None
        return (latest_close / base - 1) * 100

    # 各窗口基准收盘（None = 历史不足该窗口 → 前端「—」不编数）
    windows: Dict[str, Optional[float]] = {
        '1m': _ret(_baseline_on_or_before(series, _shift_months(last_d, -1))),
        '3m': _ret(_baseline_on_or_before(series, _shift_months(last_d, -3))),
        'ytd': _ret(_ytd_baseline(series, last_d.year)),
        '1y': _ret(_baseline_on_or_before(series, _shift_months(last_d, -12))),
        '2y': _ret(_baseline_on_or_before(series, _shift_months(last_d, -24))),
        '3y': _ret(_baseline_on_or_before(series, _shift_months(last_d, -36))),
    }
    return {
        'as_of': latest_date,
        'windows': windows,
        'volatility_1y': _annualized_volatility(series, today=last_d),
    }


def _fetch_series(code: str) -> List[Tuple[str, float]]:
    """中证官网优先，腾讯兜底（两源互补，实测见模块 docstring）。"""
    start = date.today() - timedelta(days=_SERIES_LOOKBACK_DAYS)
    try:
        rows = fetch_daily_csindex(code, start_date=start)
    except Exception as e:  # noqa: BLE001 —— 源异常不可阻断详情页
        logger.warning(f'中证官网日线异常 code={code}: {e}')
        rows = []
    if rows:
        return rows
    # 腾讯兜底：裸码前缀映射（399 → sz 等）由 direct_feeds._tencent_symbol 处理
    try:
        return fetch_daily_tencent(code, start_date=start)
    except Exception as e:  # noqa: BLE001
        logger.warning(f'腾讯日线异常 code={code}: {e}')
        return []


def fetch_period_returns(symbol: str) -> Optional[Dict[str, Any]]:
    """按需取指数阶段性收益（详情页指数区块；L3：按需 + TTL 缓存 + 降级 None）。"""
    code = _bare_code(symbol)
    if not code:
        return None
    now = time.monotonic()
    if code in _returns_cache:
        ts, payload = _returns_cache[code]
        if now - ts < _TTL_SECONDS:
            return payload
    series = _fetch_series(code)
    if not series:
        return None  # 双源皆空：不缓存（瞬时故障下次重试）
    result = compute_period_returns(series)
    if result is None:
        return None  # 序列异常短：同样不缓存
    _returns_cache[code] = (now, result)
    return result
