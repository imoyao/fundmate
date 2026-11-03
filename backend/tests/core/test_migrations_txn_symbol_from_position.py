# -*- coding: utf-8 -*-
"""#2855 回归：缺 ``symbol`` 的挂仓流水按持仓回填迁移。

## 这张卡要钉住的是什么

卖出/分红/拆分的写路径曾直接写 ``symbol=data.get('symbol')``，请求漏带就落 NULL。
读侧（产品详情交易记录、清仓周期分组）按 symbol 匹配 ⇒ 这些行静默消失，
已清仓产品「有买无卖」。写入侧兜底只管新数据，存量要靠本迁移：

1. **挂了持仓的**：真源 = position_id 指向的持仓，回填 ``symbol`` 并按
   ``symbol_identity(pos.symbol, t.asset_type)`` 重算 ``symbol_norm``；
2. **悬空 / 未挂载的**：无确定性真源，**不动**（按名称猜身份比缺更危险）；
3. 幂等（二次 `[SKIP]`）、空库安全；
4. 全标准 SQL，PG（生产 user 域）同样可执行。
"""

import sqlite3

from sqlalchemy import create_engine, text

from app.core.migrations import migrate_transaction_symbol_from_position


def _make_db(path, txn_rows, pos_rows=()):
    """造一个旧库（列名取真实 schema 的子集；`type` 是 txn_type 的库列名）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30) NOT NULL,
            type VARCHAR(20),
            ledger_id INTEGER,
            family_id INTEGER
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30),
            symbol_norm VARCHAR(64) NOT NULL DEFAULT '',
            asset_type VARCHAR(20),
            type VARCHAR(20),
            position_name VARCHAR(100),
            position_id INTEGER,
            ledger_id INTEGER,
            family_id INTEGER
        );
        """
    )
    if pos_rows:
        conn.executemany(
            'INSERT INTO positions(id, symbol, type, ledger_id, family_id) VALUES (?, ?, ?, ?, ?)', pos_rows
        )
    conn.executemany(
        'INSERT INTO transactions(id, symbol, symbol_norm, asset_type, type, position_name, position_id, ledger_id, family_id)'
        ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        txn_rows,
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    return create_engine(f'sqlite:///{path.as_posix()}')


def _rows(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


def test_挂仓的缺symbol卖出按持仓回填(tmp_path):
    """核心回归：SZ002311 形态——position_id 全对、symbol 全 NULL。"""
    p = tmp_path / 'db.sqlite'
    _make_db(
        p,
        txn_rows=[
            # id, symbol, symbol_norm, asset_type, type, position_name, position_id, ledger_id, family_id
            (1, None, '', 'stock', 'sell', '海大集团', 600, 12, 1),
            (2, None, '', 'stock', 'sell', '海大集团', 600, 12, 1),
        ],
        pos_rows=[(600, 'SZ002311', 'stock', 12, 1)],
    )
    eng = _engine_for(p)

    result = migrate_transaction_symbol_from_position(eng)
    assert '[OK]' in result and '2 行' in result

    rows = _rows(eng, 'SELECT id, symbol, symbol_norm FROM transactions ORDER BY id')
    assert rows[0][1] == 'SZ002311'
    assert rows[0][2] == 'EXCHANGE:SZ002311', f'symbol_norm 应按身份键重算，实际 {rows[0][2]!r}'
    assert rows[1][1] == 'SZ002311'


def test_分红行同样回填且身份按asset_type(tmp_path):
    """场外基金分红：OTC 身份（asset_type=fund ⇒ OTC:裸码）。"""
    p = tmp_path / 'db.sqlite'
    _make_db(
        p,
        txn_rows=[(10, None, '', 'fund', 'dividend', '某某基金', 7, 3, 1)],
        pos_rows=[(7, '020106', 'fund', 3, 1)],
    )
    eng = _engine_for(p)

    migrate_transaction_symbol_from_position(eng)
    row = _rows(eng, 'SELECT symbol, symbol_norm FROM transactions WHERE id=10')[0]
    assert row[0] == '020106'
    assert row[1] == 'OTC:020106', f'fund 的身份键应是 OTC:裸码，实际 {row[1]!r}'


def test_悬空持仓与未挂载的行不动(tmp_path):
    """持仓行已删（#2343 之前的历史）或 position_id 为 NULL：无真源，保持原样。"""
    p = tmp_path / 'db.sqlite'
    _make_db(
        p,
        txn_rows=[
            (1, None, '', 'stock', 'sell', '已删持仓的卖出', 999, 12, 1),  # 悬空
            (2, None, '', 'stock', 'sell', '孤儿卖出', None, 12, 1),  # 未挂载
        ],
        pos_rows=[(600, 'SZ002311', 'stock', 12, 1)],
    )
    eng = _engine_for(p)

    result = migrate_transaction_symbol_from_position(eng)
    assert '[SKIP]' in result or '[OK]' in result

    rows = _rows(eng, 'SELECT id, symbol FROM transactions ORDER BY id')
    assert rows[0][1] is None, '悬空 position_id 的行不能按名称猜身份'
    assert rows[1][1] is None, '未挂载的行保持原样'


def test_幂等_二次运行skip(tmp_path):
    p = tmp_path / 'db.sqlite'
    _make_db(
        p,
        txn_rows=[(1, None, '', 'stock', 'sell', '海大集团', 600, 12, 1)],
        pos_rows=[(600, 'SZ002311', 'stock', 12, 1)],
    )
    eng = _engine_for(p)

    assert '[OK]' in migrate_transaction_symbol_from_position(eng)
    assert '[SKIP]' in migrate_transaction_symbol_from_position(eng), '二次运行必须 [SKIP]'


def test_空库安全(tmp_path):
    p = tmp_path / 'db.sqlite'
    _make_db(p, txn_rows=[])
    eng = _engine_for(p)
    assert '[SKIP]' in migrate_transaction_symbol_from_position(eng)


def test_已填symbol的行不被改写(tmp_path):
    """symbol 是交易发生时的快照：已有值的行一律不碰（与 #1662 同一条纪律）。"""
    p = tmp_path / 'db.sqlite'
    _make_db(
        p,
        txn_rows=[
            # 字面量与持仓不同但**有值**：可能是历史写法，迁移无权改写
            (1, '002311.SZ', 'EXCHANGE:002311.SZ', 'stock', 'sell', '海大集团', 600, 12, 1),
        ],
        pos_rows=[(600, 'SZ002311', 'stock', 12, 1)],
    )
    eng = _engine_for(p)

    assert '[SKIP]' in migrate_transaction_symbol_from_position(eng)
    row = _rows(eng, 'SELECT symbol, symbol_norm FROM transactions WHERE id=1')[0]
    assert row[0] == '002311.SZ'
