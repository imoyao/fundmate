# -*- coding: utf-8 -*-
"""positions 快照锚点迁移：加列 + 回填日期，**不回填份额**。

迁移的核心约束是「不猜」：历史快照份额已经丢了，同一个 quantity 可能是
「先流水后快照」的正确值，也可能是「先快照后流水」的翻倍值。盲猜任一方向都会把
另一半账户改坏，所以迁移只做无歧义的两件事——加列、从 position_import_meta 回填
snapshot_date（并置 anchor_kind='external'），份额列保持 NULL。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_positions_snapshot_anchor


def _make_legacy_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE positions(
            id INTEGER PRIMARY KEY,
            symbol TEXT,
            quantity INTEGER,
            avg_price INTEGER
        );
        CREATE TABLE position_import_meta(
            id INTEGER PRIMARY KEY,
            position_id INTEGER,
            snapshot_date DATE
        );
        -- 1 号：有快照日（E账户导入过）
        INSERT INTO positions VALUES (1, '012708', 221664444, 13234);
        -- 2 号：纯手工持仓，无快照日
        INSERT INTO positions VALUES (2, '000001', 1000000, 100000);
        INSERT INTO position_import_meta VALUES (10, 1, '2026-08-12');
        """
    )
    conn.commit()
    conn.close()


def test_migration_adds_columns_and_backfills_date_only(tmp_path):
    db = tmp_path / 'invest.db'
    _make_legacy_db(str(db))
    engine = create_engine(f'sqlite:///{db}')

    msg = migrate_positions_snapshot_anchor(engine)
    assert '回填' in msg

    cols = {c['name'] for c in inspect(engine).get_columns('positions')}
    assert {'snapshot_quantity', 'snapshot_avg_price', 'snapshot_date', 'anchor_kind'} <= cols

    with engine.connect() as conn:
        row = conn.execute(
            text('SELECT snapshot_quantity, snapshot_avg_price, snapshot_date, anchor_kind FROM positions WHERE id = 1')
        ).fetchone()
    # 份额/成本价必须保持 NULL——迁移不猜
    assert row[0] is None
    assert row[1] is None
    # 日期与来源来自 meta，无歧义
    assert row[2] == '2026-08-12'
    assert row[3] == 'external'

    with engine.connect() as conn:
        row2 = conn.execute(text('SELECT snapshot_date, anchor_kind FROM positions WHERE id = 2')).fetchone()
    # 无 meta 的持仓不写锚点
    assert row2[0] is None
    assert row2[1] is None

    engine.dispose()


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_legacy_db(str(db))
    engine = create_engine(f'sqlite:///{db}')

    migrate_positions_snapshot_anchor(engine)
    msg2 = migrate_positions_snapshot_anchor(engine)
    assert msg2.startswith('[SKIP]')

    engine.dispose()


def test_migration_skips_when_table_absent(tmp_path):
    db = tmp_path / 'empty.db'
    engine = create_engine(f'sqlite:///{db}')
    msg = migrate_positions_snapshot_anchor(engine)
    assert msg.startswith('[SKIP]')
    engine.dispose()


# ── cleared_at（#2343 第二步）：只加列，不回填 ────────────────


def test_cleared_at_migration_adds_column_without_backfill(tmp_path):
    """cleared_at 只加列：历史清仓行已被删除，无可靠数据源，保持 NULL。"""
    from app.core.migrations import migrate_positions_cleared_at

    db = tmp_path / 'cleared.db'
    _make_legacy_db(str(db))
    engine = create_engine(f'sqlite:///{db}')

    msg = migrate_positions_cleared_at(engine)
    assert 'cleared_at' in msg

    cols = {c['name'] for c in inspect(engine).get_columns('positions')}
    assert 'cleared_at' in cols

    with engine.connect() as conn:
        rows = conn.execute(text('SELECT id, cleared_at FROM positions ORDER BY id')).fetchall()
    assert all(r[1] is None for r in rows), '迁移绝不伪造清仓时间'


def test_cleared_at_migration_is_idempotent(tmp_path):
    from app.core.migrations import migrate_positions_cleared_at

    db = tmp_path / 'cleared2.db'
    _make_legacy_db(str(db))
    engine = create_engine(f'sqlite:///{db}')

    migrate_positions_cleared_at(engine)
    msg = migrate_positions_cleared_at(engine)
    assert '已存在' in msg or 'SKIP' in msg
