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

权重是**两路串联**（月频）：中证口径优先（akshare ``index_stock_cons_weight_csindex``，
实测 931151 → 50 行、权重合计恰为 100.0；⚠️ ``ak.index_csindex`` 在 akshare 1.18.91
已不存在，不可用），**口径不覆盖时回退国证官网**
（``adapters/index_weights.fetch_weights_cni``）。

⚠️ 为什么必须有第二路（2026-11-03 实测）：中证权重源**只发布中证系列**。深证/国证系
（399001 深证成指、399006 创业板指、899xxx 等）在中证官网没有权重文件，返回 HTML 404，
pandas 读它时抛「Excel file format cannot be determined」——名录 4100 只里约 2370 只
（58%）属此类，属**数据源不覆盖**而非抓取故障，由 ``_is_weight_scope_miss`` 识别。
回退**只对这种「口径不覆盖」触发**：中证系指数一次就拿到，不会多打一次国证请求；
中证通道的真故障（网络/解析）也不回退，否则会把「中证挂了」掩盖成「国证也没有」。
国证对不认识的码同样返回 200 + 「暂无数据」，故回退侧也用 attachment 头判定口径。

两套表头不同（中证：``成分券代码/成分券名称/权重/交易所``；国证：``样本代码/样本简称/
权重（%）``，且无交易所列），由 ``_normalize_weight_columns`` 先归一再到 ``_pick_weights``。

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
from app.services.adapters.index_weights import fetch_weights_cni

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
        # 波动率窗口与收益窗口同锚点（#2299 口径：锚数据日，非日历 today——
        # 自动变基合并时此处曾遗留 today 引用，CI 实测 _shift_months(None) 炸）
        y1_idx = _last_index_on_or_before(dates, _shift_months(anchor, -12))
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


# ── 纯函数：权重表头归一（中证 / 国证两套源 → 同一形状）─────────────────
# 国证官网实测列（2026-11-03）：日期 / 样本代码 / 样本简称 / 所属行业 /
# 总市值(亿元) / 权重（%）——注意「权重（%）」是全角括号，且**没有「交易所」列**。
# 中证口径（akshare）已是本表右值，映射对它是幂等的。
_WEIGHT_COLUMN_ALIASES: Dict[str, str] = {
    '样本代码': '成分券代码',
    '股票代码': '成分券代码',
    '样本简称': '成分券名称',
    '股票名称': '成分券名称',
}


def _normalize_weight_columns(df: Any) -> Any:
    """把两套权重表头映射到 ``_pick_weights`` 认的形状（幂等，只改列名不动行）。

    「权重」按**前缀**匹配：国证用「权重（%）」、中证用「权重」；认不出的列原样
    保留（``_pick_weights`` 只取必需列，多余列无害）。非 DataFrame / None 原样返回，
    让下游的「列缺失 → None」判据照旧生效。
    """
    if df is None or not hasattr(df, 'columns'):
        return df
    rename = {}
    for col in df.columns:
        text = str(col).strip()
        if text.startswith('权重'):
            rename[col] = '权重'
        elif text in _WEIGHT_COLUMN_ALIASES:
            rename[col] = _WEIGHT_COLUMN_ALIASES[text]
    return df.rename(columns=rename) if rename else df


# ── 纯函数：权重解析（B 的 _pick_rows，输出保持 A 的形状）───────────────
def _pick_weights(df: Any, top_n: int = _WEIGHT_TOP_N) -> Optional[Dict[str, Any]]:
    """DataFrame → A 形状的前 N 大权重聚合（纯转换，便于测试注入）。

    入参须是 ``_normalize_weight_columns`` 归一后的形状：日期 / 成分券代码 /
    成分券名称 / 权重，``交易所`` 可选（国证源没有该列 → 该字段为 None）。
    中证源侧另有指数代码/指数名称/英文名等列，多余列不参与计算。
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
    """权重全量降级形态：两路全空 / 接口失败 / 码族不适用共用，前端整块「—」。"""
    return {
        'index_code': code,
        'as_of': None,
        'frequency': 'monthly',
        'source': None,
        'constituent_count': 0,
        'total_weight': None,
        'top10_weight': None,
        'top10': [],
    }


def _is_weight_scope_miss(exc: Exception) -> bool:
    """判断异常是「码族不在中证权重口径内」，而不是抓取故障。

    WHY（2026-11-03 实测）：中证权重源是中证官网的月度 Excel，**只发布中证系列**。
    深证/国证系（399001 深证成指、399006 创业板指、899xxx 北证等）在中证官网
    没有对应文件，返回的是 HTML 404 页面，akshare 内部 pandas 读它时抛
    ``ValueError: Excel file format cannot be determined``。

    这不是「抓取失败」：名录 4100 只里约 58% 属此类（实测 2370 只）。原先把它们
    一律记 WARNING，等于把「数据源不覆盖」当故障报警——每码每 24h 一条，既误导
    排查方向，也让真正的网络/解析故障淹没在噪音里。

    该判据现在有**两个消费方**：决定记 debug 还是 WARNING（降噪），以及是否
    回退国证源（见 ``_fetch_weights_frame``）。两件事都必须只认「口径不覆盖」，
    故仍用错误特征而不是码族白名单：名录的 ``source`` / ``publisher`` 存在 NULL
    （sina 转发源无法权威判定发布方），按前缀猜码族会误伤 000xxx 里的非中证指数。
    """
    return isinstance(exc, ValueError) and 'Excel file format' in str(exc)


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


def _fetch_weights_frame(code: str) -> Tuple[Any, Optional[str]]:
    """权重帧 + 来源：中证口径优先，**口径不覆盖**时回退国证官网。

    回退只对「口径不覆盖」触发（``_is_weight_scope_miss``）：中证系指数一次就拿到，
    不会为它们多打一次国证请求；中证通道的真故障（网络 / 解析）也不回退——否则
    会把「中证挂了」掩盖成「国证也没有」，两路都空时失去排查线索。

    Returns:
        ``(df, 'csindex' | 'cni')``；两路都取不到 → ``(None, None)``（调用方转空形态）。
    """
    try:
        from app.core.akshare_lazy import get_akshare

        df = get_akshare().index_stock_cons_weight_csindex(symbol=code)
    except Exception as e:  # noqa: BLE001 - 外部接口失败不阻断详情页
        if not _is_weight_scope_miss(e):
            logger.warning(f'指数权重抓取失败 code={code}: {e}')
            return None, None
        # 口径不覆盖 ≠ 故障（详见 _is_weight_scope_miss）→ 回退国证
        logger.debug(f'中证权重口径不覆盖 code={code} → 回退国证')
    else:
        if df is not None and not getattr(df, 'empty', True):
            return df, 'csindex'
        logger.debug(f'中证权重空返回 code={code} → 试国证')

    df = fetch_weights_cni(code)
    if df is not None and not getattr(df, 'empty', True):
        return df, 'cni'
    return None, None


def build_index_weights(db: Session, symbol: str) -> Optional[Dict[str, Any]]:
    """十大权重 + 前十大集中度（详情页指数区块，月频数据 TTL 24h）。"""
    entry = _catalog_entry(db, symbol)
    if entry is None:
        return None
    code, _exchange = entry

    def _compute() -> Dict[str, Any]:
        df, source = _fetch_weights_frame(code)
        if df is None:
            return _empty_weights(code)
        picked = _pick_weights(_normalize_weight_columns(df))
        if picked is None:
            return _empty_weights(code)
        picked['index_code'] = code
        picked['frequency'] = 'monthly'
        picked['source'] = source
        return picked

    return _METRICS_CACHE.get_or_set(f'weights:{code}', _compute, ttl=_WEIGHTS_TTL_SECONDS)
