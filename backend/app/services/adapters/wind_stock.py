# -*- coding: utf-8 -*-
"""万得股票档案适配器（Wind MCP 路，S5 / #2749）：个股 / 可转债 → 行业口径。

## 为什么补这条路（2026-10-30 真机实测）

``security_industry_maps`` 原只有两路：申万一级（全量 31 请求）与证监会门类
（巨潮逐只、5000+ 请求刷不起）。而穿透的**主口径恰好是 csrc**（基金侧
``fund_industry_allocs`` 只有 csrc），于是「直持股票 + 可转债」几乎全部落进
``industry_map_missing`` —— 这是 #2749 里覆盖率硬上限最大的一块。

万得股票 MCP 一个工具就把三件事一起解决了（实测报文见下方常量注释）：

| 需要什么 | 万得 ``get_stock_basicinfo`` | 原通道 |
|---|---|---|
| 申万一级 | ``所属申万一级行业`` 直接给中文名 | 申万官网 31 请求全量 |
| 证监会门类 | ``所属证监会门类行业`` 直接给中文名 | 巨潮逐只 |
| 可转债 → 正股 | 传债券代码，**返回正股的行业** | 无（原本不支持） |

## 批量边界（实测，别想当然）

2026-10-30 真机：

- **10 只股票一次问**（``查询 A、B、… 的申万一级行业、证监会门类行业``）→ 10/10 行，
  两套口径都在，返回顺序**不保证**与请求一致，故必须按 ``Wind代码`` 回填而不是按行序；
- **两只转债一次问** → 返回的是**正股**（``002714.SZ`` / ``600000.SH``），且顺序与请求
  相反 —— 批量问债券后**无法把结果映射回是哪只债**，故债券一律**单只提问**；
- **股票 + 转债混批** → 只回股票的 1 行，转债被静默丢掉。故两类必须分开问。

## 与申万/巨潮两路的关系

不替换它们：``sw1`` 全量仍走申万官网（一次刷全市场，Wind 逐批问反而更贵）；本模块只负责
**按需补**（组合里真实出现的标的）的 csrc 与 sw1。两条路写进同一张表、同一个 ``scheme``，
读侧（``penetration``）一行都不用改。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.services.mcp import get_provider
from app.services.mcp.credentials import is_configured, resolve_token
from app.services.mcp.providers.wind_stock_data import WIND_STOCK_MCP_URL_ENV

#: 上游工具名（实测：``get_stock_basicinfo`` 是唯一给行业分类的档案工具）
STOCK_BASICINFO_TOOL = 'get_stock_basicinfo'
#: 上游能力名（provider 里登记在 ``_CAPABILITY_TOOLS``）
CAPABILITY = 'stock_industry'
#: provider 名。股票域是**独立的 vserver**，协议形状与指数域不同（直连工具、无二级网关），
#: 故不叫 ``'wind'``——用错名字的报错现场是「工具不存在: market_call_tool」（实测）。
PROVIDER = 'wind_stock'

#: 关心的列（两套口径 + 代码回填键）
COL_CODE = 'Wind代码'
COL_NAME = '证券简称'
COL_SW1 = '申万一级行业'
COL_CSRC = '证监会门类行业'
_COLUMNS = (COL_CODE, COL_NAME, COL_SW1, COL_CSRC)

#: 一次问多少只股票。10 已实测通过；留 10 而不是更大，是因为上游对超长问句的截断行为
#: **未实测**，而截断的表现是「少几行」——少行比多问几次贵得多（缺失会静默变成覆盖率缺口）。
STOCK_CHUNK_SIZE = 10

#: 可转债前缀（交易所归属与「是否债券」都由它判定，实测口径见项目 ``convertible_bond`` 域）
BOND_SH_PREFIXES = ('110', '111', '113', '118', '132')
BOND_SZ_PREFIXES = ('123', '127', '128')

#: 各交易所股票前缀。**穷举而非「猜」**：认不出就返回 None 让它留在缺口里，
#: 错配交易所的后果是上游返回空（看起来像「这只票没有行业」），极难定位。
_STOCK_PREFIX_EXCHANGE = {
    'SH': ('600', '601', '603', '605', '688', '689'),
    'SZ': ('000', '001', '002', '003', '300', '301'),
    'BJ': ('430', '831', '832', '833', '834', '835', '836', '837', '838', '839', '870', '871', '872', '873', '920'),
}


def is_available() -> bool:
    """Wind 股票域是否可用（Token + 股票域地址都配了才算），判据与 :mod:`wind_index` 一致。"""
    return is_configured(PROVIDER) and bool((os.getenv(WIND_STOCK_MCP_URL_ENV) or '').strip())


def is_bond_code(symbol: str) -> bool:
    """裸 6 位码是否属于可转债 / 可交换债（按前缀判定）。"""
    code = (symbol or '').strip()
    return len(code) == 6 and code.isdigit() and code.startswith(BOND_SH_PREFIXES + BOND_SZ_PREFIXES)


def to_wind_code(symbol: str) -> Optional[str]:
    """裸 6 位码 → 万得代码（``600519`` → ``600519.SH``）；认不出返回 ``None``。

    债券按前缀分流（110/111/113/118/132 → 沪，123/127/128 → 深）；股票按交易所前缀穷举。
    已经带后缀的输入原样归一（``600519.sh`` → ``600519.SH``），不重复加后缀。
    """
    raw = (symbol or '').strip().upper()
    if '.' in raw:
        code, _, suffix = raw.partition('.')
        if len(code) == 6 and code.isdigit() and suffix in ('SH', 'SZ', 'BJ'):
            return f'{code}.{suffix}'
        return None
    if len(raw) != 6 or not raw.isdigit():
        return None
    if raw.startswith(BOND_SH_PREFIXES):
        return f'{raw}.SH'
    if raw.startswith(BOND_SZ_PREFIXES):
        return f'{raw}.SZ'
    for exchange, prefixes in _STOCK_PREFIX_EXCHANGE.items():
        if raw.startswith(prefixes):
            return f'{raw}.{exchange}'
    return None


def _post_factory(provider: Any, token: str):
    """构造传输层的 ``post`` 回调（与 :mod:`wind_index` 同形状，HTTP 细节只在这里）。"""
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


def _clean(value: Any) -> Optional[str]:
    """列值 → 去空白字符串；空值返回 ``None``（不写空串进库）。"""
    text = str(value or '').strip()
    return text or None


def _quote_codes(wind_codes: List[str]) -> str:
    """把代码列表拼成问句里的顿号分隔串。"""
    return '、'.join(wind_codes)


def _rows_from_text(provider: Any, text: str) -> List[Dict[str, Any]]:
    """上游文本 → 行字典列表（列名缺列补 ``None``，见 ``WindProvider.extract``）。"""
    return provider.extract(text, columns=_COLUMNS)


def fetch_stock_industries(
    symbols: List[str], *, provider: Any = None, transport: Any = None
) -> Dict[str, Dict[str, Any]]:
    """批量取**股票**的两套行业口径。

    Args:
        symbols: 裸 6 位码（``['600519', '000001']``）。非股票码（债券 / 认不出交易所）
            一律跳过——债券要走 :func:`fetch_bond_industry`（逐只，理由见模块 docstring）。
        provider / transport: 测试注入点；默认走真实 Wind 连接。

    Returns:
        ``{裸6位码: {'sw1': '食品饮料', 'csrc': '制造业', 'name': '贵州茅台', 'wind_code': '600519.SH'}}``。
        取不到的代码**不出现在结果里**（由调用方决定是否回退巨潮），不会给一个假值。

    Raises:
        McpError 子类: 鉴权 / 额度 / 协议错误。**按 chunk 捕获**，单块失败只记 warning，
            不让一次网络抖动把其余块的数据全丢掉。
    """
    wanted: Dict[str, str] = {}
    for symbol in symbols or []:
        code = (symbol or '').strip()
        if is_bond_code(code):
            continue
        wind_code = to_wind_code(code)
        if wind_code:
            wanted[wind_code] = code

    if not wanted:
        return {}

    provider = provider or get_provider(PROVIDER)
    if transport is None:
        token = resolve_token(provider.name, provider.scope_of(CAPABILITY))
        transport = provider.build_transport(_post_factory(provider, token))
    else:
        token = None

    codes = list(wanted)
    result: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(codes), STOCK_CHUNK_SIZE):
        chunk = codes[start : start + STOCK_CHUNK_SIZE]
        question = f'查询 {_quote_codes(chunk)} 的申万一级行业、证监会门类行业'
        try:
            text = transport.call_tool(
                provider.tool_for(CAPABILITY),
                provider.map_args(CAPABILITY, question=question),
                token=token,
            )
            records = _rows_from_text(provider, text)
        except Exception as e:  # noqa: BLE001 - 单块失败不拖累其余块，但必须留痕
            logger.warning(f'[#2749] Wind 行业分类批量取数失败（{len(chunk)} 只，起 {chunk[0]}）: {e}')
            continue

        for record in records:
            wind_code = _clean(record.get(COL_CODE))
            if not wind_code or wind_code not in wanted:
                # 上游可能多回（把问句里的名称也当标的）或回成别的代码空间：认不出的丢掉，
                # 不按行序强配 —— 实测返回顺序与请求顺序不一致。
                continue
            result[wanted[wind_code]] = {
                'name': _clean(record.get(COL_NAME)),
                'sw1': _clean(record.get(COL_SW1)),
                'csrc': _clean(record.get(COL_CSRC)),
                'wind_code': wind_code,
            }
        missing = [c for c in chunk if c not in result and wanted[c] not in result]
        if missing:
            logger.warning(f'[#2749] Wind 未返回 {len(missing)} 只的行业分类: {missing}')
    return result


def fetch_bond_industry(symbol: str, *, provider: Any = None, transport: Any = None) -> Optional[Dict[str, Any]]:
    """取**单只**可转债对应正股的行业（上游会把债券代码解析成正股，返回正股的行）。

    为什么逐只：实测两只转债一次问，返回两行**正股**且顺序与请求相反，无法映射回是哪只债；
    债券数量少（一个组合通常个位数），逐只换正确性划算。

    Returns:
        ``{'sw1': ..., 'csrc': ..., 'name': 正股简称, 'underlying': 正股代码}``；
        认不出 / 上游无数据返回 ``None``（不猜）。
    """
    code = (symbol or '').strip()
    if not is_bond_code(code):
        return None
    wind_code = to_wind_code(code)
    if not wind_code:
        return None

    provider = provider or get_provider(PROVIDER)
    if transport is None:
        token = resolve_token(provider.name, provider.scope_of(CAPABILITY))
        transport = provider.build_transport(_post_factory(provider, token))
    else:
        token = None

    question = f'查询 {wind_code} 可转债对应正股的申万一级行业、证监会门类行业'
    try:
        text = transport.call_tool(
            provider.tool_for(CAPABILITY),
            provider.map_args(CAPABILITY, question=question),
            token=token,
        )
        records = _rows_from_text(provider, text)
    except Exception as e:  # noqa: BLE001 - 单只失败只留痕，由调用方决定要不要回退
        logger.warning(f'[#2749] Wind 转债行业取数失败 {code}: {e}')
        return None

    for record in records or []:
        sw1 = _clean(record.get(COL_SW1))
        csrc = _clean(record.get(COL_CSRC))
        if not sw1 and not csrc:
            continue
        # 返回的 Wind代码 是**正股**（实测），与请求的债券代码不同，故按行取、不校验代码
        return {
            'sw1': sw1,
            'csrc': csrc,
            'name': _clean(record.get(COL_NAME)),
            'underlying': _clean(record.get(COL_CODE)),
        }
    return None
