# -*- coding: utf-8 -*-
"""#2875 切片 A 回归：``positions`` 状态一致性 CHECK 约束。

钉住六件事：

1. **迁移后三条 CHECK 真的落库**（SQLite 反射不出约束内容，只能查 DDL 文本）；
2. **存量行一条不少、内容不变**（整表重建最容易在这里出事）；
3. **索引一条不少**——`positions` 的唯一键是**独立** `CREATE UNIQUE INDEX`，
   `DROP TABLE` 会连它们一起删；不重建 = 悄悄丢掉唯一约束（比不加 CHECK 严重）；
4. **违规写入当场被拒**：`cleared` 带份额 / 锚点半残；
5. **合法边界不被误伤**：shadow 行（有观测日、无份额）与 `active` 零份额
   （「清仓当天再买入」的已知边界）都必须能写；
6. **存量已有违反时 fail closed**：不猜测、不自动改数据，抛错并报出行数。

PG 侧连不上真库，按 `migrations_pg_fake` 的老套路钉 SQL 形态与「不早退」
（#2534：写错方言要等生产才发现，那是 #2469 / #2532 两次停摆的同一个坑）。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.migrations import migrate_positions_state_check_constraints

from .migrations_pg_fake import PgFake

#: 刻意只有两条：`cleared_at IS NOT NULL` 不加（旧库允许「无已知清仓时间」，
#: 见 `migrate_positions_cleared_at` 的 docstring 与模型里的注释）。
_CHECK_NAMES = ('ck_positions_cleared_zero_qty', 'ck_positions_anchor_pair')

_OLD_DDL = """
CREATE TABLE positions (
    id INTEGER NOT NULL PRIMARY KEY,
    family_id INTEGER NOT NULL DEFAULT 1,
    ledger_id INTEGER,
    symbol VARCHAR(30) NOT NULL,
    symbol_norm VARCHAR(64) NOT NULL DEFAULT '',
    quantity INTEGER DEFAULT 0,
    avg_price INTEGER DEFAULT 0,
    ownership_status VARCHAR(20) NOT NULL DEFAULT 'active',
    snapshot_quantity INTEGER,
    snapshot_avg_price INTEGER,
    snapshot_date DATE,
    anchor_kind VARCHAR(20),
    cleared_at DATETIME,
    import_hash VARCHAR(64)
);
CREATE UNIQUE INDEX uq_positions_ledger_symbol ON positions(ledger_id, symbol);
CREATE UNIQUE INDEX uq_positions_import_hash ON positions(import_hash);
CREATE UNIQUE INDEX uq_positions_ledger_symbol_norm ON positions (ledger_id, symbol_norm);
CREATE INDEX idx_positions_ledger_id ON positions(ledger_id);
CREATE INDEX idx_positions_symbol ON positions(symbol);
INSERT INTO positions
    (id, ledger_id, symbol, symbol_norm, quantity, avg_price, ownership_status,
     snapshot_quantity, snapshot_avg_price, snapshot_date, anchor_kind, cleared_at)
VALUES
    -- active 且锚点齐全
    (1, 1, 'SZ000001', '000001.SZ', 1000, 10000, 'active', 900, 9000, '2026-10-01', 'manual', NULL),
    -- cleared 且零份额、有清仓时间
    (2, 1, 'SH600000', '600000.SH', 0, 0, 'cleared', 0, 0, '2026-09-01', 'manual', '2026-09-01 10:00:00'),
    -- shadow：只有观测日、没有份额（设计如此，CHECK 必须豁免）
    (3, NULL, '023887', '023887', 295514300, 10000, 'shadow', NULL, NULL, '2026-10-23', NULL, NULL),
    -- active 零份额：清仓当天再买入的已知边界（不得被 CHECK 误伤）
    (4, 12, 'SZ159316', '159316.SZ', 0, 0, 'active', 0, 0, '2026-11-02', 'manual', '2026-11-02 23:31:32');
"""


@pytest.fixture
def old_db(tmp_path):
    path = tmp_path / 'old_user.db'
    conn = sqlite3.connect(str(path))
    conn.executescript(_OLD_DDL)
    conn.commit()
    conn.close()
    engine = create_engine(f'sqlite:///{path}')
    yield engine
    engine.dispose()


def _ddl(engine):
    with engine.connect() as conn:
        return (
            conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='positions'")).scalar() or ''
        )


def _index_names(engine):
    with engine.connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='positions' AND sql IS NOT NULL")
            )
        }


def test_三条CHECK落库且存量行与索引不变(old_db):
    before_rows = [tuple(r) for r in _rows(old_db)]
    before_idx = _index_names(old_db)

    result = migrate_positions_state_check_constraints(old_db)

    assert result.startswith('[OK]'), result
    ddl = _ddl(old_db)
    for name in _CHECK_NAMES:
        assert name in ddl, f'{name} 没落库:\n{ddl}'

    # 存量行逐字节不变 + 索引一条不少（重建的两大风险点）
    assert [tuple(r) for r in _rows(old_db)] == before_rows
    assert _index_names(old_db) == before_idx
    assert {'uq_positions_ledger_symbol', 'uq_positions_import_hash'} <= _index_names(old_db)


def _rows(engine):
    with engine.connect() as conn:
        return conn.execute(text('SELECT * FROM positions ORDER BY id')).fetchall()


def test_幂等_第二次调用跳过(old_db):
    """幂等 + **第一次真的改了结构**。

    只断言「第二次返回 SKIP」等于给空实现发绿灯（变异探针实测：把迁移改成
    直接 return 时，纯幂等用例照绿）。故先钉第一次是 [OK] 且约束已落库。
    """
    assert migrate_positions_state_check_constraints(old_db).startswith('[OK]')
    ddl = _ddl(old_db)
    for name in _CHECK_NAMES:
        assert name in ddl
    assert migrate_positions_state_check_constraints(old_db).startswith('[SKIP]')


def test_清理后仍可正常插入与更新(old_db):
    migrate_positions_state_check_constraints(old_db)
    with old_db.connect() as conn:
        conn.execute(text('UPDATE positions SET quantity = 2000, avg_price = 12000 WHERE id = 1'))
        conn.commit()
    with old_db.connect() as conn:
        assert conn.execute(text('SELECT quantity FROM positions WHERE id = 1')).scalar() == 2000


def test_cleared带份额被拒(old_db):
    migrate_positions_state_check_constraints(old_db)
    with pytest.raises(IntegrityError) as exc:
        with old_db.connect() as conn:
            conn.execute(text('UPDATE positions SET quantity = 500 WHERE id = 2'))
            conn.commit()
    assert 'ck_positions_cleared_zero_qty' in str(exc.value)


def test_cleared缺清仓时间不被拦(old_db):
    """刻意**不**约束这条：`migrate_positions_cleared_at` 把 NULL 定义为
    「无已知清仓时间」，旧库允许该形态。若哪天有人补上这条 CHECK，
    本用例会红——那正是需要重新讨论「旧库怎么办」的时候。
    """
    migrate_positions_state_check_constraints(old_db)
    with old_db.connect() as conn:
        conn.execute(text('UPDATE positions SET cleared_at = NULL WHERE id = 2'))
        conn.commit()
        assert conn.execute(text('SELECT cleared_at FROM positions WHERE id = 2')).scalar() is None


def test_锚点半残被拒而shadow豁免(old_db):
    migrate_positions_state_check_constraints(old_db)
    with pytest.raises(IntegrityError) as exc:
        with old_db.connect() as conn:
            conn.execute(text('UPDATE positions SET snapshot_quantity = NULL WHERE id = 1'))
            conn.commit()
    assert 'ck_positions_anchor_pair' in str(exc.value)

    # shadow 行本来就是这个形态（id=3），重建后必须仍然在、且还能再插一条同形态的
    with old_db.connect() as conn:
        assert conn.execute(text('SELECT snapshot_date FROM positions WHERE id = 3')).scalar()
        conn.execute(
            text(
                'INSERT INTO positions (id, symbol, symbol_norm, quantity, ownership_status, '
                "snapshot_date) VALUES (9, '110011', '110011', 100, 'shadow', '2026-10-24')"
            )
        )
        conn.commit()


def test_存量已有违反时fail_closed(tmp_path):
    """旧结构允许 cleared 带份额；迁移必须拒绝加约束并报出行数，而不是静默跳过。"""
    path = tmp_path / 'dirty_user.db'
    conn = sqlite3.connect(str(path))
    conn.executescript(_OLD_DDL)
    conn.execute('UPDATE positions SET quantity = 777 WHERE id = 2')  # cleared 却有份额
    conn.commit()
    conn.close()
    engine = create_engine(f'sqlite:///{path}')
    try:
        with pytest.raises(RuntimeError) as exc:
            migrate_positions_state_check_constraints(engine)
        msg = str(exc.value)
        assert 'cleared 但仍有份额' in msg
        assert '1 行' in msg
        # 关键：失败后不得改数据（用户的手工修复口径优先）
        with engine.connect() as c:
            assert c.execute(text('SELECT quantity FROM positions WHERE id = 2')).scalar() == 777
    finally:
        engine.dispose()


def test_PG分支发ALTER约束且不早退(monkeypatch):
    fake = PgFake(
        {'positions': ['id', 'quantity', 'ownership_status', 'snapshot_quantity', 'snapshot_date', 'cleared_at']}
    )
    fake.install(monkeypatch)

    result = migrate_positions_state_check_constraints(fake.engine)

    assert result.startswith('[OK]'), result
    ddl = [s for s in fake.sql if s.lstrip().upper().startswith('ALTER TABLE POSITIONS')]
    assert len(ddl) == len(_CHECK_NAMES)
    joined = ' '.join(ddl)
    for name in _CHECK_NAMES:
        assert f'ADD CONSTRAINT {name} CHECK' in joined
    # PG 没有 IF NOT EXISTS，重复执行必须靠反射跳过（否则第二次启动就炸）
    assert 'IF NOT EXISTS' not in joined


def test_PG分支幂等(monkeypatch):
    fake = PgFake(
        {'positions': ['id', 'quantity', 'ownership_status', 'snapshot_quantity', 'snapshot_date', 'cleared_at']}
    )
    fake.install(monkeypatch)

    migrate_positions_state_check_constraints(fake.engine)
    second = migrate_positions_state_check_constraints(fake.engine)

    assert second.startswith('[SKIP]')
    assert len([s for s in fake.sql if 'ADD CONSTRAINT' in s]) == len(_CHECK_NAMES)


def test_PG分支同样拒绝带病数据(monkeypatch):
    """SQLite 会 fail closed，PG 不能因为「不重建表」就放过。"""
    fake = PgFake(
        {'positions': ['id', 'quantity', 'ownership_status', 'snapshot_quantity', 'snapshot_date', 'cleared_at']},
        rows=[(3,)],
    )
    fake.install(monkeypatch)

    with pytest.raises(RuntimeError) as exc:
        migrate_positions_state_check_constraints(fake.engine)
    assert '拒绝加 CHECK 约束' in str(exc.value)


def test_模型与迁移的约束表达式逐字一致():
    """两处不同步 = 新库按 model 建、老库按迁移改，而 SQLite 反射不出 CHECK。

    改约束时必须同 PR 改两处；本用例把「忘了改另一处」钉成红。
    """
    from app.core.migrations import _POSITION_STATE_CHECKS
    from app.domains.positions.models import Position

    model = {
        c.name: str(c.sqltext) for c in Position.__table__.constraints if c.name and c.name.startswith('ck_positions')
    }
    assert set(model) == {n for n, _ in _POSITION_STATE_CHECKS}
    for name, expr in _POSITION_STATE_CHECKS:
        assert model[name] == expr, f'{name} 两边不一致: model={model[name]!r} migration={expr!r}'
