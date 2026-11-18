# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/25
# File : wind_edb.py
# backend/app/services/adapters/wind_edb.py

"""Wind EDB 经济数据库适配器（#1502 步骤 1 · 行业日频换手率）。

**为什么单开这一路**：换手率此前唯一来源是东财 push2his（限流敏感，#1431 实测连续请求
即封禁 5+ 分钟），fundfof 又是未授权源（#1502 待摘）。Wind EDB「换手率:申万行业指数:<行业名>」
为日频、1999 年起的**授权源**（2026-11-16 真机复核可正常取数）。

与 :mod:`app.services.adapters.wind_index` 同 provider / 同 ``market_call_tool`` 网关，
差别只在能力名（``edb_query``）与返回形状（``metrics``），故解析落在本模块。

## 为什么按「精确指标名」逐行业查

实测（2026-10-25）：多行业问题**单次最多返回 10 条指标**，且混入中信口径、指标代码是
不稳定的 Wind 内部码。精确名能保证目标指标**必在批次内**；但**不等于**上游只回一条
（2026-11-16 复核：仍回 10 个同族行业、约 52 KB），靠 ``meta.name`` 精确匹配筛出，
**别把过滤去掉**。宁要多 30 次请求换确定性，不猜。

上游契约（2026-11-16 经 ``market_search_tools`` 复核，**非 tools/list**）：工具
``economic_query_indicator_series``，参数 ``question`` + ``startDate``/``endDate``（成对）
**或** ``observation``（期数，互斥）。旧工具名 ``query_economic_indicator_data`` 与旧参数
``beginDate`` 均已被上游废弃，且调用方按「上游故障回缓存」降级 ⇒ 长期静默返回空、无告警。

请求纪律：增量优先（传缓存最新日之后的天窗）、行业间留间隔（调用方负责，与东财同规矩）。
"""

import json
import os
from datetime import date, datetime
from typing import Any, Dict, Optional

import requests
from loguru import logger

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.services.mcp import get_provider
from app.services.mcp.credentials import is_configured, resolve_token
from app.services.mcp.errors import McpBadResponse
from app.services.mcp.providers.wind import WIND_MCP_URL_ENV

#: EDB 换手率指标的精确命名（Wind 口径，2021 版申万行业名）
TURNOVER_INDICATOR = '换手率:申万行业指数:{name}'


def is_available() -> bool:
    """Wind EDB 路是否可用（Token + 服务地址都配了才算）。

    与 :func:`wind_index.is_available` 同款判据：job 需要**事先**区分「未配置」
    （可选组件降级）与「上游失败」（真故障），两者运维动作不同。
    """
    return is_configured('wind') and bool((os.getenv(WIND_MCP_URL_ENV) or '').strip())


def _post_factory(provider: Any, token: str):
    """构造传输层的 ``post`` 回调（HTTP 细节只在这里；与 wind_index 同形状）。"""
    session = requests.Session()

    def post(payload: dict, sid: Optional[str]) -> Any:
        headers: Dict[str, str] = {
            **provider.auth_headers(token),
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
        }
        if sid:
            headers['Mcp-Session-Id'] = sid
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        return session.post(provider.base_url(), data=body, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)

    return post


def _parse_edb_date(raw: Any) -> Optional[date]:
    """EDB 日期（实测 ``20261021``，兼容 ISO）→ ``date``；认不出返回 ``None``（不猜）。"""
    text = str(raw or '').strip()[:10]
    if not text:
        return None
    for fmt in ('%Y%m%d', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_value(raw: Any) -> Optional[float]:
    """空值 / 非数字返回 ``None``（**不写 0**：0 会被分位计算读成真值）。"""
    text = str(raw or '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_edb_series(indicator_question: str, begin: date, end: date) -> Dict[date, float]:
    """按精确指标名取 EDB 日频时间序列。

    Args:
        indicator_question: **精确指标名**（如 ``换手率:申万行业指数:农林牧渔``）。
            实测精确名稳定返回唯一指标；含糊问题会混入口径且被 10 条截断（见模块头）。
        begin / end: 取数窗口（含）。

    Returns:
        ``{date: value}`` 升序；空字典表示「上游确实没有该窗口数据」。

    Raises:
        McpTokenMissing / WindEndpointMissing: 未配置（调用方应先用 :func:`is_available`）。
        McpBadResponse: 上游返回不可解析（形状漂移当场显式报错，不静默吞）。
    """
    provider = get_provider('wind')
    token = resolve_token(provider.name, provider.scope_of('edb_query'))
    transport = provider.build_transport(_post_factory(provider, token))

    args = {
        'question': indicator_question,
        'startDate': begin.isoformat(),
        'endDate': end.isoformat(),
    }
    # 数据工具名直接传：WindProvider._wire 自动包一层 market_call_tool 网关
    text = transport.call_tool(provider.tool_for('edb_query'), args, token=token)

    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as e:
        raise McpBadResponse(f'EDB 返回非 JSON：{text[:120]}', provider='wind') from e
    metrics = payload.get('metrics') if isinstance(payload, dict) else None
    if not metrics:
        logger.debug(f'EDB 无数据：{indicator_question}（{begin}~{end}）')
        return {}
    if not isinstance(metrics, list):
        raise McpBadResponse(f'EDB metrics 形状漂移：{text[:120]}', provider='wind')

    out: Dict[date, float] = {}
    for metric in metrics:
        meta = metric.get('meta') or {}
        name = str(meta.get('name') or '')
        # 精确名查询可能仍返回近名指标（如中信口径混入）：只收**精确匹配**的，
        # 认不出就跳过——错口径的数据比缺数据危险（同 #1431「不猜」纪律）。
        if name != indicator_question:
            logger.debug(f'EDB 返回非精确匹配指标 {name!r}（期望 {indicator_question!r}），跳过')
            continue
        for raw_day, raw_val in zip(metric.get('date') or [], metric.get('value') or []):
            day, value = _parse_edb_date(raw_day), _parse_value(raw_val)
            if day is not None and value is not None and begin <= day <= end:
                out[day] = value
    return out
