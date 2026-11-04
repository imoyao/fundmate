#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wind MCP 只读探针（S3）：人工探测 + 真实错误报文采样。

用法（``pdm run mcp-probe ...``）::

    pdm run mcp-probe --list
    pdm run mcp-probe --question "沪深300 最近一年收益率" --args '{"question": "沪深300"}'
    pdm run mcp-probe --capability index_kline --args '{"windcode": "000300.SH", "begin_date": "2026-10-15", "end_date": "2026-10-23"}'
    pdm run mcp-probe --capability index_kline --args '{...}' --save-body .tmp/wind_err.json

为什么单独一个 CLI（设计文档 §6.3）
----------------------------------
生产链路**不做自然语言检索**：``market_search_tools`` 每次 1–2s 且结果依赖语义，线上会出现
「同一份代码今天取不到、明天又好了」的不可复现故障。故工具名一律走 registry 静态映射，
检索只留给人在终端里用。本探针就是那个「只留给人」的入口。

只读纪律
--------
允许的工具集合来自 :meth:`WindProvider.read_only_tool_names`，**不提供任意 ``--tool`` 直传**：
Wind 的写接口误调不可撤销，而探针的职责只是探测与采样。

采样纪律（S3 的验收项）
----------------------
失败时打印 ``kind / http_status / retryable / action / user_message`` 与**已脱敏**的上游报文
（``errors.sanitize`` 已抹掉 ``Authorization`` / ``token=`` 这类回显），
``--save-body <path>`` 可把同一份脱敏报文落盘留证。Token 只从环境变量读，**任何分支都不打印**。

退出码
------
====  =========================================================
0     调用成功
2     本地输入 / 配置缺失（Token、WIND_MCP_URL、参数 JSON）——**没有结论**
3     上游调用失败（已分类，结论有效）
====  =========================================================
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 将项目根目录（backend/）加入 Python 路径 —— 必须在 import app 之前。
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=BACKEND_DIR / '.env')

import requests  # noqa: E402

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT  # noqa: E402
from app.services.mcp import get_provider  # noqa: E402
from app.services.mcp.credentials import resolve_token  # noqa: E402
from app.services.mcp.errors import McpError, McpTokenMissing, sanitize  # noqa: E402
from app.services.mcp.providers.wind import WindEndpointMissing, WindProvider  # noqa: E402

_PROVIDER = 'wind'


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='mcp-probe',
        description='Wind MCP 只读探针（只允许只读工具；失败时输出可采样的错误报文）',
    )
    parser.add_argument('--list', action='store_true', help='列出能力名与工具名（不需要 Token / 地址）')
    parser.add_argument('--capability', help='按能力名调用（见 --list）')
    parser.add_argument('--question', help='自然语言问题：等价于 --capability market_search')
    parser.add_argument(
        '--args',
        dest='args_json',
        default='{}',
        help='工具参数的 JSON 对象（参数名按上游文档写，本探针不发明参数名）',
    )
    parser.add_argument('--save-body', help='失败时把**已脱敏**的上游报文写到该路径（Git 忽略区）')
    parser.add_argument('--timeout', type=int, default=DEFAULT_REQUEST_TIMEOUT, help='HTTP 超时秒数')
    parser.add_argument('--max-chars', type=int, default=4000, help='成功时打印的结果长度上限')
    return parser


def _print_capabilities(provider: WindProvider) -> None:
    print(f'{provider.name} 的能力（工具名走静态映射，生产链路不用检索）：')
    for capability in provider.capabilities():
        print(f'  {capability:<20} -> {provider.tool_for(capability)}')


def _post_factory(provider: WindProvider, token: str, timeout: int):
    """构造传输层的 ``post`` 回调（HTTP 细节只在这里，传输层不认识 requests）。"""
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
        return session.post(provider.base_url(), data=body, headers=headers, timeout=timeout)

    return post


def _report_failure(err: McpError, save_body: Optional[str]) -> None:
    """打印一次失败的**可采样**现场（已脱敏）。"""
    print('---- 调用失败（可采样现场）----')
    print(f'kind          : {err.kind}')
    print(f'http_status   : {err.http_status if err.http_status is not None else "(无 HTTP 语义)"}')
    print(f'retryable     : {err.retryable}')
    print(f'action        : {err.action}')
    print(f'user_message  : {err.user_message}')
    print(f'detail        : {err.detail or "(上游未给 detail)"}')
    if save_body:
        path = Path(save_body)
        path.parent.mkdir(parents=True, exist_ok=True)
        # 只写 err.detail（构造时已过 sanitize），且带 BOM 会污染仓库文件，故无 BOM
        path.write_text(err.detail + '\n', encoding='utf-8')
        print(f'已保存脱敏报文: {path}')


def _parse_args_json(raw: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f'--args 不是合法 JSON：{exc}') from None
    if not isinstance(parsed, dict):
        raise ValueError('--args 必须是 JSON 对象（键值对），例如 \'{"codes": ["000300.SH"]}\'')
    return parsed


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    ns = parser.parse_args(argv)

    provider = get_provider(_PROVIDER)
    if not isinstance(provider, WindProvider):  # pragma: no cover - 注册表错配才会走到
        print(f'注册表里的 {_PROVIDER} 不是 WindProvider：{type(provider)!r}', file=sys.stderr)
        return 2

    if ns.list:
        _print_capabilities(provider)
        return 0

    if ns.question and ns.capability:
        print('--question 与 --capability 只能二选一（前者等价于 market_search）', file=sys.stderr)
        return 2
    capability = ns.capability or ('market_search' if ns.question else '')
    if not capability:
        parser.print_help()
        return 2

    if capability not in provider.capabilities():
        print(f'未知能力 {capability!r}（已知：{", ".join(provider.capabilities())}）', file=sys.stderr)
        return 2
    tool = provider.tool_for(capability)
    if tool not in provider.read_only_tool_names():  # pragma: no cover - 能力表即白名单
        print(f'拒绝调用非只读工具 {tool!r}（探针只做只读探测）', file=sys.stderr)
        return 2

    try:
        arguments = _parse_args_json(ns.args_json)
        if ns.question and 'query' not in arguments:
            # 参数名未实测：只做「把问题塞进 query」的便利，报错时提示改用 --args
            arguments = {**arguments, 'query': ns.question}
        arguments = provider.map_args(capability, **arguments)
        token = resolve_token(_PROVIDER, provider.scope_of(capability))
        base_url = provider.base_url()
    except ValueError as exc:
        print(f'参数不合法：{exc}', file=sys.stderr)
        return 2
    except (McpTokenMissing, WindEndpointMissing) as exc:
        print(f'本地配置缺失，本次**没有结论**：{exc}', file=sys.stderr)
        return 2

    transport = provider.build_transport(_post_factory(provider, token, ns.timeout))
    print(f'provider={_PROVIDER} capability={capability} tool={tool} url={base_url}')
    print(f'arguments={json.dumps(arguments, ensure_ascii=False)}')
    try:
        text = transport.call_tool(tool, arguments, token=token)
    except McpError as exc:
        _report_failure(exc, ns.save_body)
        return 3

    print('---- 调用成功 ----')
    clipped = text if len(text) <= ns.max_chars else text[: ns.max_chars] + f'…（截断，共 {len(text)} 字符）'
    print(f'raw（已脱敏）: {sanitize(clipped, ns.max_chars)}')
    try:
        rows = provider.extract(text)
    except McpError as exc:
        print(f'（未能解析为 columnNames/rows 表格：{exc.detail or exc}）')
        return 0
    print(f'解析出 {len(rows)} 行，前 3 行：')
    for row in rows[:3]:
        print(f'  {json.dumps(row, ensure_ascii=False)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
