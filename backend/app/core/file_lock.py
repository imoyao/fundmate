# -*- coding: utf-8 -*-
# app/core/file_lock.py
"""跨平台原子文件锁（进程级排他）。

从 `services/sync/orchestrator.py` 抽出（#1467）。抽出原因不是「文件太长」，而是
**依赖方向**：进程内每日调度器（`services/daily_scheduler.py`）与应用启动路径都需要
这把锁，若从 orchestrator 借，会把 akshare / pandas / xalpha 等重依赖连带加载进
「应用启动」这条链路（启动路径只应触碰 core）。锁是纯基础设施，归 core。

语义：OS 级排他锁（Windows `msvcrt.locking` / POSIX `flock`），**非阻塞**获取。
进程退出（含崩溃）时由内核自动释放，不存在需要人工清理的 stale 锁文件——这也是
「用文件锁而不是 PID 文件」的原因。

约定：`acquire_lock` 返回的 fd 必须由调用方持有；一旦 close，锁即刻释放。
"""

import os
import sys
from pathlib import Path
from typing import Optional, Tuple


def acquire_lock(lock_file: Path) -> Tuple[bool, Optional[int]]:
    """尝试获取原子文件锁（非阻塞）。

    Args:
        lock_file: 锁文件路径（父目录不存在会自动创建）。

    Returns:
        (是否获取成功, 文件描述符)。失败时返回 (False, None)——**不等待**，
        调用方据此决定「跳过本次」还是「排队重试」。
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_RDWR)
        if sys.platform == 'win32':
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True, fd
    except (OSError, IOError):
        if 'fd' in locals():
            os.close(fd)
        return False, None


def release_lock(fd: Optional[int]) -> None:
    """释放锁（close 即释放）。

    刻意**不删除锁文件**：删除会在「A 释放 → B 已获取 → A 删文件」的窗口里把 B 的
    锁文件删掉，而 B 的 fd 仍锁着一个已 unlink 的 inode（Windows 上删除会因被占用
    而失败）。残留一个 0 字节文件是无害的，换取的是无需推理的竞态安全。
    """
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:  # pragma: no cover - 仅重复释放时触发
        pass
