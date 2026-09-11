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
import os
import pickle
import re
import tempfile
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests
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
    _to_float,
    label_fear,
    label_temp,
    label_volume,
)

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


def _parse_pct(value: Any) -> Optional[float]:
    """把 '4.54%' / '4.54' / '' / None 解析为 float(4.54)；非法返回 None。

    且慢持仓占比字段是字符串（含 %），需先剥离再转 float。
    """
    if value is None:
        return None
    s = str(value).replace('%', '').replace(',', '').strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_holding(item: dict, category: Optional[str] = None) -> Optional[dict]:
    """把一条且慢持仓记录归一化成统一 schema；缺少基金代码视为无效记录，返回 None。

    兼容两套字段命名：
      · 中文键（MCP 真实返回）  ：基金代码 / 基金名称 / 持仓占比 / 最新净值 / 最新更新时间（或 调仓时间）/ 基金类型
      · 英文键（旧扁平形态）    ：code|fundCode / name|fundName / ratio|weight

    占比可能是带百分号的字符串（``"4.54%"``），统一用 :func:`_parse_pct` 转成 float，
    避免调用方再各自处理百分号。
    """
    code = str(item.get('基金代码') or item.get('code') or item.get('fundCode') or '').strip()
    if not code:
        return None

    ratio_raw = item.get('持仓占比')
    if ratio_raw is None:
        ratio_raw = item.get('ratio')
    if ratio_raw is None:
        ratio_raw = item.get('weight')

    return {
        'code': code,
        'name': str(item.get('基金名称') or item.get('name') or item.get('fundName') or '').strip(),
        'ratio': _parse_pct(ratio_raw),
        'category': category,
        'nav': _to_float(item.get('最新净值')),
        'nav_date': str(item.get('最新净值日期') or '') or None,
        # 实测：该接口不同组合/版本返回 最新更新时间 / 调仓时间 / 最新净值日期 之一，全部兜底
        'adj_time': str(item.get('最新更新时间') or item.get('调仓时间') or item.get('最新净值日期') or '') or None,
        'fund_type': str(item.get('基金类型') or '') or None,
    }


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

    def _mcp_handshake(self, api_key: str) -> Optional[str]:
        """MCP 握手（initialize + notifications/initialized），返回会话 sid。

        且慢 Streamable HTTP：tools/call 必须在同会话（同一 Mcp-Session-Id）内调用。
        """
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
        return r.headers.get('Mcp-Session-Id') or sid

    def _call_tool(self, api_key: str, tool: str, arguments: dict) -> str:
        """完成 MCP 握手并调用任意工具，返回解析出的文本片段（兼容 SSE / JSON 两种响应）。

        #1392 扩展点：原 `_call_mcp` 只调 `GetLatestQuotations`；抽成通用方法后，
        且慢组合持仓（BatchGetStrategiesComposition）等可复用同一传输，无需重复握手逻辑。
        """
        sid = self._mcp_handshake(api_key)
        r2 = self._mcp_post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, sid)
        if r2.status_code >= 400:
            raise RuntimeError(f'MCP initialized 通知失败: HTTP {r2.status_code}')
        sid = r2.headers.get('Mcp-Session-Id') or sid

        r3 = self._mcp_post(
            {
                'jsonrpc': '2.0',
                'id': 2,
                'method': 'tools/call',
                'params': {'name': tool, 'arguments': arguments},
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
        return text

    def fetch_strategy_composition(self, strategy_code: str) -> List[dict]:
        """且慢组合持仓（#1392）：BatchGetStrategiesComposition。

        真实返回结构（实测 2026-09）：
            {"<code>": {"<基金类别>": {"持有成分":[{"基金代码","基金名称","持仓占比":"4.54%",
                "最新净值","调仓时间","基金类型",...}], "分类占比":<str|num>}, ...}}
        即**按基金类别分桶**，故需遍历每个类别的 ``持有成分`` 列表并打平，
        这样单靠外层 code 取不到任何持仓（早期按扁平结构解析会静默返回空列表）。

        另保留两种扁平形态兜底（旧版/其他版本工具）：顶层 list，或 ``{result|data: [...]}``。

        返回归一化列表：[{code, name, ratio, category, nav, nav_date, adj_time, fund_type}]。
        ratio 由 "4.54%" 解析为 float(4.54)；字段缺失一律置 None。
        无 key / code 不存在 / 结构不可识别时返回 []。
        """
        api_key = os.getenv('QIEMAN_API_KEY')
        if not api_key:
            logger.warning('QIEMAN_API_KEY 未配置，跳过且慢组合持仓')
            return []
        try:
            text = self._call_tool(api_key, 'BatchGetStrategiesComposition', {'strategyCodes': [strategy_code]})
            parsed = json.loads(text)
        except Exception as e:  # noqa: BLE001
            logger.error(f'且慢组合持仓获取失败 {strategy_code}: {e}')
            return []

        # 收集 (原始记录, 所属类别)；扁平形态没有类别信息，故为 None
        raw_items: List[tuple] = []
        if isinstance(parsed, list):
            raw_items.extend((i, None) for i in parsed if isinstance(i, dict))
        elif isinstance(parsed, dict):
            code_block = parsed.get(strategy_code)
            if isinstance(code_block, dict):
                # 主路径：{strategy_code: {类别: {持有成分: [...]}}}
                for category, body in code_block.items():
                    if not isinstance(body, dict):
                        continue
                    raw_items.extend((i, category) for i in body.get('持有成分') or [] if isinstance(i, dict))
            else:
                # 兜底：{result|data: [...]} 扁平容器
                flat = parsed.get('result') or parsed.get('data') or []
                if isinstance(flat, list):
                    raw_items.extend((i, None) for i in flat if isinstance(i, dict))

        out = []
        for raw, category in raw_items:
            rec = _normalize_holding(raw, category)
            if rec:
                out.append(rec)
        return out

    def fetch(self) -> Optional[Dict[str, Any]]:
        api_key = os.getenv('QIEMAN_API_KEY')
        if not api_key:
            logger.warning('QIEMAN_API_KEY 未配置，跳过且慢温度')
            return None

        records = updated = None
        last_err: Optional[Exception] = None
        for attempt in range(2):
            try:
                text = self._call_tool(api_key, QIEMAN_TOOL, {})
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    records = parsed.get('temperatureList') or parsed.get('result') or []
                    updated = parsed.get('updatedOn') or parsed.get('updated')
                else:
                    records = parsed
                    updated = (
                        records[0].get('updatedOn') or records[0].get('updated')
                        if records and isinstance(records[0], dict)
                        else None
                    )
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
    """自算估值分位（本地计算，依赖 akshare / pandas）。"""

    source = 'self_calc'
    name = '自算估值分位'

    def fetch(self) -> Optional[Dict[str, Any]]:
        try:
            # 缓存 key
            CACHE_KEY = 'self_calc_data'

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

            # 使用缓存（12小时）

            result = _cached(CACHE_KEY, 12 * 3600, _producer)
            return result

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
