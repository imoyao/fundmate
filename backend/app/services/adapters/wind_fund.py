# -*- coding: utf-8 -*-
"""万得基金持仓 / 档案适配器（Wind MCP 基金域，S6 / #2749）。

## 落点

``penetration.py`` 把 ``etf`` 列为可穿透类型，但注释写着「ETF 目前无底层数据……待 B3
补齐 ETF 持仓后自动生效」。本模块就是那个补齐动作的取数侧：把
:func:`fetch_fund_holdings` 的结果写进 ``fund_holdings`` 表（``source='wind'``），
穿透链路读同一张表，**不需要改 penetration 一行**。

## 真机实测（2026-10-30，全部为实际返回，不是文档推断）

**① 只要名称、不问代码时，比例列是「资产类别」口径而不是「个股」口径。**

===============================================  ==========================================
问法                                              返回的比例列
===============================================  ==========================================
「…的前十大重仓股」                                股票市值占基金资产净值比 = 98.8876
                                                    ← 每一行都相同（是股票总仓位）
「…前十大重仓股的**股票代码**、…、占净值比例」        前十大重仓股市值占基金资产净值比 = 4.2109
                                                    ← 每行不同（是个股占净值比）
===============================================  ==========================================

两者语义完全不同，混用会把「茅台占净值 4.21%」写成 98.89%（整只基金的股票仓位）。
故本模块**固定问代码**（同时拿到个股口径的比例），另用「资产类别配置」单问一次拿总仓位。

**② 持股数量单位是「股」、持股市值是「亿元」**，而 ``FundHolding`` 存「万股」/「万元」，
换算在 :func:`fetch_fund_holdings` 里做一次，不留给下游。

**③ 港股代码带 ``.HK`` 后缀**（实测 ``0700.HK`` 腾讯控股）。``FundHolding.stock_code``
的口径是「A 股 6 位 / 港股 5 位，不做补零」，故一律去掉交易所后缀。

**④ 报告期从列名里读**，不是入参：列名形如「2025年中报前十大重仓股股票代码」；
问「最新报告期」时列名里**没有**报告期（变成「…最新重仓股股票代码」），此时
:func:`fetch_fund_holdings` 返回 ``report_period=None``，由调用方决定是否接受
「不知道是哪一期」的数据 —— 本模块不猜。
"""

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.services.mcp import get_provider
from app.services.mcp.credentials import is_configured, resolve_token

PROVIDER = 'wind_fund'
CAPABILITY_HOLDINGS = 'fund_holdings'
CAPABILITY_INFO = 'fund_info'

#: 披露口径：本工具给的是「前十大」，与 ``FundHolding.holding_basis`` 的枚举对齐
HOLDING_BASIS_TOP10 = 'top10'
#: 落库来源标识（``fund_holdings.source``）
SOURCE_WIND = 'wind'

#: 报告期中文 → 季度末（``2025年中报`` → ``2025Q2``）。年报是 Q4，中报是 Q2。
_PERIOD_SUFFIX = {'一季报': 'Q1', '中报': 'Q2', '半年报': 'Q2', '三季报': 'Q3', '年报': 'Q4'}
_PERIOD_RE = re.compile(r'(20\d{2})\s*年\s*(一季报|中报|半年报|三季报|年报)')

#: 数值合理区间（超界视为上游异常，**不落库**）。依据：PE 为负时上游另有字段，
#: 这里只接受正区间；PB / 股息率的界取「A 股现实极值再放大一倍」，宁缺不错。
_PE_RANGE = (0.0, 1000.0)
_PB_RANGE = (0.0, 100.0)
_YIELD_RANGE = (-5.0, 40.0)

#: 数量 / 市值单位换算（上游 → ``FundHolding`` 口径）
_SHARES_PER_WAN = 1e4  # 股 → 万股
_WAN_PER_YI = 1e4  # 亿元 → 万元


def is_available() -> bool:
    """基金域是否可用。

    判据只有 Token：服务地址由 ``WIND_MCP_BASE`` + 固定路径给出（已实测），
    不再要求单独配置 URL —— 否则新接的域默认就是死代码（见 ``wind_direct`` docstring）。
    """
    return is_configured(PROVIDER)


def _post_factory(provider: Any, token: str):
    """传输层 ``post`` 回调（与 :mod:`wind_stock` / :mod:`wind_index` 同形状）。"""
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


def _call(capability: str, question: str, provider: Any, transport: Any) -> List[Dict[str, Any]]:
    """问一句、拿行字典列表（列名不预设 —— 本域列名随问法变化）。"""
    if provider is None:
        provider = get_provider(PROVIDER)
    if transport is None:
        token = resolve_token(provider.name, provider.scope_of(capability))
        transport = provider.build_transport(_post_factory(provider, token))
    else:
        token = None
    text = transport.call_tool(
        provider.tool_for(capability), provider.map_args(capability, question=question), token=token
    )
    return provider.extract(text)


def parse_report_period(column_names: List[str]) -> Optional[str]:
    """从列名里读报告期（``2025年中报…`` → ``2025Q2``）；读不出返回 ``None``。

    **不猜**：问「最新报告期」时上游列名里没有期次，此时返回 ``None`` 让调用方决策，
    而不是默认成今天所在季度（那会把「不知道哪一期」写成一条看起来正常的假数据）。
    """
    for name in column_names:
        match = _PERIOD_RE.search(str(name or ''))
        if match:
            year, suffix = match.group(1), match.group(2)
            return f'{year}{_PERIOD_SUFFIX[suffix]}'
    return None


def _pick(record: Dict[str, Any], *predicates: str, exclude: Tuple[str, ...] = ()) -> Any:
    """按谓词顺序取第一个匹配列的值（越具体越靠前）。

    越具体的谓词写在越前面：例如 ``('分位', '市盈率')`` 会先找含「分位」的列，
    避免把「历史每日市盈率」误当成当前 PE。

    ``exclude`` 用于排除子串重叠的列（如只锚「市值」时要排除「市值占基金资产净值比」）。
    """
    for predicate in predicates:
        for name, value in record.items():
            text = str(name)
            if predicate in text and not any(blocked in text for blocked in exclude):
                return value
    return None


def _to_float(value: Any) -> Optional[float]:
    """列值 → ``float``；空 / 非数字返回 ``None``（**不写 0**，0 会被下游当成真实值）。"""
    text = str(value if value is not None else '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _strip_exchange(code: Any) -> Optional[str]:
    """``600519.SH`` / ``0700.HK`` → 裸代码（``FundHolding.stock_code`` 口径：不带后缀）。"""
    text = str(code or '').strip().upper()
    if not text:
        return None
    return text.split('.')[0] or None


def fetch_fund_holdings(
    fund_code: str,
    report_period: str = '',
    *,
    provider: Any = None,
    transport: Any = None,
) -> Dict[str, Any]:
    """取基金前十大重仓股（含个股占净值比、股数、市值）与资产类别构成。

    Args:
        fund_code: 万得代码（``510300.SH`` / ``005827.OF``）。
        report_period: 报告期中文（``2025年中报`` / ``2024年年报``）。空串表示问「最新报告期」，
            此时返回的 ``report_period`` 为 ``None``（上游不给期次，见模块 docstring ④）。

    Returns:
        ``{'fund_code', 'report_period', 'holding_basis', 'rows': [...], 'alloc': {...}, 'warnings': [...]}``

        - ``rows``: ``[{'stock_code','stock_name','ratio','shares','market_value','rank'}]``，
          单位已换成 ``FundHolding`` 的「万股 / 万元」，``ratio`` 是个股占净值百分比；
        - ``alloc``: ``{'stock','bond','fund','warrant','cash','other'}``（占净值百分比，
          取不到的键不出现在字典里 —— 不补 0，``None`` 与「真的 0%」必须可区分）；
        - ``warnings``: 上游静默丢弃的信息（例如无效字段），非空时调用方应记录。

    Raises:
        McpError 子类: 鉴权 / 额度 / 协议错误。**不在本层吞掉** —— 取数与「上游说没有」
            是两件事，前者必须让 job 记 errors。
    """
    code = str(fund_code or '').strip().upper()
    period_phrase = str(report_period or '').strip()
    # 「前十大重仓股的股票代码」这个措辞是必需的：不写「代码」时上游只给名称，
    # 且比例列会退化成资产类别口径（见模块 docstring ①）。
    question = f'查询{code}{period_phrase}前十大重仓股的股票代码、股票名称、持股数量、持股市值和占净值比例'
    records = _call(CAPABILITY_HOLDINGS, question, provider, transport)

    if not records:
        return {'fund_code': code, 'report_period': None, 'holding_basis': HOLDING_BASIS_TOP10, 'rows': [], 'alloc': {}}

    column_names = list(records[0].keys())
    period = parse_report_period(column_names)
    warnings: List[str] = []

    rows: List[Dict[str, Any]] = []
    for record in records:
        stock_code = _strip_exchange(_pick(record, '股票代码'))
        if not stock_code:
            # 名称在、代码不在 = 这行不能用（FundHolding.stock_code 非空且下游按代码 join）
            warnings.append(f'缺股票代码的行已跳过：{_pick(record, "股票名称")}')
            continue
        shares = _to_float(_pick(record, '持股数量', '持有数量', '数量'))
        # 「市值」这一列的名字**在同一天的不同调用之间就会变**：实测同一问句
        # 先返回「前十大重仓股持股市值」、再返回「重仓股持有市值」。故只锚「市值」，
        # 并排除「占基金资产净值比」那一列（它是比例，不是金额）。
        market_value = _to_float(_pick(record, '市值', exclude=('占基金', '净值比', '占净值')))
        rank = _to_float(_pick(record, '名次'))
        rows.append(
            {
                'stock_code': stock_code,
                'stock_name': (str(_pick(record, '股票名称') or '').strip() or None),
                # 个股口径：列名含「前十大重仓股市值占基金资产净值比」；退一步取含「占基金资产净值比」的列。
                'ratio': _to_float(_pick(record, '重仓股市值占基金资产净值比', '占基金资产净值比')),
                'shares': (shares / _SHARES_PER_WAN) if shares is not None else None,
                'market_value': (market_value * _WAN_PER_YI) if market_value is not None else None,
                'rank': int(rank) if rank is not None else None,
            }
        )

    return {
        'fund_code': code,
        'report_period': period,
        'holding_basis': HOLDING_BASIS_TOP10,
        'rows': rows,
        'alloc': _fetch_asset_alloc(code, period_phrase, provider, transport),
        'warnings': warnings,
    }


def _fetch_asset_alloc(fund_code: str, period_phrase: str, provider: Any, transport: Any) -> Dict[str, Optional[float]]:
    """单问一次「资产类别配置」，补上股票 / 债券 / 现金等总仓位。

    单独一问而不是从前十大那批行里读：那批行的资产类别列只在**不问代码**的问法下才出现，
    而本模块为了个股比例固定问代码（见模块 docstring ①）。两件事拆开问，各自口径干净。
    """
    question = f'查询{fund_code}{period_phrase}的资产类别配置比例'
    try:
        records = _call(CAPABILITY_HOLDINGS, question, provider, transport)
    except Exception as e:  # noqa: BLE001 - 资产类别是补充信息，失败不该拖垮持仓明细
        logger.warning(f'[#2749] Wind 资产类别配置取数失败（{fund_code}）: {e}')
        return {}
    if not records:
        return {}
    record = records[0]
    mapping = {
        'stock': '股票市值占基金资产净值比',
        'bond': '债券市值占基金资产净值比',
        'fund': '基金市值占基金资产净值比',
        'warrant': '权证市值占基金资产净值比',
        'cash': '银行存款占基金资产净值比',
        'other': '其他资产占基金资产净值比',
    }
    alloc: Dict[str, Optional[float]] = {}
    for key, column in mapping.items():
        value = _to_float(_pick(record, column))
        if value is not None:
            alloc[key] = value
    return alloc


def candidate_report_periods(today: date) -> List[str]:
    """按披露**窗口开启时间**倒序列出「可能已有数据」的报告期（中文短语）。

    为什么需要这个：``fetch_fund_holdings`` 只有拿到具体报告期才能给出可落库的
    ``report_period``；问「最新报告期」时上游不给期次（见模块 docstring ④），
    而 ``fund_holdings`` 的版本键必须带期次，猜一个就等于写假数据。

    本函数给的是**确定性**候选：公募基金法定披露窗口分别是
    一季报 4/1 起、中报 7/1 起、三季报 10/1 起、年报次年 1/1 起
    （中报 8/31、三季报 10/31 是**截止日**，不是起始日——披露可以更早，
    故按「窗口已开启」而不是「已过截止日」判断，否则 10 月中旬的三季报会漏掉）。

    调用方按返回顺序逐个试，取第一个真有数据的即可；空结果不算错误。
    """
    candidates: List[str] = []
    for year in (today.year, today.year - 1):
        # 同年内由近及远；年份降序保证跨年时「2025年年报」排在「2025年三季报」之前
        windows = (
            (f'{year}年三季报', date(year, 10, 1)),
            (f'{year}年中报', date(year, 7, 1)),
            (f'{year}年一季报', date(year, 4, 1)),
        )
        if year == today.year:
            # 上一年的年报窗口在**今年** 1/1 开启，故挂在今年这一轮里，位置排在季报之后
            candidates.extend(phrase for phrase, opened in windows if today >= opened)
            candidates.append(f'{year - 1}年年报')
        else:
            candidates.extend(phrase for phrase, opened in windows if today >= opened)
    return candidates


# ── 档案 ──────────────────────────────────────────────────────────────


def fetch_fund_profile(fund_code: str, *, provider: Any = None, transport: Any = None) -> Dict[str, Any]:
    """取基金档案（跟踪指数 / 费率 / 现任经理 / 投资类型）。

    用途：基金经理画像（#1970）与费率核对。字段名同样随问法变化，故按谓词取。

    Returns:
        ``{'fund_code','name','category','tracking_index','management_fee','custody_fee','manager'}``；
        取不到的键不出现（不填占位值）。
    """
    code = str(fund_code or '').strip().upper()
    question = f'查询{code}的投资类型、跟踪指数、管理费率、托管费率和现任基金经理'
    records = _call(CAPABILITY_INFO, question, provider, transport)
    if not records:
        return {'fund_code': code}
    record = records[0]
    profile: Dict[str, Any] = {'fund_code': code}
    fields: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
        ('name', ('证券简称',)),
        ('category', ('投资类型',)),
        ('tracking_index', ('跟踪指数',)),
        ('management_fee', ('管理费率',)),
        ('custody_fee', ('托管费率',)),
        ('manager', ('基金经理',)),
    )
    for key, predicates in fields:
        raw = _pick(record, *predicates)
        if key.endswith('_fee'):
            value = _to_float(raw)
        else:
            value = str(raw or '').strip() or None
        if value is not None:
            profile[key] = value
    return profile


__all__ = [
    'CAPABILITY_HOLDINGS',
    'CAPABILITY_INFO',
    'HOLDING_BASIS_TOP10',
    'PROVIDER',
    'SOURCE_WIND',
    'candidate_report_periods',
    'fetch_fund_holdings',
    'fetch_fund_profile',
    'is_available',
    'parse_report_period',
]
