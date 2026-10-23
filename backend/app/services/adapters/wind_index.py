# -*- coding: utf-8 -*-
"""万得指数日线适配器（Wind MCP 路，S4）。

**为什么单开这一路**：`.WI` 只是代码形态，不决定数据源。韭圈儿覆盖了大部分万得系
基金指数，但 `885002.WI`（万得平衡混合型基金指数）在韭圈儿**源侧未收录**
（2026-10-21 实测 `disabled=True` / `data={}` / `series` 长度 0），而万得官方
MCP **可取真实收盘**（2026-10-23 实测：5537 条，2003-12-31 起，2026-10-22 收 7206.3199）。
`#2476` 因此被误判成「万得没有这个指数」，实际是「我们没接这条源」。

口径
----
``price_mode='raw'``：万得给的是**指数真实点位**，既不是韭圈儿 anchored（反推派生、
锚随最新收盘平移）、也不是 normalized（起点归一化 1000）。三种口径不能混用，
故单列 ``wind``/``raw``，让下游能区分。

源选择为什么写死在代码里、不做「先韭圈儿、失败再万得」
-----------------------------------------------------
运行时回退会在某天 A 源恢复时**静默换源**，而两条源**不是同一尺度**。2026-10-23 实测同一
代码同一交易日（`index_daily` 存量 vs 万得 MCP）：

===========================  =================  ==================
代码                          韭圈儿（库内）        万得 MCP（真实点位）
===========================  =================  ==================
`885001.WI`                  925.6               10877.345
`885000.WI`                  935.7              14769.2608
===========================  =================  ==================

差一个数量级：拼接后就是一段凭空涨跌（同族教训 #2464）。故由
``index_daily_job.WIND_MCP_INDEX_CODES`` 显式声明谁走哪条源，不做试探。

不做缓存 / 落库
---------------
本模块只负责「取 + 归一化成行」，写库仍是 job 的职责（upsert 语义见
``index_daily_job._save_data``）。一次调用建一个会话（initialize + call），
因为当前只有 1 个目标；目标变多时再考虑复用 transport，别提前优化。
"""

import json
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT
from app.services.mcp import get_provider
from app.services.mcp.credentials import is_configured, resolve_token
from app.services.mcp.providers.wind import WIND_MCP_URL_ENV

#: 全历史起点。万得该指数序列始于 2003-12-31（实测），1990 只作为「早于一切」的界。
_FULL_SYNC_BEGIN = date(1990, 1, 1)
#: 增量窗口天数，与腾讯 / 韭圈儿两路对齐（12 月）。
_INCREMENT_DAYS = 365
#: 关心的列：`MATCH` 是收盘（实测语义，非 `CLOSE`）。
_COLUMNS = ('TIME', 'MATCH')


def is_available() -> bool:
    """Wind 路是否可用（Token + 服务地址都配了才算）。

    单独的判据函数而不是「调用时抛错再兜」：job 需要**事先**区分「未配置」（可选组件
    不可用，降级计数）与「配置了但上游失败」（真故障，记 errors）。两者的运维动作不同，
    混成一个 try/except 会让「今天没配 Token」永远显示成「数据源故障」。
    """
    return is_configured('wind') and bool((os.getenv(WIND_MCP_URL_ENV) or '').strip())


def _post_factory(provider: Any, token: str):
    """构造传输层的 ``post`` 回调：HTTP 细节只在这里，传输层不认识 requests。"""
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


def _parse_trade_date(raw: Any) -> Optional[date]:
    """``2026-10-22T00:00:00.000+08:00`` → ``date(2026, 10, 22)``；认不出返回 ``None``。"""
    text = str(raw or '')[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_close(raw: Any) -> Optional[float]:
    """空值 / 非数字返回 ``None``（**不写 0**：0 会被下游算成一个 -100% 的交易日）。"""
    text = str(raw or '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_index_daily(code: str, full_sync: bool = False) -> List[Dict[str, Any]]:
    """取万得指数日线（真实收盘）。

    Args:
        code: 万得代码，如 ``885002.WI``。**认代码、不认名称**（实测），故不做名称映射。
        full_sync: ``True`` 取成立以来；``False`` 取近 12 月。

    Returns:
        ``[{'trade_date': date, 'close': float}, ...]``，按日期升序、已去重。
        空列表表示「上游确实没有序列」，由调用方决定是降级还是报错。

    Raises:
        McpTokenMissing / WindEndpointMissing: 未配置（调用方应先用 :func:`is_available` 判断）。
        McpError 子类: 上游 / 鉴权 / 额度错误。**一次性抛给 job**，不在本层吞掉。
    """
    provider = get_provider('wind')
    token = resolve_token(provider.name, provider.scope_of('index_kline'))
    transport = provider.build_transport(_post_factory(provider, token))

    begin = _FULL_SYNC_BEGIN if full_sync else date.today() - timedelta(days=_INCREMENT_DAYS)
    args = provider.map_args(
        'index_kline',
        windcode=code,
        period='10',  # 日 K：上游只认 "10"（provider 内已映射，这里显式写死避免误传）
        begin_date=begin.isoformat(),
        end_date=date.today().isoformat(),
    )
    text = transport.call_tool(provider.tool_for('index_kline'), args, token=token)
    records = provider.extract(text, columns=_COLUMNS)

    by_date: Dict[date, float] = {}
    for record in records:
        trade_date = _parse_trade_date(record.get('TIME'))
        close = _parse_close(record.get('MATCH'))
        if trade_date is None or close is None:
            continue
        by_date[trade_date] = close  # 同日重复以最后一条为准（上游偶发重复行）
    rows = [{'trade_date': day, 'close': by_date[day]} for day in sorted(by_date)]
    logger.debug(f'Wind 指数日线 {code}: {len(rows)} 条（full_sync={full_sync}，起 {begin.isoformat()}）')
    return rows
