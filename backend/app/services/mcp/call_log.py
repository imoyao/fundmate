# -*- coding: utf-8 -*-
"""MCP 调用记录与回读（S2）：``mcp_call_logs`` 的唯一写方与唯一读方。

两个职责刻意放在一起：**写什么由读的需要决定**。health 段要回答的三个问题是
「最近一次失败是哪一类」「今天调了多少次」「24 小时内错了几次」，表就只存这几件事
需要的列，不预留「以后可能有用」的字段（数据策略：新列必须当场指定读者）。

三条纪律：

1. **记录永不打断主链路**：落库失败只 warning（与 ``core.cache`` 同口径）——
   审计坏了不能让取数跟着坏，但**必须留日志**，不能静默；
2. **读不到 ≠ 没有错误**：:func:`provider_snapshot` 查询失败时返回
   ``available=False``，health 据此报 ``unknown``。把它退化成"没有错误"就是 #171
   那类假绿（拿不到输入却输出正常结论）；
3. **时间口径统一**：``called_at`` 存东八区 naive（SQLite 不保留时区），
   比较前一律 ``now_shanghai().replace(tzinfo=None)``，避免 aware/naive 相减 500（#1793）。
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterator, Optional

from loguru import logger
from sqlalchemy import desc, func

from app.core.database import market_session
from app.core.time_utils import as_shanghai, now_shanghai
from app.models.mcp_call_log import McpCallLog
from app.services.mcp.errors import McpError, sanitize

#: 默认回看窗口（小时）：health 的「最近 24h 错误数」
DEFAULT_WINDOW_HOURS = 24


@dataclass
class CallRecord:
    """一次调用的计时上下文（``record_call`` 产出，调用方无需使用其字段）。"""

    provider: str
    capability: str
    scope: Optional[str] = None
    started_at: float = field(default_factory=time.monotonic)


def _scope_value(scope: Any) -> Optional[str]:
    """``DataScope`` / 字符串 → 落库用的字符串（``StrEnum`` 取 value）。"""
    if scope is None:
        return None
    return str(getattr(scope, 'value', scope))


@contextmanager
def record_call(provider: str, capability: str, *, scope: Any = None) -> Iterator[CallRecord]:
    """记录一次 MCP 调用的结果（成功与失败都记），失败时**原样上抛**。

    用法::

        with record_call('qieman', 'latest_quotations', scope=DataScope.PLATFORM_PUBLIC):
            text = transport.call_tool(...)

    ⚠️ 不要在这里 ``except`` 掉异常：本上下文管理器的契约是"记账并上抛"，
    吞掉异常会让调用方重新回到「空数据 = 成功」的旧形态。
    """
    rec = CallRecord(provider=provider, capability=capability, scope=_scope_value(scope))
    try:
        yield rec
    except McpError as exc:
        persist(
            provider=provider,
            capability=capability,
            scope=rec.scope,
            ok=False,
            error_kind=str(exc.kind),
            http_status=exc.http_status,
            duration_ms=_elapsed_ms(rec),
            message=exc.user_message,
        )
        raise
    except Exception as exc:  # noqa: BLE001 - 非 MCP 家族异常同样要留痕，然后原样上抛
        persist(
            provider=provider,
            capability=capability,
            scope=rec.scope,
            ok=False,
            error_kind='unexpected',
            duration_ms=_elapsed_ms(rec),
            message=sanitize(f'{type(exc).__name__}: {exc}'),
        )
        raise
    else:
        persist(
            provider=provider,
            capability=capability,
            scope=rec.scope,
            ok=True,
            duration_ms=_elapsed_ms(rec),
        )


def _elapsed_ms(rec: CallRecord) -> int:
    return int((time.monotonic() - rec.started_at) * 1000)


def persist(
    *,
    provider: str,
    capability: str,
    ok: bool,
    scope: Optional[str] = None,
    error_kind: Optional[str] = None,
    http_status: Optional[int] = None,
    duration_ms: Optional[int] = None,
    message: Optional[str] = None,
) -> None:
    """写一行调用审计（**永不抛异常**；失败只 warning）。"""
    try:
        with market_session() as db:
            db.add(
                McpCallLog(
                    provider=provider,
                    capability=capability,
                    scope=scope,
                    ok=ok,
                    error_kind=error_kind,
                    http_status=http_status,
                    duration_ms=duration_ms,
                    message=sanitize(message) or None,
                    # 落库用 naive 东八区墙钟：SQLite 不保留时区偏移，读回来才不会 500（#1793 同因）
                    called_at=now_shanghai().replace(tzinfo=None),
                )
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - 审计故障不得影响取数主链路
        logger.warning(f'MCP 调用审计落库失败（已忽略）：{sanitize(exc)}')


def provider_snapshot(
    provider: str,
    *,
    now: Optional[datetime] = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> Dict[str, Any]:
    """某 provider 的最近状态（health 段的唯一数据来源；只读库、不联网）。

    Returns:
        ``{'available': bool, ...}``。``available=False`` 表示**读不到**（表缺 / DB 抖动），
        调用方必须显式表达"结论不可信"，不得当作"没有错误"。
    """
    current = as_shanghai(now) if now is not None else now_shanghai()
    naive_now = current.replace(tzinfo=None)
    day_start = naive_now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = naive_now - timedelta(hours=window_hours)
    try:
        with market_session() as db:
            last_error = (
                db.query(McpCallLog)
                .filter(McpCallLog.provider == provider, McpCallLog.ok.is_(False))
                .order_by(desc(McpCallLog.called_at))
                .first()
            )
            last_ok = (
                db.query(McpCallLog)
                .filter(McpCallLog.provider == provider, McpCallLog.ok.is_(True))
                .order_by(desc(McpCallLog.called_at))
                .first()
            )
            calls_today = (
                db.query(func.count(McpCallLog.id))
                .filter(McpCallLog.provider == provider, McpCallLog.called_at >= day_start)
                .scalar()
            )
            errors_window = (
                db.query(func.count(McpCallLog.id))
                .filter(
                    McpCallLog.provider == provider,
                    McpCallLog.ok.is_(False),
                    McpCallLog.called_at >= since,
                )
                .scalar()
            )
    except Exception as exc:  # noqa: BLE001 - health 端点不得因审计表缺失而 500
        logger.warning(f'health: 读取 mcp_call_logs 失败（{provider}）：{sanitize(exc)}')
        return {'available': False, 'reason': sanitize(exc)}

    return {
        'available': True,
        'last_error_kind': last_error.error_kind if last_error is not None else None,
        'last_error_at': _iso(last_error.called_at) if last_error is not None else None,
        'last_error_message': last_error.message if last_error is not None else None,
        'last_ok_at': _iso(last_ok.called_at) if last_ok is not None else None,
        'calls_today': int(calls_today or 0),
        'errors_24h': int(errors_window or 0),
    }


def _iso(value: Optional[datetime]) -> Optional[str]:
    """naive 东八区墙钟 → 带偏移的 ISO 串（与 health 的 scheduler 段同口径）。"""
    if value is None:
        return None
    return as_shanghai(value).isoformat()
