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

import re
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from loguru import logger

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    logger.warning('playwright 未安装，无法降级抓取韭圈儿')

from app.core.cache import CacheService
from app.core.constants import USER_AGENT
from app.services.adapters.fetcher_base import BaseFetcher, SingleValueFetcher
from app.services.adapters.qieman_fetcher import QiemanFetcher
from app.services.thermometer.constants import (
    EASTMONEY_BOARDS,
    EASTMONEY_HOSTS,
    EASTMONEY_REFERER,
    JISILU_CB_URL,
    JISILU_INDICATOR_URL,
    JISILU_REFERER,
    JIUCASHUO_URL,
    SELF_CALC_CACHE_KEY,
    SELF_CALC_CACHE_TTL,
    SINA_REFERER,
    SINA_VOLUME_BOARDS,
    SINA_VOLUME_URL,
    THERMOMETER_CACHE_NAMESPACE,
    YOUZHIYOUXING_URL,
    _to_float,
    label_fear,
    label_temp,
    label_volume,
)


# ─────────────────────────── 本地缓存 ───────────────────────────
def _cache() -> CacheService:
    """温度计抓取的本地缓存，统一走 :class:`~app.core.cache.CacheService`（#1537）。

    本模块原先自带一套 ``_cached()`` 文件缓存，目录**硬编码**全局临时目录，与
    ``CacheService`` 共用 ``fundmate_cache`` 却不认 ``CACHE_FILE_DIR``——按环境指定
    缓存目录（容器 / CI / 多实例）时只生效一半，测试的用例级隔离也漏掉了这条路径。
    现统一：目录由 ``CacheService`` 经 ``resolve_cache_file_dir()`` 解析，与它同源。

    **每次调用新建实例，不做模块级单例**：``CacheService`` 在构造期读
    ``CACHE_FILE_DIR``（#1531），做成模块级单例等于把 env 固化在「第一次调用」那一刻，
    ``tests/conftest.py::_isolate_cache_file_dir`` 的 autouse 隔离会跨用例失效——
    正是 #1537 要封的那类漏网。代价仅一个 OrderedDict + 一次 ``mkdir(exist_ok=True)``，
    可忽略；LRU 层因此不跨调用复用，实际生效的是文件层（与替换前行为一致）。
    """
    return CacheService(namespace=THERMOMETER_CACHE_NAMESPACE)


# ─────────────────────────── 单值源 ───────────────────────────
class EastmoneyVolumeFetcher(SingleValueFetcher):
    """全市场成交额（上证 + 深证 + 北证）。

    主源：东财 push2（`f48` 成交额）；#1431：东财为「突发配额后限流」通道，
    全部失败时回退 **新浪** `s_` 前缀简版行情（非东财，单请求），避免该指标整体缺失。
    """

    source = 'eastmoney_volume'
    name = '全市场成交额'
    unit = '亿'

    def fetch(self) -> Optional[Dict[str, Any]]:
        payload = self._fetch_eastmoney()
        if payload is not None:
            return payload
        logger.warning('东财全市场成交额不可用，回退新浪通道')
        return self._fetch_sina()

    def _fetch_eastmoney(self) -> Optional[Dict[str, Any]]:
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
                            time.sleep(1.5)  # 长退避（#1431）：东财限流敏感
                if success:
                    break
            if not success:
                logger.warning(f'东财 {board_name} 成交额获取失败（所有域名重试3次）')
                return None
        if total == 0:
            return None
        return self.payload(round(total, 1), label_volume(total), raw={'parts': parts, 'source': 'eastmoney'})

    def _fetch_sina(self) -> Optional[Dict[str, Any]]:
        """新浪 `s_` 前缀简版行情兜底：解析各板块成交额（非东财，单请求）。"""
        try:
            resp = self.session.get(SINA_VOLUME_URL, headers={'Referer': SINA_REFERER}, timeout=10)
            resp.raise_for_status()
            resp.encoding = 'gbk'
            total = 0.0
            parts: Dict[str, float] = {}
            for board_name, (sym, divisor) in SINA_VOLUME_BOARDS.items():
                m = re.search(rf'hq_str_{sym}="([^"]*)"', resp.text)
                fields = m.group(1).split(',') if m else []
                if len(fields) < 6:
                    logger.warning(f'新浪 {board_name} 成交额缺失')
                    return None
                amt = float(fields[5]) / divisor  # → 亿元
                total += amt
                parts[board_name] = round(amt, 1)
            if total <= 0:
                return None
            return self.payload(round(total, 1), label_volume(total), raw={'parts': parts, 'source': 'sina'})
        except Exception as e:  # noqa: BLE001
            logger.warning(f'新浪成交额兜底失败: {e}')
            return None


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
                'median_pb': _to_float(data.get('median_pb')) or 0.0,
                'median_pb_temperature': _to_float(data.get('median_pb_temperature')) or 0.0,
                'median_pb_level': label_temp(data.get('median_pb_temperature')),
                'median_pe': _to_float(data.get('median_pe')) or 0.0,
                'median_pe_temperature': _to_float(data.get('median_pe_temperature')) or 0.0,
                'median_pe_level': label_temp(data.get('median_pe_temperature')),
                'stock_count': _to_float(data.get('stock_count')) or 0.0,
                'ipo_count': _to_float(data.get('IPO_count')) or 0.0,
                'st_count': _to_float(data.get('st_count')) or 0.0,
                'index_point': _to_float(data.get('index_point')) or 0.0,
            }
            return {'data': result, 'raw': data}
        except Exception as e:  # noqa: BLE001
            logger.error(f'集思录估值指标获取失败: {e}')
            return None


class SelfCalcFetcher(BaseFetcher):
    """自算估值分位（本地计算，依赖 akshare / pandas）。

    结果经 :class:`~app.core.cache.CacheService` 缓存 12 小时（#1537）——akshare 侧
    CPI 历史约 19 页顺序下载、单次 20+ 秒，而数据日内变化极小。
    """

    source = 'self_calc'
    name = '自算估值分位'

    def fetch(self) -> Optional[Dict[str, Any]]:
        try:

            def _producer():
                from app.core.akshare_lazy import get_akshare

                ak = get_akshare()

                import pandas as pd

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

                if percent is None:
                    level = '未知'
                else:
                    level = label_temp(percent)

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

            # 12 小时缓存。producer 返回 None 时 CacheService 不写盘、下次调用重试
            # （#1537 起由 CacheService 定义该语义；替换前的 _cached 会把 None 也缓存
            #   12 小时，一次 akshare 抖动就让本指标连续标灰且不重试）。
            return _cache().get_or_set(SELF_CALC_CACHE_KEY, _producer, ttl=SELF_CALC_CACHE_TTL)

        except Exception as e:
            logger.error(f'自算估值分位计算失败: {e}')
            return None


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
}
