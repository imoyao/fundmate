# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/4
# File : direct_feeds.py
# -*- coding: utf-8 -*-
"""
乖离率直连行情（绕开 akshare / 东财限流）

优先级：腾讯行情（股票/ETF/宽基指数） > 东财 push2his（申万行业 / 兜底）。
不依赖 akshare，避免其上游东财接口限流/封 IP 导致的运行时失败。

symbol 约定（与 bias/constants.py 一致）：
  - 申万一级行业: '801010.SI'  -> 东财 secid '90.801010'
  - 宽基指数    : '000300.SH'  -> 腾讯 'sh000300' / 东财 '1.000300'
  - ETF        : '510300.SH'  -> 腾讯 'sh510300'
  - 股票       : '600519.SH'  -> 腾讯 'sh600519'
  - 场外基金    : 腾讯/东财 K 线不支持净值，走 akshare 兜底（见 calculator._fetch_akshare）
"""

import time
from datetime import date, timedelta
from typing import List, Optional, Tuple

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


def fetch_close_eastmoney(secid: str, days: int = 90, timeout: int = 8) -> Optional[Tuple[List[float], str]]:
    """东财 K 线（申万行业 / 指数兜底）。带 Referer + 退避重试。"""
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3',
        'fields2': 'f51,f53',
        'klt': '101',  # 日线
        'fqt': '1',  # 前复权
        'beg': '0',
        'end': '20500101',
    }
    for _ in range(3):
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
            time.sleep(2)
    return None
