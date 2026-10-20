# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/18
# File : etf_scale_fee.py
# app/services/etf_scale_fee.py
"""指数详情页 ETF 对比表的「规模 / 费率」取数（#2333）。

数据链（2026-10-18 本机实测定型，替代 issue 早期「免费 JSON 源」假设——逐一排查
确认东财 JSON 系无运作费用字段、腾讯无基金档案、新浪空返回，HTML 双源是唯一可行路径）：

- **规模（亿元，TTL 缓存不入库）**：
  - 沪市主源：上交所 ``query.sse.com.cn/commonQuery.do``（sqlId 同 akshare
    ``fund_etf_scale_sse``；**必须带 Referer: https://www.sse.com.cn/**，否则拒）。
    整表 924 行、一次请求全场，只有份额列（``TOT_VOL`` 万份）⇒ 规模 = 份额 × 净值，
    净值复用对比表既有净值链（``nav_map``，#2275 的 ``fund_etf_fund_daily_em``）。
  - 深市主源：深交所 ``fund.szse.cn/api/report/ShowReport``（SHOWTYPE=xlsx，
    CATALOGID=1000_lf，Referer 同站必带）。整表 1071 行，**自带净值列** ⇒
    份额 × 净值直接得亿元，不依赖 nav_map。⚠️ xlsx 用 ``pd.read_excel(io.BytesIO(...))``
    包一层（akshare 现版直接传 bytes 在本环境 TypeError）；该表基金代码是**数值型**，
    比较前 str 化补零 6 位。
  - 兜底：腾讯 ``qt.gtimg.cn/q=sh..,sz..`` 批量快照，``[45]`` = 总市值（亿元，
    市价口径与资产净值有 0.15%~2.2% 偏差，仅兜底展示）。
  - 降级：交易所源挂 → 腾讯 → null（前端 —）；交易所源是整表批量，TTL 12h。

- **费率（管理费率 + 托管费率，%/年）**：
  - 主源：东财 F10 ``fundf10.eastmoney.com/jjfl_{code}.html``（浏览器 UA）。
    费率表是**一行四列**：``['管理费率','0.15%（每年）','托管费率','0.05%（每年）']``。
    解析失败判据：找不到该 table、或值非「数字%」形态 → 视为源失败（该域有间歇
    风控史，可能返回空 body / 风控页）。
  - 备源：同花顺 ``fund.10jqka.com.cn/{code}/interduce.html``，解析 ``ul.g-dialog``
    下 ``li`` 的 ``span.key``/``span.value``（键 ``管理费``/``托管费``，值如 ``0.15%``）。
  - 兜底：费率小表 ``etf_fee_rates`` 旧值 → null。
  - 写时机：任一源解析成功即 upsert（``etf_code`` 唯一键 + 来源 + ``fetched_at``）；
    读取时若 ``fetched_at`` 超 30 天则尝试重抓，失败沿用旧值。
    **只写对比表触达的 ETF，无全市场回填 job**（数据策略硬规则：目标池 = 触达范围）。

失败态纪律（AGENTS.md 三之二）：**「拿到空」≠「没拿到」**——请求异常与解析失败
一律 log（带 source 与 code）后走降级链，禁止 ``except: return None`` 一把梭当正常空值。
每字段独立降级：规模失败不影响费率，反之亦然；单只 ETF 失败不影响同表其它行。
"""

from __future__ import annotations

import io
import random
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from loguru import logger
from pandas import isna as pd_isna
from sqlalchemy.orm import Session

from app.core.cache import CacheService

# ── 规模：交易所整表（TTL 12h）────────────────────────────────────────
_SSE_URL = 'https://query.sse.com.cn/commonQuery.do'
# sqlId 与 akshare fund_etf_scale_sse 同源；STAT_DATE 留空即取最新交易日
_SSE_PARAMS = {
    'sqlId': 'COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L',
    'isPagination': 'true',
    'pageHelp.pageSize': '10000',
}
# Referer 是该接口的准入条件（服务端校验来源），与「东财 WAF 禁加 UA 硬修」是两回事——
# requests_patch 的全局 TLS 补丁不覆盖交易所这两家，直接 requests 即可
_SSE_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://www.sse.com.cn/'}

_SZSE_URL = 'https://fund.szse.cn/api/report/ShowReport'
_SZSE_PARAMS = {'SHOWTYPE': 'xlsx', 'CATALOGID': '1000_lf', 'TABKEY': 'tab1'}
_SZSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://fund.szse.cn/marketdata/fundslist/index.html',
}

_TENCENT_QUOTE_URL = 'https://qt.gtimg.cn/q='
# 腾讯响应为 GB 编码，~ 分隔字段：[2]=代码（带 sh/sz 前缀）、[45]=总市值（亿元）
_TENCENT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

_SCALE_TTL_SECONDS = 12 * 3600  # 交易所整表日频变化，12h 兼顾新鲜度与请求量
_HTTP_TIMEOUT = 15

_SCALE_CACHE = CacheService(namespace='etf_scale_fee')


# ── 规模：纯函数解析（便于确定性单测）─────────────────────────────────
def parse_sse_scale(payload: Any) -> Dict[str, float]:
    """上交所整表 JSON → ``{裸码: 份额(万份)}``。

    源侧形态：``{'pageHelp': {'data': [{'SEC_CODE': '510300', 'TOT_VOL': '12752.44', ...}]}}``。
    坏行（非 6 位码 / 份额非数值）丢弃不编数。
    """
    if not isinstance(payload, dict):
        return {}
    rows = (payload.get('pageHelp') or {}).get('data') or []
    out: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get('SEC_CODE') or '').strip()
        if not (code.isdigit() and len(code) == 6):
            continue
        try:
            shares_wan = float(row.get('TOT_VOL'))
        except (TypeError, ValueError):
            continue
        if pd_isna(shares_wan) or shares_wan <= 0:
            continue
        out[code] = shares_wan
    return out


def parse_szse_scale(df: Any) -> Dict[str, Dict[str, float]]:
    """深交所 xlsx DataFrame → ``{裸码: {'shares': 份, 'nav': 净值}}``。

    ⚠️ 源侧基金代码是**数值型**（前导零被吞），必须 str 化补零；「当前规模(份)」
    带千分位逗号需去；净值列自带。坏行丢弃不编数。
    """
    if not hasattr(df, 'columns'):
        return {}
    cols = list(df.columns)
    code_col = next((c for c in cols if str(c).startswith('基金代码')), None)
    share_col = next((c for c in cols if str(c).startswith('当前规模')), None)
    nav_col = next((c for c in cols if str(c).strip() == '净值'), None)
    if code_col is None or share_col is None:
        return {}

    out: Dict[str, Dict[str, float]] = {}
    for _, r in df.iterrows():
        raw = str(r[code_col]).strip()
        if raw.endswith('.0'):
            raw = raw[:-2]  # 数值型代码 str 化后的尾巴
        if raw.isdigit() and len(raw) < 6:
            raw = raw.zfill(6)
        if not (raw.isdigit() and len(raw) == 6):
            continue
        try:
            shares = float(str(r[share_col]).replace(',', ''))
        except (TypeError, ValueError):
            continue
        if pd_isna(shares) or shares <= 0:
            continue
        nav: Optional[float] = None
        if nav_col is not None:
            try:
                nav = float(r[nav_col])
            except (TypeError, ValueError):
                nav = None
            if nav is not None and (pd_isna(nav) or nav <= 0):
                nav = None
        item: Dict[str, float] = {'shares': shares}
        if nav is not None:
            item['nav'] = nav
        out[raw] = item
    return out


def parse_tencent_scale(text: str) -> Dict[str, float]:
    """腾讯批量快照（已 GB 解码文本）→ ``{裸码: 总市值(亿元)}``。

    形态：``v_sh510300="1~名称~510300~...~1209.50~..."``；``;`` 分隔多行，``~`` 分隔字段；
    ``[2]``=代码（带前缀）、``[45]``=总市值（亿元，市价口径）。
    """
    out: Dict[str, float] = {}
    for line in text.split(';'):
        line = line.strip()
        if '=' not in line:
            continue
        payload = line.split('=', 1)[1].strip('"')
        fields = payload.split('~')
        if len(fields) <= 45:
            continue
        code = fields[2].strip()
        if not (code.isdigit() and len(code) == 6):
            continue
        try:
            scale = float(fields[45])
        except (TypeError, ValueError):
            continue
        if pd_isna(scale) or scale <= 0:
            continue
        out[code] = scale
    return out


# ── 规模：网络层（异常上抛，由编排层降级 + log）────────────────────────
def fetch_sse_shares() -> Dict[str, float]:
    """沪市 ETF 份额整表（万份）；请求/空表视为源失败上抛（不缓存假空）。"""
    resp = requests.get(_SSE_URL, params=_SSE_PARAMS, headers=_SSE_HEADERS, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    data = parse_sse_scale(resp.json())
    if not data:
        # 交易所整表不可能 0 行：拿到空 = 源异常（风控/改版），不当正常空值缓存
        raise ValueError('上交所 ETF 规模整表解析为空（疑似风控或接口改版）')
    return data


def fetch_szse_scale() -> Dict[str, Dict[str, float]]:
    """深市 ETF 规模整表（份额 + 净值）；同样空表视为源失败上抛。"""
    params = dict(_SZSE_PARAMS, random=f'{random.random():.16f}')  # 绕缓存参数
    resp = requests.get(_SZSE_URL, params=params, headers=_SZSE_HEADERS, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    # 必须 BytesIO 包一层：akshare 现版 pd.read_excel(bytes) 在本环境 TypeError
    df = pd.read_excel(io.BytesIO(resp.content))
    data = parse_szse_scale(df)
    if not data:
        raise ValueError('深交所 ETF 规模整表解析为空（疑似改版）')
    return data


def fetch_tencent_scale(codes: List[str]) -> Dict[str, float]:
    """腾讯批量快照兜底：``{裸码: 亿元}``；按行批量单请求（约 60 码/批防 URL 过长）。"""
    out: Dict[str, float] = {}
    for start in range(0, len(codes), 60):
        batch = codes[start : start + 60]
        symbols = ','.join(('sh' if c[0] in ('5', '6', '9') else 'sz') + c for c in batch)
        resp = requests.get(_TENCENT_QUOTE_URL + symbols, headers=_TENCENT_HEADERS, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        out.update(parse_tencent_scale(resp.content.decode('gbk', errors='replace')))
    return out


def _cached_sse_shares() -> Dict[str, float]:
    hit = _SCALE_CACHE.get('sse_shares')
    if hit is not None:
        return hit
    data = fetch_sse_shares()
    _SCALE_CACHE.set('sse_shares', data, ttl=_SCALE_TTL_SECONDS)
    return data


def _cached_szse_scale() -> Dict[str, Dict[str, float]]:
    hit = _SCALE_CACHE.get('szse_scale')
    if hit is not None:
        return hit
    data = fetch_szse_scale()
    _SCALE_CACHE.set('szse_scale', data, ttl=_SCALE_TTL_SECONDS)
    return data


def build_scale_map(
    codes: List[str],
    nav_map: Dict[str, Dict[str, Any]],
) -> Dict[str, float]:
    """``{裸码: 规模(亿元)}``：深市自带净值直乘，沪市份额 × 对比表净值链，缺项腾讯兜底。

    Args:
        codes: 对比表 ETF 裸码集（通常 2~10 只）。
        nav_map: #2275 净值链 ``{裸码: {'nav': ...}}``（沪市规模乘它；深市优先用源内净值）。

    每只 ETF 独立降级：交易所源挂 → 该侧全部落腾讯兜底；腾讯也挂 → 该码缺席
    （调用方 ``.get`` 得 None → 前端 —）。源失败一律 log，禁止静默。
    """
    out: Dict[str, float] = {}
    if not codes:
        return out

    sse_shares: Dict[str, float] = {}
    szse_rows: Dict[str, Dict[str, float]] = {}
    try:
        sse_shares = _cached_sse_shares()
    except Exception as e:  # noqa: BLE001 - 单源失败不阻塞另一交易所与兜底
        logger.warning(f'沪市 ETF 规模整表获取失败（沪市行转腾讯兜底）: {e}')
    try:
        szse_rows = _cached_szse_scale()
    except Exception as e:  # noqa: BLE001
        logger.warning(f'深市 ETF 规模整表获取失败（深市行转腾讯兜底）: {e}')

    pending: List[str] = []
    for code in codes:
        fallback_nav = (nav_map.get(code) or {}).get('nav')
        # 深市：源内自带净值直乘；源内净值缺失时退回对比表净值链（沪市同款）
        sz = szse_rows.get(code)
        if sz is not None and sz.get('shares'):
            nav = sz.get('nav') or fallback_nav
            if nav:
                out[code] = round(sz['shares'] * float(nav) / 1e8, 2)
                continue
        # 沪市：份额(万份) × 对比表净值 / 1e4（万份→元 = ×1e4；再 /1e8 → 亿元）
        shares_wan = sse_shares.get(code)
        if shares_wan and fallback_nav:
            out[code] = round(shares_wan * float(fallback_nav) / 1e4, 2)
            continue
        pending.append(code)

    if pending:
        try:
            out.update(fetch_tencent_scale(pending))
        except Exception as e:  # noqa: BLE001 - 兜底也挂 → 缺席 → None → 前端 —
            logger.warning(f'腾讯 ETF 规模兜底失败（{len(pending)} 只降级—）: {e}')
    return out


# ── 费率：纯函数解析 ───────────────────────────────────────────────────
_FEE_PCT_RE = re.compile(r'([0-9]+(?:\.[0-9]+)?)\s*%')


def _parse_pct(text: str) -> Optional[float]:
    """``'0.15%（每年）'`` → ``0.15``；非「数字%」形态 → None（源失败判据之一）。"""
    m = _FEE_PCT_RE.search(str(text or ''))
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    return None if value < 0 else value


def parse_fee_em(html: str) -> Optional[Dict[str, Optional[float]]]:
    """东财 F10 费率页 HTML → ``{'mgmt_fee_pct': .., 'custody_fee_pct': ..}``；解析失败 None。

    费率表形态：**一行四列** ``['管理费率','0.15%（每年）','托管费率','0.05%（每年）']``——
    第 0/2 列是键、第 1/3 列是值。找不到含「管理费率」的 table、或两个值都非
    「数字%」形态 → 判源失败（风控页 / 空 body / 改版）。
    """
    from bs4 import BeautifulSoup

    if not html or '管理费率' not in html:
        return None
    soup = BeautifulSoup(html, 'lxml')
    for table in soup.find_all('table'):
        cells = [td.get_text(strip=True) for td in table.find_all('td')]
        if '管理费率' not in cells:
            continue
        mgmt_idx = cells.index('管理费率')
        mgmt = _parse_pct(cells[mgmt_idx + 1]) if mgmt_idx + 1 < len(cells) else None
        custody: Optional[float] = None
        if '托管费率' in cells:
            custody_idx = cells.index('托管费率')
            if custody_idx + 1 < len(cells):
                custody = _parse_pct(cells[custody_idx + 1])
        if mgmt is None and custody is None:
            return None  # 键在但值全坏：源失败，不半编数
        return {'mgmt_fee_pct': mgmt, 'custody_fee_pct': custody}
    return None


def parse_fee_ths(html: str) -> Optional[Dict[str, Optional[float]]]:
    """同花顺 interduce 页 HTML → 同上结构；``ul.g-dialog`` 缺失或键全缺 → None。"""
    from bs4 import BeautifulSoup

    if not html:
        return None
    soup = BeautifulSoup(html, 'lxml')
    dialog = soup.find('ul', class_='g-dialog')
    if dialog is None:
        return None
    found: Dict[str, Optional[float]] = {}
    for li in dialog.find_all('li'):
        key_span = li.find('span', class_='key')
        val_span = li.find('span', class_='value')
        if key_span is None or val_span is None:
            continue
        key = key_span.get_text(strip=True)
        if key == '管理费':
            found['mgmt_fee_pct'] = _parse_pct(val_span.get_text(strip=True))
        elif key == '托管费':
            found['custody_fee_pct'] = _parse_pct(val_span.get_text(strip=True))
    if not found or all(v is None for v in found.values()):
        return None  # g-dialog 在但费率键缺失/值全坏：源失败
    return {'mgmt_fee_pct': found.get('mgmt_fee_pct'), 'custody_fee_pct': found.get('custody_fee_pct')}


# ── 费率：网络层 ───────────────────────────────────────────────────────
_EM_FEE_URL = 'https://fundf10.eastmoney.com/jjfl_{code}.html'
_THS_FEE_URL = 'https://fund.10jqka.com.cn/{code}/interduce.html'
_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
)


def fetch_fee_em(code: str) -> Optional[Dict[str, Optional[float]]]:
    """东财 F10 费率（主源）；请求异常由调用方捕获降级。"""
    resp = requests.get(_EM_FEE_URL.format(code=code), headers={'User-Agent': _BROWSER_UA}, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return parse_fee_em(resp.content.decode('utf-8', errors='replace'))


def fetch_fee_ths(code: str) -> Optional[Dict[str, Optional[float]]]:
    """同花顺费率（备源）；页面 UTF-8，content 直喂解析避免 requests 猜错编码。"""
    resp = requests.get(_THS_FEE_URL.format(code=code), headers={'User-Agent': _BROWSER_UA}, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return parse_fee_ths(resp.content.decode('utf-8', errors='replace'))


# ── 费率：小表读写 + 编排 ──────────────────────────────────────────────
# 超 30 天尝试重抓（费率年频变化，30 天窗口足够新；抓失败沿用旧值不删行）
_FEE_REFRESH_DAYS = 30


def _fee_row_to_dict(row: Any) -> Dict[str, Optional[float]]:
    return {
        'mgmt_fee_pct': float(row.mgmt_fee_pct) if row.mgmt_fee_pct is not None else None,
        'custody_fee_pct': float(row.custody_fee_pct) if row.custody_fee_pct is not None else None,
    }


def upsert_fee_row(
    db: Session,
    code: str,
    fees: Dict[str, Optional[float]],
    source: str,
) -> None:
    """费率成功解析即 upsert（``etf_code`` 唯一键，幂等）；写失败不打断返回值。"""
    from app.domains.funds.models import EtfFeeRate

    try:
        row = db.query(EtfFeeRate).filter(EtfFeeRate.etf_code == code).first()
        if row is None:
            row = EtfFeeRate(etf_code=code)
            db.add(row)
        row.mgmt_fee_pct = fees.get('mgmt_fee_pct')
        row.custody_fee_pct = fees.get('custody_fee_pct')
        row.source = source
        row.fetched_at = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        db.commit()
    except Exception as e:  # noqa: BLE001 - 缓存表写失败不影响本次对比表返回
        db.rollback()
        logger.warning(f'ETF 费率 upsert 失败 code={code} source={source}: {e}')


def _resolve_fee(db: Session, code: str) -> Dict[str, Optional[float]]:
    """单只 ETF 费率：新值(≤30d)直用 → 主源 → 备源 → 旧值 → None。

    降级链每步 log（区分「请求挂」「解析失败」「沿用旧值」），禁止静默。
    """
    from app.domains.funds.models import EtfFeeRate

    row = db.query(EtfFeeRate).filter(EtfFeeRate.etf_code == code).first()
    if row is not None and row.fetched_at is not None:
        age = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None) - row.fetched_at
        if age <= timedelta(days=_FEE_REFRESH_DAYS):
            return _fee_row_to_dict(row)  # 新鲜旧值：零外部请求

    for source, fetcher in (('em', fetch_fee_em), ('ths', fetch_fee_ths)):
        try:
            fees = fetcher(code)
        except Exception as e:  # noqa: BLE001 - 单源失败走下一环
            logger.warning(f'ETF 费率抓取失败 code={code} source={source}: {e}')
            continue
        if fees is None:
            logger.warning(f'ETF 费率解析失败 code={code} source={source}（风控页或改版）')
            continue
        upsert_fee_row(db, code, fees, source)
        return fees

    if row is not None:
        logger.warning(f'ETF 费率双源均失败，沿用 {row.fetched_at} 旧值 code={code}')
        return _fee_row_to_dict(row)
    logger.warning(f'ETF 费率双源均失败且无旧值 code={code}，降级 null')
    return {'mgmt_fee_pct': None, 'custody_fee_pct': None}


def build_fee_map(db: Session, codes: List[str]) -> Dict[str, Dict[str, Optional[float]]]:
    """``{裸码: {'mgmt_fee_pct': .., 'custody_fee_pct': ..}}``；逐只独立降级（见
    :func:`_resolve_fee`）。只对对比表触达的 ETF 抓取与写表，无全市场回填。"""
    return {code: _resolve_fee(db, code) for code in codes}
