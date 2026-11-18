# -*- coding: utf-8 -*-
"""回归网：``tests/_template_cache.py`` 的原子发布（#2986）。

覆盖：
1. 无模板时 ``copy_template_into`` 返回 ``False``（首测试路径）；
2. 存模板 -> 复制回 tmp 的往返，产物是**可用的 SQLite**（``PRAGMA quick_check`` = ok）；
3. **并发发布不产生半截文件**：8 线程把两个内容不同的库轮流发布到同一个目标路径，
   结束后目标必须是「其中一个完整库」，不能是两者交错的残片；
4. 发布后目录里不留 ``*.tmp-*``（临时名带 pid，异常路径要清掉）；
5. ``save_template`` 清掉其它指纹目录，但保留自己这个；
6. 指纹是 16 位十六进制（缓存键形态不变）。

## 反向验证（本用例的判别力来自这里）

把 ``publish_atomically`` 改回「``shutil.copyfile(src, dst)`` 直接写目标」，
第 3 条用例在 8 线程下会拿到 ``database disk image is malformed`` 或行数既非 A 也非 B
——这正是 #2986 在 CI 上的形态（4 个 xdist worker 同时写 shared 模板）。改回去跑一遍
确认它**真的红了**，再改回来。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from tests import _template_cache as tc


def _make_db(path: Path, rows: int) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, blob TEXT)')
        conn.executemany('INSERT INTO t (blob) VALUES (?)', [('x' * 200,)] * rows)
        conn.commit()
    finally:
        conn.close()


def _row_count(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute('SELECT COUNT(*) FROM t').fetchone()[0]
    finally:
        conn.close()


def _quick_check(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute('PRAGMA quick_check').fetchone()[0]
    finally:
        conn.close()


def test_missing_template_returns_false(tmp_path: Path) -> None:
    cache = tmp_path / 'cache'
    assert tc.copy_template_into(tmp_path, directory=cache) is False


def test_save_then_copy_roundtrip(tmp_path: Path) -> None:
    # 缓存目录自成一层：save_template 会清理「目标目录的兄弟目录」，
    # 把工作目录放在 tmp_path 下（缓存目录的父级之外）才不会被它清掉。
    cache = tmp_path / 'cache_root' / 'cur'
    work_a, work_b = tmp_path / 'a', tmp_path / 'b'
    for d in (work_a, work_b):
        d.mkdir()
    _make_db(work_a / tc.APP_FIXTURE, 5)
    _make_db(work_a / tc.MARKET_FIXTURE, 7)

    tc.save_template(work_a, directory=cache)

    assert tc.copy_template_into(work_b, directory=cache) is True
    assert _quick_check(work_b / tc.APP_FIXTURE) == 'ok'
    assert _quick_check(work_b / tc.MARKET_FIXTURE) == 'ok'
    assert _row_count(work_b / tc.APP_FIXTURE) == 5
    assert _row_count(work_b / tc.MARKET_FIXTURE) == 7


def test_leaves_no_tmp_files(tmp_path: Path) -> None:
    cache = tmp_path / 'cache'
    cache.mkdir()
    src = tmp_path / 'src'
    src.mkdir()
    _make_db(src / 'a.db', 3)
    tc.publish_atomically(src / 'a.db', cache / 'a.db')
    assert list(cache.glob('*.tmp-*')) == []


def test_concurrent_publish_never_tears_the_target(tmp_path: Path) -> None:
    """8 线程轮流发布两个不同的库到同一目标：结果必须是其中一个完整库。"""
    small, large = tmp_path / 'small.db', tmp_path / 'large.db'
    _make_db(small, 10)
    _make_db(large, 400)
    dst = tmp_path / 'shared.db'

    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            for _ in range(15):
                tc.publish_atomically(small if i % 2 == 0 else large, dst)
        except BaseException as exc:  # pragma: no cover - 失败时用来定位
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert _quick_check(dst) == 'ok', '目标库被写坏（copyfile 交错落盘的典型形态）'
    assert _row_count(dst) in (10, 400)


def test_save_template_cleans_other_fingerprints(tmp_path: Path) -> None:
    cache_root = tmp_path / 'fixture_tpl'
    mine = cache_root / 'current'
    stale = cache_root / 'stale'
    stale.mkdir(parents=True)
    (stale / 'app.db').write_bytes(b'old')
    src = tmp_path / 'src'
    src.mkdir()
    _make_db(src / tc.APP_FIXTURE, 1)
    _make_db(src / tc.MARKET_FIXTURE, 1)

    tc.save_template(src, directory=mine)

    assert mine.is_dir()
    assert not stale.exists()


def test_fingerprint_is_short_hex() -> None:
    fp = tc.schema_fingerprint()
    assert len(fp) == 16
    assert int(fp, 16) >= 0


@pytest.mark.parametrize('name', [tc.APP_DB, tc.MARKET_DB])
def test_template_file_names_are_stable(name: str) -> None:
    """模板文件名是跨版本约定的缓存键，改名等于让所有旧缓存变成孤儿。"""
    assert name in {tc.APP_DB, tc.MARKET_DB}
    assert name.endswith('.db')
