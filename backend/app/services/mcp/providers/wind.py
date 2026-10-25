# -*- coding: utf-8 -*-
"""Wind（万得）MCP provider：两级网关 + 真机报文形状（S3，2026-10-23 采样后重写）。

与且慢（:mod:`app.services.mcp.providers.qieman`）的差别只有「这家服务长什么样」三点，
都落在基类的扩展点上，**不改** :mod:`app.services.mcp.transport`：

1. 上游只暴露**两个**工具：``market_search_tools``（自然语言 → 工具清单）与
   ``market_call_tool``（``toolName`` + ``arguments`` JSON 串 → 取数）。**没有**
   ``get_index_fundamentals`` 这类直连工具 —— 调它只会拿到 ``isError: true``；
2. 数据工具一律经 ``market_call_tool`` 转发（:meth:`WindProvider._wire`），
   请求体本身仍是标准 JSON-RPC ``tools/call``；
3. 鉴权头是 ``Authorization: Bearer <token>``，且 **服务地址没有内置默认值**。

地址为什么不做默认值
--------------------
设计文档 §4.3 的形状是 ``os.getenv('WIND_MCP_URL') or WIND_DEFAULT_URL``，但本仓库
（含 issue / 文档 / 历史代码）**没有可确认的 Wind 网关地址常量**。此时硬写一个「看起来像」
的默认值，失效形态是 **DNS / WAF 报错** —— 现场会去查网络与鉴权，而真正的原因是
「地址没配」。这与 #171 同族（拿不到输入却输出一个看起来正常的结论），故：

``WIND_MCP_URL`` 未设置 ⇒ :class:`WindEndpointMissing` **当场抛出**，文案直接点名该变量。
配好地址后本模块的行为与 §4.3 完全一致（env 覆盖点仍在 §8 的预留里）。

实测坑（2026-10-23 真机采样，#2516）
-----------------------------------
===============================  ==============================================
坑                               处理
===============================  ==============================================
``period`` 必须是 ``"10"``（日 K）  :func:`_normalize_period`：``D``/``1d``/``day`` → ``"10"``
``question`` 类工具只吃自然语言      :data:`INDEX_QUERY_NAMES` 映射代码→名称，再拼进问题
返回**不是** ``{columnNames, rows}``  :meth:`extract`：认 ``data.columns[].name``，也认
                                   多包一层的 ``data.data[].columns``（两个工具形状不同）
工具名错时是 **HTTP 200 + isError**  传输层检查 ``isError``（采样后补，见 #2516）
===============================  ==============================================

第 2、4 条是「宁可显式报错，不要猜一个像样的值」：猜错时上游只回一句 ``Invalid value``，
排查者拿不到「我们传了什么」这一半事实。

为什么不做「代码 → 上游代码」的反推
-----------------------------------
实测：同一个问题（「沪深300的发布机构、基日基点与成份数量」）两次采样，
``get_index_basicinfo`` 分别返回过 ``399300.SZ`` 与 ``000300.SH``。上游会按问题重排结果，
两个代码空间**不一致**，故任何「拿返回的代码回查」都不可靠；需要代码时用请求侧的代码。
"""

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.mcp.base import McpProvider
from app.services.mcp.credentials import DataScope
from app.services.mcp.errors import McpBadResponse, classify_payload
from app.services.mcp.registry import register_provider

#: 服务地址所在环境变量（**没有默认值**，理由见模块 docstring）
WIND_MCP_URL_ENV = 'WIND_MCP_URL'
#: 握手协议版本（Wind 网关按新版本协商）
WIND_PROTOCOL_VERSION = '2025-06-18'
#: 握手时上报的客户端信息（不含凭据）
WIND_CLIENT_INFO = {'name': 'fundmate', 'version': '1.0.0'}

#: 网关的二级入口：除检索外的工具都经它转发（实测形状，见模块 docstring 第 1 条）
GATEWAY_CALL_TOOL = 'market_call_tool'
#: 人工探针用的自然语言检索工具（生产链路不用它，§6.3）
MARKET_SEARCH_TOOL = 'market_search_tools'

#: 能力名 → 上游工具名（**只登记实测确认过工具名的能力**；生产链路不做自然语言检索，§6.3）。
#: EDB 双工具 2026-10-25 真机实测（search 列清单 / query 取时间序列，
#: 返回 ``metrics`` 形状与表格不同，解析在 :mod:`app.services.adapters.wind_edb`）。
_CAPABILITY_TOOLS: Dict[str, str] = {
    'index_kline': 'get_index_kline',
    'index_basicinfo': 'get_index_basicinfo',
    'index_technicals': 'get_index_technicals',
    'edb_search': 'search_economic_indicator',
    'edb_query': 'query_economic_indicator_data',
    'market_search': MARKET_SEARCH_TOOL,
}

#: 只吃自然语言 ``question`` 的能力（上游的 ``inputSchema`` 里就只有这一个必填键）。
#: 用于「代码 → 名称」的归一化：这些工具认名称，``get_index_kline`` 两种都认。
_QUESTION_CAPABILITIES = frozenset({'index_basicinfo', 'index_technicals', 'market_search'})

#: 指数代码 → 上游查询名（``question`` 类工具用名称更稳）。
#: 只登记核心宽基；未登记的代码**报错**而不是原样透传 —— 透传的结果是上游回
#: ``Invalid value``，现场看不出是我们没做映射。
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
    """指数代码 → 上游查询名。未登记代码抛 ``ValueError``（不静默透传）。"""
    key = (code or '').strip().upper()
    try:
        return INDEX_QUERY_NAMES[key]
    except KeyError:
        known = ', '.join(sorted(INDEX_QUERY_NAMES))
        raise ValueError(f'指数代码 {code!r} 未登记查询名（已知：{known}）；上游认名称不认代码') from None


@register_provider
class WindProvider(McpProvider):
    """Wind MCP：公开市场数据（指数点位 / 档案 / 技术指标）。"""

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

    def _wire(self, tool: str, arguments: dict) -> Dict[str, Any]:
        """``tools/call`` 请求体（标准 JSON-RPC，但数据工具要过二级网关）。

        实测（2026-10-23）：直接 POST ``{'toolName': …}`` 会被上游按 pydantic 校验拒收
        （``HTTP 400`` + 11 条 ``JSONRPCMessage`` 字段缺失），所以**请求体仍是 JSON-RPC**；
        而**工具**只有 ``market_call_tool`` 能转发数据查询 —— 于是「形状」与「转发」两件事
        分开：形状走基类，转发在这里。

        ``market_search_tools`` 是上游的检索入口，直接以工具名调用即可。
        """
        if tool == MARKET_SEARCH_TOOL:
            return super()._wire(tool, arguments)
        return super()._wire(
            GATEWAY_CALL_TOOL,
            {'toolName': tool, 'arguments': json.dumps(arguments, ensure_ascii=False)},
        )

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

    # ── 参数归一化（§6.2）──
    def map_args(self, capability: str, **kwargs: Any) -> Dict[str, Any]:
        """业务参数 → 上游参数。

        只做**值级**归一化（不发明参数名）：参数名由调用方按上游文档写，这里负责
        「日期 / 代码 / 批量」三种值的形态差异。这样即使上游改了参数名，本方法也不需要跟着改。
        """
        args: Dict[str, Any] = {}
        for key, value in kwargs.items():
            if isinstance(value, (list, tuple, set, frozenset)):
                # 坑③：批量参数是逗号分隔字符串，不是数组（元素同样走值级归一化）
                normalized = [self._normalize_value(capability, key, item) for item in value]
                args[key] = ','.join(str(item) for item in normalized)
            else:
                args[key] = self._normalize_value(capability, key, value)
        return args

    @staticmethod
    def _normalize_value(capability: str, key: str, value: Any) -> Any:
        """单个值的归一化（``period`` 别名 / 指数代码 → 查询名），其余原样。"""
        if key == 'period':
            return _normalize_period(value)
        if capability in _QUESTION_CAPABILITIES and isinstance(value, str) and _INDEX_CODE_RE.match(value.strip()):
            return index_query_name(value)
        return value

    # ── 结果解析（坑④）──
    def extract(self, text: str, columns: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        """上游表格 → 行字典列表。

        实测（2026-10-23）**两种**形状都要认，且都**不是** ``{columnNames, rows}``：

        ``get_index_kline``::

            {"data": {"columns": [{"name": "TIME", "type": "string"}, ...],
                      "rows": [["2026-10-15T00:00:00.000+08:00", "4145.95", ...]],
                      "unit": {"TURNOVER 单位": "元"}}, "error": null}

        ``get_index_basicinfo``（**多包一层** ``data.data`` 且是个数组）::

            {"data": {"data": [{"columns": [{"name": "Wind代码"}, ...],
                                "rows": [["399300.SZ", "沪深300", ...]]}]}, "error": null}

        旧的 ``{columnNames: [str], rows: [[...]]}`` 一并保留（``market_search_tools``
        与历史夹具都是这个形状）。

        Args:
            text: 传输层返回的文本片段（网关的 JSON 字符串）。
            columns: 关心的列名。**缺列显式填 ``None``**（坑④），
                让「上游这期没给这一列」与「我们没取这一列」在数据上可区分。

        Raises:
            McpBadResponse: 不是 JSON、``error`` 非空，或里面没有可识别的表格。
                不返回空列表 —— 空列表在上层会被读成「这只指数没有数据」。
        """
        payload = self._decode(text)
        self._raise_for_error(payload)
        tables = list(self._iter_tables(payload))  # 必须物化：生成器恒为真，`if not tables` 会失效
        rows: List[Dict[str, Any]] = []
        for names, raw_rows in tables:
            for raw_row in raw_rows:
                record = self._row_to_record(names, raw_row)
                for column in columns or ():
                    record.setdefault(column, None)
                rows.append(record)
        if not tables:
            raise McpBadResponse(f'Wind 返回里没有可识别的表格：{text[:120]}', provider=self.name)
        return rows

    def _decode(self, text: str) -> Any:
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            raise McpBadResponse(f'Wind 返回非 JSON：{text[:120]}', provider=self.name) from None

    def _raise_for_error(self, payload: Any) -> None:
        """``error`` 非空即抛（顶层与 ``data.error`` 都要看）。

        实测上游成功时两个位置都是 ``null``；但「工具名不存在」这类失败是
        ``{"data": ..., "error": {"code": 400, "message": "..."}}`` —— 只有当
        ``isError`` 被传输层漏看时才轮到它兜底，故照样分类，不静默。
        """
        if not isinstance(payload, dict):
            return
        candidates = [payload.get('error')]
        data = payload.get('data')
        if isinstance(data, dict):
            candidates.append(data.get('error'))
        for err in candidates:
            if err:
                raise classify_payload(err, provider=self.name)

    @classmethod
    def _iter_tables(cls, node: Any) -> Iterable[Tuple[List[str], List[Any]]]:
        """递归找出所有表格块，产出 ``(列名, 行)``（网关会把多张表并列 / 多包一层）。"""
        if isinstance(node, dict):
            if 'columnNames' in node or 'rows' in node or 'columns' in node:
                yield cls._column_names(node), list(node.get('rows') or [])
                return
            for value in node.values():
                yield from cls._iter_tables(value)
        elif isinstance(node, list):
            for item in node:
                yield from cls._iter_tables(item)

    @staticmethod
    def _column_names(node: Dict[str, Any]) -> List[str]:
        """两种列名形状 → ``[str]``：``columnNames: ["日期"]`` 或 ``columns: [{"name": "日期"}]``。"""
        legacy = node.get('columnNames')
        if isinstance(legacy, list):
            return [str(name) for name in legacy]
        columns = node.get('columns')
        if isinstance(columns, list):
            names = [item.get('name') for item in columns if isinstance(item, dict) and item.get('name')]
            return [str(name) for name in names]
        return []

    @staticmethod
    def _row_to_record(names: Sequence[str], raw_row: Any) -> Dict[str, Any]:
        """一行原始数据 → 列名到值的映射；短行缺的位置填 ``None``（不丢列）。"""
        if isinstance(raw_row, dict):
            return dict(raw_row)
        cells = list(raw_row) if isinstance(raw_row, (list, tuple)) else [raw_row]
        return {name: (cells[index] if index < len(cells) else None) for index, name in enumerate(names)}
