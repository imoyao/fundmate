# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/17
# File : index_metrics.py
# app/services/index_metrics.py
"""指数详情页指标（#2278 · 阶段性收益 + 年化波动率 + 十大权重）。

数据策略（L3/L4 口径，用户已授权）：**按需抓 + TTL 缓存 + 不入库 + 可降级**——
外部请求集中在用户打开指数详情页时，缓存窗口内重复打开零外部请求；
本地 ``index_daily`` 仅 22 个乐咕核心码，行业/主题指数无覆盖，故日线走直连。

数据链（2026-10-17 实测定型）：
- **中证官网日线优先**（``direct_feeds.fetch_daily_csindex``）：一次请求给全历史
  （000300 实测 5290 行），且是 9 系中证专属码（931151 光伏产业等）的**唯一**
  数据源——腾讯对这类码返回 0 行（与 #167 中证2000 同款坑）；
- **腾讯兜底**：中证官网不覆盖国证系（399001 深证成指等）。⚠️ 裸码直传腾讯有
  市场误路由坑（``_tencent_symbol`` 把 0 开头一律当深市，而 000300 是沪市指数），
  故名录里带 ``exchange``（SH/SZ）时必须拼成 ``code.SH`` 形态传入；
- 两路都空 → 全字段 ``null``，前端诚实降级「—」，不编数。

权重走 akshare ``index_stock_cons_weight_csindex``（月频，实测 931151 → 50 行、
权重合计恰为 100.0；⚠️ ``ak.index_csindex`` 在 akshare 1.18.91 已不存在，不可用）。

缓存：进程内 + 文件两级（``CacheService``，与温度计同一基建）。收益日线 1h、
权重月频 24h。**无数据（两路全空 / 权重接口不适用）也进缓存**——负结果同样
避免同一指数每次打开都白打外部请求；网络级故障由底层 best-effort 吞掉后同样
落入「无数据」结果，TTL 过期后自然重试。

> 实现说明：本文件由两条分叉的半成品 worktree（feat/2278-index-detail-enhance 与
> feat/2278-index-info）合并取优而来——以 A 的「单服务 + 独立读端点 + CacheService
> 两级缓存」为骨架，吸收 B 的**自然月窗口口径**、**波动率样本 ≥20 阈值**与**纯函数
> 计算核**（便于确定性单测）。窗口键保持 ``m1/m3/ytd/y1/y2/y3`` 以匹配前端组件。
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.core.cache import CacheService
from app.domains.indices.models import IndexCatalog
from app.services.adapters import direct_feeds

# TTL：日线盘中不变化（收盘后微调一次）→ 1h；权重是月频 → 24h
_METRICS_CACHE = CacheService(namespace='index_detail')
_RETURNS_TTL_SECONDS = 3600
_WEIGHTS_TTL_SECONDS = 24 * 3600

# 阶段性收益窗口（key 与前端 IndexReturnsWindows 对齐）：months=None = 今年至今（特殊基期）
_WINDOWS: Tuple[Tuple[str, Optional[int]], ...] = (
    ('m1', 1),
    ('m3', 3),
    ('ytd', None),
    ('y1', 12),
    ('y2', 24),
    ('y3', 36),
)

_WEIGHT_TOP_N = 10
# 年化波动率最小日收益样本数：样本太少（<20）算出来的波动率没意义 → 诚实降级 None
_VOL_MIN_SAMPLES = 20


# ── 名录解析（与 index_profile 同源归一）────────────────────────────────
def _catalog_entry(db: Session, symbol: str) -> Optional[Tuple[str, Optional[str]]]:
    """名录命中返回 ``(裸码, exchange)``，未命中返回 ``None``（调用方转 404）。

    只取两列轻量字段；``exchange`` 可能是 ``NULL``（历史数据未回填）→ 上层按
    裸码启发式兜底。``_bare_index_code`` 与 index-profile 同源归一。
    """
    from app.services.index_profile import _bare_index_code

    code = _bare_index_code(symbol)
    if not code:
        raise ValueError('缺少指数代码')
    row = db.query(IndexCatalog.index_code, IndexCatalog.exchange).filter(IndexCatalog.index_code == code).first()
    if row is None:
        return None
    return row.index_code, row.exchange


def _fetch_daily_series(code: str, exchange: Optional[str]) -> Tuple[List[Tuple[str, float]], Optional[str]]:
    """拉全历史日线：中证官网优先（全历史一次拿全 + 9 系唯一源），腾讯兜底。

    腾讯兜底带交易所后缀（``code.SH``），规避裸码的市场误路由（见模块 docstring）；
    ``exchange`` 缺失时退回裸码启发式（``_tencent_symbol`` 内置）。全空返回
    ``([], None)``，不抛异常（best-effort，与 direct_feeds 各路一致）。
    """
    rows = direct_feeds.fetch_daily_csindex(code)
    if rows:
        return rows, 'csindex'
    symbol = f'{code}.{exchange}' if exchange in ('SH', 'SZ') else code
    rows = direct_feeds.fetch_daily_tencent(symbol)
    if rows:
        return rows, 'tencent'
    return [], None


# ── 纯函数：窗口计算（B 的自然月口径 + 不依赖外部抓取，便于确定性单测）────
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


def _last_index_on_or_before(dates: List[date], target: date) -> Optional[int]:
    """序列里 <= target 的最后一个下标；最早日期仍在 target 之后则 None。"""
    idx = bisect_right(dates, target)
    return idx - 1 if idx > 0 else None


def compute_period_returns(
    rows: List[Tuple[str, float]],
    today: Optional[date] = None,
    windows: Tuple[Tuple[str, Optional[int]], ...] = _WINDOWS,
    volatility: bool = True,
) -> Optional[Dict[str, Any]]:
    """由日线序列现算窗口收益 + 可选近 1 年年化波动率（自然月口径，纯函数）。

    Args:
        rows: ``[(trade_date_iso, close), ...]`` 升序（direct_feeds 输出形态）。
        today: 注入当前日期（测试确定性用）；默认 ``date.today()``。
        windows: 窗口集 ``[(key, months|None), ...]``；#2275 ETF 对比复用同一口径
            但只要 m1/m3/m6/y1（无 ytd/y2/y3），故参数化而不复制算法。
        volatility: 是否计算近 1 年年化波动率（ETF 对比行不需要）。

    Returns:
        ``{'index_code': None, 'as_of': str, 'source': None,
        'returns': {<windows keys>: float%|None}, 'volatility_y1': float%|None}``；
        序列少于 2 点（算不出任何收益）→ ``None``。
    """
    if len(rows) < 2:
        return None
    # 防御性按交易日升序：direct_feeds 契约保证升序，此处兜底乱序输入（纯函数不依赖调用方顺序）
    rows = sorted(rows, key=lambda r: r[0])
    latest_date, latest_close = rows[-1]
    if latest_close <= 0:
        return None

    # 窗口锚点 = 序列最新数据日（中证官网同口径：终点是最新收盘，不是日历今天）。
    # 锚 date.today() 会在周末/节假日把非 ytd 窗口的基期整体前移一个交易日：
    # 2026-10-17（周六）实测 931151 y1 偏离官网 4.6pp、m3 偏 3.5pp——只此一处根因。
    anchor = today or date.fromisoformat(latest_date)

    dates = [date.fromisoformat(d) for d, _ in rows]
    closes = [close for _, close in rows]

    def _ret(base_idx: Optional[int]) -> Optional[float]:
        if base_idx is None or closes[base_idx] <= 0:
            return None
        return round((latest_close / closes[base_idx] - 1) * 100, 2)

    # 各窗口基准收盘（None = 历史不足该窗口 → 前端「—」不编数）。
    returns: Dict[str, Optional[float]] = {}
    for key, months in windows:
        if months is None:  # 今年至今：基期 = 上一自然年最后一个交易日
            base_idx = _last_index_on_or_before(dates, date(anchor.year - 1, 12, 31))
        else:  # 自然月回溯（月末钳位），基准 = 目标日当日或之前最近交易日
            base_idx = _last_index_on_or_before(dates, _shift_months(anchor, -months))
        returns[key] = _ret(base_idx)

    # 年化波动率（近 1 年）：日频简单收益样本标准差 × √252；样本 < 20 → None。
    # 序列整体落在近 1 年内（起点晚于 1 年前）→ 窗口从首点起算，取全部可用收益。
    volatility_y1: Optional[float] = None
    if volatility:
        y1_idx = _last_index_on_or_before(dates, _shift_months(today, -12))
        start_idx = 0 if y1_idx is None else y1_idx
        daily_rets = [closes[i] / closes[i - 1] - 1 for i in range(start_idx + 1, len(closes))]
        if len(daily_rets) >= _VOL_MIN_SAMPLES:
            volatility_y1 = round(statistics.stdev(daily_rets) * math.sqrt(252) * 100, 2)

    return {
        'index_code': None,
        'as_of': latest_date,
        'source': None,
        'returns': returns,
        'volatility_y1': volatility_y1,
    }


# ── 纯函数：权重解析（B 的 _pick_rows，输出保持 A 的形状）───────────────
def _pick_weights(df: Any, top_n: int = _WEIGHT_TOP_N) -> Optional[Dict[str, Any]]:
    """DataFrame → A 形状的前 N 大权重聚合（纯转换，便于测试注入）。

    列名以源侧实测为准（2026-10-17）：日期 / 指数代码 / 指数名称 / 指数英文名称 /
    成分券代码 / 成分券名称 / 成分券英文名称 / 交易所 / 交易所英文名称 / 权重。
    源侧返回顺序**不是**权重降序（实测 931151 首行权重 1.266 而最大权重
    9.218 在后），必须自行排序。列缺失 / 空 df → ``None``（调用方转空形态）。
    """
    needed = ('日期', '成分券代码', '成分券名称', '权重')
    if not hasattr(df, 'columns') or any(c not in df.columns for c in needed):
        return None
    if len(df) == 0:
        return None
    as_of = str(df['日期'].iloc[0])[:10]
    parsed: List[Dict[str, Any]] = []
    total = 0.0
    for _, r in df.iterrows():
        try:
            weight = float(r['权重'])
        except (TypeError, ValueError):
            continue  # 坏行丢弃不编数
        raw_code = str(r['成分券代码']).strip()
        # 源侧形态 '000591'（str）；防御 pandas 把前导零吃掉读成 int
        if raw_code.isdigit() and len(raw_code) < 6:
            raw_code = raw_code.zfill(6)
        parsed.append(
            {
                'code': raw_code,
                'name': str(r['成分券名称']).strip(),
                'weight': round(weight, 3),
                'exchange': (str(r['交易所']).strip() if r.get('交易所') else None),
            }
        )
        total += weight
    if not parsed:
        return None
    parsed.sort(key=lambda item: item['weight'], reverse=True)
    top10 = parsed[:top_n]
    return {
        'as_of': as_of,
        'constituent_count': len(parsed),
        'total_weight': round(total, 2),
        'top10_weight': round(sum(item['weight'] for item in top10), 2),
        'top10': top10,
    }


# ── 降级形态 ───────────────────────────────────────────────────────────
def _empty_returns(code: str) -> Dict[str, Any]:
    """收益全量降级形态：两路全空 / 序列过短共用，前端逐项「—」。"""
    return {
        'index_code': code,
        'as_of': None,
        'source': None,
        'returns': {key: None for key, _ in _WINDOWS},
        'volatility_y1': None,
    }


def _empty_weights(code: str) -> Dict[str, Any]:
    """权重全量降级形态：接口失败 / 码族不适用 / 空返回共用，前端整块「—」。"""
    return {
        'index_code': code,
        'as_of': None,
        'frequency': 'monthly',
        'constituent_count': 0,
        'total_weight': None,
        'top10_weight': None,
        'top10': [],
    }


# ── 编排层：名录 + 缓存 + 抓取 ──────────────────────────────────────────
def build_index_returns(db: Session, symbol: str) -> Optional[Dict[str, Any]]:
    """阶段性收益 + 年化波动率（详情页指数区块，TTL 缓存）。

    Returns:
        结果 dict；**指数不在名录时返回 None**（调用方转 404，与 index-profile 同约定）。
    """
    entry = _catalog_entry(db, symbol)
    if entry is None:
        return None
    code, exchange = entry

    def _compute() -> Dict[str, Any]:
        rows, source = _fetch_daily_series(code, exchange)
        if not rows:
            return _empty_returns(code)
        result = compute_period_returns(rows)
        if result is None:
            return _empty_returns(code)
        result['index_code'] = code
        result['source'] = source
        return result

    return _METRICS_CACHE.get_or_set(f'returns:{code}', _compute, ttl=_RETURNS_TTL_SECONDS)


def build_index_weights(db: Session, symbol: str) -> Optional[Dict[str, Any]]:
    """十大权重 + 前十大集中度（详情页指数区块，月频数据 TTL 24h）。"""
    entry = _catalog_entry(db, symbol)
    if entry is None:
        return None
    code, _exchange = entry

    def _compute() -> Dict[str, Any]:
        try:
            from app.core.akshare_lazy import get_akshare

            ak = get_akshare()
            df = ak.index_stock_cons_weight_csindex(symbol=code)
        except Exception as e:  # noqa: BLE001 - 外部接口失败不阻断详情页
            logger.warning(f'指数权重抓取失败 code={code}: {e}')
            return _empty_weights(code)
        if df is None or getattr(df, 'empty', True):
            return _empty_weights(code)
        picked = _pick_weights(df)
        if picked is None:
            return _empty_weights(code)
        picked['index_code'] = code
        picked['frequency'] = 'monthly'
        return picked

    return _METRICS_CACHE.get_or_set(f'weights:{code}', _compute, ttl=_WEIGHTS_TTL_SECONDS)
