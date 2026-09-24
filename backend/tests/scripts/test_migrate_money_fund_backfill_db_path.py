# -*- coding: utf-8 -*-
"""migrate_money_fund_backfill 的 SQLite 路径解析单测（#1687）。

背景：该脚本 `_resolve_db_paths()` 曾用 `urlsplit` / `urlunsplit` 往返来剥掉
`DATABASE_URL` 的查询参数。但 `urlunsplit` 只在 scheme 属于
`urllib.parse.uses_netloc` 时才补 `//`，而 **`sqlite` 不在那张表里**，于是

    'sqlite:///./invest.db'
      → urlsplit  ('sqlite', '', '/./invest.db')
      → urlunsplit 'sqlite:/./invest.db'          # 少了一个 '/'
      → replace('sqlite:///', '') 不匹配          # 原样保留
      → abspath()  '<cwd>/sqlite:/invest.db'

默认调用（不带位置参数）因此**必然**打印「文件不存在，跳过」再以 0 退出 ——
本仓 #1661 的存量修复就是这么被静默跳过的。本文件把这几种 URL 形态钉死，
并补上「一个库都没找到必须非 0 退出」的行为。

只测路径解析与退出码，**不碰真实数据库**。
"""

import os
import sqlite3
import subprocess
import sys

import pytest

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import migrate_money_fund_backfill as m  # noqa: E402

_SCRIPT = os.path.join(_SCRIPTS_DIR, 'migrate_money_fund_backfill.py')


def test_relative_three_slash_url() -> None:
    assert m._sqlite_path_from_url('sqlite:///./invest.db') == os.path.abspath('./invest.db')


def test_windows_drive_url() -> None:
    assert m._sqlite_path_from_url('sqlite:///C:/x/y/invest.db') == 'C:/x/y/invest.db'


def test_absolute_four_slash_url() -> None:
    assert m._sqlite_path_from_url('sqlite:////abs/p.db') == '/abs/p.db'


def test_query_params_are_not_part_of_the_path() -> None:
    # 查询参数是给驱动看的，绝不能混进文件路径（这正是当初引入 urlsplit 的初衷）
    assert m._sqlite_path_from_url('sqlite:///./invest.db?mode=ro') == os.path.abspath('./invest.db')


def test_driver_variant_url() -> None:
    assert m._sqlite_path_from_url('sqlite+pysqlite:///./a.db') == os.path.abspath('./a.db')


def test_url_without_database_name_raises() -> None:
    with pytest.raises(ValueError):
        m._sqlite_path_from_url('sqlite://')


def test_default_url_no_longer_yields_bogus_path(monkeypatch) -> None:
    """核心回归（#1687）：默认 DATABASE_URL 必须解析出真文件，不能带 `sqlite:` 前缀。

    旧实现会得到 `<cwd>/sqlite:/invest.db` —— 名字里带着 `sqlite:`，
    任何真实文件系统上都绝不可能存在。
    """
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///./invest.db')
    paths = m._resolve_db_paths()
    assert paths
    assert os.path.basename(paths[0]) == 'invest.db'
    assert 'sqlite:' not in paths[0]
    assert os.path.isabs(paths[0])


def test_resolve_db_paths_uses_env(monkeypatch, tmp_path) -> None:
    db = tmp_path / 'invest.db'
    db.write_bytes(b'')
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db.as_posix()}')
    paths = m._resolve_db_paths()
    assert os.path.abspath(paths[0]) == os.path.abspath(str(db))


def test_resolve_db_paths_appends_alt_when_present(monkeypatch, tmp_path) -> None:
    db = tmp_path / 'invest.db'
    db.write_bytes(b'')
    alt = tmp_path / 'invest.user.dev.db'
    alt.write_bytes(b'')
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db.as_posix()}')
    paths = m._resolve_db_paths()
    assert len(paths) == 2
    assert os.path.abspath(paths[1]) == os.path.abspath(str(alt))


def _make_empty_db(path: str) -> None:
    """建一个只有 positions / transactions 两张空表的库（不让脚本去查名录）。"""
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE positions(id INTEGER PRIMARY KEY, ledger_id INTEGER, symbol TEXT, type TEXT,
                               is_money_fund INTEGER);
        CREATE TABLE transactions(id INTEGER PRIMARY KEY, ledger_id INTEGER, position_id INTEGER,
                                  symbol TEXT, type TEXT, is_income INTEGER);
        """
    )
    conn.commit()
    conn.close()


def test_script_dryrun_on_existing_db_exits_zero(tmp_path) -> None:
    db = str(tmp_path / 'invest.db')
    _make_empty_db(db)
    r = subprocess.run([sys.executable, _SCRIPT, db], capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0, r.stderr
    assert '目标库' in r.stdout


def test_script_exits_nonzero_when_no_db_found(tmp_path) -> None:
    """一个库都没找到 → 必须非 0 退出，否则「静默跳过」会被误读成「没什么要改」。"""
    missing = str(tmp_path / 'nope.db')
    r = subprocess.run([sys.executable, _SCRIPT, missing], capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 1
    assert '迁移未执行' in (r.stdout + r.stderr)


def test_script_dryrun_writes_nothing(tmp_path) -> None:
    db = str(tmp_path / 'invest.db')
    _make_empty_db(db)
    before = open(db, 'rb').read()
    r = subprocess.run([sys.executable, _SCRIPT, db], capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0, r.stderr
    assert open(db, 'rb').read() == before
