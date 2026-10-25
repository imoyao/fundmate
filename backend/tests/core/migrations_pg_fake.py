# -*- coding: utf-8 -*-
"""迁移 PG 分支的假引擎（#2534）：本地没有 PG 可连，PG 行为只能钉「不早退 + SQL 形态」。

## 为什么需要它

迁移此前的默认形态是「非 SQLite 就跳过」，对应的测试用**只有一个 url 属性的
``_FakeEngine`` 断言「返回 SKIP」——那是在钉 bug 本身（#2469 / #2532 两次生产
停摆的根因）。#2534 把迁移改成全引擎后，这类测试必须改写为钉**新契约**：

- PG 分支**不再早退**（返回 ``[OK]`` / 真实执行结果，而不是 ``[SKIP] 非 SQLite``）；
- PG 发出的 DDL 是 ``ADD COLUMN IF NOT EXISTS`` / ``CREATE [UNIQUE] INDEX IF
  NOT EXISTS`` 形态（语法错要等生产才发现，故在本地钉住文本）。

## 用法

::

    def test_pg_branch(monkeypatch):
        fake = PgFake({'watchlist': ['id', 'symbol', 'market', 'venue']})
        fake.install(monkeypatch)
        result = migrate_watchlist_name_snapshot(fake.engine)
        assert result.startswith('[OK]')
        assert any('ADD COLUMN IF NOT EXISTS name VARCHAR(100)' in s for s in fake.sql)

- ``engine.url`` 是 postgres 形态 ⇒ ``_is_postgres()`` 为真；
- ``inspect`` 被换成假的：表名 / 列名 / 索引名由构造参数决定，DDL 执行后会同步
  更新（加列改列集合、建索引改索引集合），因此**幂等路径**（第二次跑不发 DDL）
  也能被测；
- 每条 SQL 记录到 ``fake.sql``；``SELECT`` 返回 ``fake.rows``（默认空，
  数据回填类迁移因此走「无行」分支，不碰 market 域名录）；
- ``apply_ddl=False`` 时 DDL **不生效**，用于测「收尾自校验必须抛错」。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

_ADD_COL_RE = re.compile(r'ALTER TABLE (\w+) ADD COLUMN (?:IF NOT EXISTS )?(\w+)', re.IGNORECASE)
_CREATE_INDEX_RE = re.compile(r'CREATE (?:UNIQUE )?INDEX (?:IF NOT EXISTS )?(\w+) ON (\w+)', re.IGNORECASE)
# 建表：表名 + 列名列表（够 fake 维护「表在不在、哪些列」即可，不必真解析约束）
_CREATE_TABLE_RE = re.compile(r'CREATE TABLE (?:IF NOT EXISTS )?(\w+)\s*\((.*?)\)', re.IGNORECASE | re.DOTALL)
_CREATE_TABLE_COL_RE = re.compile(r'^\s*(\w+)\s+[A-Z]', re.IGNORECASE | re.MULTILINE)


class _Result:
    """假游标：只实现迁移用到的四个方法/属性。"""

    def __init__(self, rows: Optional[list] = None, rowcount: int = 0):
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows

    def scalar(self):
        if not self._rows:
            return 0
        return self._rows[0][0]

    def mappings(self):
        return [dict(zip(('id',), r)) if not isinstance(r, dict) else r for r in self._rows]


class _Conn:
    def __init__(self, fake: 'PgFake'):
        self._fake = fake

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self._fake.sql.append(sql)
        head = sql.lstrip().split(' ', 1)[0].upper()
        if head in ('ALTER', 'CREATE'):
            if self._fake.apply_ddl:
                self._fake._apply_ddl(sql)
            return _Result()
        return _Result(self._fake.rows, rowcount=len(self._fake.rows))

    def commit(self):
        pass


class _Engine:
    """只需 url / connect / begin 的假引擎（PG 形态）。"""

    def __init__(self, fake: 'PgFake'):
        self._fake = fake
        self.url = 'postgresql+psycopg://u:p@127.0.0.1:1/db'

    def connect(self):
        return _Conn(self._fake)

    def begin(self):
        return _Conn(self._fake)


class _Inspector:
    def __init__(self, fake: 'PgFake'):
        self._fake = fake

    def get_table_names(self):
        return list(self._fake.columns)

    def get_columns(self, table):
        return [{'name': c} for c in self._fake.columns.get(table, [])]

    def get_indexes(self, table):
        return [{'name': n} for n in self._fake.indexes.get(table, [])]


class PgFake:
    """PG 形态假引擎 + 假 inspect（见模块 docstring）。"""

    def __init__(self, columns: Dict[str, List[str]], *, rows: Optional[list] = None, apply_ddl: bool = True):
        self.columns = {t: list(c) for t, c in columns.items()}
        self.indexes: Dict[str, List[str]] = {}
        self.rows = rows or []
        self.apply_ddl = apply_ddl
        self.sql: List[str] = []
        self.engine = _Engine(self)

    def install(self, monkeypatch) -> None:
        """把 ``app.core.migrations.inspect`` 换成假 inspect。"""
        import app.core.migrations as migrations_mod

        monkeypatch.setattr(migrations_mod, 'inspect', lambda _engine: _Inspector(self))

    def _apply_ddl(self, sql: str) -> None:
        m = _ADD_COL_RE.search(sql)
        if m:
            table, name = m.group(1), m.group(2)
            if name not in self.columns.get(table, []):
                self.columns.setdefault(table, []).append(name)
            return
        m = _CREATE_INDEX_RE.search(sql)
        if m:
            name, table = m.group(1), m.group(2)
            self.indexes.setdefault(table, [])
            if name not in self.indexes[table]:
                self.indexes[table].append(name)
            return
        # 建表（#1173）：把表登记进去，列名从 DDL 里逐行抽出来
        # （只取「列名 + 类型」形态的行，跳过 PRIMARY KEY / CONSTRAINT 之类的约束行）。
        m = _CREATE_TABLE_RE.search(sql)
        if m:
            table, body = m.group(1), m.group(2)
            cols = self.columns.setdefault(table, [])
            for line in body.split(','):
                cm = _CREATE_TABLE_COL_RE.match(line)
                if cm and cm.group(1).upper() not in (
                    'PRIMARY',
                    'FOREIGN',
                    'CONSTRAINT',
                    'UNIQUE',
                    'CHECK',
                ):
                    name = cm.group(1)
                    if name not in cols:
                        cols.append(name)
