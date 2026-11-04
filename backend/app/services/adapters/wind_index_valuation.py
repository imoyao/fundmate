# -*- coding: utf-8 -*-
"""万得指数估值适配器（Wind MCP 指数域，S6 / #2749）。

## 为什么单开这一个能力

``wind.py`` 已有的 ``index_kline`` / ``index_basicinfo`` / ``index_technicals`` 都是
**点位**，温度计要的是**估值**（成份股加权 PE / PB / 股息率）与**历史分位**。指数域
（``vserver_index_data``）直连的 ``get_index_fundamentals`` 正好给这三样，且分位数
是上游算好的，不用我们自己攒历史序列。

## 「加权」这个词的坑（2026-10-30 真机实测，必须保留这段证据）

同一指数、同一交易日，只改问法里的一个词::

    问「沪深300 的市盈率」               → 最新市盈率PE_TTM = 12.8773   ✅
    问「沪深300 的加权市盈率」            → 最新市盈率       = 12.8772   ✅
    问「沪深300 的加权市盈率、加权市净率」   → 指数加权市盈率   = 19.18     ⚠️（与 PE 不同口径）
    问「沪深300、中证500、创业板指的加权
        市盈率、加权市净率和股息率」         → 指数加权市盈率   = 1917.8866 ❌（放大百倍，单位标 %）

单只正常、两只给了另一个口径、三只放大百倍 —— 形态不稳定，无法归纳出「哪种问法安全」。

故本模块的**硬规则**：问句里不出现「加权」二字，只用「市盈率、市净率、股息率」。
并对返回的每个数值做区间校验（:data:`_PE_RANGE` 等），超界即丢弃并记 warning ——
宁可当次没有估值，也不把 1917 当成 PE 写进温度计（同族教训 #171：拿不到输入却输出
一个看起来正常的结论）。

## 列名随问法变，按谓词取

实测三种列名都出现过：``最新市盈率PE_TTM`` / ``最新市盈率PE`` / ``最新市盈率``；
要分位时还会多出 ``历史每日市盈率``（含「市盈率」但**不是当前值**）与
``最新市盈率在历史中的分位数``。故 :func:`_pick` 按谓词顺序匹配，
「分位」类谓词必须排在「市盈率」之前。
"""

import json
from typing import Any, Dict, List, Optional, Sequence

import requests
from loguru import logger

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.services.mcp import get_provider
from app.services.mcp.credentials import is_configured, resolve_token

PROVIDER = 'wind_index'
CAPABILITY = 'index_valuation'
SOURCE_WIND = 'wind'

#: 数值合理区间（超界即视为上游异常，**不落库**）。
#: 上限取「A 股现实极值再放大数倍」：接到一个 1917 的 PE 时应当拒收而不是入库。
_PE_RANGE = (0.0, 1000.0)
_PB_RANGE = (0.0, 100.0)
_YIELD_RANGE = (-5.0, 40.0)
_PERCENTILE_RANGE = (0.0, 100.0)


def is_available() -> bool:
    """指数域是否可用（判据只有 Token；地址由 ``WIND_MCP_BASE`` + 固定路径给出）。"""
    return is_configured(PROVIDER)


def _post_factory(provider: Any, token: str):
    """传输层 ``post`` 回调（与 :mod:`wind_stock` / :mod:`wind_fund` 同形状）。"""
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


def _pick(record: Dict[str, Any], *predicates: str, exclude: Sequence[str] = ()) -> Any:
    """按谓词顺序取第一个匹配列的值（越具体越靠前）。

    ``exclude`` 是必需的，不是保险：实测列名 ``最新市盈率在历史中的分位数``
    **同时包含**「最新市盈率」与「分位数」两个子串，不加排除时同一个数会被
    既当成当前 PE、又当成百分位（2026-10-30 实测：沪深300 两处都是 44.5866）。
    """
    for predicate in predicates:
        for name, value in record.items():
            text = str(name)
            if predicate in text and not any(blocked in text for blocked in exclude):
                return value
    return None


def _normalize_date(raw: Any) -> Optional[str]:
    """日期归一为 ``YYYY-MM-DD``。

    实测同一个问题的两张表日期格式不同：估值表给 ``20261030``、分位表给 ``2026-10-30``。
    不归一的话下游按字符串比较会把同一天当成两天。
    """
    text = str(raw or '').strip()
    if len(text) == 8 and text.isdigit():
        return f'{text[:4]}-{text[4:6]}-{text[6:]}'
    return text or None


def _in_range(value: Optional[float], bounds: tuple, label: str, code: str) -> Optional[float]:
    """区间校验：超界记 warning 并返回 ``None``（拒收，不修正、不夹取）。"""
    if value is None:
        return None
    low, high = bounds
    if not (low <= value <= high):
        logger.warning(f'[#2749] Wind 估值超界已丢弃：{code} {label}={value}（合理区间 {low}~{high}）')
        return None
    return value


def fetch_index_valuations(
    entities: Sequence[str],
    *,
    with_percentile: bool = False,
    provider: Any = None,
    transport: Any = None,
) -> List[Dict[str, Any]]:
    """批量取指数估值（PE / PB / 股息率，可选历史分位）。

    Args:
        entities: 指数代码或名称（``['000300.SH', '801120.SI']`` 或 ``['沪深300']``）。
            上游两种都认，但**用名称时返回的代码空间可能与请求不完全一致**
            （实测同一问题两次分别返回 ``399300.SZ`` 与 ``000300.SH``），故需要稳定
            代码时请传代码。
        with_percentile: 是否连历史分位一起取。``True`` 时上游会多返回
            ``最新市盈率在历史中的分位数``（百分数）与序号/最大序号。

    Returns:
        ``[{'wind_code','name','date','pe','pb','dividend_yield','pe_percentile'}]``，
        **只包含取到至少一个有效估值字段的行**；超界字段为 ``None`` 而不是被夹取。

    Raises:
        McpError 子类: 鉴权 / 额度 / 协议错误。按批捕获后抛给调用方，
            不在本层把「上游故障」变成「这批指数没有估值」。
    """
    codes = [str(e or '').strip() for e in entities or [] if str(e or '').strip()]
    if not codes:
        return []

    question = f'查询{"、".join(codes)}最新交易日的市盈率PE、市净率PB、股息率'
    if with_percentile:
        question += '，以及市盈率PE的历史分位数'

    if provider is None:
        provider = get_provider(PROVIDER)
    if transport is None:
        token = resolve_token(provider.name, provider.scope_of(CAPABILITY))
        transport = provider.build_transport(_post_factory(provider, token))
    else:
        token = None

    text = transport.call_tool(
        provider.tool_for(CAPABILITY), provider.map_args(CAPABILITY, question=question), token=token
    )
    records = provider.extract(text)

    # 上游把「估值」和「历史分位」作为**两张并列的表**返回，而 ``extract()`` 会把两张表
    # 的行拼成一个平铺列表（它只保证列名→值的映射，不保证表边界）。故这里按代码**归并**：
    # 估值表那几行给 pe/pb/股息率、分位表那几行给 pe_percentile，缺什么补什么。
    # 直接 append 会产生同一指数两行（一行只有估值、一行只有分位），下游会当成两个指数。
    merged: Dict[str, Dict[str, Any]] = {}
    for record in records:
        code = str(_pick(record, 'Wind代码') or '').strip()
        if not code:
            logger.warning(f'[#2749] Wind 估值行缺 Wind代码，已跳过：{record}')
            continue
        # 「分位」类列必须排除在估值之外：``最新市盈率在历史中的分位数`` 含「最新市盈率」
        # 子串，不排除会把百分位当成 PE（实测沪深300 曾两处同为 44.5866）。
        pe_percentile = _in_range(_to_float(_pick(record, '分位数')), _PERCENTILE_RANGE, 'pe_percentile', code)
        pe = _in_range(
            _to_float(_pick(record, '最新市盈率', '市盈率', exclude=('分位', '历史'))), _PE_RANGE, 'pe', code
        )
        pb = _in_range(
            _to_float(_pick(record, '最新市净率', '市净率', exclude=('分位', '历史'))), _PB_RANGE, 'pb', code
        )
        dividend_yield = _in_range(
            _to_float(_pick(record, '股息率', exclude=('分位', '历史'))), _YIELD_RANGE, 'dividend_yield', code
        )
        row = merged.setdefault(
            code,
            {
                'wind_code': code,
                'name': None,
                'date': None,
                'pe': None,
                'pb': None,
                'dividend_yield': None,
                'pe_percentile': None,
                'source': SOURCE_WIND,
            },
        )
        for key, value in (
            ('name', str(_pick(record, '证券简称') or '').strip() or None),
            ('date', _normalize_date(_pick(record, '日期'))),
            ('pe', pe),
            ('pb', pb),
            ('dividend_yield', dividend_yield),
            ('pe_percentile', pe_percentile),
        ):
            if row.get(key) is None and value is not None:
                row[key] = value

    # 一行有效估值都没有的（只有名字/日期）不算结果 —— 别让下游把空壳当成「估值缺失但指数存在」
    return [
        row
        for row in merged.values()
        if row['pe'] is not None or row['pb'] is not None or row['dividend_yield'] is not None
    ]


__all__ = [
    'CAPABILITY',
    'PROVIDER',
    'SOURCE_WIND',
    'fetch_index_valuations',
    'is_available',
]
