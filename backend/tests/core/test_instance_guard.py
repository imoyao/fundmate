# -*- coding: utf-8 -*-
"""单实例守门测试（#1809 / #1816）。

守门要解决的是「同一 SQLite 被多个后端实例并发写 → `database is locked`」，
本文件锁定它的四条规则、三条边界与 #1816 补的三道防线：

规则：① 空闲即拿到并落持有者信息；② 已被占用 → 冲突且给出可操作说明；
      ③ 同进程重复调用幂等；④ 冲突时以专用退出码退出。
边界：测试进程 / `APP_INSTANCE_GUARD=0` → 跳过；
      **服务子进程（`WERKZEUG_RUN_MAIN=true`）必须真守门**，不被 `--debug` 骗过。
#1816：⑤ 退出码**不得**等于 werkzeug 的 reload 信号；⑥ 重载父进程只探查不持锁，
       且锁被占时要在 `init_db()` 之前就退出；⑦ `app.main` 导入即关掉
       `allow_reuse_address`，让第二个实例在绑端口处就失败。
"""

import inspect
import os
import re
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
def test_reloader_parent_probes_but_never_holds(tmp_path, monkeypatch, flag):
    """重载父进程**探查但不持锁**：持锁会让服务子进程起不来（热重载报废）。

    #1816 之前这里是「整段放行」，于是父进程会带着 `init_db()` 绕过守门往同一个
    SQLite 下启动期 DDL——正是 #1809 的成因。改成探查后，锁必须是**空闲**的。
    """
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', flag])
    lock = tmp_path / 'app_instance.lock'

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '重载父进程' in reason
    assert instance_guard._held_fd is None, '父进程不得持有锁（否则子进程拿不到）'

    # 探查完必须真释放：服务子进程紧接着就要来拿
    held, fd = acquire_lock(lock)
    assert held, '父进程探查后必须释放，否则热重载子进程拿不到锁'
    release_lock(fd)


def test_reloader_parent_reports_conflict_before_init_db(tmp_path, monkeypatch):
    """锁被占时重载父进程必须报冲突——它据此在 `init_db()` **之前**就退出，不碰库。

    没有这条，第二个 `flask run` 的父进程会先写库、再绑端口，#1810 的
    「第二个实例根本不会碰这个库」在该路径上落空（#1816）。
    """
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', '--debug'])
    lock = tmp_path / 'app_instance.lock'
    held, fd = acquire_lock(lock)
    assert held, '前置条件：模拟出的“另一个实例”应能拿到锁'
    try:
        ok, reason = instance_guard.acquire_web_instance_lock(lock)

        assert ok is False
        assert 'database is locked' in reason
        assert str(lock) in reason
        assert instance_guard._held_fd is None
    finally:
        release_lock(fd)


def test_reloader_parent_conflict_exits_with_dedicated_code(tmp_path, monkeypatch):
    """父进程拿到冲突说明后要**真退出**，而不是打条日志继续跑 init_db。"""
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', '--debug'])
    lock = tmp_path / 'app_instance.lock'
    held, fd = acquire_lock(lock)
    assert held
    try:
        with pytest.raises(SystemExit) as err:
            instance_guard.enforce_web_instance_or_exit(lock)

        assert err.value.code == instance_guard.EXIT_CODE_CONFLICT
    finally:
        release_lock(fd)


@pytest.mark.parametrize(
    'argv',
    [
        ['flask', 'run', '--debug', '--no-reload'],
        ['flask', 'run', '--reload', '--no-reload'],
        ['flask', 'run', '--no-reload', '--reload'],
    ],
)
def test_no_reload_flag_wins_so_init_db_is_never_skipped(tmp_path, monkeypatch, argv):
    """`--no-reload` 是 Click 成对布尔的关断位，必须压过 `--debug`/`--reload`。

    没有子进程时当前进程**就是**服务进程：若仍判成父进程而放行，`init_db()` 会被
    整个跳过、库永远不建；若因此持锁倒不会有事，但判据必须指向同一事实（#1816）。
    """
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    monkeypatch.setattr(sys, 'argv', argv)
    lock = tmp_path / 'app_instance.lock'

    assert instance_guard.is_reloader_parent() is False

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '重载父进程' not in reason, '没有重载就没有子进程，当前进程必须真持锁'
    assert lock.exists()


def _werkzeug_reload_signal() -> int:
    """从 werkzeug 源码里解析出「请重载」信号量。

    不硬编码 3：上游若改了值，本用例会跟着红而不是静默放过。
    """
    import werkzeug._reloader as reloader_mod

    src = inspect.getsource(reloader_mod.ReloaderLoop.trigger_reload)
    matched = re.search(r'sys\.exit\((\d+)\)', src)
    assert matched, '未能从 werkzeug.ReloaderLoop.trigger_reload 解析出 reload 信号，上游实现变了'
    signal_value = int(matched.group(1))

    # 反向确认重载循环确实按这个值决定「再拉一个子进程」
    loop_src = inspect.getsource(reloader_mod.ReloaderLoop.restart_with_reloader)
    assert f'exit_code != {signal_value}' in loop_src, 'werkzeug 重载循环的哨兵值与 trigger_reload 不一致'
    return signal_value


def test_conflict_exit_code_must_not_be_werkzeug_reload_signal():
    """冲突退出码**不得**占用 werkzeug 的 reload 信号（#1816 的直接根因）。

    werkzeug 的 `restart_with_reloader()` 以「子进程退出码 == 3」判定「请重载」，
    #1810 恰好也用 3 表示冲突 → 父进程把冲突当 reload，无限 `Restarting with stat`
    刷屏，第二个实例永远起不来也停不下来。
    """
    reload_signal = _werkzeug_reload_signal()

    assert instance_guard.EXIT_CODE_CONFLICT != reload_signal, (
        f'冲突退出码 {instance_guard.EXIT_CODE_CONFLICT} 撞上了 werkzeug 的 reload 信号 '
        f'{reload_signal}，重载器会把冲突当成「再拉一个子进程」无限重启'
    )


def test_app_main_disables_socket_address_reuse():
    """`app.main` 导入即关掉地址复用：Windows 的 SO_REUSEADDR 会让第二个实例
    静默绑上同一端口，把「又起一个实例」伪装成「重启成功」（#1816）。"""
    from werkzeug.serving import BaseWSGIServer

    import app.main  # noqa: F401  导入即执行开关

    assert BaseWSGIServer.allow_reuse_address is False


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


# ─────────── #2728：`.env` 的 FLASK_DEBUG 也是重载开关 ───────────


def _as_flask_run(monkeypatch, debug_value):
    """复刻 `flask run` 下 `create_app()` 期的环境。

    `FLASK_RUN_FROM_CLI` 由 flask CLI 的 `make_context` 设置；`FLASK_DEBUG` 由
    `main.py` 的 `load_dotenv()`（`.env`）或 `_set_debug` 回调（`--debug/--no-debug`）
    写入——两者都在工厂函数执行前就位。
    """
    monkeypatch.setenv('FLASK_RUN_FROM_CLI', 'true')
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    if debug_value is None:
        monkeypatch.delenv('FLASK_DEBUG', raising=False)
    else:
        monkeypatch.setenv('FLASK_DEBUG', debug_value)
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)


@pytest.mark.parametrize(
    'argv',
    [
        ['flask', 'run', '--port', '8000'],
        ['python.exe', '-m', 'flask', '--app', 'app.main:app', 'run', '--port', '8000'],
    ],
)
def test_env_debug_counts_as_reloader_switch(tmp_path, monkeypatch, argv):
    """`.env` 的 `FLASK_DEBUG=1` 下 `flask run` 照样有父/子进程，父进程不得持锁（#2728）。

    只查 argv 会让父进程被判成服务进程去持锁，真正服务的子进程随即 `exit 4`，且文案
    报「持有者 pid=<自己的父进程>」——把人往「有僵尸实例」方向带。修复前本用例在
    第一个断言处即转红（实测：父进程 `_held_fd=5`、子进程 exit 4）。
    """
    _as_flask_run(monkeypatch, '1')
    monkeypatch.setattr(sys, 'argv', argv)
    lock = tmp_path / 'app_instance.lock'

    assert instance_guard.is_reloader_parent() is True

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '重载父进程' in reason
    assert instance_guard._held_fd is None, '父进程持锁会让服务子进程拿不到锁（exit 4）'

    held, fd = acquire_lock(lock)
    assert held, '父进程探查后必须真释放，否则热重载子进程起不来'
    release_lock(fd)


def test_env_debug_without_flask_run_cli_still_guards(tmp_path, monkeypatch):
    """没有 `flask run` 上下文时，`.env` 的 `FLASK_DEBUG=1` **不得**被当成重载开关。

    `app/main.py` 第 9 行无条件 `load_dotenv()`，所以 pytest / `flask db upgrade` /
    脚本 / scheduler 里同样能看到 `FLASK_DEBUG=1`。若无条件采信，这些进程会被判成
    「重载父进程」→ 只探查不持锁 → 守门在这些路径上静默失效，**比 #2728 本身更糟**。
    """
    monkeypatch.delenv('FLASK_RUN_FROM_CLI', raising=False)
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    monkeypatch.setenv('FLASK_DEBUG', '1')
    monkeypatch.setattr(instance_guard, '_in_test_process', lambda: False)
    monkeypatch.setattr(sys, 'argv', ['pytest', '-q'])
    lock = tmp_path / 'app_instance.lock'

    assert instance_guard.is_reloader_parent() is False

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '重载父进程' not in reason
    assert instance_guard._held_fd is not None, '守门必须真持锁，不能被 .env 的 debug 开关放宽'
    assert lock.exists()


def test_env_debug_ignored_for_non_run_subcommand(tmp_path, monkeypatch):
    """`flask db upgrade` 等子命令同样带 `FLASK_RUN_FROM_CLI=true`，但不拉 reloader。"""
    _as_flask_run(monkeypatch, '1')
    monkeypatch.setattr(sys, 'argv', ['flask', 'db', 'upgrade'])
    lock = tmp_path / 'app_instance.lock'

    assert instance_guard.is_reloader_parent() is False

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '重载父进程' not in reason
    assert instance_guard._held_fd is not None


@pytest.mark.parametrize('debug_value', ['0', 'false', 'no', ''])
def test_env_debug_falsy_means_no_reloader(tmp_path, monkeypatch, debug_value):
    """`FLASK_DEBUG` 为假值 → flask 不起 reloader，当前进程就是服务进程，必须真持锁。"""
    _as_flask_run(monkeypatch, debug_value)
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', '--port', '8000'])
    lock = tmp_path / 'app_instance.lock'

    assert instance_guard.is_reloader_parent() is False

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '重载父进程' not in reason
    assert instance_guard._held_fd is not None


def test_env_debug_off_string_matches_flask_semantics(tmp_path, monkeypatch):
    """`FLASK_DEBUG=off` 在 flask 眼里仍是「开」（`get_debug_flag` 只排除 0/false/no）。

    判据必须与 flask **同源**：若按「更合理」的语义把 `off` 判成关，就会漏判父进程，
    回到 #2728 的现场；这条用例正是防止后人「顺手把集合补全」。
    """
    _as_flask_run(monkeypatch, 'off')
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', '--port', '8000'])

    assert instance_guard.is_reloader_parent() is True


def test_env_debug_respects_no_reload(tmp_path, monkeypatch):
    """`--no-reload` 压过 `.env` 的 `FLASK_DEBUG=1`：没有子进程，当前进程必须持锁。"""
    _as_flask_run(monkeypatch, '1')
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', '--no-reload'])
    lock = tmp_path / 'app_instance.lock'

    assert instance_guard.is_reloader_parent() is False

    ok, reason = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert '重载父进程' not in reason
    assert instance_guard._held_fd is not None


def test_reloader_child_under_env_debug_is_guarded(tmp_path, monkeypatch):
    """`.env FLASK_DEBUG=1` 起的重载**子进程**必须真守门（`WERKZEUG_RUN_MAIN` 优先）。"""
    _as_flask_run(monkeypatch, '1')
    monkeypatch.setenv('WERKZEUG_RUN_MAIN', 'true')
    monkeypatch.setattr(sys, 'argv', ['flask', 'run', '--port', '8000'])
    lock = tmp_path / 'app_instance.lock'

    ok, _ = instance_guard.acquire_web_instance_lock(lock)

    assert ok
    assert lock.exists(), '服务子进程应当真正持有锁'
    assert instance_guard._held_fd is not None
