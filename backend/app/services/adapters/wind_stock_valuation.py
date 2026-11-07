# -*- coding: utf-8 -*-
"""万得**个股**估值分位适配器（Wind 股票域，#2944）。

## 为什么问句必须固定成一句

2026-11-07 真机对比四条候选问句（同一批 3 只 A 股，见
``docs/working-notes/stock-valuation-source-probe-2026-11-06.md`` 的后续实现）：

============================================================  ==================================
问法                                                          返回
============================================================  ==================================
A 查询…最新交易日的市盈率PE、市净率PB，以及…过去5年的          两张表各 3 行，PE/PB 分位齐全，
  历史分位数                                                    日期 2026-11-06（最新交易日）
B 问「各自在过去5年的历史分位数」                                两张表各 3 行，但日期退回
                                                                  2026-11-05（T-1），列名加「的」
C 只问市盈率分位                                                一张表 3 行，**没有 PB 分位**
D 问「PE(TTM) / PB(LF) 当前值 + 最近 5 年历史分位数」             两张表各 3 行，但 PE 与 PB 的
                                                                  「当前值」分散在两张表里
============================================================  ==================================

⇒ 只有 A 同时给出「最新交易日 + PE/PB 两个分位 + 当前 PE/PB」且形态稳定。
**改问句等于换口径**，故 :data:`QUESTION_TEMPLATE` 不许按调用方参数拼接修饰词；
要换窗口（近 5 年 / 上市以来）必须另立模板并重新真机验证。

## 列名随问句变，按「必须同时含哪些子串」认列

即便固定 A，上游列名仍有三种写法（``过去5年市盈率`` / ``近5年市盈率`` /
``最新市盈率``），且分位列 ``最新市盈率在过去5年的分位数`` **同时含「市盈率」**。
故 :func:`_column` 要求所有必需子串同时命中，并显式排除「分位 / 序号」——
否则会把百分位当成 PE（同族教训见 ``wind_index_valuation.py``）。

## 与指数/行业估值的边界

本模块**只返回，不落库**。``thermometer/wind_valuation.py`` 的
``source='wind_valuation'`` 是宽基 / 申万一级行业的成份股加权口径，其
``market_multi_items`` 唯一键没有个股位置；两者的数值与口径都不可混用。
"""

import json
from typing import Any, Dict, List, Optional, Sequence

import requests
from loguru import logger

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.services.mcp import get_provider
from app.services.mcp.credentials import is_configured, resolve_token

PROVIDER = 'wind_stock'
CAPABILITY = 'stock_valuation'
SOURCE = 'wind_stock_valuation'
WINDOW = '5y'

#: 一次问几只。**不写 10**：#2944 探针只实测到 3 只/次返回 3 行，单次上限未测，
#: 超长问句被截断的表现是「静默少几行」（``adapters/wind_stock.py`` 同款教训）。
#: 放量前必须真机实测上限，禁止把 3 只外推成 10 只。
CHUNK_SIZE = 3

#: 固定问句（2026-11-07 真机验证，见模块 docstring）。占位符只放代码串。
QUESTION_TEMPLATE = '查询{codes}最新交易日的市盈率PE、市净率PB，以及市盈率PE、市净率PB在过去5年的历史分位数'

#: 数值合理区间；超界拒收并返回 ``None``，不夹取、不写 0。
_PE_RANGE = (0.0, 1000.0)
_PB_RANGE = (0.0, 100.0)
_PERCENTILE_RANGE = (0.0, 100.0)


def is_available() -> bool:
    """股票域是否可用（判据只有 Token；地址由 ``WIND_MCP_BASE`` + 固定路径给出）。"""
    return is_configured(PROVIDER)


def _post_factory(provider: Any, token: str):
    """传输层 ``post`` 回调（与 :mod:`wind_stock` / :mod:`wind_index_valuation` 同形状）。"""
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
        return session.post(provider.base_url(), data=body, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT * 2)

    return post


def _to_float(value: Any) -> Optional[float]:
    """列值 → ``float``；空 / 非数字返回 ``None``（不写 0）。"""
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _column(record: Dict[str, Any], *required: str, exclude: Sequence[str] = ()) -> Any:
    """取列名**同时含全部** ``required`` 子串、且不含 ``exclude`` 子串的第一个值。

    与 ``wind_index_valuation._pick`` 的「谓词 OR」不同：这里必须同时命中
    「市盈率」+「分位」才能取到 PE 分位，否则分位列会被当成当前 PE。
    """
    for name, value in record.items():
        text = str(name)
        if all(word in text for word in required) and not any(blocked in text for blocked in exclude):
            return value
    return None


def _normalize_date(raw: Any) -> Optional[str]:
    """日期归一为 ``YYYY-MM-DD``（上游同一批表出现过 ``20261106`` 与 ``2026-11-06``）。"""
    text = str(raw or '').strip()
    if len(text) == 8 and text.isdigit():
        return f'{text[:4]}-{text[4:6]}-{text[6:]}'
    return text or None


def _in_range(value: Optional[float], bounds: tuple, label: str, code: str) -> Optional[float]:
    """区间校验：超界记 warning 并返回 ``None``（拒收，不修正）。"""
    if value is None:
        return None
    low, high = bounds
    if not (low <= value <= high):
        logger.warning(f'[#2944] Wind 个股估值超界已丢弃：{code} {label}={value}（合理区间 {low}~{high}）')
        return None
    return value


def _call(provider: Any, transport: Any, question: str) -> List[Dict[str, Any]]:
    """问一句、拿平铺行字典列表（表边界由调用方按 Wind代码 归并）。"""
    token = None
    if transport is None:
        token = resolve_token(provider.name, provider.scope_of(CAPABILITY))
        transport = provider.build_transport(_post_factory(provider, token))
    text = transport.call_tool(
        provider.tool_for(CAPABILITY), provider.map_args(CAPABILITY, question=question), token=token
    )
    return provider.extract(text)


def _chunks(codes: Sequence[str], size: int) -> List[List[str]]:
    return [list(codes[i : i + size]) for i in range(0, len(codes), size)]


def fetch_stock_valuations(
    wind_codes: Sequence[str],
    *,
    provider: Any = None,
    transport: Any = None,
) -> List[Dict[str, Any]]:
    """批量取个股 PE/PB 当前值与近 5 年历史分位（只读，不落库）。

    Args:
        wind_codes: 万得代码（``['600519.SH', '000858.SZ']``）。非万得形态由调用方
            先用 ``adapters.wind_stock.to_wind_code`` 归一；本层不猜代码空间。

    Returns:
        ``[{'wind_code','name','date','pe','pb','pe_percentile','pb_percentile',
        'window','source'}]``。上游把 PE 分位与 PB 分位放在**两张并列的表**里，
        ``extract()`` 会平铺，故这里按 ``Wind代码`` 归并成一行；缺的字段为 ``None``。
        **只保留至少有一个有效估值字段的行**，空壳不返（避免下游把「没数」读成 0）。

    Raises:
        McpError 子类: 鉴权 / 额度 / 协议错误。**不在本层吞成「这批股票没数」**，
        由 service 层降级并显式标 ``degraded``。
    """
    codes = [str(c or '').strip() for c in wind_codes or [] if str(c or '').strip()]
    if not codes:
        return []
    if provider is None:
        provider = get_provider(PROVIDER)

    merged: Dict[str, Dict[str, Any]] = {}
    for chunk in _chunks(codes, CHUNK_SIZE):
        question = QUESTION_TEMPLATE.format(codes='、'.join(chunk))
        for record in _call(provider, transport, question):
            code = str(_column(record, 'Wind代码') or '').strip()
            if not code:
                logger.warning(f'[#2944] Wind 个股估值行缺 Wind代码，已跳过：{record}')
                continue
            values = {
                'name': str(_column(record, '证券简称') or '').strip() or None,
                'date': _normalize_date(_column(record, '日期')),
                'pe': _in_range(_to_float(_column(record, '市盈率', exclude=('分位', '序号'))), _PE_RANGE, 'pe', code),
                'pb': _in_range(_to_float(_column(record, '市净率', exclude=('分位', '序号'))), _PB_RANGE, 'pb', code),
                'pe_percentile': _in_range(
                    _to_float(_column(record, '市盈率', '分位', exclude=('序号',))),
                    _PERCENTILE_RANGE,
                    'pe_percentile',
                    code,
                ),
                'pb_percentile': _in_range(
                    _to_float(_column(record, '市净率', '分位', exclude=('序号',))),
                    _PERCENTILE_RANGE,
                    'pb_percentile',
                    code,
                ),
            }
            row = merged.setdefault(
                code,
                {
                    'wind_code': code,
                    'name': None,
                    'date': None,
                    'pe': None,
                    'pb': None,
                    'pe_percentile': None,
                    'pb_percentile': None,
                    'window': WINDOW,
                    'source': SOURCE,
                },
            )
            for key, value in values.items():
                if row.get(key) is None and value is not None:
                    row[key] = value

    return [
        row
        for row in merged.values()
        if any(row[key] is not None for key in ('pe', 'pb', 'pe_percentile', 'pb_percentile'))
    ]


__all__ = [
    'CAPABILITY',
    'CHUNK_SIZE',
    'PROVIDER',
    'QUESTION_TEMPLATE',
    'SOURCE',
    'WINDOW',
    'fetch_stock_valuations',
    'is_available',
]
