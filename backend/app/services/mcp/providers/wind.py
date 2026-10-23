# -*- coding: utf-8 -*-
"""Wind（万得）MCP provider：网关型「检索 / 调用」两段式 + 四个实测坑的归一化（S3）。

与且慢（:mod:`app.services.mcp.providers.qieman`）的差别只有「这家服务长什么样」两点，
都落在基类的扩展点上，**不改** :mod:`app.services.mcp.transport`：

1. 网关对外只暴露**两个** MCP 工具：``market_search_tools``（自然语言检索工具名）与
   ``market_call_tool``（按工具名取数）。真实业务工具（``get_index_kline`` 等）必须
   经 ``market_call_tool`` 二次调用，参数形态是
   ``{'toolName': <业务工具名>, 'arguments': '<业务参数 JSON 字符串>'}``
   （在 :meth:`WindProvider.map_args` 里组装）；
2. 鉴权头是 ``Authorization: Bearer <token>``，且 **服务地址没有内置默认值**。

请求体是**标准 JSON-RPC**（见下「真实报文」），因此本类**不再覆盖** ``_wire``。

地址为什么不做默认值
--------------------
设计文档 §4.3 的形状是 ``os.getenv('WIND_MCP_URL') or WIND_DEFAULT_URL``，但本仓库
（含 issue / 文档 / 历史代码）**没有可确认的 Wind 网关地址常量**。此时硬写一个「看起来像」
的默认值，失效形态是 **DNS / WAF 报错** —— 现场会去查网络与鉴权，而真正的原因是
「地址没配」。这与 #171 同族（拿不到输入却输出一个看起来正常的结论），故：

``WIND_MCP_URL`` 未设置 ⇒ :class:`WindEndpointMissing` **当场抛出**，文案直接点名该变量。

真实报文（2026-10-23 采样，`#2516`）
-----------------------------------
``initialize`` 返回 ``serverInfo = wind-mcp-streamable-http-stateless 1.25.0``，
``tools/list`` 只有 ``market_search_tools`` / ``market_call_tool`` 两个工具。
本次采样推翻了两条**按文档写的假设**（都曾是 S3 的实现依据，且失败形态是静默的）：

===============================  ==============================================
旧假设                            实测
===============================  ==============================================
请求体是 ``{toolName, arguments}``  HTTP 400：``JSONRPCRequest.method Field required``
返回是 ``{columnNames, rows}``      ``{data: {columns: [{name, type}], rows: [[...]]}}``
===============================  ==============================================

第二条尤其危险：旧 :meth:`extract` 在 ``data`` 节点上看到 ``rows`` 就取表，
``columnNames`` 取不到 ⇒ 列名列表为空 ⇒ 每行都变成 ``{}``（**行数对、值全 None，不报错**）。
故现在两种形状都认，且 ``error`` 非空时**显式抛错**。

四个实测坑（设计文档 §6.2）
--------------------------
===============================  ==============================================
坑                               处理
===============================  ==============================================
``period`` 必须是 ``"10"``（日 K）  :func:`_normalize_period`：``D``/``1d``/``day`` → ``"10"``
``get_index_fundamentals`` 认名称  :data:`INDEX_QUERY_NAMES` 显式映射；未登记**报错，不猜**
批量参数是**逗号分隔字符串**        list / tuple / set → ``','.join``
返回是表格（两种形状）              :meth:`extract`：按列名出行，**缺列显式为 ``None``**
===============================  ==============================================

坑②只适用于 ``index_fundamentals``：``get_index_kline`` 的 ``windcode`` **认代码**
（实测 ``885002.WI`` 直接可用），故 K 线路径不做名称映射 —— 多做一步映射反而会
把能取到的代码挡在门外。
"""

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.mcp.base import McpProvider
from app.services.mcp.credentials import DataScope
from app.services.mcp.errors import McpBadResponse
from app.services.mcp.registry import register_provider

#: 服务地址所在环境变量（**没有默认值**，理由见模块 docstring）
WIND_MCP_URL_ENV = 'WIND_MCP_URL'
#: 握手协议版本（Wind 网关按新版本协商）
WIND_PROTOCOL_VERSION = '2025-06-18'
#: 握手时上报的客户端信息（不含凭据）
WIND_CLIENT_INFO = {'name': 'fundmate', 'version': '1.0.0'}

#: 网关唯一入口工具（实测 ``tools/list`` 只有这两个）
SEARCH_TOOL = 'market_search_tools'
CALL_TOOL = 'market_call_tool'

#: 能力名 → **网关 MCP 工具名**（``market_call_tool`` 是二次调用的统一入口）
_CAPABILITY_TOOLS: Dict[str, str] = {
    'index_fundamentals': CALL_TOOL,
    'index_kline': CALL_TOOL,
    'market_search': SEARCH_TOOL,
}

#: 能力名 → **上游业务工具名**（经 ``market_call_tool`` 转发的那个名字）。
#: 只登记实测确认过的工具名；不在此表的能力（``market_search``）直接走 MCP 工具。
_WIND_TOOLS: Dict[str, str] = {
    'index_fundamentals': 'get_index_fundamentals',
    'index_kline': 'get_index_kline',
}

#: 指数代码 → 上游查询名（坑②：``get_index_fundamentals`` 认名称不认代码）。
#: 只登记核心宽基；未登记的代码**报错**而不是原样透传 —— 透传的结果是上游回
#: ``Invalid value``，现场看不出是我们没做映射。
#: **``index_kline`` 不走这张表**（``windcode`` 认代码，实测 ``885002.WI`` 可用）。
INDEX_QUERY_NAMES: Dict[str, str] = {
    '000300.SH': '沪深300',
    '000905.SH': '中证500',
    '000852.SH': '中证1000',
    '000016.SH': '上证50',
    '000001.SH': '上证指数',
    '399001.SZ': '深证成指',
    '399006.SZ': '创业板指',
    '000688.SH': '科创50',
}

#: 指数代码形态（``000300.SH`` / ``399006.SZ`` / ``H30533.CSI``）
_INDEX_CODE_RE = re.compile(r'^[0-9A-Za-z]{6,9}\.(SH|SZ|CSI|BJ)$')

#: 日 K 的别名集合（坑①：上游只认 ``"10"``，传 ``"D"`` 直接 ``Invalid value``）。
#: 周 / 月 K 的取值**尚未实测**，故不在此列 —— 遇到就报错，不猜一个数字。
_DAY_PERIOD_ALIASES = frozenset({'10', 'd', '1d', 'day', 'daily'})


class WindEndpointMissing(McpBadResponse):
    """未配置 ``WIND_MCP_URL``（本地配置缺失，不是服务故障）。

    继承 :class:`McpBadResponse` 而不是新增 ``McpErrorKind``：错误种类是
    ``mcp_call_logs.error_kind`` 的落库契约（8 类），加第 9 类会破坏存量数据的可读性。
    """

    _TEMPLATE = '{who} 未配置服务地址（WIND_MCP_URL），无法调用'


def _normalize_period(value: object) -> str:
    """``period`` 归一化为上游认的 ``"10"``（坑①）。未知取值直接报错，不猜。"""
    text = str(value).strip().lower()
    if text in _DAY_PERIOD_ALIASES:
        return '10'
    raise ValueError(
        f'period 只支持日 K（映射为 "10"），收到 {value!r}；周 / 月 K 的上游取值尚未实测，确认后再补映射（不猜）'
    )


def index_query_name(code: str) -> str:
    """指数代码 → 上游查询名（坑②，**仅 ``index_fundamentals``**）。未登记抛 ``ValueError``。"""
    key = (code or '').strip().upper()
    try:
        return INDEX_QUERY_NAMES[key]
    except KeyError:
        known = ', '.join(sorted(INDEX_QUERY_NAMES))
        raise ValueError(f'指数代码 {code!r} 未登记查询名（已知：{known}）；上游认名称不认代码') from None


@register_provider
class WindProvider(McpProvider):
    """Wind MCP：公开市场数据（指数点位 / 估值 / 档案）。"""

    name = 'wind'
    protocol_version = WIND_PROTOCOL_VERSION
    client_info = WIND_CLIENT_INFO

    def base_url(self) -> str:
        url = (os.getenv(WIND_MCP_URL_ENV) or '').strip()
        if not url:
            raise WindEndpointMissing(f'未设置环境变量 {WIND_MCP_URL_ENV}', provider=self.name)
        return url

    def auth_headers(self, token: str) -> Dict[str, str]:
        """空 token 不发 ``Authorization`` 头（不许把「没配凭据」伪装成「凭据错误」）。"""
        return {'Authorization': f'Bearer {token}'} if token else {}

    def tool_for(self, capability: str) -> str:
        try:
            return _CAPABILITY_TOOLS[capability]
        except KeyError:
            known = ', '.join(sorted(_CAPABILITY_TOOLS))
            raise KeyError(f'Wind 没有能力 {capability}（已知：{known}）') from None

    def scope_of(self, capability: str) -> DataScope:
        """索引 / 估值这类公开市场数据用系统 Token。

        未登记的能力落到基类默认 ``USER_PRIVATE``：新加能力时若忘了声明，后果是
        「调用抛 ``McpUserTokenMissing``」——响亮地失败，而不是悄悄烧系统额度（§5.1）。
        """
        return DataScope.PUBLIC_MARKET if capability in _CAPABILITY_TOOLS else DataScope.USER_PRIVATE

    # ── 能力清单（探针与报错文案的读者）──
    @classmethod
    def capabilities(cls) -> Tuple[str, ...]:
        """已登记的能力名（给探针 ``--list`` 与报错文案用）。"""
        return tuple(sorted(_CAPABILITY_TOOLS))

    @classmethod
    def read_only_tool_names(cls) -> Tuple[str, ...]:
        """本 provider 允许被人工探针调用的工具集合（全是只读查询）。

        探针**不提供**任意 ``--tool`` 直传：Wind 的写接口一旦被误调，后果不可撤销，
        而探针的价值只是「探测 + 采样」。
        """
        return tuple(sorted(set(_CAPABILITY_TOOLS.values())))

    # ── 参数归一化（§6.2 四个坑）──
    def map_args(self, capability: str, **kwargs: Any) -> Dict[str, Any]:
        """业务参数 → 上游参数。

        只做**值级**归一化（不发明参数名）：参数名由调用方按上游文档写，这里负责
        「日期 / 代码 / 批量」三种值的形态差异。这样即使上游改了参数名，本方法也不需要跟着改。

        走 ``market_call_tool`` 的能力（``_WIND_TOOLS``）在这里**再包一层**：
        网关要 ``{'toolName': ..., 'arguments': '<JSON 字符串>'}``，其中 ``arguments``
        必须是字符串（实测传对象会被拒）。这一层收在 provider 内，业务侧看到的仍是
        ``windcode=...`` 这样的普通参数。
        """
        args: Dict[str, Any] = {}
        for key, value in kwargs.items():
            if isinstance(value, (list, tuple, set, frozenset)):
                # 坑③：批量参数是逗号分隔字符串，不是数组（元素同样走值级归一化）
                normalized = [self._normalize_value(capability, key, item) for item in value]
                args[key] = ','.join(str(item) for item in normalized)
            else:
                args[key] = self._normalize_value(capability, key, value)

        wind_tool = _WIND_TOOLS.get(capability)
        if wind_tool is None:
            return args
        return {'toolName': wind_tool, 'arguments': json.dumps(args, ensure_ascii=False)}

    @staticmethod
    def _normalize_value(capability: str, key: str, value: Any) -> Any:
        """单个值的归一化（``period`` 别名 / 指数代码 → 查询名），其余原样。"""
        if key == 'period':
            return _normalize_period(value)
        if capability == 'index_fundamentals' and isinstance(value, str) and _INDEX_CODE_RE.match(value.strip()):
            return index_query_name(value)
        return value

    # ── 结果解析（坑④）──
    def extract(self, text: str, columns: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        """表格 → 行字典列表（**两种形状都认**）。

        实测形状：``{'data': {'columns': [{'name': 'TIME', 'type': 'string'}, ...],
        'rows': [['2026-07-01T00:00:00.000+08:00', '8636.7147', ...]]}, 'error': None}``；
        文档形状：``{'columnNames': [...], 'rows': [[...]]}``。

        Args:
            text: 传输层返回的文本片段（网关的 JSON 字符串）。
            columns: 关心的列名。**缺列显式填 ``None``**（坑④），
                让「上游这期没给这一列」与「我们没取这一列」在数据上可区分。

        Raises:
            McpBadResponse: 不是 JSON，或上游 ``error`` 非空，或里面没有表格形状。
                **不返回空列表** —— 空列表在上层会被读成「这只指数没有数据」。
        """
        payload = self._decode(text)
        if isinstance(payload, dict) and payload.get('error'):
            raise McpBadResponse(
                f'Wind 返回错误：{json.dumps(payload["error"], ensure_ascii=False)[:200]}', provider=self.name
            )
        tables = list(self._iter_tables(payload))  # 必须物化：生成器恒为真，`if not tables` 会失效
        if not tables:
            raise McpBadResponse(
                f'Wind 返回里没有表格（columnNames / columns + rows）：{text[:120]}', provider=self.name
            )
        rows: List[Dict[str, Any]] = []
        for table in tables:
            names = self._column_names(table)
            for raw_row in table.get('rows') or []:
                record = self._row_to_record(names, raw_row)
                for column in columns or ():
                    record.setdefault(column, None)
                rows.append(record)
        return rows

    def _decode(self, text: str) -> Any:
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            raise McpBadResponse(f'Wind 返回非 JSON：{text[:120]}', provider=self.name) from None

    @classmethod
    def _iter_tables(cls, node: Any) -> Iterable[Dict[str, Any]]:
        """递归找出所有表格块（网关可能把多张表并列放在一层 dict 里）。"""
        if isinstance(node, dict):
            if 'rows' in node and ('columnNames' in node or 'columns' in node):
                yield node
                return
            for value in node.values():
                yield from cls._iter_tables(value)
        elif isinstance(node, list):
            for item in node:
                yield from cls._iter_tables(item)

    @staticmethod
    def _column_names(table: Dict[str, Any]) -> List[str]:
        """列名：兼容 ``columnNames: ['a']`` 与 ``columns: [{'name': 'a'}]`` 两种形态。"""
        flat = table.get('columnNames')
        if flat:
            return [str(name) for name in flat]
        columns = table.get('columns') or []
        names: List[str] = []
        for column in columns:
            if isinstance(column, dict):
                names.append(str(column.get('name')))
            else:
                names.append(str(column))
        return names

    @staticmethod
    def _row_to_record(names: Sequence[str], raw_row: Any) -> Dict[str, Any]:
        """一行原始数据 → 列名到值的映射；短行缺的位置填 ``None``（不丢列）。"""
        if isinstance(raw_row, dict):
            return dict(raw_row)
        cells = list(raw_row) if isinstance(raw_row, (list, tuple)) else [raw_row]
        return {name: (cells[index] if index < len(cells) else None) for index, name in enumerate(names)}
