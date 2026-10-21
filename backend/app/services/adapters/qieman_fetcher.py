# -*- coding: utf-8 -*-
"""且慢（盈米）MCP 取数：市场温度 + 投顾组合持仓/概览。

从 ``thermometer.fetchers`` / ``thermometer.constants`` 上提到适配层（#1607 批次 4）：
且慢投顾适配器 ``adapters/qieman_advisor_adapter`` 复用 ``QiemanFetcher``，而原实现
落在 thermometer 家族内，形成 ``adapters → thermometer`` 反向边（R5 违规）。上提后，
thermometer 家族反过来依赖本模块（合法方向），方向自洽。

包含：``QIEMAN_*`` 常量、3 个归一化助手、``QiemanFetcher``（自原文件**逐字搬运**）。

调用量（2026-10 实测量级）：且慢投顾 job 每晚抓 111 只 QIEMAN 组合的持仓 + 概览。
原始实现每只组合**各调一次**工具、且**每次调用都重新握手**（initialize + initialized +
tools/call = 3 个 HTTP 请求），于是 111×2 = 222 次工具调用 = 666 个请求。本模块有三处收敛：

1. **会话复用**：``Mcp-Session-Id`` 缓存在 fetcher 实例上（且慢服务端**不回**该响应头，
   实测 2026-10-20）——故「已握手」本身也要缓存，否则连续调用会退回逐次握手；
2. **概览批量**：:meth:`QiemanFetcher.fetch_strategy_details` 本就按 ``batch_size`` 分批，
   适配器改为一次传入全部 code ⇒ 111 只 = 3 次调用；
3. **持仓批量**：``strategyCodes`` 传多只，响应 ``{code: {...}}`` 按 code 切分；
   批量语义未被上游文档保证，故**缺键即该批降级逐只**（批量拿不到 ≠ 数据变空）。

2026-10-21（MCP S1）：上面第 1 条的**实现**（会话缓存 / 握手 / 失效重握 / SSE 解析）已抽到
``app/services/mcp/``（传输层与 provider 基类），本模块只保留业务解析与批量策略；
调用量收敛的三条结论不变，且 Wind 接入不再需要照抄这份传输。
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.core.utils import to_float as _to_float
from app.services.adapters.fetcher_base import SingleValueFetcher
from app.services.mcp import McpTransport, get_provider
from app.services.mcp.providers.qieman import (  # noqa: F401  兼容再导出：既有导入点（含测试）不必改
    QIEMAN_CLIENT_INFO,
    QIEMAN_MCP_URL,
    QIEMAN_PROTOCOL_VERSION,
    QIEMAN_STRATEGY_COMPOSITION_TOOL,
    QIEMAN_STRATEGY_DETAIL_TOOL,
    QIEMAN_TOOL,
)

# ─── 且慢 MCP（Streamable HTTP）───
# 服务地址 / 协议版本 / 客户端信息 / 工具名已搬去 ``app/services/mcp/providers/qieman.py``
# （2026-10-21，MCP S1）：它们描述「这家服务长什么样」，不属于取数逻辑，Wind 接入时同理。
# 上面那行 import 是**兼容再导出** —— 旧导入点（含测试）取到的仍是同一批值。

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


def _normalize_codes(strategy_codes: Any) -> List[str]:
    """组合代码去空、去重、保序（批量调用前统一口径，避免空串污染 ``strategyCodes``）。"""
    out: List[str] = []
    seen: set = set()
    for c in strategy_codes or []:
        s = str(c).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _flat_holding_rows(parsed: Any) -> Optional[list]:
    """取扁平形态的持仓数组（顶层 list / ``{result|data: [...]}``）；无则 None。

    用「键是否存在 + 是否 list」判定，不用真值判定：``{'result': []}`` 是合法的空持仓，
    而 ``[] or None`` 会把它误判成「认不出这个 code」，白白多打一次批量外的单只请求。
    """
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ('result', 'data'):
            rows = parsed.get(key)
            if isinstance(rows, list):
                return rows
    return None


def _flatten_flat_holdings(rows: Any) -> List[dict]:
    """扁平形态（旧版 / 单组合响应）：无类别信息，逐条归一化。"""
    out: List[dict] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        rec = _normalize_holding(item)
        if rec:
            out.append(rec)
    return out


def _flatten_category_block(block: dict) -> List[dict]:
    """真实结构 ``{基金类别: {持有成分: [...], 分类占比}}``：遍历类别打平并保留类别归属。"""
    out: List[dict] = []
    for category, body in block.items():
        if not isinstance(body, dict):
            continue
        for item in body.get('持有成分') or []:
            if not isinstance(item, dict):
                continue
            rec = _normalize_holding(item, category)
            if rec:
                out.append(rec)
    return out


def _parse_composition(parsed: Any, code: str) -> Optional[List[dict]]:
    """解析响应中 ``code`` 的持仓；返回 ``None`` 表示**响应里认不出该 code**。

    调用方据此决定是否降级逐只（``None`` = 缺键，``[]`` = 确认没有持仓）——
    这两种情况必须分开，否则「批量拿不到」会被静默写成「持仓变空」。
    """
    rows = _flat_holding_rows(parsed)
    if rows is not None:
        return _flatten_flat_holdings(rows)
    if isinstance(parsed, dict):
        block = parsed.get(code)
        if isinstance(block, dict):
            return _flatten_category_block(block)
        if block is not None:
            # 键在但不是对象（脏数据）：该组合确认为空，不触发降级
            return []
    return None


class QiemanFetcher(SingleValueFetcher):
    """且慢：市场温度计（中证全A），通过 MCP Streamable HTTP 协议获取。

    传输（会话缓存 / 握手 / SSE 解析 / 失效重握）自 2026-10-21（MCP S1）起由
    :class:`app.services.mcp.McpTransport` 承担；本类保留「这家服务怎么调」——
    地址与请求头来自 :class:`app.services.mcp.providers.qieman.QiemanProvider`，
    业务解析（归一化助手、批量与降级）仍全部在本模块。
    """

    source = 'qieman'
    name = '市场温度计(中证全A)'
    unit = '%'

    def __init__(self, timeout: int = DEFAULT_REQUEST_TIMEOUT):
        super().__init__(timeout)
        self._provider = get_provider('qieman')
        #: 传输对象**惰性构造**：构造时才捕获 ``self._mcp_post``（测试会 monkeypatch 它）。
        #: 若在 ``__init__`` 里就绑定，被替换掉的替身不会被看到，测试会静默失效。
        self._transport_obj: Optional[McpTransport] = None

    # ---- 且慢 MCP（Streamable HTTP）----
    @property
    def _transport(self) -> McpTransport:
        """本实例的传输（首次调用时构造，理由见 :meth:`__init__`）。"""
        if self._transport_obj is None:
            self._transport_obj = self._provider.build_transport(self._mcp_post, auth=self._apply_token)
        return self._transport_obj

    def _mcp_post(self, payload: dict, sid: Optional[str]) -> requests.Response:
        """且慢网关的 HTTP 细节：地址、来源头、会话头、超时。"""
        headers = {
            **self._provider.auth_headers(self.session.headers.get('x-api-key') or ''),
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
        }
        if sid:
            headers['Mcp-Session-Id'] = sid
        return self.session.post(self._provider.base_url(), json=payload, headers=headers, timeout=20)

    def _apply_token(self, token: str) -> None:
        """把 token 写进 session 头（:meth:`_mcp_post` 从中取 ``x-api-key``）。"""
        self.session.headers['x-api-key'] = token

    def _call_tool(self, api_key: str, tool: str, arguments: dict) -> str:
        """调用任意 MCP 工具，返回解析出的文本片段（兼容 SSE / JSON 两种响应）。

        ``#1392`` 扩展点：原 `_call_mcp` 只调 `GetLatestQuotations`；抽成通用方法后，
        且慢组合持仓（BatchGetStrategiesComposition）等可复用同一传输。

        **会话复用 / 失效重握**（2026-10-20 落地，S1 搬进传输层）：正常路径下连续 N 次
        调用**只握手一次**；仅当服务端明确不认当前会话（400/404/非 JSON）时**重新握手
        一次**再重试同一次调用，仍失败则抛错——不做无限重试，也不把失败吞成空结果
        （空结果会被上层读成「这组合没持仓」）。

        本方法是本模块**唯一**的工具调用入口，且保持同名可替换：测试与适配器都
        monkeypatch 它。
        """
        return self._transport.call_tool(tool, arguments, token=api_key)

    def fetch_strategy_composition(self, strategy_code: str) -> List[dict]:
        """且慢组合持仓（#1392）：BatchGetStrategiesComposition（单只入口）。

        真实返回结构（实测 2026-09）：
            {"<code>": {"<基金类别>": {"持有成分":[{"基金代码","基金名称","持仓占比":"4.54%",
                "最新净值","调仓时间","基金类型",...}], "分类占比":<str|num>}, ...}}
        即**按基金类别分桶**，故需遍历每个类别的 ``持有成分`` 列表并打平，
        这样单靠外层 code 取不到任何持仓（早期按扁平结构解析会静默返回空列表）。

        实现委托给 :meth:`fetch_strategy_composition_batch`（单只即长度为 1 的批量），
        保证单只与批量走**同一条解析/回退路径**，不会各修一半。

        返回归一化列表：[{code, name, ratio, category, nav, nav_date, adj_time, fund_type}]。
        ratio 由 "4.54%" 解析为 float(4.54)；字段缺失一律置 None。
        无 key / code 不存在 / 结构不可识别时返回 []。
        """
        code = str(strategy_code).strip()
        return self.fetch_strategy_composition_batch([code]).get(code, [])

    def fetch_strategy_composition_batch(
        self, strategy_codes: List[str], batch_size: int = QIEMAN_STRATEGY_BATCH_SIZE
    ) -> Dict[str, List[dict]]:
        """批量抓取组合持仓：一次 ``tools/call`` 传多个 ``strategyCodes``。

        **按 ``batch_size`` 分批**（与概览同一常量 50）：单请求的 code 上限未被上游文档
        或实测覆盖（只证实了 2 只可同批返回），分批把「未知上限」的风险限制在一批之内，
        且 111 只 = 3 次调用，相对逐只仍是 37 倍收敛。

        **批量语义的防御性回退**：响应按 code 分键（``{code: {...}}``）。逐只看：
        - 键在且是对象 ⇒ 按类别打平（正常路径）；
        - 键在但不是对象 ⇒ 该组合确认为空（``[]``），**不**降级；
        - **键不在 ⇒ 该 code 进降级名单**，整批解析完后逐只重取一次，
          避免「批量拿不到」被静默读成「这只组合没有持仓」。
        扁平形态（顶层 list / ``{result|data: [...]}``，旧版只支持单只）在多 code 时
        无法归属，同样全部降级逐只。

        返回 ``{code: [归一化持仓]}``，键覆盖**全部请求的 code**（拿不到的为 ``[]``）。
        """
        codes = _normalize_codes(strategy_codes)
        if not codes:
            return {}

        api_key = os.getenv('QIEMAN_API_KEY')
        if not api_key:
            logger.warning('QIEMAN_API_KEY 未配置，跳过且慢组合持仓')
            return {c: [] for c in codes}

        out: Dict[str, List[dict]] = {}
        for i in range(0, len(codes), batch_size):
            out.update(self._fetch_composition_chunk(api_key, codes[i : i + batch_size]))
        return out

    def _fetch_composition_chunk(self, api_key: str, codes: List[str]) -> Dict[str, List[dict]]:
        """单批持仓（含缺键降级逐只）。"""
        try:
            text = self._call_tool(api_key, self._provider.tool_for('strategy_composition'), {'strategyCodes': codes})
            parsed = json.loads(text)
        except Exception as e:  # noqa: BLE001
            logger.error(f'且慢组合持仓获取失败（{len(codes)} 个，如 {codes[:3]}）: {e}')
            return {c: [] for c in codes}

        out: Dict[str, List[dict]] = {}
        missing: List[str] = []
        flat_rows = _flat_holding_rows(parsed)
        if flat_rows is not None:
            # 扁平形态（旧版/单组合响应）没有 code 归属信息：单只采信，多只无法归属 ⇒ 全部降级
            if len(codes) == 1:
                out[codes[0]] = _flatten_flat_holdings(flat_rows)
            else:
                missing = list(codes)
        else:
            for code in codes:
                items = _parse_composition(parsed, code)
                if items is None:
                    missing.append(code)
                else:
                    out[code] = items

        if missing:
            logger.warning(
                f'且慢组合持仓批量响应里认不出 {len(missing)}/{len(codes)} 个组合（如 {missing[:3]}），降级逐只重取'
            )
            for code in missing:
                out[code] = self._fetch_composition_single(api_key, code)
        return out

    def _fetch_composition_single(self, api_key: str, code: str) -> List[dict]:
        """单只重取（批量响应缺键时的兜底）；失败返回 ``[]`` 并记日志。"""
        try:
            text = self._call_tool(api_key, self._provider.tool_for('strategy_composition'), {'strategyCodes': [code]})
            parsed = json.loads(text)
        except Exception as e:  # noqa: BLE001
            logger.error(f'且慢组合持仓获取失败 {code}: {e}')
            return []
        return _parse_composition(parsed, code) or []

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

        codes = _normalize_codes(strategy_codes)
        if not codes:
            return []

        out: List[dict] = []
        seen: set = set()
        for i in range(0, len(codes), batch_size):
            chunk = codes[i : i + batch_size]
            try:
                text = self._call_tool(
                    api_key,
                    self._provider.tool_for('strategy_details'),
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
                text = self._call_tool(api_key, self._provider.tool_for('latest_quotations'), {})
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
