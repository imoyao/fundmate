# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/4
# File : direct_feeds.py
# -*- coding: utf-8 -*-
"""
直连行情适配（腾讯 / 东财 / 申万，绕开 akshare 限流与 V8 风险）

**归属（2026-10-01）**：本模块原在 `services/bias/`，因 index_daily job（sync 家族）也要
用同一路腾讯行情，跨家族共享件按 `architecture.md` §6「跨家族共享件一律放 services/ 顶层」
上提到 `services/adapters/`（家族包内只留该家族独有实现）。依赖方向仍是叶子：仅 core / 标准库 / requests。

优先级：
  - 申万行业        : 申万宏源研究官网（akshare index_hist_sw，非东财） > 东财 push2his 兜底；
  - 股票/ETF/宽基指数: 腾讯行情 > 东财 push2his 兜底。
不依赖单点数据源，避免某一路（尤其东财 push2his）限流/封 IP 导致的运行时全败。

东财 push2his 属「突发配额后限流」型通道（2026-09-12 隔离实证：隔离探针前 2 次 200，
随后连续失败 RemoteDisconnected），故一律降为**兜底**并配长退避（见 _EM_BACKOFF_BASE）。

symbol 约定（与 bias/constants.py 一致）：
  - 申万一级行业: '801010.SI'  -> 东财 secid '90.801010'
  - 宽基指数    : '000300.SH'  -> 腾讯 'sh000300' / 东财 '1.000300'
  - ETF        : '510300.SH'  -> 腾讯 'sh510300'
  - 股票       : '600519.SH'  -> 腾讯 'sh600519'
  - 场外基金    : 腾讯/东财 K 线不支持净值，走 akshare 兜底（见 calculator._fetch_akshare）
"""

import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import requests
from loguru import logger

_TENCENT = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
_EASTMONEY = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
_HEAD_T = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
_HEAD_E = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/',
}

# 市场后缀 -> 腾讯前缀 / 东财指数 secid 前缀
_SUFFIX_TENCENT = {'SH': 'sh', 'SZ': 'sz', 'BJ': 'bj'}
_SUFFIX_EM_INDEX = {'SH': '1', 'SZ': '0', 'BJ': '0'}

# 东财退避基数（秒）：#1431 —— 东财为「突发配额后限流」通道，退避窗口显著拉长，
# 避免持续冲击同一出口加重封禁；配合重试次数下调为 2。
_EM_BACKOFF_BASE = 8.0
_EM_RETRIES = 2

# 腾讯单页覆盖的自然日跨度（2026-10-01 实测：接口 count 上限 800 条交易日，
# 1200 自然日返回 798 条；取 1400 天留冗余，满页即约 800 条）。
_TENCENT_PAGE_SPAN_DAYS = 1400
# 分页之间的礼貌间隔（秒）：同一出口连续翻页，别打成突发请求
_TENCENT_PAGE_INTERVAL = 0.5
# 分页页数上限（防御）：16 页 × 800 条 ≈ 12800 个交易日，足够覆盖任何指数的成立以来
_TENCENT_MAX_PAGES = 16


def _split_code(symbol: str) -> Tuple[str, str]:
    """'000300.SH' -> ('000300', 'SH')；无后缀按裸码处理。"""
    symbol = symbol.strip().upper()
    if '.' in symbol:
        code, suffix = symbol.rsplit('.', 1)
        return code, suffix
    return symbol, ''


def _tencent_symbol(symbol: str) -> str:
    """转腾讯前缀代码：已带 sh/sz/bj 直接小写返回；否则按后缀补全。"""
    if symbol.lower().startswith(('sh', 'sz', 'bj')):
        return symbol.lower()
    code, suffix = _split_code(symbol)
    prefix = _SUFFIX_TENCENT.get(suffix, '')
    if prefix:
        return prefix + code
    # 裸码兜底：6/5/9 开头视为沪市
    return ('sh' if code[0] in ('6', '5', '9') else 'sz') + code


def _eastmoney_secid(symbol: str) -> Optional[str]:
    """申万行业 '801010.SI' -> '90.801010'；指数 '000300.SH' -> '1.000300'；否则 None。"""
    code, suffix = _split_code(symbol)
    if suffix == 'SI':
        return f'90.{code[:6]}'
    if suffix in _SUFFIX_EM_INDEX:
        return f'{_SUFFIX_EM_INDEX[suffix]}.{code}'
    return None


def fetch_close_tencent(symbol: str, days: int = 90, timeout: int = 8) -> Optional[Tuple[List[float], str]]:
    """腾讯 K 线（股票/ETF/宽基指数）。返回 (收盘价序列, 最后交易日) 或 None。"""
    end = date.today()
    start = end - timedelta(days=days + 15)
    sym = _tencent_symbol(symbol)
    param = f'{sym},day,{start:%Y-%m-%d},{end:%Y-%m-%d},800,qfq'
    try:
        r = requests.get(_TENCENT, params={'param': param}, headers=_HEAD_T, timeout=timeout)
        r.raise_for_status()
        item = r.json().get('data', {}).get(sym, {})
        rows = item.get('qfqday') or item.get('day') or []
        closes = [float(x[2]) for x in rows if isinstance(x, list) and len(x) >= 3]
        if closes:
            return closes, str(rows[-1][0])[:10]
    except Exception as e:  # noqa: BLE001
        logger.debug(f'腾讯行情失败 {symbol}: {e}')
    return None


def fetch_kline_tencent(
    symbol: str,
    start: date,
    end: date,
    count: int = 800,
    timeout: int = 12,
) -> List[Tuple[str, float]]:
    """腾讯日线 K 线（**含交易日**——这是与 `fetch_close_tencent` 的唯一差别）。

    返回 `[(trade_date, close), ...]` **升序**；无数据 / 失败返回 `[]`（best-effort）。

    字段形态（2026-10-01 实测）：每行 `[日期, 开, 收, 高, 低, 量]`，故 `x[2]` 是**收盘**。
    已与东财 push2his 逐值核对（沪深300 2026-09-30 两源同为 4357.62）。宽基指数不复权、
    源侧落在 `day` 键（ETF/股票可能在 `qfqday`），故两者都取，顺序不影响语义。
    """
    sym = _tencent_symbol(symbol)
    param = f'{sym},day,{start:%Y-%m-%d},{end:%Y-%m-%d},{count},qfq'
    try:
        r = requests.get(_TENCENT, params={'param': param}, headers=_HEAD_T, timeout=timeout)
        r.raise_for_status()
        item = r.json().get('data', {}).get(sym) or {}
        rows = item.get('qfqday') or item.get('day') or []
    except Exception as e:  # noqa: BLE001
        logger.debug(f'腾讯日线失败 {symbol}: {e}')
        return []
    out: List[Tuple[str, float]] = []
    for x in rows:
        if not (isinstance(x, list) and len(x) >= 3):
            continue
        try:
            out.append((str(x[0])[:10], float(x[2])))
        except (TypeError, ValueError):
            continue
    return out


def fetch_daily_tencent(
    symbol: str,
    start_date: Optional[date] = None,
    timeout: int = 12,
    max_pages: int = _TENCENT_MAX_PAGES,
) -> List[Tuple[str, float]]:
    """腾讯日线**分页回补**：返回 `[(trade_date, close), ...]` 升序、已去重。

    腾讯单次最多 800 个交易日，长历史靠「以本页首日为新的区间终点」往前翻页实现
    （`start_date=None` 翻到源侧耗尽＝成立以来；给定日期则覆盖到该日即止）。

    去重口径：同日多页重叠（实测相邻页会在边界日重叠一天）取**先出现**的那条——
    先出现的是更靠近今天的那一页，与「最新数据优先」一致；两页同值，实际无差异。

    成本：每页 1 个 HTTP 请求 + 页间 0.5s 礼貌间隔。沪深300 成立以来约 7 页。
    任何一页取空即停（视作源侧耗尽或通道异常），已取到的数据照常返回。
    """
    collected: Dict[str, float] = {}
    end = date.today()
    start_iso = start_date.isoformat() if start_date else None

    for page in range(max_pages):
        # 首页区间两种定界，别混（2026-10-01 真机实测踩坑）：
        # - 给了 start_date（增量）：**首页就按它定界**，一页取完即止。若沿用「固定跨
        #   page_span」，增量会一次拉回 800 条≈3.2 年（实测），与韭圈儿侧的 12 月口径
        #   不一致，且每次都白写数百行无用 upsert。
        # - 未给（全量）：从今天往前跨 page_span，再由后续页继续往前翻到成立以来。
        page_start = start_date if (page == 0 and start_date) else end - timedelta(days=_TENCENT_PAGE_SPAN_DAYS)
        rows = fetch_kline_tencent(symbol, page_start, end, timeout=timeout)
        if not rows:
            break
        for trade_date, close in rows:
            collected.setdefault(trade_date, close)
        if start_iso and page_start.isoformat() <= start_iso:
            break  # 首页已按 start_date 定界（或分页翻到了该日），覆盖完整区间
        # 本页最旧交易日：源侧实测升序（rows[0] 最旧），但取 min 以免依赖返回顺序——
        # 顺序假设一旦被源侧改掉，翻页会静默退化成「原地打转」。
        first = min(trade_date for trade_date, _ in rows)
        next_end = date.fromisoformat(first) - timedelta(days=1)
        if next_end >= end:  # 无进展保护：源侧首日不变时立即收手，避免空转翻页
            break
        end = next_end
        if page < max_pages - 1:
            time.sleep(_TENCENT_PAGE_INTERVAL)

    return sorted(collected.items())


def fetch_close_eastmoney(secid: str, days: int = 90, timeout: int = 8) -> Optional[Tuple[List[float], str]]:
    """东财 K 线（申万行业兜底 / 指数兜底）。带 Referer + 长退避重试（#1431）。"""
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3',
        'fields2': 'f51,f53',
        'klt': '101',  # 日线
        'fqt': '1',  # 前复权
        'beg': '0',
        'end': '20500101',
    }
    for attempt in range(_EM_RETRIES):
        try:
            r = requests.get(_EASTMONEY, params=params, headers=_HEAD_E, timeout=timeout)
            r.raise_for_status()
            kl = (r.json().get('data') or {}).get('klines') or []
            if not kl:
                break
            parsed = [x.split(',') for x in kl if ',' in x]
            closes = [float(p[1]) for p in parsed]
            if closes:
                return closes[-days:] or closes, str(parsed[-1][0])[:10]
        except Exception as e:  # noqa: BLE001
            logger.debug(f'东财行情失败 {secid}: {e}')
            if attempt < _EM_RETRIES - 1:
                time.sleep(_EM_BACKOFF_BASE * (attempt + 1))  # 8s / 16s 递增退避
    return None


def fetch_close_sw_industry(symbol: str, days: int = 90) -> Optional[Tuple[List[float], str]]:
    """申万行业日线（申万宏源研究官网，akshare index_hist_sw；**非东财**，作为申万行业首选源）。

    symbol 约定：'801010.SI' -> akshare index_hist_sw('801010', period='day')。
    非申万后缀直接返回 None（交回上层走腾讯/东财）。
    返回 (收盘价序列, 最后交易日) 或 None；异常一律吞掉降级，不阻塞主链路。
    """
    code, suffix = _split_code(symbol)
    if suffix != 'SI':
        return None
    try:
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        df = ak.index_hist_sw(symbol=code[:6], period='day')
        if df is None or df.empty or '收盘' not in df.columns:
            return None
        df = df.sort_values('日期')
        closes = df['收盘'].astype(float).tolist()
        if not closes:
            return None
        return closes[-days:], str(df['日期'].iloc[-1])[:10]
    except Exception as e:  # noqa: BLE001
        logger.debug(f'申万行业行情失败 {symbol}: {e}')
    return None
