# -*- coding: utf-8 -*-
"""MCP 调用审计单测（S2，#2490）：``mcp_call_logs`` 的唯一写方与唯一读方。

三件事必须钉住：

1. **成功与失败都留痕**：否则 health 段只能回答"最近没调用过"，回答不了"是不是一直在失败"；
2. **失败原样上抛**：记账不是吞异常的许可 —— 吞掉就等于回到「空数据 = 成功」的旧形态；
3. **读不到 ≠ 没有错误**：``provider_snapshot`` 读库失败必须返回 ``available=False``，
   由 health 报 ``unknown``。退化成「没有错误」就是拿不到输入却输出正常结论（#171）。

时间口径：``called_at`` 存东八区 naive 墙钟，比较前统一归一 —— 本文件显式传入固定
``called_at`` / ``now``，不依赖「跑测试时的当前时刻」（否则午夜前后会随机红）。
"""

from datetime import datetime, timedelta

import pytest

from app.core.database import market_session
from app.core.time_utils import SHANGHAI_TZ
from app.models.mcp_call_log import McpCallLog
from app.services.mcp.call_log import DEFAULT_WINDOW_HOURS, persist, provider_snapshot, record_call
from app.services.mcp.credentials import DataScope
from app.services.mcp.errors import McpAuthError, McpUnavailable

_PROVIDER = 'qieman'
#: 固定「现在」：东八区 12:00 —— 余量足够，无论窗口怎么算都不会跨日/跨界
_NOW = datetime(2026, 5, 20, 12, 0, tzinfo=SHANGHAI_TZ)


def _naive(dt: datetime) -> datetime:
    """aware → naive 墙钟（与 ``called_at`` 落库口径一致）。"""
    return dt.replace(tzinfo=None)


def _insert(provider=_PROVIDER, *, ok, called_at, error_kind=None, capability='cap', message=None) -> None:
    """直接插一行（不经 ``persist``）—— 用例要的是**确定的时刻**，不是"刚才"。"""
    with market_session() as db:
        db.add(
            McpCallLog(
                provider=provider,
                capability=capability,
                scope=DataScope.PLATFORM_PUBLIC.value,
                ok=ok,
                error_kind=error_kind,
                duration_ms=12,
                message=message,
                called_at=_naive(called_at),
            )
        )
        db.commit()


def _rows(provider=_PROVIDER):
    with market_session() as db:
        return db.query(McpCallLog).filter(McpCallLog.provider == provider).order_by(McpCallLog.id).all()


def test_success_writes_one_ok_row():
    with record_call(_PROVIDER, 'strategy_composition', scope=DataScope.PLATFORM_PUBLIC):
        pass

    rows = _rows()
    assert len(rows) == 1
    assert rows[0].ok is True
    assert rows[0].error_kind is None
    assert rows[0].capability == 'strategy_composition'
    assert rows[0].scope == 'platform_public'


def test_failure_writes_error_row_and_reraises_same_exception():
    """审计与上抛必须同时发生：只记账不抛 = 假绿；只抛不记账 = 无痕。"""
    boom = McpAuthError('401 unauthorized', provider=_PROVIDER, http_status=401)

    with pytest.raises(McpAuthError) as excinfo:
        with record_call(_PROVIDER, 'strategy_composition'):
            raise boom

    assert excinfo.value is boom  # 原样上抛，不包装
    rows = _rows()
    assert len(rows) == 1
    assert rows[0].ok is False
    assert rows[0].error_kind == 'auth'
    assert rows[0].http_status == 401
    # 落库的是**已脱敏的人话**，不是上游原文
    assert rows[0].message == boom.user_message


def test_non_mcp_exception_is_recorded_as_unexpected():
    """非本家族的异常（代码 bug / 三方库新异常）也要留痕，否则这类失败永远不可见。"""
    with pytest.raises(ValueError):
        with record_call(_PROVIDER, 'strategy_composition'):
            raise ValueError('unexpected shape')

    rows = _rows()
    assert len(rows) == 1
    assert rows[0].ok is False
    assert rows[0].error_kind == 'unexpected'


def test_scope_defaults_to_none_when_not_given():
    with record_call(_PROVIDER, 'latest_quotations'):
        pass

    assert _rows()[0].scope is None


def test_persist_never_raises_when_database_is_unavailable(monkeypatch):
    """审计坏掉不得让取数跟着坏：只 warning、不抛（与 ``core.cache`` 同口径）。"""

    def _boom():
        raise RuntimeError('market db down')

    monkeypatch.setattr('app.services.mcp.call_log.market_session', _boom)

    # 不抛即通过
    persist(provider=_PROVIDER, capability='cap', ok=True)


def test_snapshot_empty_table_reports_available_with_zero_counts():
    snap = provider_snapshot(_PROVIDER, now=_NOW)

    assert snap['available'] is True
    assert snap['calls_today'] == 0
    assert snap['errors_24h'] == 0
    assert snap['last_error_kind'] is None
    assert snap['last_ok_at'] is None


def test_snapshot_counts_today_and_window_and_picks_latest_error():
    """当日调用数 / 24h 错误数 / 最近一次失败 —— health 段的三问，各自由此回答。"""
    _insert(ok=True, called_at=_NOW - timedelta(hours=3))
    _insert(ok=True, called_at=_NOW - timedelta(hours=2))
    _insert(ok=False, called_at=_NOW - timedelta(hours=1), error_kind='auth', message='授权已失效')
    # 窗口外（3 天前）：不计入 errors_24h，也不计入 calls_today
    _insert(ok=False, called_at=_NOW - timedelta(days=3), error_kind='unavailable')
    # 别的 provider 的行不得串味
    _insert('wind', ok=False, called_at=_NOW - timedelta(hours=1), error_kind='quota')

    snap = provider_snapshot(_PROVIDER, now=_NOW)

    assert snap['available'] is True
    assert snap['calls_today'] == 3
    assert snap['errors_24h'] == 1
    assert snap['last_error_kind'] == 'auth'
    assert snap['last_error_message'] == '授权已失效'
    assert snap['last_error_at'] == (datetime(2026, 5, 20, 11, 0, tzinfo=SHANGHAI_TZ)).isoformat()
    assert snap['last_ok_at'] == (datetime(2026, 5, 20, 10, 0, tzinfo=SHANGHAI_TZ)).isoformat()


def test_snapshot_window_is_configurable():
    _insert(ok=False, called_at=_NOW - timedelta(hours=30), error_kind='unavailable')

    assert provider_snapshot(_PROVIDER, now=_NOW)['errors_24h'] == 0
    assert provider_snapshot(_PROVIDER, now=_NOW, window_hours=48)['errors_24h'] == 1
    assert DEFAULT_WINDOW_HOURS == 24


def test_snapshot_unreadable_table_reports_unavailable(monkeypatch):
    """**关键**：读不到必须显式声明"结论不可信"，不得退化成「没有错误」。"""

    def _boom():
        raise RuntimeError('table missing')

    monkeypatch.setattr('app.services.mcp.call_log.market_session', _boom)

    snap = provider_snapshot(_PROVIDER, now=_NOW)

    assert snap['available'] is False
    assert snap['reason']
    assert 'errors_24h' not in snap  # 不提供看起来正常的计数


def test_record_call_does_not_swallow_and_row_is_persisted_before_raise():
    """失败路径的落库发生在**上抛之前**：调用方拿到异常时，审计已经写完。"""
    with pytest.raises(McpUnavailable):
        with record_call(_PROVIDER, 'strategy_details'):
            raise McpUnavailable('503', provider=_PROVIDER, http_status=503)

    snap = provider_snapshot(_PROVIDER)
    assert snap['available'] is True
    assert snap['last_error_kind'] == 'unavailable'
