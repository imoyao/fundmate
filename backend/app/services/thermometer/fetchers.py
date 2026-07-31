# -*- coding: utf-8 -*-
"""
市场温度聚合器 —— 返回统一 JSON
=================================
聚合多个平台的市场温度/情绪指标，输出统一结构，便于 Web 展示 / 微信推送。

数据源分层：
  · 稳定层（真实接口，基本免维护）
      - 东财市场交易量        : push2.eastmoney.com 公开行情接口（已验证可用）
      - 韭圈儿恐贪 + 中长期温度 : app.jiucaishuo.com 官方页面（Playwright 渲染取值，已验证可用）
      - 集思录温度(官方)      : www.jisilu.cn/data/indicator/ 官方接口
                                 get_cb_temperature(可转债温度) + get_last_indicator(全市场中位数PB/PE温度)
                                 需登录态 Cookie(kbzw__Session)，配 JISILU_COOKIE 即用官方真值（已验证：73.56）
  · 脆弱层（App 私有 / 无公开接口，单源失败不影响整体）
      - 且慢温度计            : 官方 MCP(stargate.yingmi.com) 的 GetLatestQuotations（用户提供 key，已验证可用）
      - 有知有行温度计        : youzhiyouxing.cn/thermometer 网页 SSR（公开可抓，已验证可用）
      - 富来智投(指数宝)      : api.fulaizhitou.com 需微信 OAuth 登录态(headers.token)，【可选源】
                                未提供 FULAI_TOKEN 时优雅跳过；提供后接 资金/强弱/龙虎榜 增量
  · 自算层（完全自主，无需第三方授权）
      - 股债利差估值分位      : valuation_jiucai.py（沪深300 PE + 10Y国债 + CPI，免费数据，复刻"韭菜投资学"思路）
      - 行业拥挤度(可选源)    : industry_crowding.py（韭菜单行业方法；优先级 Tushare > baostock > legulegu）
                                无可用数据源/网络受限时整组优雅标灰，不影响主链路

每个 fetcher 返回统一结构（或结构列表）：
  {"source","name","value","label","updated_at","stale","note"}
stale=True 表示数据不可用（已标灰），不会阻塞其它源。

设计
----
- 每个数据源是一个 ``Fetcher`` 子类，统一实现 :meth:`Fetcher.fetch`，返回与下游兼容的载荷：

  * 单值源： ``{'value', 'label', 'unit', 'updated_at', 'raw'}``
  * 复合源： ``{'data': {...}}``

- 抓取失败统一返回 ``None``，由调用方标记 stale / 决定是否重试。
- 所有常量集中在 :mod:`app.core.constants` 与 :mod:`app.services.thermometer.constants`。
- 每个 fetcher 持有一个独立的 ``requests.Session``，因此可安全并发抓取。

注意：``fulai`` / ``industry_crowding`` 等可选源当前未接入聚合流程，已从本模块移除
（如需启用，新增对应 Fetcher 子类并在 ``SINGLE_FETCHERS`` 注册即可）。
"""

import json
import logging
import os
import pickle
import re
import tempfile
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import akshare as ak
import openai
import pandas as pd
import requests
from bs4 import BeautifulSoup
from loguru import logger

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    logger.warning('playwright 未安装，无法降级抓取韭圈儿')

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.services.thermometer.constants import (
    EASTMONEY_BOARDS,
    EASTMONEY_HOSTS,
    EASTMONEY_REFERER,
    JISILU_CB_URL,
    JISILU_INDICATOR_URL,
    JISILU_REFERER,
    JIUCASHUO_URL,
    QIEMAN_CLIENT_INFO,
    QIEMAN_MCP_URL,
    QIEMAN_PROTOCOL_VERSION,
    QIEMAN_TOOL,
    YOUZHIYOUXING_URL,
    label_fear,
    label_temp,
    label_volume,
)

logger = logging.getLogger(__name__)

# 轻量文件缓存（用于缓存 akshare 等慢速抓取结果，按 TTL 复用）
_CACHE_DIR = Path(tempfile.gettempdir()) / 'fundmate_cache'


def _cached(key: str, ttl: int, producer: Callable[[], Any]) -> Any:
    """简单文件缓存：命中且在 ttl 秒内直接返回，否则调用 producer 并写入缓存。

    akshare 的部分接口需顺序下载大量分页数据（如 CPI 历史约 19 页），
    单次要 20+ 秒；这些数据日内变化极小，缓存 12 小时可大幅缩短同步耗时。
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f'{key}.pkl'
        if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
            with open(path, 'rb') as fh:
                return pickle.load(fh)
    except Exception:  # noqa: BLE001
        pass
    data = producer()
    try:
        with open(path, 'wb') as fh:
            pickle.dump(data, fh)
    except Exception:  # noqa: BLE001
        pass
    return data


# ─────────────────────────── 基类 ───────────────────────────
class BaseFetcher(ABC):
    """所有数据源的抽象基类。"""

    source: str = ''
    name: str = ''

    def __init__(self, timeout: int = DEFAULT_REQUEST_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                'User-Agent': USER_AGENT,
                'Accept': 'application/json, text/html, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
        )

    @abstractmethod
    def fetch(self) -> Optional[Dict[str, Any]]:
        """抓取并返回数据载荷；失败返回 ``None``。"""

    # 通用 HTTP 辅助
    def _get(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def _get_json(self, url: str, **kwargs) -> Dict[str, Any]:
        return self._get(url, **kwargs).json()


class SingleValueFetcher(BaseFetcher, ABC):
    """产出单值 {value,label,unit,updated_at,raw} 的源。"""

    unit: str = ''

    def payload(self, value, label, updated_at: Any = None, raw: Any = None) -> Dict[str, Any]:
        return {
            'value': value,
            'label': label,
            'unit': self.unit,
            'updated_at': updated_at,
            'raw': raw,
        }


# ─────────────────────────── 单值源 ───────────────────────────
class EastmoneyVolumeFetcher(SingleValueFetcher):
    """东财：全市场成交额（上证 + 深证 + 北证）。"""

    source = 'eastmoney_volume'
    name = '全市场成交额'
    unit = '亿'

    def fetch(self) -> Optional[Dict[str, Any]]:
        total = 0.0
        parts: Dict[str, float] = {}
        for board_name, secid in EASTMONEY_BOARDS.items():
            success = False
            for host in EASTMONEY_HOSTS:
                for attempt in range(3):
                    try:
                        url = f'https://{host}/api/qt/stock/get?secid={secid}&fields=f48'
                        resp = self.session.get(url, headers={'Referer': EASTMONEY_REFERER}, timeout=10)
                        if resp.status_code == 200:
                            amt = resp.json().get('data', {}).get('f48', 0) / 1e8
                            total += amt
                            parts[board_name] = round(amt, 1)
                            success = True
                            break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 2:
                            logger.debug(f'东财 {board_name} {host} 失败: {e}')
                        else:
                            time.sleep(0.5)
                if success:
                    break
            if not success:
                logger.warning(f'东财 {board_name} 成交额获取失败（所有域名重试3次）')
                return None
        if total == 0:
            return None
        return self.payload(round(total, 1), label_volume(total), raw={'parts': parts})


class JisiluCBFetcher(SingleValueFetcher):
    """集思录：可转债温度。"""

    source = 'jisilu_cb'
    name = '可转债温度'
    unit = '%'

    def fetch(self) -> Optional[Dict[str, Any]]:
        try:
            resp = self._get(JISILU_CB_URL, headers={'Referer': JISILU_REFERER})
            temp_str = resp.json().get('cb_temperature')
            if temp_str is None:
                return None
            value = float(temp_str)
            return self.payload(value, label_temp(value))
        except Exception as e:  # noqa: BLE001
            logger.error(f'集思录可转债温度获取失败: {e}')
            return None


class QiemanFetcher(SingleValueFetcher):
    """且慢：市场温度计（中证全A），通过 MCP Streamable HTTP 协议获取。"""

    source = 'qieman'
    name = '市场温度计(中证全A)'
    unit = '%'

    # ---- 且慢 MCP（Streamable HTTP）----
    def _mcp_post(self, payload: dict, sid: Optional[str]) -> requests.Response:
        headers = {
            'x-api-key': self.session.headers.get('x-api-key'),
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
            'Origin': QIEMAN_MCP_URL,
            'Referer': QIEMAN_MCP_URL + '/',
        }
        if sid:
            headers['Mcp-Session-Id'] = sid
        return self.session.post(QIEMAN_MCP_URL, json=payload, headers=headers, timeout=20)

    def _call_mcp(self, api_key: str):
        """完成 MCP 握手并调用 GetLatestQuotations，返回 (temperatureList, updatedOn)。"""
        self.session.headers['x-api-key'] = api_key
        sid: Optional[str] = None

        r = self._mcp_post(
            {
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'initialize',
                'params': {
                    'protocolVersion': QIEMAN_PROTOCOL_VERSION,
                    'capabilities': {},
                    'clientInfo': QIEMAN_CLIENT_INFO,
                },
            },
            sid,
        )
        if r.status_code != 200:
            raise RuntimeError(f'MCP initialize 失败: HTTP {r.status_code}')
        sid = r.headers.get('Mcp-Session-Id') or sid

        r2 = self._mcp_post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, sid)
        if r2.status_code >= 400:
            raise RuntimeError(f'MCP initialized 通知失败: HTTP {r2.status_code}')
        sid = r2.headers.get('Mcp-Session-Id') or sid

        r3 = self._mcp_post(
            {
                'jsonrpc': '2.0',
                'id': 2,
                'method': 'tools/call',
                'params': {'name': QIEMAN_TOOL, 'arguments': {}},
            },
            sid,
        )
        if r3.status_code != 200:
            raise RuntimeError(f'MCP tools/call 失败: HTTP {r3.status_code}')

        content_type = (r3.headers.get('content-type') or '').lower()
        if 'text/event-stream' in content_type:
            text = ''
            for line in r3.iter_lines(decode_unicode=True):
                if line and line.startswith('data:'):
                    data = line[len('data:') :].strip()
                    try:
                        msg = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if msg.get('id') == 2 and 'result' in msg:
                        content = msg['result'].get('content', [])
                        text = ''.join(c.get('text', '') for c in content if c.get('type') == 'text')
                        break
        else:
            try:
                msg = r3.json()
            except ValueError:
                raise RuntimeError('MCP tools/call 返回非 JSON（疑似 WAF 拦截）')
            if 'error' in msg:
                raise RuntimeError(f'MCP tools/call 返回错误: {msg["error"]}')
            content = msg.get('result', {}).get('content', [])
            text = ''.join(c.get('text', '') for c in content if c.get('type') == 'text')

        if not text:
            raise RuntimeError('MCP 调用返回为空')

        parsed = json.loads(text)
        if isinstance(parsed, dict):
            arr = parsed.get('temperatureList') or parsed.get('result') or []
            upd = parsed.get('updatedOn') or parsed.get('updated')
        else:
            arr = parsed
            upd = arr[0].get('updatedOn') or arr[0].get('updated') if arr and isinstance(arr[0], dict) else None
        return arr, upd

    def fetch(self) -> Optional[Dict[str, Any]]:
        api_key = os.getenv('QIEMAN_API_KEY')
        if not api_key:
            logger.warning('QIEMAN_API_KEY 未配置，跳过且慢温度')
            return None

        records = updated = None
        last_err: Optional[Exception] = None
        for attempt in range(2):
            try:
                records, updated = self._call_mcp(api_key)
                if records:
                    break
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning(f'且慢 MCP 第 {attempt + 1} 次尝试失败: {e}')
                time.sleep(2 * (attempt + 1))

        if not records:
            if last_err:
                logger.error(f'且慢温度获取失败: {last_err}')
            return None

        main = next((r for r in records if r.get('temperatureIndexCode') == '000985'), records[0])
        value = float(main['temperature'])
        label = main.get('ratingText') or ''

        updated_at = None
        if updated:
            tm = re.search(r'([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日 ([0-9]{1,2}):([0-9]{2})', updated)
            if tm:
                updated_at = datetime(
                    int(tm.group(1)),
                    int(tm.group(2)),
                    int(tm.group(3)),
                    int(tm.group(4)),
                    int(tm.group(5)),
                )
        return self.payload(
            value,
            label,
            updated_at=updated_at,
            raw={'updated': updated, 'indices': records},
        )


class YouzhiyouxingFetcher(SingleValueFetcher):
    """有知有行：全市场温度。"""

    source = 'youzhiyouxing'
    name = '全市场温度'
    unit = '%'

    def fetch(self) -> Optional[Dict[str, Any]]:
        try:
            resp = self._get(YOUZHIYOUXING_URL)
            resp.encoding = 'utf-8'
            html = resp.text

            m = re.search(r'tw-text-\[40px\][^>]*>(\d+)°', html)
            if not m:
                m = re.search(r'>(\d+)°<', html)
            if not m:
                return None
            temp = int(m.group(1))
            pos = m.end()

            lm = re.search(r'<div class="tw-leading-normal">([一-龥]{2})</div>', html[pos : pos + 500])
            label = lm.group(1) if lm else ''

            updated_at = None
            t = re.search(r'温度更新时间：([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日 [0-9]{1,2}:[0-9]{2})', html)
            if t:
                tm = re.search(r'([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日 ([0-9]{1,2}):([0-9]{2})', t.group(1))
                if tm:
                    updated_at = datetime(
                        int(tm.group(1)),
                        int(tm.group(2)),
                        int(tm.group(3)),
                        int(tm.group(4)),
                        int(tm.group(5)),
                    )

            idx_codes = {'沪深300': '000300', '中证500': '000905', '上证50': '000016'}
            idx = {}
            for name, code in idx_codes.items():
                im = re.search(re.escape(code) + r'.*?(\d+)°', html, re.S)
                if im:
                    idx[name] = int(im.group(1))

            return self.payload(
                float(temp),
                label,
                updated_at=updated_at,
                raw={'updated': t.group(1) if t else '', 'indices': idx},
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f'有知有行温度获取失败: {e}')
            return None


# ─────────────────────────── 韭圈儿：API 优先 + Playwright 降级 ───────────────────────────
class JiucaishuoFetcher(BaseFetcher):
    """
    韭圈儿：恐惧贪婪指数 + 中长期温度

    策略（两阶段降级）：
      1. API 优先：POST https://apiv2.jiucaishuo.com/site/indexes
         返回干净的 JSON，解析短期情绪 + 中长期温度
      2. Playwright 降级：API 失败时，无头渲染官方页面取综合值
      3. 全部失败：返回 None，由调用方标灰

    优势：API 免浏览器、速度快；降级路径保证稳定性。
    """

    source = 'jiucaishuo'
    name = '韭圈儿'

    # API 接口
    API_URL = 'https://apiv2.jiucaishuo.com/site/indexes'
    API_REFERER = 'https://app.jiucaishuo.com/'

    # 页面 URL（Playwright 降级用）
    PAGE_URL = JIUCASHUO_URL

    def fetch(self) -> Optional[Dict[str, Any]]:
        """主入口：API 优先 → Playwright 降级"""
        # 1. 优先尝试 API
        result = self._fetch_via_api()
        if result and (result.get('fear') is not None or result.get('medium') is not None):
            logger.debug('韭圈儿 API 获取成功')
            return result

        logger.info('韭圈儿 API 失败/无数据，降级到 Playwright 渲染')
        return self._fetch_via_playwright()

    def _fetch_via_api(self) -> Optional[Dict[str, Any]]:
        """
        免浏览器主路：POST 官方 indexes 接口。
        GET 返回空，必须用 POST + 空 JSON body。
        """
        try:
            resp = self.session.post(
                self.API_URL,
                json={},
                headers={
                    'Content-Type': 'application/json',
                    'Referer': self.API_REFERER,
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                logger.warning(f'韭圈儿 API HTTP {resp.status_code}')
                return None

            data = resp.json()
            arr = (data.get('data') or {}).get('data') or []
            if not arr:
                logger.warning('韭圈儿 API 返回空数组')
                return None

            result = {}
            for item in arr:
                name = item.get('name1')
                num = item.get('num')
                desc = item.get('desc') or ''
                if name == '短期情绪' and num is not None:
                    try:
                        result['fear'] = {'value': int(num), 'label': desc or label_fear(float(num))}
                    except (ValueError, TypeError):
                        pass
                elif name == '中长期温度' and num is not None:
                    try:
                        result['medium'] = {'value': int(num), 'label': desc}
                    except (ValueError, TypeError):
                        pass

            # 至少拿到一个子指标才算成功
            if result.get('fear') is not None or result.get('medium') is not None:
                return result

            logger.warning('韭圈儿 API 未匹配到短期情绪/中长期温度')
            return None

        except requests.exceptions.Timeout:
            logger.warning('韭圈儿 API 超时')
            return None
        except Exception as e:
            logger.warning(f'韭圈儿 API 请求异常: {e}')
            return None

    def _fetch_via_playwright(self) -> Optional[Dict[str, Any]]:
        """
        降级方案：Playwright 无头渲染官方页面，读已渲染的公开文本。
        不依赖加密接口，只取综合值（短期情绪 + 中长期温度）。
        """
        result = {'fear': None, 'medium': None}
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage'],
                )
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(self.PAGE_URL, wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(2500)
                txt = page.inner_text('body') or ''
                browser.close()

                # 解析短期情绪
                m = re.search(r'短期情绪\s*(\d{1,3})\s*([一-龥]+)', txt)
                if m:
                    val = int(m.group(1))
                    result['fear'] = {'value': val, 'label': m.group(2) or label_fear(val)}

                # 解析中长期温度
                m = re.search(r'中长期温度\s*(\d{1,3})\s*℃\s*([一-龥]+)', txt)
                if m:
                    result['medium'] = {'value': int(m.group(1)), 'label': m.group(2)}

                # 只要有任何一个子指标就算成功
                if result.get('fear') is not None or result.get('medium') is not None:
                    return result

                logger.warning('韭圈儿 Playwright 未能解析到有效数据')
                return None

        except Exception as e:
            logger.error(f'韭圈儿 Playwright 渲染异常: {e}')
            return None


# ─────────────────────────── 复合源 ───────────────────────────
class JisiluIndicatorFetcher(BaseFetcher):
    """集思录：估值指标（中位数 PE/PB 温度等）。"""

    source = 'jisilu_indicator'
    name = '集思录估值指标'

    def fetch(self) -> Optional[Dict[str, Any]]:
        try:
            resp = self._get(JISILU_INDICATOR_URL, headers={'Referer': JISILU_REFERER})
            data = resp.json()
            result = {
                'price_dt': data.get('price_dt'),
                'median_pb': float(data.get('median_pb', 0)),
                'median_pb_temperature': float(data.get('median_pb_temperature', 0)),
                'median_pe': float(data.get('median_pe', 0)),
                'median_pe_temperature': float(data.get('median_pe_temperature', 0)),
                'stock_count': float(data.get('stock_count', 0)),
                'ipo_count': float(data.get('IPO_count', 0)),
                'st_count': float(data.get('st_count', 0)),
                'index_point': float(data.get('index_point', 0)),
            }
            return {'data': result, 'raw': data}
        except Exception as e:  # noqa: BLE001
            logger.error(f'集思录估值指标获取失败: {e}')
            return None


class SelfCalcFetcher(BaseFetcher):
    """自算估值分位（本地计算，依赖 akshare / pandas）。"""

    source = 'self_calc'
    name = '自算估值分位'

    def fetch(self) -> Optional[Dict[str, Any]]:
        try:
            # 缓存 key
            CACHE_KEY = 'self_calc_data'

            def _producer():
                # 1. 沪深300 PE（滚动市盈率）
                pe_df = ak.stock_index_pe_lg(symbol='沪深300')
                if pe_df is None or pe_df.empty:
                    return None
                pe_df = pe_df[['日期', '滚动市盈率']].rename(columns={'滚动市盈率': 'pe'})
                pe_df['日期'] = pd.to_datetime(pe_df['日期'])
                pe_df = pe_df.dropna()
                if pe_df.empty:
                    return None

                # 2. 10Y 国债收益率
                bond_df = ak.bond_zh_us_rate()
                if bond_df is None or bond_df.empty:
                    return None
                bond_df = bond_df[['日期', '中国国债收益率10年']].rename(columns={'中国国债收益率10年': 'y10'})
                bond_df['日期'] = pd.to_datetime(bond_df['日期'])
                bond_df = bond_df.dropna()

                # 3. CPI 同比（最慢的接口，必走缓存）
                cpi_df = ak.macro_china_cpi()
                if cpi_df is None or cpi_df.empty:
                    return None
                cpi_df = cpi_df[['月份', '全国-同比增长']].rename(columns={'全国-同比增长': 'cpi_yoy'})
                cpi_df['月份'] = cpi_df['月份'].astype(str).str.replace('份', '', regex=False)
                cpi_df['月份'] = pd.to_datetime(cpi_df['月份'], format='%Y年%m月')
                cpi_df = cpi_df.dropna()
                cpi_series = cpi_df.set_index('月份')['cpi_yoy']

                # 4. 按日期合并
                df = pe_df.set_index('日期')
                df['y10'] = bond_df.set_index('日期')['y10']
                df = df.dropna()

                cpi_map = {pd.Period(m, 'M'): v for m, v in cpi_series.items()}
                df['cpi_yoy'] = df.index.to_series().dt.to_period('M').map(cpi_map)
                df['cpi_yoy'] = df['cpi_yoy'].ffill()
                df = df.dropna()

                if df.empty:
                    return None

                # 5. 股债利差
                df['ey'] = 1.0 / df['pe']
                df['spread'] = df['ey'] - df['y10'] / 100.0 + 0.3 * df['cpi_yoy'] / 100.0

                # 6. 今日利差历史分位
                cur = df.iloc[-1]
                percent = (df['spread'] < cur['spread']).mean() * 100.0
                percent = round(percent, 1)

                if percent < 30:
                    level = '偏低'
                elif percent <= 70:
                    level = '正常'
                else:
                    level = '偏高'

                return {
                    'data': {
                        'percent': percent,
                        'level': level,
                        'spread_pct': round(cur['spread'] * 100, 2),
                        'y10': round(cur['y10'], 2),
                        'cpi': round(cur['cpi_yoy'], 2),
                        'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    },
                    'collected_at': datetime.now(),
                    'stale': False,
                }

            # 使用缓存（12小时）

            result = _cached(CACHE_KEY, 12 * 3600, _producer)
            return result

        except Exception as e:
            logger.error(f'自算估值分位计算失败: {e}')
            return None


# ---- 常量 ----
ER_NIAO_SOURCES = {
    'xueqiu': {
        'url': 'https://xueqiu.com/u/3502863673',
        'list_selector': 'div.timeline__item',
        'title_pattern': r'手抄报\|第(\d+)期[:：]*(.*)',
        'key_pattern': r'本周的系数为\s*(\d+)',
    },
    'haotou': {
        'url': 'https://www.haotouxt.com/tag/手抄报',
        'list_selector': 'article.post',
        'title_pattern': r'手抄报\|第(\d+)期[:：]*(.*)',
        'key_pattern': r'本周的系数为\s*(\d+)',
    },
    'eastmoney': {
        'url': 'https://caifuhao.eastmoney.com/author/3502863673',
        'list_selector': 'div.article-item',
        'title_pattern': r'手抄报\|第(\d+)期[:：]*(.*)',
        'key_pattern': r'本周的系数为\s*(\d+)',
    },
}

# 系数 0-12 对应的情绪标签
SENTIMENT_MAP = {
    0: '极热',
    2: '过热',
    4: '较热',
    6: '正常',
    8: '正常偏冷',
    10: '较冷',
    12: '极冷',
}

# 基金组合枚举
PORTFOLIO_ENUMS = [
    '价值五剑',
    '成长五剑',
    '平衡五剑',
    '天颐五剑',
    '稳益五剑',
]


class ErNiaoFetcher(BaseFetcher):
    """

    二鸟说手抄报 Fetcher

    数据来源：
      1. 微信公众号「二鸟说」（原始 ID: gh_8f468ec0d3ec）
      2. 雪球镜像：https://xueqiu.com/u/3502863673
      3. 东方财富财富号
      4. 好投汇：https://www.haotouxt.com/

    采集策略：
      - 主路：UA 伪装抓取雪球/好投汇文章列表 → 正则或 LLM 解析
      - 降级：用户粘贴文本（纯文本）
      - 备降级：用户上传截图 OCR（由前端处理）

    输出格式：
      存入 market_composites 表，source='er_niao'
      data 字段 JSON 结构：
      {
        "issue_no": 58,
        "title": "手抄报|第58期：市场震荡",
        "coefficient": 6,
        "sentiment": "正常",
        "portfolio": ["价值五剑", "成长五剑"],
        "annualized_return": 12.5,
        "publish_date": "2026-07-25",
        "market_view": "市场处于震荡区间，保持均衡配置",
        "empirical_action": "正常定投，无需调整"
      }


    采集方式：
      1. 抓取雪球/好投汇/东财镜像 → 提取文章列表 → 解析最新一期
      2. 如果抓取失败，返回 stale=True，由上层标记为"数据暂缺"
      3. 用户可通过前端提交文本（由 LLM 解析）作为补充

    注意：本 Fetcher 只做自动抓取，不依赖 LLM（LLM 解析由单独的 API 端点处理）
    """

    source = 'er_niao'
    name = '二鸟说手抄报'

    def __init__(self, timeout: int = DEFAULT_REQUEST_TIMEOUT):
        super().__init__(timeout)
        # 引入 LLM 解析（可选，用于内容深度解析）
        self.llm_api_key = os.getenv('LLM_API_KEY')
        self.llm_base_url = os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1')
        self.llm_model = os.getenv('LLM_MODEL', 'gpt-4o-mini')

    def fetch(self) -> Optional[Dict[str, Any]]:
        """
        主入口：尝试多源抓取，返回结构化数据
        """
        # 1. 尝试从雪球抓取
        result = self._fetch_from_source('xueqiu')
        if result:
            return self._format_result(result)

        # 2. 尝试从好投汇抓取
        result = self._fetch_from_source('haotou')
        if result:
            return self._format_result(result)

        # 3. 尝试从东财抓取
        result = self._fetch_from_source('eastmoney')
        if result:
            return self._format_result(result)

        # 4. 全部失败
        logger.warning('二鸟说所有源均抓取失败')
        return None

    def _fetch_from_source(self, source_key: str) -> Optional[Dict[str, Any]]:
        """从指定源抓取最新文章"""
        source = ER_NIAO_SOURCES.get(source_key)
        if not source:
            return None

        try:
            resp = self.session.get(
                source['url'],
                timeout=self.timeout,
                headers={
                    'User-Agent': USER_AGENT,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                },
            )
            if resp.status_code != 200:
                logger.warning(f'{source_key} 返回 HTTP {resp.status_code}')
                return None

            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')

            # 查找文章列表
            articles = soup.select(source['list_selector'])
            if not articles:
                logger.warning(f'{source_key} 未找到文章列表')
                return None

            for article in articles[:5]:  # 只检查最近5篇
                # 提取标题
                title_elem = article.find('a') or article.find('h3') or article.find('h2')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                title_match = re.search(source['title_pattern'], title)
                if not title_match:
                    continue

                # 提取内容
                content = article.get_text(strip=True)
                key_match = re.search(source['key_pattern'], content)
                if not key_match:
                    continue

                return {
                    'issue_no': int(title_match.group(1)),
                    'title': title_match.group(2) or '',
                    'coefficient': int(key_match.group(1)),
                    'raw_content': content[:2000],  # 保留前2000字符供调试
                    'source_url': article.find('a').get('href') if article.find('a') else None,
                    'publish_date': self._extract_date(article),
                }

            logger.warning(f'{source_key} 未找到匹配的手抄报文章')
            return None

        except requests.exceptions.Timeout:
            logger.warning(f'{source_key} 请求超时')
            return None
        except Exception as e:
            logger.warning(f'{source_key} 抓取异常: {e}')
            return None

    def _extract_date(self, article) -> Optional[str]:
        """从文章元素中提取日期"""
        date_pattern = r'(\d{4}-\d{2}-\d{2}|\d{4}年\d{2}月\d{2}日)'
        text = article.get_text(strip=True)
        match = re.search(date_pattern, text)
        if match:
            return match.group(1).replace('年', '-').replace('月', '-').replace('日', '')
        return None

    def _format_result(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """将抓取结果格式化为标准输出"""
        coefficient = raw.get('coefficient', 6)

        # 确定情绪标签
        sentiment = SENTIMENT_MAP.get(coefficient, '正常')

        return {
            'data': {
                'issue_no': raw.get('issue_no'),
                'title': raw.get('title', ''),
                'coefficient': coefficient,
                'sentiment': sentiment,
                'portfolio': [],  # 需要进一步解析才能提取
                'annualized_return': None,
                'publish_date': raw.get('publish_date'),
                'market_view': '',
                'empirical_action': '',
                'source_url': raw.get('source_url'),
                'raw_content': raw.get('raw_content', ''),
            },
            'collected_at': datetime.now(),
            'stale': False,
        }

    def parse_with_llm(self, text: str) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 解析手抄报文章（供前端提交文本或抓取失败后调用）

        Args:
            text: 文章全文

        Returns:
            解析后的结构化数据
        """
        if not self.llm_api_key:
            logger.warning('LLM_API_KEY 未配置，无法解析')
            return None

        try:
            client = openai.Client(
                api_key=self.llm_api_key,
                base_url=self.llm_base_url,
            )

            system_prompt = """你是一个专业的基金公众号文章结构化解析器。

从"二鸟说·基金手抄报"文章提取以下字段，按 JSON 格式输出：

字段说明：
  - issue_no: 期号（整数）
  - title: 文章标题
  - coefficient: 系数（0-12 的整数）
  - sentiment: 情绪标签（从以下选择：极热/过热/较热/正常/正常偏冷/较冷/极冷）
  - portfolio: 涉及的基金组合（数组，从以下选择：价值五剑、成长五剑、平衡五剑、天颐五剑、稳益五剑）
  - annualized_return: 年化收益率（浮点数，没有则为 null）
  - publish_date: 发布日期（YYYY-MM-DD 格式）
  - market_view: 市场观点（1-3句话概括）
  - empirical_action: 具体操作建议（没有则为 null）

只输出 JSON，不要其他内容。"""
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': f'请解析以下文章：\n\n{text[:8000]}'},
                ],
                temperature=0,
                max_tokens=1024,
            )

            content = response.choices[0].message.content
            if not content:
                return None

            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                return None

            data = json.loads(json_match.group())
            return {
                'data': data,
                'collected_at': datetime.now(),
                'stale': False,
            }

        except ImportError:
            logger.warning('openai 库未安装，无法使用 LLM 解析')
            return None
        except Exception as e:
            logger.error(f'LLM 解析失败: {e}')
            return None

    def validate(self, data: Dict[str, Any]) -> bool:
        """校验数据合法性"""
        if not data or not data.get('data'):
            return False

        d = data.get('data', {})
        # 必须包含期号和系数
        if d.get('issue_no') is None or d.get('coefficient') is None:
            return False

        # 系数必须在 0-12 之间
        coeff = d.get('coefficient')
        if not (0 <= coeff <= 12):
            return False

        # 期号必须是正整数
        if d.get('issue_no', 0) <= 0:
            return False

        return True


# ─────────────────────────── 注册表 ───────────────────────────
SINGLE_FETCHERS: Dict[str, SingleValueFetcher] = {
    'eastmoney_volume': EastmoneyVolumeFetcher(),
    'qieman': QiemanFetcher(),
    'youzhiyouxing': YouzhiyouxingFetcher(),
    'jisilu_cb': JisiluCBFetcher(),
}

COMPOSITE_FETCHERS: Dict[str, BaseFetcher] = {
    'jisilu_indicator': JisiluIndicatorFetcher(),
    'self_calc': SelfCalcFetcher(),
    'er_niao': ErNiaoFetcher(),
}
