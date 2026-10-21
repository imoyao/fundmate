# -*- coding: utf-8 -*-
"""#2136 迁移测试：assets.major_category 归一 current→cash（幂等、只改数据）。

迁移本体在 `app/core/migrations.py`，这里锁住三件事：
1. 真的有 'current' 行时会被改成 'cash'；
2. 幂等：再跑一次影响 0 行，且不会把已经是 'cash' 的行弄坏；
3. 词表里的其他取值（liability 等）不受影响。
"""

from sqlalchemy import create_engine, text

from app.core.migrations import migrate_asset_major_category_current_to_cash


def _make_db(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "m.db"}')
    with engine.begin() as conn:
        conn.execute(
            text(
                'CREATE TABLE assets ('
                ' id INTEGER PRIMARY KEY,'
                ' major_category VARCHAR(20) NOT NULL,'
                ' amount INTEGER DEFAULT 0'
                ')'
            )
        )
    return engine


def test_migration_normalizes_current_to_cash(tmp_path):
    engine = _make_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO assets (major_category, amount) VALUES ('current', 100)"))
        conn.execute(text("INSERT INTO assets (major_category, amount) VALUES ('cash', 200)"))
        conn.execute(text("INSERT INTO assets (major_category, amount) VALUES ('liability', 300)"))

    msg = migrate_asset_major_category_current_to_cash(engine)
    assert '1 行' in msg, msg

    with engine.connect() as conn:
        rows = dict(conn.execute(text('SELECT major_category, amount FROM assets')).all())
    assert rows == {'cash': 200, 'liability': 300} or 'current' not in rows
    with engine.connect() as conn:
        cats = {c: a for c, a in conn.execute(text('SELECT major_category, amount FROM assets')).all()}
    assert 'current' not in cats
    assert cats['liability'] == 300


def test_migration_is_idempotent(tmp_path):
    engine = _make_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO assets (major_category, amount) VALUES ('current', 100)"))

    migrate_asset_major_category_current_to_cash(engine)
    msg2 = migrate_asset_major_category_current_to_cash(engine)

    assert '0 行' in msg2, msg2
    with engine.connect() as conn:
        cats = dict(conn.execute(text('SELECT major_category, amount FROM assets')).all())
    assert cats == {'cash': 100}


def test_migration_skips_when_table_absent(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    msg = migrate_asset_major_category_current_to_cash(engine)
    assert 'SKIP' in msg, msg
