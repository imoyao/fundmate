# -*- coding: utf-8 -*-
# app/core/instance_guard.py
"""同一 DB 的单实例守门（#1809）。

**WHY：为什么必须有这道闸门**

SQLite 只允许**一个写者**。本机（尤其 Windows）极容易出现「多个后端实例共享同一个
`invest.db`」：

- `flask run` 用的是 werkzeug `run_simple`，默认 `allow_reuse_address=True`；
  **Windows 的 SO_REUSEADDR 语义让第二个实例照样绑定成功、不报「端口被占用」**——
  于是「重启后端」静默变成「又多起一个实例」，旧实例还活着；
- 重载器残留、终端没关、IDE 再点一次运行……都会叠出第二个、第三个实例。

一旦发生：任一实例的长写事务（启动期 `init_db()` / 迁移 DDL、同步任务、卡住的线程）
会按住写锁，其他实例的写请求只能等 `busy_timeout`（`db_factory` 里 `timeout=30`），
等满即抛 `database is locked`。2026-09-30 的「编辑账户保存失败」正是这个链路：
同机三个实例握着同一个库，失败的 PATCH 每个都卡满 ~30s，而报错信息完全指不到真因。

**做法**：启动时用一把 OS 级排他锁（`core/file_lock.py`：Windows `msvcrt.locking` /
POSIX `flock`，**非阻塞**、进程退出（含崩溃）由内核释放、无 stale 文件问题）把
「同一 DB 只能有一个 web 实例」变成硬约束。拿不到锁的实例**直接退出**，
且这一步排在 `init_db()` / 迁移**之前**——不让它再往同一个库里写任何东西。

**边界**（刻意如此，避免误伤）

- 只管 **web 应用进程**（`create_app()`）：`sync` / `scheduler-daemon` 等 CLI 与
  `pytest` 都不经此路，可以照常跑（它们与 web 实例并存是既有用法）；
- 重载父进程**探查但不持锁**：`flask run --debug` 下父进程也会执行 `create_app()`，
  若父进程持锁，真正服务的子进程（`WERKZEUG_RUN_MAIN=true`）就拿不到锁，开发热重载会废；
  但完全放行又会让它带着 `init_db()` 绕过守门写库，故改为「探不到锁即退出」（#1816）；
- `APP_INSTANCE_GUARD=0` 可显式关闭（多实例是刻意行为的场景，如本地压测）。

**#1816 修掉的三处坑**（#1810 上线当天即被实测打回，记在这里避免后人照抄旧写法）：

1. 退出码从 3 改 4——3 是 werkzeug 重载器的「请重载」哨兵，冲突退 3 会让父进程
   无限拉子进程刷屏（见 `EXIT_CODE_CONFLICT` 注释）；
2. 重载父进程从「整段放行」改为「探查不持锁」——放行会让它在守门覆盖之外跑 `init_db()`；
3. `main.py` 导入期把 `BaseWSGIServer.allow_reuse_address` 置 `False`——Windows 的
   `SO_REUSEADDR` 会让第二个实例**静默绑上同一端口**，把「又起一个」伪装成「重启成功」。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger

from app.core.file_lock import acquire_lock, release_lock
from app.core.logging_config import BACKEND_DIR

# 锁文件（默认）：与调度单实例锁同目录，便于运维一眼看到
DEFAULT_INSTANCE_LOCK = BACKEND_DIR / 'data' / 'app_instance.lock'

# 显式关闭守门（取值语义与 LOG_ENABLED 一致：0/false/no/off 关闭）
ENV_DISABLE = 'APP_INSTANCE_GUARD'
_FALSY = {'0', 'false', 'no', 'off'}

# 冲突退出码：与 argparse 的 2 区分开，便于脚本判断「是实例冲突而不是参数错」。
#
# **绝不能用 3**：werkzeug 把 3 保留给重载器——`_reloader.py` 里 `trigger_reload()`
# 就是 `sys.exit(3)`，而 `restart_with_reloader()` 的循环条件是 `if exit_code != 3:
# return`，即「子进程退 3 = 请再拉一个」。#1810 曾取 3，于是守门冲突被父进程当成
# reload 信号 → 无限 `Restarting with stat` 刷屏，第二个实例永远起不来也停不下来（#1816）。
EXIT_CODE_CONFLICT = 4

# 本进程持有的锁 fd。模块级而非实例级：锁要活到进程结束（file_lock 的 fd 一旦 close 即释放）
_held_fd: Optional[int] = None
_held_path: Optional[Path] = None


def _in_test_process() -> bool:
    """当前是否 pytest 进程（判据与 `logging_config._in_test_process` 一致）。

    `tests/conftest.py` 的 `app` fixture 每个用例都调 `create_app()`：不跳过的话，
    进程内第一个用例拿锁、第二个用例仍持有（模块级 fd），看似无碍；但一旦用例之间
    有 `monkeypatch` 换锁文件路径，就会出现「自己跟自己冲突」的假失败。
    测试进程里跳过整道守门最省心，也符合「守门只针对真实服务进程」的定位。
    """
    return 'pytest' in sys.modules or 'PYTEST_CURRENT_TEST' in os.environ


def _disabled_by_env() -> bool:
    return os.getenv(ENV_DISABLE, '').strip().lower() in _FALSY


def is_reloader_parent() -> bool:
    """当前是否是 werkzeug **重载父进程**（会执行 create_app，但不真正服务）。

    判据：`WERKZEUG_RUN_MAIN` 未被设置（该变量只由重载器注入**子进程**），
    且命令行带着重载开关（`--debug` / `--reload`）。两者同时成立才判定为父进程——
    宁可漏判（退回「不跳过」，让父进程也去抢锁）也不误判成非服务进程而放宽守门。

    `--no-reload` 必须**优先于** `--debug`：它是 Click 成对布尔的关断位，
    `flask run --debug --no-reload` 下根本不产生子进程，**当前进程就是服务进程**——
    此时若仍判成父进程，`main.py` 的 `init_db()` 会被整个跳过、库永远不建（#1816）。
    同理 `--reload --no-reload`（后写者胜）也算关断。
    """
    if os.environ.get('WERKZEUG_RUN_MAIN'):
        return False
    if '--no-reload' in sys.argv:
        return False
    return '--debug' in sys.argv or '--reload' in sys.argv


def _owner_file(lock_file: Path) -> Path:
    """持有者信息的落点：与锁文件同名的 `.owner` 兄弟文件。

    刻意**不写进锁文件本身**：Windows 的字节区间锁会拦住其它句柄对该区间的读
    （实测 `Path.read_text()` 直接 PermissionError），而这份信息的唯一用途就是
    「让抢不到锁的那个进程能读到是谁占着」——写进被锁住的文件等于自断用途。
    """
    return lock_file.with_suffix('.owner')


def _write_owner_info(lock_file: Path) -> None:
    """把持有者信息写进 `.owner`（供后来者/运维定位是谁占着）。"""
    info = f'pid={os.getpid()} started_at={_now_text()}\n'
    try:
        _owner_file(lock_file).write_text(info, encoding='utf-8')
    except OSError as exc:  # pragma: no cover - 写不进去不影响锁本身
        logger.debug(f'写入实例持有者信息失败（忽略）：{exc}')


def _now_text() -> str:
    from app.core.time_utils import now_shanghai

    return now_shanghai().strftime('%Y-%m-%d %H:%M:%S')


def read_owner_info(lock_file: Optional[Path] = None) -> str:
    """读取持有者信息（读不到返回空串）。"""
    path = Path(lock_file or DEFAULT_INSTANCE_LOCK)
    try:
        return _owner_file(path).read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def _conflict_message(path: Path, owner: str) -> str:
    """抢不到锁时给后来者的说明（谁占着、为什么致命、怎么清理）。"""
    return (
        f'另一个后端实例正在使用同一个数据库（实例锁 {path} 已被占用'
        + (f'，持有者：{owner}' if owner else '')
        + '）。多个实例共享 SQLite 会互相锁死（写入报 database is locked），'
        '请先停掉旧实例——Windows 下 `Get-Process python` 找到多余进程后结束它，'
        '再重启本实例。'
    )


def acquire_web_instance_lock(lock_file: Optional[Path] = None) -> Tuple[bool, str]:
    """尝试成为「本机唯一 web 实例」。

    Returns:
        (是否通过, 说明)。`False` 表示已有其它实例在跑（说明里带清理指引）。

    规则（按序）：
        1. 本进程已持有 → 通过（幂等，`create_app()` 可能被调多次）；
        2. `APP_INSTANCE_GUARD=0` → 跳过；
        3. pytest 进程 → 跳过；
        4. 重载父进程 → **探查一次但不持锁**（详见下方注释）；
        5. 否则取 OS 级排他锁：拿到即持有到进程结束；拿不到即冲突。
    """
    global _held_fd, _held_path

    if _held_fd is not None:
        return True, '本进程已持有实例锁'
    if _disabled_by_env():
        return True, f'{ENV_DISABLE}=0，已显式关闭单实例守门'
    if _in_test_process():
        return True, '测试进程，跳过单实例守门'

    path = Path(lock_file or DEFAULT_INSTANCE_LOCK)

    if is_reloader_parent():
        # 重载父进程**不能持锁**（否则真正服务的子进程 `WERKZEUG_RUN_MAIN=true` 拿不到锁，
        # 开发热重载直接报废）；但它绝不能因此整段放行——`create_app()` 里紧跟着就是
        # `init_db()` / 迁移 DDL，放行等于让第二个实例**绕过守门**往同一个 SQLite 下
        # 启动期写操作，正是 #1809 的成因，#1810「第二个实例根本不会碰这个库」也就在
        # 这条路径上落空（#1816 实测：第二个 `flask run` 的父进程确实跑到了 init_db）。
        #
        # 故改为**非阻塞探查一次**：探不到锁 → 立即以冲突退出（排在 init_db 之前）；
        # 探得到 → 立刻释放，父进程自身不持有。残留的空锁文件无害（见 file_lock 文档）。
        # 残留竞态：释放到服务子进程真正拿锁之间有一个极短窗口，另一个实例可趁虚而入，
        # 此时由子进程侧的正式守门兜底（冲突即退出），不会退化成「两边都在写」。
        locked, fd = acquire_lock(path)
        if not locked:
            return False, _conflict_message(path, read_owner_info(path))
        release_lock(fd)
        return True, '重载父进程：探查通过（不持锁，由服务子进程持锁）'

    locked, fd = acquire_lock(path)
    if not locked:
        return False, _conflict_message(path, read_owner_info(path))

    _held_fd = fd
    _held_path = path
    _write_owner_info(path)
    logger.info(f'单实例守门通过：本进程持有 {path}（pid={os.getpid()}）')
    return True, 'ok'


def enforce_web_instance_or_exit(lock_file: Optional[Path] = None) -> None:
    """守门不通过就**明确报错并退出**（`create_app()` 调用；排在迁移之前）。

    刻意不抛异常：抛异常会被上层当成普通启动失败而在各种 handler 里被吞掉或包装，
    而这里的语义是「本进程不该继续跑」，用退出码表达最直白（`EXIT_CODE_CONFLICT`）。
    """
    ok, reason = acquire_web_instance_lock(lock_file)
    if ok:
        logger.debug(f'单实例守门：{reason}')
        return
    logger.error('单实例守门失败，进程退出：{}', reason)
    sys.exit(EXIT_CODE_CONFLICT)
