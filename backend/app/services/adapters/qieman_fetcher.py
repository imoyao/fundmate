# -*- coding: utf-8 -*-
"""且慢（盈米）MCP 取数：市场温度 + 投顾组合持仓/概览。

从 ``thermometer.fetchers`` / ``thermometer.constants`` 上提到适配层（#1607 批次 4）：
且慢投顾适配器 ``adapters/qieman_advisor_adapter`` 复用 ``QiemanFetcher``，而原实现
落在 thermometer 家族内，形成 ``adapters → thermometer`` 反向边（R5 违规）。上提后，
thermometer 家族反过来依赖本模块（合法方向），方向自洽。

包含：``QIEMAN_*`` 常量、3 个归一化助手、``QiemanFetcher``（自原文件**逐字搬运**）。
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.core.constants import USER_AGENT
from app.core.utils import to_float as _to_float
from app.services.adapters.fetcher_base import SingleValueFetcher

# ─── 且慢 MCP（Streamable HTTP）───
QIEMAN_MCP_URL = 'https://stargate.yingmi.com/mcp/v2'
QIEMAN_PROTOCOL_VERSION = '2024-11-05'
QIEMAN_CLIENT_INFO = {'name': 'fundmate', 'version': '1.0.0'}
QIEMAN_TOOL = 'GetLatestQuotations'  # 市场温度计
QIEMAN_STRATEGY_DETAIL_TOOL = 'GetStrategyDetails'  # 投顾组合概览/风险收益指标
QIEMAN_STRATEGY_COMPOSITION_TOOL = 'BatchGetStrategiesComposition'  # 投顾组合持仓

# 且慢组合概览（GetStrategyDetails）中文字段 → 归一化英文键（实测 2026-09）。
# 集中在此便于接口扩字段时只改一处，勿散落到 fetcher / job。
QIEMAN_STRATEGY_DETAIL_FIELDS: Dict[str, str] = {
    '策略代码': 'code',
    '策略名称': 'name',
    '策略简介': 'summary',
    '策略描述': 'desc',
    '策略成立时间': 'estab_date',
    '策略风险等级': 'risk_level',
    '管理人名称': 'org_name',
    '管理人简介': 'org_intro',
    '管理人头像': 'org_avatar',
    '是否实名认证': 'verified',
    '策略净值': 'nav',
    '最新净值日期': 'nav_date',
    '日收益率': 'return_1d',
    '周收益率': 'return_1w',
    '月收益率': 'return_1m',
    '季度收益率': 'return_1q',
    '半年收益率': 'return_6m',
    '年收益率': 'return_1y',
    '成立以来收益率': 'return_since_incep',
    '最大回撤': 'max_drawdown',
    '夏普比率': 'sharpe_ratio',
    '波动率': 'volatility',
    '年化收益率': 'annual_return',
    'url': 'url',
}

#: 上述字段中「带百分号的字符串」集合，归一化时剥 % 转 float（'20.32%' → 20.32）
QIEMAN_STRATEGY_PCT_FIELDS = frozenset(
    {
        'return_1d',
        'return_1w',
        'return_1m',
        'return_1q',
        'return_6m',
        'return_1y',
        'return_since_incep',
        'max_drawdown',
        'volatility',
        'annual_return',
    }
)

#: 上述字段中的纯数值字段，归一化时直接转 float
QIEMAN_STRATEGY_NUM_FIELDS = frozenset({'nav', 'sharpe_ratio'})

#: GetStrategyDetails 单次可传的组合代码上限（接口 pageSize 上限 100，留余量）
QIEMAN_STRATEGY_BATCH_SIZE = 50


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


def _normalize_strategy_detail(item: dict) -> Optional[dict]:
    """把 GetStrategyDetails 单条记录归一化成英文键 schema（#1468）。

    中文键按 :data:`QIEMAN_STRATEGY_DETAIL_FIELDS` 映射为英文键：
      · 百分比字段（``'20.32%'``）剥 % 转 float；
      · 纯数值字段（策略净值 / 夏普比率）直接转 float；
      · 其余字符串字段 strip 后空串归一为 None。
    缺少「策略代码」视为无效记录，返回 None。

    返回形如 ``{code, name, summary, desc, estab_date, risk_level, org_name,
    nav, nav_date, return_1w, return_1m, return_1y, return_since_incep,
    max_drawdown, sharpe_ratio, volatility, annual_return, url, ...}``。
    """
    if not isinstance(item, dict):
        return None
    code = str(item.get('策略代码') or item.get('code') or '').strip()
    if not code:
        return None

    rec: dict = {'code': code}
    for cn_key, en_key in QIEMAN_STRATEGY_DETAIL_FIELDS.items():
        if en_key == 'code':
            continue
        raw = item.get(cn_key)
        if en_key in QIEMAN_STRATEGY_PCT_FIELDS:
            rec[en_key] = _parse_pct(raw)
        elif en_key in QIEMAN_STRATEGY_NUM_FIELDS:
            rec[en_key] = _to_float(raw)
        elif isinstance(raw, str):
            rec[en_key] = raw.strip() or None
        else:
            rec[en_key] = raw
    return rec


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
            text = self._call_tool(api_key, QIEMAN_STRATEGY_COMPOSITION_TOOL, {'strategyCodes': [strategy_code]})
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

    def fetch_strategy_details(
        self, strategy_codes: List[str], batch_size: int = QIEMAN_STRATEGY_BATCH_SIZE
    ) -> List[dict]:
        """且慢投顾组合概览 / 风险收益指标（#1468）：GetStrategyDetails。

        真实返回结构（实测 2026-09）：
            {"pageSize":100,"rows":[{"策略代码":"ZH012926","策略名称":"远足",
              "策略简介":..., "策略描述":..., "策略成立时间":"2017-07-24",
              "策略风险等级":"中高风险","管理人名称":"盈米基金","策略净值":3.2206,
              "最新净值日期":"2026-09-11","日收益率":"-0.68%","周收益率":"0.80%",
              "月收益率":"-0.14%","年收益率":"20.32%","成立以来收益率":"222.06%",
              "最大回撤":"32.96%","夏普比率":0.6724,"波动率":"18.07%",
              "年化收益率":"13.65%","url":"https://qieman.com/alfa/portfolio/ZH012926"},
              ...],"status":"查询成功","hasMoreRows":false}

        归一化交给 :func:`_normalize_strategy_detail`（中文键 → 英文键 + 百分号剥除）。
        按 ``batch_size`` 分批调用（接口 pageSize 上限 100，且显式传 pageSize 避免默认 20 截断），
        单批失败只跳过该批、不影响其余批次；无 key 或全部失败时返回 []，不抛错。
        """
        api_key = os.getenv('QIEMAN_API_KEY')
        if not api_key:
            logger.warning('QIEMAN_API_KEY 未配置，跳过且慢组合概览')
            return []

        codes = [str(c).strip() for c in (strategy_codes or []) if str(c).strip()]
        if not codes:
            return []

        out: List[dict] = []
        seen: set = set()
        for i in range(0, len(codes), batch_size):
            chunk = codes[i : i + batch_size]
            try:
                text = self._call_tool(
                    api_key,
                    QIEMAN_STRATEGY_DETAIL_TOOL,
                    {'strategyCodes': chunk, 'pageSize': min(len(chunk), 100)},
                )
                parsed = json.loads(text)
            except Exception as e:  # noqa: BLE001
                logger.error(f'且慢组合概览获取失败（{len(chunk)} 个，如 {chunk[:3]}）: {e}')
                continue
            rows = parsed.get('rows') if isinstance(parsed, dict) else parsed
            for raw in rows or []:
                rec = _normalize_strategy_detail(raw)
                if rec and rec['code'] not in seen:
                    seen.add(rec['code'])
                    out.append(rec)
        logger.info(f'且慢组合概览抓取 {len(out)}/{len(codes)} 条')
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
