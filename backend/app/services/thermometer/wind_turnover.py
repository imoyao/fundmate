# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/25
# File : wind_turnover.py
# backend/app/services/thermometer/wind_turnover.py

"""申万一级行业日频换手率 · Wind EDB 源（#1502 步骤 1）。

**接的是哪条缝**：温度计换手率维度此前只有两条路——fundfof（未授权临时源，
``industry_crowding`` 优先级 0）与东财 push2his（限流敏感，仅 legulegu 兜底路径的
8 个中证行业）。申万官网单源路径（31 行业的默认主力）**根本没有换手率**——中证
官网不提供、东财不敢打。本模块用 Wind EDB 授权源把这条缝补上：

- ``industry_crowding._sw_share_records``（31 行业默认路径）：``turnover`` 从
  恒 ``None`` 变为真实值 + 历史分位；
- ``industry_crowding._extra_dims``（legulegu 兜底路径）：Wind 为主、东财降兜底，
  摘掉「换手率唯东财」的单点。

数据形状与纪律见 :mod:`app.services.adapters.wind_edb`（精确指标名逐行业查、
增量窗口、行业间留间隔）。fundfof 的关停属 #1502 步骤 3（60 日维度自算后），
本模块不动它的开关——先让免费栈具备**替代能力**，再摘未授权源。

**分位窗口的诚实口径**（2026-10-25 实测）：EDB 取数工具单次返回约 **1200 条封顶**
（请求 2010-06 起实际只回 2021-10-25 起 ≈1212 行），故历史分位窗口 ≈ **5 年**而非
东财路径的 15 年——满足 200 天下限，但与东财/legulegu 路径的分位**不可直接比大小**。
需要更长窗口时走「向前翻页多拉几段拼接」，本期不做（收益递减）。

缓存：``CACHE_FILE_DIR`` 下 ``wind_edb_turnover/<code>.csv``，语义与东财
``em_industry_hist`` 一致（新鲜直接复用 0 请求；过期只拉增量）。
"""

import os
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from loguru import logger

from app.core.cache import resolve_cache_subdir
from app.services.adapters.wind_edb import TURNOVER_INDICATOR, fetch_edb_series, is_available

#: 全历史起点：与行业拥挤度的分位窗口对齐（2010-06 起，见 industry_crowding 模块头）。
_FULL_SYNC_BEGIN = date(2010, 6, 1)

#: 行业间请求间隔（秒）：Wind 是授权源、无东财式 WAF，但仍保持克制。
_REQUEST_GAP_SECONDS = 0.5

#: 分位窗口下限：与 _turnover_rank 同规矩（历史不足 200 天不给分位）。
_MIN_HISTORY = 200


def cache_dir() -> str:
    """Wind EDB 换手率缓存目录（运行时解析，随 env CACHE_FILE_DIR 生效）。"""
    return str(resolve_cache_subdir('wind_edb_turnover'))


def _cache_path(code: str) -> str:
    return os.path.join(cache_dir(), f'{code}.csv')


def _load_cache(code: str) -> Optional[pd.DataFrame]:
    """读缓存为 DataFrame（index=date，列 turnover）；不存在 / 损坏回 None。"""
    path = _cache_path(code)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, parse_dates=['date'], index_col='date')
        return df if not df.empty else None
    except Exception as e:  # noqa: BLE001  缓存坏行不阻塞：当作无缓存重拉
        logger.warning(f'[#1502] Wind 换手率缓存损坏 {code}，重拉: {e}')
        return None


def _save_cache(code: str, df: pd.DataFrame) -> None:
    os.makedirs(cache_dir(), exist_ok=True)
    df.to_csv(_cache_path(code), index_label='date')


def _recent_trading_day() -> date:
    """最近交易日（节假日由调用方「今天-3 天」兜底放宽，与东财缓存同规矩）。"""
    today = date.today()
    if today.weekday() < 5:
        return today
    return today - timedelta(days=today.weekday() - 4)


def _is_fresh(df: pd.DataFrame) -> bool:
    """缓存最新日期 >= 最近交易日，或落在 3 天内（长假兜底）。"""
    last = df.index[-1].date()
    return last >= max(_recent_trading_day(), date.today() - timedelta(days=3))


def wind_turnover_hist(code: str, name: str) -> Optional[pd.DataFrame]:
    """某申万一级行业的日频换手率序列（缓存优先 + 增量）。

    Args:
        code: 申万一级行业代码（``801010``）。
        name: 行业名（``农林牧渔``），拼精确指标名用。

    Returns:
        DataFrame（index=date 升序，列 ``turnover``）；Wind 未配置 / 上游失败回
        ``None``（调用方降级，绝不抛异常阻塞温度计主链路）。
    """
    cached = _load_cache(code)
    if cached is not None and _is_fresh(cached):
        return cached

    if not is_available():
        # 未配置是**可选组件缺失**：debug 级即可，别在每次温度任务里刷 warning
        logger.debug('[#1502] Wind EDB 未配置，换手率走原路径')
        return cached

    indicator = TURNOVER_INDICATOR.format(name=name)
    try:
        if cached is None:
            series = fetch_edb_series(indicator, _FULL_SYNC_BEGIN, date.today())
        else:
            begin = cached.index[-1].date() + timedelta(days=1)
            series = fetch_edb_series(indicator, begin, date.today()) if begin <= date.today() else {}
    except Exception as e:  # noqa: BLE001  上游故障：回缓存（可能 stale），不阻塞主链路
        logger.warning(f'[#1502] Wind 换手率取数失败 {code} {name}: {str(e)[:80]}')
        return cached

    if not series:
        return cached
    fresh = pd.DataFrame(
        {'turnover': list(series.values())},
        index=pd.to_datetime(list(series.keys())),
    )
    merged = fresh if cached is None else (pd.concat([cached[~cached.index.isin(fresh.index)], fresh]).sort_index())
    _save_cache(code, merged)
    return merged


def wind_turnover_rank(code: str, name: str) -> Optional[dict]:
    """换手率分位（Wind 源）：当前值 + 历史百分位。

    返回 ``{'turnover': 当前值, 'turnover_rank': 历史百分位}``；历史不足
    ``_MIN_HISTORY`` 天或无数据回 ``None``。分位公式与
    ``industry_crowding._turnover_rank`` 一致（同口径，勿在此再造第二套）。
    """
    df = wind_turnover_hist(code, name)
    if df is None or df.empty:
        return None
    s = df['turnover'].dropna()
    if len(s) < _MIN_HISTORY:
        return None
    cur = s.iloc[-1]
    return {
        'turnover': round(float(cur), 2),
        'turnover_rank': round(float((s < cur).mean() * 100), 1),
    }
