# -*- coding: utf-8 -*-
"""migrate_money_fund_backfill 的孤儿流水挂回单测（#1305 #25 / #26）。

只测 `plan_for` 的挂回候选计算（不写库、不碰真实数据库）。钉住两件事：

1. **#26 列错**：`transactions.type` 是**交易方向**（buy/sell/deposit/dividend/tax…），
   资产类型在另一个列 `asset_type` 上（`Transaction.txn_type = Column('type')` 与
   `Transaction.asset_type` 两列并存）。原写法 `type IN ('money_fund','reverse_repo')`
   恒不成立 → 命中**永远 0 行**，挂回功能一直静默失效。

   ⚠️ 注意 **positions 表相反**：那里 `type` **就是**资产类型（ORM 属性名 `asset_type`），
   所以 positions 的查询照旧用 `type`。两张表列名语义不同，别一起改。

2. **#25 去重**：同 (ledger_id, symbol) 存在多个持仓时，同一条孤儿流水只能挂到
   **一个**持仓，不能被后一个持仓覆盖（原实现取决于遍历顺序，归属不确定）。
"""

import os
import sqlite3
import sys

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import migrate_money_fund_backfill as m  # noqa: E402

_DDL = """
CREATE TABLE positions(id INTEGER PRIMARY KEY, ledger_id INTEGER, symbol TEXT, type TEXT,
                       is_money_fund INTEGER);
CREATE TABLE transactions(id INTEGER PRIMARY KEY, ledger_id INTEGER, position_id INTEGER,
                          symbol TEXT, type TEXT, asset_type TEXT, is_income INTEGER);
"""


def _make_db(path: str, positions, transactions) -> None:
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_DDL)
        conn.executemany('INSERT INTO positions(id, ledger_id, symbol, type) VALUES (?,?,?,?)', positions)
        conn.executemany(
            'INSERT INTO transactions(id, ledger_id, position_id, symbol, type, asset_type, is_income)'
            ' VALUES (?,?,?,?,?,?,?)',
            transactions,
        )
        conn.commit()
    finally:
        conn.close()


# (id, ledger_id, symbol, type)
_MF_POS = (1, 7, '001937', 'money_fund')
# (id, ledger_id, position_id, symbol, type, asset_type, is_income)
_MF_ORPHAN = (11, 7, None, '001937', 'buy', 'money_fund', 0)


def test_orphan_query_matches_asset_type_column(tmp_path) -> None:
    """核心回归（#1305 #26）：孤儿流水必须按 `asset_type` 匹配，按 `type` 会永远 0 行。

    构造的流水 `type='buy'`（交易方向）、`asset_type='money_fund'`（资产类型）——
    这正是真实数据的形态：本机 transactions.type 只有 buy/sell/deposit/dividend 等，
    从来不会是 'money_fund'。
    """
    db = str(tmp_path / 'invest.db')
    _make_db(db, [_MF_POS], [_MF_ORPHAN])
    _flag_updates, reattach = m.plan_for(db, {})
    assert reattach == [(1, [11])], f'挂回候选应为 [(1, [11])]，实际 {reattach}'


def test_orphan_of_other_asset_type_is_not_picked(tmp_path) -> None:
    """资产类型不是现金等价物的孤儿流水不挂回（asset_type='stock'）。"""
    db = str(tmp_path / 'invest.db')
    _make_db(db, [_MF_POS], [(11, 7, None, '001937', 'buy', 'stock', 0)])
    _flag_updates, reattach = m.plan_for(db, {})
    assert reattach == []


def test_income_rows_are_not_reattached(tmp_path) -> None:
    """is_income=1 的收益行不挂回（收益桶独立于本金，见 #863 D1）。"""
    db = str(tmp_path / 'invest.db')
    _make_db(db, [_MF_POS], [(11, 7, None, '001937', 'deposit', 'money_fund', 1)])
    _flag_updates, reattach = m.plan_for(db, {})
    assert reattach == []


def test_already_attached_rows_are_not_picked(tmp_path) -> None:
    """已有 position_id 的流水不是孤儿，不应被重新挂回。"""
    db = str(tmp_path / 'invest.db')
    _make_db(db, [_MF_POS], [(11, 7, 9, '001937', 'buy', 'money_fund', 0)])
    _flag_updates, reattach = m.plan_for(db, {})
    assert reattach == []


def test_same_orphan_attached_to_only_one_position(tmp_path) -> None:
    """核心回归（#1305 #25）：同 (ledger, symbol) 两个持仓时，孤儿流水只挂一次。

    原实现逐个 UPDATE，后一个持仓会覆盖前一个 → 归属取决于遍历顺序。
    """
    db = str(tmp_path / 'invest.db')
    _make_db(
        db,
        [(1, 7, '001937', 'money_fund'), (2, 7, '001937', 'money_fund')],
        [_MF_ORPHAN],
    )
    _flag_updates, reattach = m.plan_for(db, {})
    picked = [tid for _pid, txn_ids in reattach for tid in txn_ids]
    assert picked == [11], f'同一条孤儿流水只能出现一次，实际 {picked}'
    # 只应落在**一个**持仓上（先到先得）
    assert len(reattach) == 1, f'只应有一个持仓拿到它，实际 {reattach}'


def test_each_orphan_goes_to_one_position_across_symbols(tmp_path) -> None:
    """多持仓 + 多孤儿：每条流水恰好被分一次，总数守恒。"""
    db = str(tmp_path / 'invest.db')
    _make_db(
        db,
        [(1, 7, '001937', 'money_fund'), (2, 7, '001937', 'money_fund')],
        [
            (11, 7, None, '001937', 'buy', 'money_fund', 0),
            (12, 7, None, '001937', 'buy', 'money_fund', 0),
            (13, 7, None, '001937', 'deposit', 'reverse_repo', 0),
        ],
    )
    _flag_updates, reattach = m.plan_for(db, {})
    picked = [tid for _pid, txn_ids in reattach for tid in txn_ids]
    assert sorted(picked) == [11, 12, 13]
    assert len(picked) == len(set(picked)), '出现重复挂回'
