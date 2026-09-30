# -*- coding: utf-8 -*-
"""单实例守门测试（#1809）。

守门要解决的是「同一 SQLite 被多个后端实例并发写 → `database is locked`」，
本文件锁定它的四条规则与两条边界：

规则：① 空闲即拿到并落持有者信息；② 已被占用 → 冲突且给出可操作说明；
      ③ 同进程重复调用幂等；④ 冲突时以专用退出码退出。
边界：测试进程 / `APP_INSTANCE_GUARD=0` / 重载父进程 → 跳过；
      **服务子进程（`WERKZEUG_RUN_MAIN=true`）必须真守门**，不被 `--debug` 骗过。
"""

import os
import sys

import pytest

from app.core import instance_guard
from app.core.file_lock import acquire_lock, release_lock


@pytest.fixture(autouse=True)
def _reset_guard_state():
    """每个用例前后清掉模块级持锁状态并释放 fd。

    锁是进程级资源：不释放会让下一个用例「自己跟自己冲突」而假失败/假通过。
    """
    instance_guard._held_fd = None
    instance_guard._held_path = None
    yield
    release_lock(instance_guard._held_fd)
    instance_guard._held_fd = None
    instance_guard._held_path = None


@pytest.fixture
def guard_active(monkeypatch):
    """关掉「跳过」规则，让守门逻辑真正执行（否则在 pytest 进程里永远走 skipped 分支）"""
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.setattr(instance_guard, 'is_reloader_parent', lambda: False)
    monkeypatch.delenv(instance_guard.ENV_DISABLE, raising=False)


def test_acquire_writes_owner_pid(tmp_path, guard_active):
    """拿到锁后把持有者 PID 落进锁文件：多实例排查时要能知道「是谁占着」"""
    lock = tmp_path / 'app_instance.lock'

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok, reason
    assert f'pid={os.getpid()}' in instance_guard.read_owner_info(lock)


def test_second_instance_is_blocked_with_actionable_message(tmp_path, guard_active):
    """已被占用 → 冲突，且说明里必须点出「共享 SQLite 会 database is locked」与怎么清理"""
    lock = tmp_path / 'app_instance.lock'
    held, fd = acquire_lock(lock)
    assert held, '前置条件：模拟出的“另一个实例”应能拿到锁'
    try:
        ok, reason = instance_guard.acquire_web_instance_lock(lock)

        assert ok is False
        assert 'database is locked' in reason
        assert str(lock) in reason
        assert 'Get-Process' in reason
    finally:
        release_lock(fd)


def test_acquire_is_idempotent_in_same_process(tmp_path, guard_active):
    """create_app() 可能被同进程多次调用：第二次必须直接放行（不能自己跟自己冲突）"""
    lock = tmp_path / 'app_instance.lock'

    first, _ = instance_guard.acquire_web_instance_lock(lock)
    second, reason = instance_guard.acquire_web_instance_lock(lock)

    assert first and second
    assert '已持有' in reason


def test_skips_in_test_process(tmp_path):
    """pytest 进程跳过守门，且不留下锁文件（避免测试之间互相抢锁）"""
    lock = tmp_path / 'app_instance.lock'

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '测试进程' in reason
    assert not lock.exists()


def test_skips_when_disabled_by_env(tmp_path, monkeypatch):
    """APP_INSTANCE_GUARD=0 显式关闭（多实例是刻意行为的场景）"""
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.setenv(instance_guard.ENV_DISABLE, '0')
    lock = tmp_path / 'app_instance.lock'

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert instance_guard.ENV_DISABLE in reason
    assert not lock.exists()


@pytest.mark.parametrize('flag', ['--debug', '--reload'])
def test_skips_for_reloader_parent(tmp_path, monkeypatch, flag):
    """重载父进程跳过：它也会执行 create_app()，持锁会让服务子进程起不来（热重载报废）"""
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', flag])
    lock = tmp_path / 'app_instance.lock'

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '重载父进程' in reason
    assert not lock.exists()


def test_reloader_child_is_guarded(tmp_path, monkeypatch):
    """真正服务的子进程必须守门：`WERKZEUG_RUN_MAIN=true` 时不得被 --debug 误判为父进程"""
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.setenv('WERKZEUG_RUN_MAIN', 'true')
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', '--debug'])
    lock = tmp_path / 'app_instance.lock'

    ok, _ = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert lock.exists(), '服务子进程应当真正持有锁'


def test_conflict_exits_with_dedicated_code(tmp_path, guard_active):
    """冲突时以专用退出码退出（脚本/运维可据此区分「实例冲突」与「参数错」）"""
    lock = tmp_path / 'app_instance.lock'
    held, fd = acquire_lock(lock)
    assert held
    try:
        with pytest.raises(SystemExit) as err:
            instance_guard.enforce_web_instance_or_exit(lock)

        assert err.value.code == instance_guard.EXIT_CODE_CONFLICT
    finally:
        release_lock(fd)


def test_enforce_passes_through_when_free(tmp_path, guard_active):
    """空闲时守门放行并持有锁（create_app 正常路径）"""
    lock = tmp_path / 'app_instance.lock'

    instance_guard.enforce_web_instance_or_exit(lock)

    assert instance_guard._held_fd is not None
    assert lock.exists()
