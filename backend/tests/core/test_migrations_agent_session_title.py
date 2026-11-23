# -*- coding: utf-8 -*-
"""#1719 后续回归：`agent_session.title` 会话标题列迁移.

验证 `migrate_agent_session_title`：

- 旧库（加列之前）执行后补列成功，并用 messages 里的**首条用户输入**回填存量行；
- 存量 messages 在库里是 ``\\uXXXX`` 转义形态（SQLite 侧 ``json.dumps`` 默认
  ``ensure_ascii=True``）——回填必须能解出中文。这正是「``LIKE '%温度%'`` 对着
  JSON 列永远 0 命中」那条结论的来源，也是标题单独成列的理由；
- 首条 user 为空 / 脏数据的行留空标题，**不得抛错**（迁移中断等于拒绝启动）；
- 幂等：重复执行不重复加列、不重复回填；
- 空库（表不存在）安全 skip，交给 create_all 建表；
- PG 分支不早退（#2534），发 ``ADD COLUMN IF NOT EXISTS``，回填走同一份 Python 逻辑。
"""

import json
import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations_agent import migrate_agent_session_title

from .migrations_pg_fake import PgFake

_LONG = '长' * 100


def _make_old_db(path) -> None:
    """造一个「加 title 列之前」的 agent_session 表，塞三行各有代表性的存量数据."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE agent_session (
            id INTEGER PRIMARY KEY,
            session_id VARCHAR(36) NOT NULL UNIQUE,
            messages TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    rows = [
        (1, 's1', json.dumps([{'user': '总资产多少', 'assistant': ''}])),
        # 首条 user 为空 → 应跳过它取第二条（空轮不是「首条输入」）
        (2, 's2', json.dumps([{'user': '  ', 'assistant': 'a'}, {'user': '第二个问题', 'assistant': ''}])),
        (3, 's3', 'not-a-json'),  # 脏数据：留空标题，不抛错
        (4, 's4', json.dumps([{'user': _LONG, 'assistant': ''}])),
    ]
    conn.executemany('INSERT INTO agent_session(id, session_id, messages) VALUES (?, ?, ?)', rows)
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def test_escaped_unicode_is_the_stored_shape(tmp_path):
    """先钉住前提：库里存的是转义形态。否则下面「回填能解出中文」的结论无意义."""
    db = tmp_path / 'invest.db'
    _make_old_db(db)

    conn = sqlite3.connect(str(db))
    raw = conn.execute('SELECT messages FROM agent_session WHERE id = 1').fetchone()[0]
    conn.close()

    assert '\\u' in raw and '总资产' not in raw  # 中文不以明文出现


def test_adds_title_column_and_backfills(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    result = migrate_agent_session_title(engine)
    assert result.startswith('[OK]'), result

    assert 'title' in {c['name'] for c in inspect(engine).get_columns('agent_session')}

    with engine.connect() as conn:
        titles = dict(conn.execute(text('SELECT id, title FROM agent_session')).fetchall())

    assert titles[1] == '总资产多少'
    assert titles[2] == '第二个问题'  # 空轮被跳过
    assert titles[3] == ''  # 脏数据留空，不抛错
    assert titles[4] == _LONG[:60]  # 按列宽截断


def test_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    assert migrate_agent_session_title(engine).startswith('[OK]')
    second = migrate_agent_session_title(engine)
    assert second.startswith('[SKIP]'), second

    cols = [c['name'] for c in inspect(engine).get_columns('agent_session')]
    assert cols.count('title') == 1  # 未重复加列


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动."""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_agent_session_title(engine).startswith('[SKIP]')


def test_pg_branch_adds_column_with_if_not_exists(monkeypatch):
    """#2534：PG 不早退，且发 `ADD COLUMN IF NOT EXISTS`（幂等语法，钉死文本）."""
    fake = PgFake({'agent_session': ['id', 'session_id', 'messages']})
    fake.install(monkeypatch)

    result = migrate_agent_session_title(fake.engine)

    assert result.startswith('[OK]'), f'PG 分支不许再返回跳过：{result}'
    expected = "ALTER TABLE agent_session ADD COLUMN IF NOT EXISTS title VARCHAR(60) NOT NULL DEFAULT ''"
    assert expected in fake.sql, f'PG 加列 DDL 形态不对：{fake.sql}'


def test_pg_branch_backfills_existing_rows(monkeypatch):
    """PG 侧回填走同一份 Python 解析（不依赖方言 JSON 函数）."""
    fake = PgFake(
        {'agent_session': ['id', 'session_id', 'messages', 'title']},
        rows=[(9, '[{"user": "\\u6e29\\u5ea6"}]')],
    )
    fake.install(monkeypatch)

    result = migrate_agent_session_title(fake.engine)

    assert result.startswith('[OK]') and '回填标题 1 行' in result
    assert any(s.lstrip().upper().startswith('UPDATE AGENT_SESSION') for s in fake.sql)


def test_pg_branch_missing_table_skips(monkeypatch):
    fake = PgFake({})
    fake.install(monkeypatch)

    assert migrate_agent_session_title(fake.engine).startswith('[SKIP]')
