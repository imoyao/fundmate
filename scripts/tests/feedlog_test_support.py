#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scripts/bridge/feedlog_bridge.py`` 的测试支撑（桩与假连接）。

为什么需要它
------------
`feedlog_bridge.py` 顶层依赖 `psycopg2` / `PyGithub`，而 CI 的 `scripts_test`
只装 `pyyaml + pytest`——直接 import 会在导入期就 `ModuleNotFoundError`。
这里用**最小桩**顶掉这两个第三方包（不是 mock 被测逻辑）：

- `psycopg2` / `psycopg2.extras`：只提供 `RealDictCursor` 符号；
- `github`：只提供 `Github` / `UnknownObjectException` 符号。

被测函数只用 DB-API 那套形状（`cursor()/execute()/fetchone()/commit()`），
假连接如实记录每条 SQL 与参数，断言就落在 SQL 上——**不需要真数据库**。

用法::

    from feedlog_test_support import FakeConn, load_bridge_module

    bridge = load_bridge_module()
    conn = FakeConn()
    bridge.create_changelog_entry(conn, 'org-1', '标题', '内容', '2026-10-09T00:00:00Z')
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from typing import Any, Optional

REPO = pathlib.Path(__file__).resolve().parents[2]
BRIDGE = REPO / 'scripts' / 'bridge' / 'feedlog_bridge.py'


def _install_third_party_stubs() -> None:
    """把 psycopg2 / github 换成最小可用的桩（仅在未安装时）。"""
    if 'psycopg2' not in sys.modules:
        psycopg2 = types.ModuleType('psycopg2')
        extras = types.ModuleType('psycopg2.extras')
        extras.RealDictCursor = object  # type: ignore[attr-defined]
        psycopg2.extras = extras  # type: ignore[attr-defined]
        sys.modules['psycopg2'] = psycopg2
        sys.modules['psycopg2.extras'] = extras
    if 'github' not in sys.modules:
        github = types.ModuleType('github')
        github.Github = object  # type: ignore[attr-defined]
        github.UnknownObjectException = type('UnknownObjectException', (Exception,), {})  # type: ignore[attr-defined]
        sys.modules['github'] = github


def load_bridge_module():
    """导入真实的 ``feedlog_bridge``（第三方包已打桩）。"""
    _install_third_party_stubs()
    spec = importlib.util.spec_from_file_location('feedlog_bridge_under_test', BRIDGE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    """记录每条 SQL 的假游标。"""

    def __init__(self, conn: 'FakeConn'):
        self.conn = conn
        self._row: Optional[dict[str, Any]] = None

    def execute(self, sql, params=None):
        self.conn.queries.append((sql, params))
        keyword = sql.lstrip().split(None, 1)[0].upper()
        if keyword == 'SELECT':
            self._row = self.conn.existing
        elif keyword == 'INSERT':
            # INSERT ... RETURNING id
            self._row = {'id': f'entry-{len(self.conn.queries)}'}
        else:
            self._row = None

    def fetchone(self):
        return self._row


class FakeConn:
    """假 DB 连接：记录 SQL 与参数，并模拟「已存在同 slug 条目」。"""

    def __init__(self):
        self.queries: list[tuple[str, tuple | None]] = []
        self.existing: Optional[dict[str, Any]] = None
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def statements(self, keyword: str):
        return [q for q in self.queries if q[0].lstrip().split(None, 1)[0].upper() == keyword]
