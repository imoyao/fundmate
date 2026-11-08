# -*- coding: utf-8 -*-
"""测试库模板缓存（#1722 机制本体，从 conftest 抽出以便单测；并发修复见 #2986）。

## 为什么独立成模块

``publish_atomically`` 的正确性只能靠**并发复现**来验（多 writer 同时写同一目标），
而它留在 conftest 里时，任何 import 都会重跑 conftest 的模块级环境改写
（``DEV_DATABASE_URL`` 重定向到临时库）——测试自身就带副作用。抽出来以后
``tests/test_template_cache.py`` 可以干净地驱动它，也能用 ``directory=`` 把它指到 tmp 目录。

## 机制（#1722）

首个进 ``app`` fixture 的测试走完整路径建「完成态模板」（schema + migrations + seed、
零业务数据）；后续测试 ``copyfile`` 秒级落地并跳过 ``init_db``（快集 87 分钟 → 15 分钟）。
模板按源码指纹分目录存放，schema/迁移逻辑一变指纹即变、自动重建，杜绝
「模板过期 → 缺表假红」。

## 并发约束（#2986）

CI 是 ``pytest -n auto``（4 worker/片），runner 上 ``.pytest_cache`` 为空 ⇒ **每个 worker
的首个 ``app`` 测试都走「首测试」分支**，同时往同一对目标路径写。直接 ``copyfile`` 是
逐页写目标位置，两个 writer 交错落盘会把模板写成 ``database disk image is malformed``，
随后所有 worker 的所有测试都复制这份坏模板（实测一整片 20+ 个无关用例同时报错、
另一片全绿）。故发布一律走 :func:`publish_atomically`。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
import time
from pathlib import Path

APP_DB = 'app.db'
MARKET_DB = 'market.db'
APP_FIXTURE = '_fixture_app.db'
MARKET_FIXTURE = '_fixture_market.db'

_FINGERPRINT_CACHE: str | None = None


def backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def schema_fingerprint() -> str:
    """进程内只算一次的源码指纹——``app/`` 或本模块/conftest 变更都使旧模板失效。"""
    global _FINGERPRINT_CACHE
    if _FINGERPRINT_CACHE is None:
        root = backend_root() / 'app'
        h = hashlib.sha256()
        for p in sorted(root.rglob('*.py')):
            h.update(str(p.relative_to(root)).encode('utf-8'))
            h.update(p.read_bytes())
        # conftest 也纳入指纹：它是「什么时候建模板」的决策方，改了必须重建。
        for extra in (Path(__file__), Path(__file__).with_name('conftest.py')):
            if extra.exists():
                h.update(extra.read_bytes())
        _FINGERPRINT_CACHE = h.hexdigest()[:16]
    return _FINGERPRINT_CACHE


def template_dir(directory: Path | None = None) -> Path:
    d = directory if directory is not None else backend_root() / '.pytest_cache' / 'fixture_tpl' / schema_fingerprint()
    d.mkdir(parents=True, exist_ok=True)
    return d


def copy_template_into(tmp_path: Path, directory: Path | None = None) -> bool:
    """模板 -> 本测试 tmp_path；无模板（首测试）返回 False。"""
    d = template_dir(directory)
    src_app, src_market = d / APP_DB, d / MARKET_DB
    if src_app.exists() and src_market.exists():
        shutil.copyfile(src_app, tmp_path / APP_FIXTURE)
        shutil.copyfile(src_market, tmp_path / MARKET_FIXTURE)
        return True
    return False


def publish_atomically(src: Path, dst: Path) -> bool:
    """复制到同目录临时文件再 ``os.replace`` 原子发布；成功返回 True。

    ``copyfile`` 是逐页写目标位置，两个 writer 交错落盘会写出 malformed 的 SQLite；
    ``os.replace`` 在同目录内是原子的，读者只会看到旧的完整文件或新的完整文件，
    **不存在半截态**。临时名带 pid + 线程号，CI 上是不同进程（pid 不同）、进程内若有
    并行（线程）也不会互相踩临时文件——只带 pid 时同进程多线程会共用同一个临时名，
    反而在 ``os.replace`` 处撞成 ``PermissionError``。

    发布失败（Windows 上目标被读句柄占住时 ``os.replace`` 会 ``PermissionError``）就放弃，
    返回 False——**只损失加速收益**：后续测试各自重建模板，正确性不受影响，
    所以不抛异常把无关用例连带弄红。
    """
    tmp = dst.with_name(f'{dst.name}.tmp-{os.getpid()}-{threading.get_ident()}')
    shutil.copyfile(src, tmp)
    for _ in range(20):
        try:
            os.replace(tmp, dst)
            return True
        except OSError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)
    return False


def save_template(tmp_path: Path, directory: Path | None = None) -> None:
    """首测试完成态 -> 模板，并清理其它指纹目录（只保留当前）。

    调用点必须在 ``create_app``（init_db 完成）之后、测试体执行**之前**，且先
    dispose 断开全部连接（回滚未提交页、确保主文件完整）——否则首测试写入的
    业务数据会随模板污染后续所有测试。

    发布走 :func:`publish_atomically`（#2986）：多 worker 并发写同一份模板时，
    直接 copyfile 会把目标写成 malformed 的 SQLite 文件。
    """
    d = template_dir(directory)
    publish_atomically(tmp_path / APP_FIXTURE, d / APP_DB)
    publish_atomically(tmp_path / MARKET_FIXTURE, d / MARKET_DB)
    for old in d.parent.iterdir():
        if old != d and old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
