# -*- coding: utf-8 -*-
"""``migrate_fund_managers_split_tenures`` 的回归测试（#2239）。

## 为什么这条迁移必须单独钉住

它是**整表重建**（建新表 → 拷贝 → 删旧 → 改名），而且是本仓第一次在启动期**删列**的迁移：

- 拷错/漏拷 → 关联数据静默丢失（`fund_managers` 是「谁在管哪只基金」的唯一来源）；
- 去重口径写错 → 留下的不是 `is_classic=True` 那行，代表作品会变差；
- 忘记加唯一约束 → 表能跑，但「重复膨胀」这个原始病灶原样保留（而且是**静默**的：
  `_validate_schema` 只查缺列，查不出少约束）；
- 顺序写反（先重建再搬任期）→ 中途失败就**永久丢任期日期**（只能重新逐只抓 F10）。

故这里覆盖：去重与保留优先级、任期搬迁与 `current` 口径、脏行跳过、唯一约束、
幂等重跑、空库跳过；PG 分支（原地改造，不整表重建）见
`test_migrations_pg_aware.py::test_pg_fund_managers_split_*`。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_fund_managers_split_tenures

from .migrations_pg_fake import PgFake


def _legacy_db(tmp_path):
    """造一个「改造前」的库：``fund_managers`` 带 start_date/end_date 且无唯一约束。

    刻意用**原生 SQL** 建旧结构（而不是模型）：模型已经是新结构，用它建不出待迁移的
    现场——那样测试就成了「跑一个空迁移」，什么都验不到。
    """
    db_path = tmp_path / 'legacy.db'
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE funds (id INTEGER PRIMARY KEY, fund_code TEXT);
        CREATE TABLE managers (id INTEGER PRIMARY KEY, mgr_code TEXT);
        CREATE TABLE fund_managers (
            id INTEGER PRIMARY KEY,
            fund_id INTEGER NOT NULL,
            mgr_id INTEGER NOT NULL,
            is_classic BOOLEAN,
            start_date DATE,
            end_date DATE
        );
        """
    )
    return db_path, conn


def _migrate(db_path):
    engine = create_engine(f'sqlite:///{db_path}')
    try:
        return migrate_fund_managers_split_tenures(engine), engine
    except Exception:
        engine.dispose()
        raise


def test_dedupes_and_keeps_is_classic_row(tmp_path):
    """同一 (fund_id, mgr_id) 只留一行，且**优先留 `is_classic=True` 的那行**。

    卡内实测：重复组内三列值完全一致，只差 id——所以「留哪行」本来无所谓，
    但 `is_classic` 是例外（代表作品标记），丢了它会让代表作挑选逻辑变差。
    """
    db_path, conn = _legacy_db(tmp_path)
    conn.executemany(
        'INSERT INTO fund_managers (id, fund_id, mgr_id, is_classic) VALUES (?,?,?,?)',
        [
            (1, 10, 100, 0),  # 先出现的「非代表作」
            (2, 10, 100, 1),  # 后出现的「代表作」→ 应被保留
            (3, 11, 100, 0),
        ],
    )
    conn.commit()
    conn.close()

    msg, engine = _migrate(db_path)

    with engine.connect() as c:
        rows = c.execute(text('SELECT id, fund_id, mgr_id, is_classic FROM fund_managers ORDER BY id')).fetchall()
    engine.dispose()

    kept = {(r[1], r[2]): r[3] for r in rows}
    assert len(rows) == 2, '重复组必须合并为一行'
    assert kept[(10, 100)] == 1, '保留的必须是 is_classic=True 那行'
    assert '[OK]' in msg and '去重' in msg


def test_drops_tenure_columns_and_adds_unique_constraint(tmp_path):
    """删掉 start_date/end_date，并加上 (fund_id, mgr_id) 唯一约束。

    唯一约束按**列**判定而不是按名：SQLite 不曝露内联约束名（反射回来是 None）。
    """
    db_path, conn = _legacy_db(tmp_path)
    conn.execute('INSERT INTO fund_managers (id, fund_id, mgr_id) VALUES (1, 10, 100)')
    conn.commit()
    conn.close()

    _, engine = _migrate(db_path)

    cols = {c['name'] for c in inspect(engine).get_columns('fund_managers')}
    uniques = inspect(engine).get_unique_constraints('fund_managers')
    engine.dispose()

    assert not ({'start_date', 'end_date'} & cols), f'任期列应已删除，实际列: {sorted(cols)}'
    assert any(sorted(u.get('column_names') or []) == ['fund_id', 'mgr_id'] for u in uniques), (
        f'缺少 (fund_id, mgr_id) 唯一约束：{uniques}'
    )


def test_moves_tenure_rows_and_sets_current_by_end_date(tmp_path):
    """任期搬进 ``manager_tenures``，`current` 按 **end_date 是否为空**落。"""
    db_path, conn = _legacy_db(tmp_path)
    conn.executemany(
        'INSERT INTO fund_managers (id, fund_id, mgr_id, start_date, end_date) VALUES (?,?,?,?,?)',
        [
            (1, 10, 100, '2018-09-05', None),  # 在任
            (2, 11, 100, '2015-01-01', '2020-01-01'),  # 已卸任
        ],
    )
    conn.commit()
    conn.close()

    _, engine = _migrate(db_path)

    with engine.connect() as c:
        rows = c.execute(
            text('SELECT fund_id, start_date, end_date, current FROM manager_tenures ORDER BY fund_id')
        ).fetchall()
    engine.dispose()

    assert rows == [
        (10, '2018-09-05', None, 1),
        (11, '2015-01-01', '2020-01-01', 0),
    ]


def test_skips_inverted_dates(tmp_path):
    """``start_date > end_date`` 属脏行：跳过，不把倒挂区间写进库。"""
    db_path, conn = _legacy_db(tmp_path)
    conn.executemany(
        'INSERT INTO fund_managers (id, fund_id, mgr_id, start_date, end_date) VALUES (?,?,?,?,?)',
        [
            (1, 10, 100, '2020-01-01', '2018-01-01'),  # 倒挂
            (2, 11, 100, '2018-01-01', '2020-01-01'),  # 正常
        ],
    )
    conn.commit()
    conn.close()

    msg, engine = _migrate(db_path)

    with engine.connect() as c:
        n = c.execute(text('SELECT COUNT(1) FROM manager_tenures')).scalar()
    engine.dispose()

    assert n == 1, '倒挂行不该入任期表'
    assert '跳过倒挂脏行 1' in msg


def test_is_idempotent(tmp_path):
    """重跑即跳过（启动期每次都会调它，不能每次都重建一遍）。"""
    db_path, conn = _legacy_db(tmp_path)
    conn.execute("INSERT INTO fund_managers (id, fund_id, mgr_id, start_date) VALUES (1, 10, 100, '2018-01-01')")
    conn.commit()
    conn.close()

    _, engine = _migrate(db_path)
    with engine.connect() as c:
        before = c.execute(text('SELECT COUNT(1) FROM fund_managers')).scalar()
    engine.dispose()

    second, engine = _migrate(db_path)
    with engine.connect() as c:
        after = c.execute(text('SELECT COUNT(1) FROM fund_managers')).scalar()
        tenure = c.execute(text('SELECT COUNT(1) FROM manager_tenures')).scalar()
    engine.dispose()

    assert '[SKIP]' in second
    assert before == after == 1
    assert tenure == 1


def test_skips_when_table_absent(tmp_path):
    """空库（表还没建）→ 跳过，交给 create_all 按新模型建。"""
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    try:
        assert '[SKIP]' in migrate_fund_managers_split_tenures(engine)
    finally:
        engine.dispose()


def test_pg_branch_never_runs_sqlite_only_statements(monkeypatch):
    """PG 分支**不早退**，也绝不把 SQLite 专属语句（`PRAGMA` / 整表重建）带过去。

    旧版这条叫 `test_skips_non_sqlite_engine`，用「只有 url 的假引擎」断言 `[SKIP]` ——
    那是在钉 bug 本身（PG 侧结构永远不迁移，#2689）。新契约用 `PgFake`：
    分支跑真实逻辑，只是把方言差异（删列/唯一索引）钉在 SQL 形态上。
    """
    fake = PgFake(
        {
            'fund_managers': ['id', 'fund_id', 'mgr_id', 'is_classic', 'start_date'],
            'manager_tenures': ['id', 'fund_id', 'mgr_id', 'start_date'],
        }
    )
    fake.install(monkeypatch)

    result = migrate_fund_managers_split_tenures(fake.engine)

    assert '非 SQLite' not in result
    joined = '\n'.join(fake.sql)
    assert 'PRAGMA' not in joined, joined
    assert 'RENAME TO' not in joined, joined
    assert 'ALTER TABLE fund_managers DROP COLUMN IF EXISTS start_date' in joined, joined


def test_dedupes_group_without_classic_flag(tmp_path):
    """重复组里没有代表作时，留任意一行即可（此处钉「行数正确」这一半）。"""
    db_path, conn = _legacy_db(tmp_path)
    conn.executemany(
        'INSERT INTO fund_managers (id, fund_id, mgr_id, is_classic) VALUES (?,?,?,?)',
        [(1, 10, 100, 0), (2, 10, 100, 0), (3, 10, 100, None)],
    )
    conn.commit()
    conn.close()

    _, engine = _migrate(db_path)
    with engine.connect() as c:
        rows = c.execute(text('SELECT id FROM fund_managers')).fetchall()
    engine.dispose()

    assert len(rows) == 1


if __name__ == '__main__':  # pragma: no cover
    pytest.main([__file__, '-q', '-p', 'no:randomly'])
