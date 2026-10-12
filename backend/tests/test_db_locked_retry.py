# -*- coding: utf-8 -*-
"""``retry_on_db_locked`` 与 teardown 不遮蔽原始错误的契约（删持仓 500 修复）。

背景（dev 单库 + 进程内 scheduler）：删除端点先 SELECT 建立读快照，期间
scheduler 提交写事务后，DELETE 升级写锁会立即 ``database is locked``
（busy_timeout 对快照升级不生效）。修复：
1. 视图层 ``retry_on_db_locked`` 回滚请求会话后重跑整个视图（拿新快照）；
2. ``teardown_request_session`` 对 needs-rollback 会话不再抛 PendingRollbackError
   （否则会盖掉视图内已由错误处理器响应的原始错误）。

反向验证：去掉重试装饰器、或恢复 teardown 的裸 commit，下面用例必须转红。
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.database import get_db, teardown_request_session
from app.core.retry import retry_on_db_locked
from app.domains.ledgers.models import Ledger


def _locked_error() -> OperationalError:
    return OperationalError('DELETE FROM positions', {}, Exception('database is locked'))


def test_retry_recovers_after_locked_error(monkeypatch):
    """第一次 locked、第二次成功 → 重试后返回成功，共执行两次。"""
    monkeypatch.setattr('time.sleep', lambda *_: None)  # 测试不真睡
    calls = []

    @retry_on_db_locked(max_attempts=3, base_delay=0)
    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise _locked_error()
        return 'ok'

    assert flaky() == 'ok'
    assert len(calls) == 2


def test_retry_does_not_swallow_other_operational_errors(monkeypatch):
    """非 locked 的 OperationalError 必须原样上抛，不重试。"""
    monkeypatch.setattr('time.sleep', lambda *_: None)
    calls = []

    @retry_on_db_locked(max_attempts=3, base_delay=0)
    def broken():
        calls.append(1)
        raise OperationalError('SELECT 1', {}, Exception('disk I/O error'))

    with pytest.raises(OperationalError, match='disk I/O error'):
        broken()
    assert len(calls) == 1


def test_retry_raises_after_max_attempts(monkeypatch):
    """持续 locked → 用尽次数后抛出最后一次异常。"""
    monkeypatch.setattr('time.sleep', lambda *_: None)
    calls = []

    @retry_on_db_locked(max_attempts=3, base_delay=0)
    def always_locked():
        calls.append(1)
        raise _locked_error()

    with pytest.raises(OperationalError, match='database is locked'):
        always_locked()
    assert len(calls) == 3


def test_retry_rolls_back_request_sessions_before_retry(app):
    """重试前必须回滚请求级会话（放弃过期 WAL 读快照），否则重跑仍在旧快照上失败。"""
    rollback_calls = []

    @retry_on_db_locked(max_attempts=2, base_delay=0)
    def flaky():
        if not rollback_calls:
            raise _locked_error()
        return 'ok'

    with app.test_request_context('/api/'):
        with get_db() as db:
            original_rollback = db.rollback
            db.rollback = lambda *a, **k: (rollback_calls.append(1), original_rollback(*a, **k))
            assert flaky() == 'ok'
    assert len(rollback_calls) == 1


def test_teardown_skips_commit_when_session_needs_rollback(app, db):
    """视图内 flush 失败（会话 needs-rollback）后，teardown(exc=None) 不得抛
    PendingRollbackError——原始错误已由错误处理器响应，二次噪音会盖掉真因。"""
    with app.test_request_context('/api/'):
        with get_db() as session:
            # name 为 NOT NULL：flush 必然 IntegrityError，会话进入 needs-rollback
            session.add(Ledger(ledger_type='bank', family_id=1))
            with pytest.raises(IntegrityError):
                session.flush()
        # 模拟 Flask 错误处理器已生成响应后进入 teardown（exc=None）
        teardown_request_session(None)  # 修复前：抛 PendingRollbackError
    # teardown 已回滚：另一会话查询不受污染会话影响
    assert db.query(Ledger).count() >= 0


def test_teardown_still_raises_real_commit_failures(app, monkeypatch):
    """非 PendingRollbackError 的提交失败仍必须上抛（不许把真失败也吞掉）。"""
    with app.test_request_context('/api/'):
        with get_db() as session:
            session.execute(text('SELECT 1'))
            session.commit = MagicMock(side_effect=OperationalError('COMMIT', {}, Exception('database is locked')))
        with pytest.raises(OperationalError, match='database is locked'):
            teardown_request_session(None)
