# -*- coding: utf-8 -*-
"""Wind EDB 宏观指标适配器（#1502 步骤 2 · Agent 宏观问答）。

与 :mod:`app.services.adapters.wind_edb` 的分工
------------------------------------------------
``wind_edb`` 管换手率：**精确指标名 + 日期窗口** → ``{date: value}``；
本模块管「自然语言 → 指标清单 → 带 meta 的时间序列」，因为 Agent 场景需要
频率（推算窗口）与单位（叙事不换算），这两样 ``wind_edb`` 的返回里没有。

## 为什么必须封成「一次工具调用」（两段收敛）

上游是**两个**工具：``economic_search_indicator``（问一句 → 指标清单）与
``economic_query_indicator_series``（给指标名 → 时间序列）。而本项目的 Agent 是
**约束式单工具选择**（``agent_loop`` 每轮只选一个工具、不观察后再决策，见
``docs/spec/agent-paradigm-selection.md``）——模型不会自己连调两步。所以
「检索 → 选择 → 取数」的收敛只能发生在**工具内部**，一次入参完成三件事。

## 歧义不猜

search 常回多个同族口径（实测「换手率」回 10 个行业；GDP 有现价/不变价/同比多口径）。
选不出来时回 ``ambiguous`` + 候选，让调用方换更精确的问法，**不取第一个**——
错口径的数据比缺数据危险（与 ``wind_edb`` 同一条纪律）。

## 上游契约陷阱（2026-11-16 实测）

- ``observation``（期数）**未生效**：传 12 仍回 52 个季度点 ⇒ 期数只能本地截断。
- ``startDate`` / ``endDate`` 必须成对出现；只给结束日会被网关拒收。

HTTP 细节不重复实现：``post`` 工厂、日期与数值解析一律**复用** ``wind_edb`` 里的
那一份（同 provider、同网关、同 ``metrics`` 形状）。两份实现必然漂移，而漂移的表现是
「静默取到空序列」——正是 #1502 这次踩到的坑。
"""

import json
from datetime import date
from typing import Dict, List, Optional

from app.services.adapters import wind_edb
from app.services.adapters.wind_edb import _parse_edb_date, _parse_value, _post_factory
from app.services.mcp import get_provider
from app.services.mcp.credentials import resolve_token
from app.services.mcp.errors import McpBadResponse

#: 上游两个能力的实现名（真相源是 ``market_search_tools``，**不是** ``tools/list``——
#: 数据工具是 ``market_call_tool`` 的入参，根本没有独立条目；见 #3145 的教训）。
_CAPABILITIES = {'search': 'edb_search', 'series': 'edb_query'}


def is_available() -> bool:
    """宏观路是否可用：与 ``wind_edb`` **同判据**（同 provider、同服务地址，只是能力不同）。

    不重复写判据：两处判据一旦分叉，会出现「换手率能取、宏观报未配置」这种自相矛盾的
    运维信号。
    """
    return wind_edb.is_available()


def _call(capability: str, args: dict) -> dict:
    """调一次 EDB 能力并回载荷；非 JSON / 非对象一律显式报错（不静默吞）。"""
    provider = get_provider('wind')
    token = resolve_token(provider.name, provider.scope_of(capability))
    transport = provider.build_transport(_post_factory(provider, token))
    text = transport.call_tool(provider.tool_for(capability), args, token=token)
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as e:
        raise McpBadResponse(f'EDB 返回非 JSON：{str(text)[:120]}', provider='wind') from e
    if not isinstance(payload, dict):
        raise McpBadResponse(f'EDB 返回非对象：{str(text)[:120]}', provider='wind')
    return payload


def _metrics_of(payload: dict) -> List[dict]:
    """载荷里的 ``metrics`` 列表；``None`` 视作空，非列表视作形状漂移。"""
    metrics = payload.get('metrics')
    if metrics is None:
        return []
    if not isinstance(metrics, list):
        raise McpBadResponse(f'EDB metrics 形状漂移：{str(metrics)[:120]}', provider='wind')
    return metrics


def _meta_of(metric: dict) -> dict:
    """指标元信息：实测在 ``meta`` 下；search 侧可能平铺，两种都认。"""
    meta = metric.get('meta')
    return meta if isinstance(meta, dict) else metric


def search_indicators(question: str) -> List[dict]:
    """自然语言 → 上游指标清单。

    Args:
        question: 用户问法或半精确指标名（如 ``中国GDP当季同比``）。

    Returns:
        ``[{'name': 精确指标名, 'code': 上游内部码, 'freq': 频率}]``，按上游顺序。
        ``code`` 是**不稳定的内部码**（随问法变），只用于日志排查，不要当业务键。

    Raises:
        McpBadResponse: 上游返回不可解析（形状漂移显式报错）。
    """
    payload = _call(_CAPABILITIES['search'], {'question': question})
    out: List[dict] = []
    for metric in _metrics_of(payload):
        meta = _meta_of(metric)
        name = str(meta.get('name') or '').strip()
        if not name:
            continue  # 没有名字的条目无法用于下一步取数，跳过
        out.append(
            {
                'name': name,
                'code': str(meta.get('code') or '').strip() or None,
                'freq': str(meta.get('freq') or '').strip() or None,
            }
        )
    return out


def fetch_series(name: str, begin: date, end: date) -> List[dict]:
    """按指标名取序列，回**上游返回的全部条目**（同族不过滤）。

    不过滤的理由：精确名查询上游仍会混回同族口径（实测换手率一次回 10 个行业），
    但哪一条才是调用方要的，只有调用方（拿着用户原话）判得准。过滤放在上层，
    本层只负责「如实搬运 + 丢掉解析不了的点」。

    Args:
        name: 指标名（通常是 :func:`search_indicators` 返回里的 ``name``）。
        begin / end: 取数窗口（含）。

    Returns:
        ``[{'name', 'freq', 'unit', 'points': {date: value}}]``，``points`` 升序由
        dict 语义天然给不了，调用方需自行排序后再截断。

    Raises:
        McpBadResponse: 上游返回不可解析。
    """
    payload = _call(
        _CAPABILITIES['series'],
        {'question': name, 'startDate': begin.isoformat(), 'endDate': end.isoformat()},
    )
    out: List[dict] = []
    for metric in _metrics_of(payload):
        meta = _meta_of(metric)
        metric_name = str(meta.get('name') or '').strip()
        points: Dict[date, float] = {}
        for raw_day, raw_val in zip(metric.get('date') or [], metric.get('value') or []):
            day, value = _parse_edb_date(raw_day), _parse_value(raw_val)
            if day is not None and value is not None and begin <= day <= end:
                points[day] = value
        if metric_name and points:
            out.append(
                {
                    'name': metric_name,
                    'freq': str(meta.get('freq') or '').strip() or None,
                    'unit': str(meta.get('unit') or '').strip() or None,
                    'points': points,
                }
            )
    return out


def normalize(text: Optional[str]) -> str:
    """指标名归一化：去空白与分隔符、全角冒号转半角、小写。

    只用于**相等/包含判定**，绝不用它回传给上游——上游要的是原始精确名。
    """
    raw = str(text or '')
    cleaned = ''.join(ch for ch in raw if not ch.isspace() and ch not in ':：·（）()、-_/')
    return cleaned.lower()


__all__ = ['fetch_series', 'is_available', 'normalize', 'search_indicators']
