# -*- coding: utf-8 -*-
"""申万一级行业 · 官网单源取数与指标（#1431 换源 + #892 多维）

背景（#1431）：东财 `push2` / `push2his` 对本机出口按源 IP 突发配额限流，行业拥挤度的
「换手率分位」维长期取不到。调研包给出一条完全绕开东财的路径，本模块是其工程化落地：

- 数据源：**申万宏源研究官网**（akshare `index_hist_sw`，swsresearch.com），实测本机可用、
  数据到当日；行业清单经 `sw_index_first_info()` 取得（akshare 底层走 legulegu）。
- 只用 **收盘 + 成交额** 两个字段，**不依赖换手率 / 流通股本**（后者只在东财）→ 天然绕开限流。

产出两类指标（口径与调研包 `industry_metrics.py` 一致，便于与既有快照互相印证）：

1. **成交额占比分位**（拥挤度·资金热度维）：横截面「行业成交额 / 当日纳入行业成交额之和」
   → 过去 `window`（默认 250 交易日 ≈ 1 年）内的百分位。占比与分位都是比值、与量纲无关；
   分位只与**自身历史**比，剔除行业天然规模差异。
2. **乖离率 BIASn**：`(收盘 − MA_n) / MA_n × 100`，n ∈ {6, 20, 60}（简单算术均线）。
   - 6 日 ≈ 一周（短期情绪），20 日 ≈ 一个月（主流），60 日 ≈ 一个季度（中期趋势）；
   - 与既有 `bias/calculator.py` 的 `LOGBIAS`（对数 EMA20，阈值 ±15/±5）**口径不同、互不替代**：
     本模块为**行业维度**的简单 MA 多窗口口径，LOGBIAS 语义保持不变。

与 `industry_crowding.py` 的关系：本模块只负责取数与上述指标；PB 分位维（估值视角）仍由
`industry_crowding.py` 的 legulegu / baostock / tushare 路径提供，两者在 `_extra_dims()` 汇合，
**失败互不影响**（任一维缺失只置 None，绝不抛异常阻塞 `TemperatureJob`）。

请求规范（对齐调研包实测参数）：串行 + `random.uniform(0.25, 0.6)` 抖动 + 指数退避（最多 3 次）；
31 行业串行约 45~60s，每日一次可接受。
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Sequence, Tuple

from loguru import logger

try:
    import pandas as pd

    HAS_PANDAS = True
except Exception as e:  # noqa: BLE001
    HAS_PANDAS = False
    logger.warning('申万行业单源依赖缺失(pandas)：{}', e)

# ── 单源请求参数（调研包实测值）──
SLEEP_MIN, SLEEP_MAX = 0.25, 0.6
MAX_RETRY = 3


def _sleep(seconds: float) -> None:
    """睡眠间接层：测试可 patch 为空操作，避免离线用例被抖动/退避拖慢。"""
    time.sleep(seconds)


# ── 指标参数 ──
RANK_WINDOW = 250  # 占比分位滚动窗口（交易日 ≈ 1 年）
MIN_PERIODS = 20  # 最小样本数（与 industry_crowding 既有口径一致）
BIAS_WINDOWS: Tuple[int, ...] = (6, 20, 60)
EXPECTED_INDUSTRY_COUNT = 31  # 申万现行一级行业数（2021 版）


def list_sw_industries() -> Dict[str, str]:
    """申万一级行业清单：`{code: name}`，code 已去 `.SI` 后缀（如 `801010`）。

    数据源为 akshare `sw_index_first_info()`（底层走 legulegu `/stockdata/sw-industry-overview`）。
    数量与 `EXPECTED_INDUSTRY_COUNT` 不一致时**只告警不报错**（口径可能调整，不阻塞主链路）；
    失败返回 `{}`（上层据此走降级）。
    """
    try:
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        df = ak.sw_index_first_info()
        if df is None or df.empty or '行业代码' not in df.columns or '行业名称' not in df.columns:
            return {}
        out = {
            str(code).replace('.SI', '').strip(): str(name).strip()
            for code, name in zip(df['行业代码'], df['行业名称'])
            if str(code).strip()
        }
        if len(out) != EXPECTED_INDUSTRY_COUNT:
            logger.warning(
                '申万一级行业清单为 {} 个（预期 {}），口径可能已调整，请核对 bias/constants.py',
                len(out),
                EXPECTED_INDUSTRY_COUNT,
            )
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning('申万行业清单获取失败: {}', str(e)[:80])
        return {}


def _fetch_one(code: str) -> Optional['pd.DataFrame']:
    """单行业日线：返回含 `date` / `close` / `amount` 列的 DataFrame；失败返回 None。

    指数退避重试（最多 3 次）；字段缺失（上游改版）按失败处理并告警。
    """
    from app.core.akshare_lazy import get_akshare

    ak = get_akshare()
    for attempt in range(1, MAX_RETRY + 1):
        try:
            df = ak.index_hist_sw(symbol=code)
            if df is None or df.empty:
                return None
            if not {'日期', '收盘', '成交额'}.issubset(set(df.columns)):
                logger.warning('index_hist_sw 字段变化({})：{}', code, list(df.columns))
                return None
            out = df[['日期', '收盘', '成交额']].copy()
            out['日期'] = pd.to_datetime(out['日期'], errors='coerce')
            out['收盘'] = pd.to_numeric(out['收盘'], errors='coerce')
            out['成交额'] = pd.to_numeric(out['成交额'], errors='coerce')
            out = out.rename(columns={'日期': 'date', '收盘': 'close', '成交额': 'amount'})
            out = out.dropna(subset=['date']).drop_duplicates(subset=['date'], keep='last')
            return out if not out.empty else None
        except Exception as e:  # noqa: BLE001
            if attempt == MAX_RETRY:
                logger.warning('申万行业日线抓取失败({})：{}', code, str(e)[:80])
                return None
            _sleep(random.uniform(1.0, 2.0) * attempt)  # 指数退避
    return None


def fetch_sw_daily(codes: Optional[List[str]] = None) -> 'pd.DataFrame':
    """串行抓取全部（或指定）申万一级行业日线，返回长表 `[date, code, close, amount]`。

    单行业之间随机抖动 `SLEEP_MIN ~ SLEEP_MAX` 秒；单行业失败**跳过、不影响其他行业**。
    """
    if not HAS_PANDAS:
        return pd.DataFrame(columns=['date', 'code', 'close', 'amount'])
    if codes is None:
        codes = list(list_sw_industries().keys())
    frames = []
    for code in codes:
        df = _fetch_one(code)
        if df is not None and not df.empty:
            df = df.copy()
            df['code'] = code
            frames.append(df)
        _sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
    if not frames:
        return pd.DataFrame(columns=['date', 'code', 'close', 'amount'])
    raw = pd.concat(frames, ignore_index=True)
    return raw[['date', 'code', 'close', 'amount']]


def _roll_rank(share: 'pd.Series', window: int = RANK_WINDOW) -> 'pd.Series':
    """t 时刻取值在过去 `window` 个交易日内的百分位（0~100，**含自身**）。

    含自身（`x <= x[-1]`）与调研包 `industry_metrics.py` 一致；
    历史不足 `MIN_PERIODS` 天时为 NaN（调用方据此判定该维不可用）。
    """
    return share.rolling(window, min_periods=MIN_PERIODS).apply(lambda x: float((x <= x[-1]).mean() * 100.0), raw=True)


def compute_share_metrics(daily: 'pd.DataFrame', window: int = RANK_WINDOW) -> Dict[str, dict]:
    """成交额占比分位：`{code: {amount_pct, amount_pct_rank, history_days, window}}`。

    - 占比分母 = **当日纳入计算的申万行业成交额之和**（横截面，单源自洽，与中证全指口径不同）；
    - 分位 = 当前占比在过去 `window` 个交易日内的百分位；
    - 数据不足（< `MIN_PERIODS` 天）的行业不返回，交由上层降级。
    """
    out: Dict[str, dict] = {}
    if not HAS_PANDAS or daily is None or daily.empty:
        return out
    amount = daily.pivot_table(index='date', columns='code', values='amount', aggfunc='last')
    if amount.empty:
        return out
    total = amount.sum(axis=1, skipna=True).replace(0, pd.NA)
    share = amount.div(total, axis=0)

    for code in share.columns:
        s = share[code].dropna()
        if len(s) < MIN_PERIODS:
            continue
        rank = _roll_rank(s, window).dropna()
        if rank.empty:
            continue
        out[str(code)] = {
            'amount_pct': round(float(s.iloc[-1]) * 100, 2),
            'amount_pct_rank': round(float(rank.iloc[-1]), 1),
            'history_days': int(len(s)),
            'window': int(window),
        }
    return out


def compute_bias_metrics(daily: 'pd.DataFrame', windows: Sequence[int] = BIAS_WINDOWS) -> Dict[str, dict]:
    """乖离率 BIASn（简单 MA 口径）：`{code: {'bias6': x, 'bias20': y, 'bias60': z}}`。

    `BIASn = (收盘 − MA_n) / MA_n × 100`，MA_n 为简单算术移动平均。
    历史不足 `n` 天时该窗口为 None；**绝不抛异常**。
    """
    out: Dict[str, dict] = {}
    if not HAS_PANDAS or daily is None or daily.empty:
        return out
    close = daily.pivot_table(index='date', columns='code', values='close', aggfunc='last')
    if close.empty:
        return out

    mas = {n: close.rolling(int(n)).mean() for n in windows}
    for code in close.columns:
        row: Dict[str, Optional[float]] = {}
        has_value = False
        for n in windows:
            c = close[code]
            ma = mas[n][code]
            cur_close, cur_ma = c.iloc[-1], ma.iloc[-1]
            if pd.isna(cur_close) or pd.isna(cur_ma) or float(cur_ma) == 0:
                row[f'bias{n}'] = None
            else:
                row[f'bias{n}'] = round((float(cur_close) - float(cur_ma)) / float(cur_ma) * 100, 2)
                has_value = True
        if has_value:
            out[str(code)] = row
    return out


def fetch_sw_metrics(
    codes: Optional[List[str]] = None,
    window: int = RANK_WINDOW,
    bias_windows: Sequence[int] = BIAS_WINDOWS,
) -> Dict[str, dict]:
    """一步到位：取数 + 计算，返回 `{code: {占比分位字段..., biasN 字段...}}`。

    这是给 `industry_crowding.py` 用的主入口：**不抛异常**，取数失败返回 `{}`（上层降级）。
    """
    try:
        daily = fetch_sw_daily(codes)
        if daily is None or daily.empty:
            return {}
        merged = compute_share_metrics(daily, window=window)
        for code, bias in compute_bias_metrics(daily, windows=bias_windows).items():
            merged.setdefault(code, {}).update(bias)
        return merged
    except Exception as e:  # noqa: BLE001
        logger.warning('申万行业指标计算失败（已降级）: {}', str(e)[:80])
        return {}
