# -*- coding: utf-8 -*-
"""`scripts/audit_symbol_venue_conformance.py` 的「流水只报不改」契约。

## 为什么需要这组测试

脚本的 `--apply` 原本对 `transactions` 也做 `symbol` 前缀改写。`transactions.symbol`
有两个不可动的理由，任何一个单独成立就够了：

1. 它是**交易发生时的快照**，改写等于篡改历史记录；
2. `import_hash` 的输入含 symbol（`source|confirm_date|symbol|business_type|shares|nav`，
   见 `services/import_records.compute_record_hash`），改写它会让重导去重失效、
   凭空产生重复流水。而历史 hash **无法从库内列反推复现**（实测 15 种 source ×
   8 种 business_type × 多种精度全不命中），「改完再重算」这条路也堵死。

历史上这条路径没被触发纯属侥幸：那 51 条 `SZ001937` 之类当时 `asset_type` 和
`position_id` 都是 NULL，判不出 venue 被 `audit()` 跳过。**#2782 的迁移把 `asset_type`
回填之后，它们会正式暴露给 `--apply`** —— 若不改脚本，跑一次就毁掉这些行的去重指纹。

故契约是：形态不合规**只报不改**（`audit_immutable_symbols`），
派生列 `symbol_norm` 照常重算（`audit_symbol_norm` / `repair_symbol_norm`）。
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script():
    """按路径加载脚本模块（`scripts/` 不是包，只能走 importlib）。"""
    path = _REPO_ROOT / 'scripts' / 'audit_symbol_venue_conformance.py'
    spec = importlib.util.spec_from_file_location('audit_symbol_venue', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['audit_symbol_venue'] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def script():
    return _load_script()


def _make_db(path: Path, *, txn_norm: str = 'OTC:011341', pos_norm: str = 'OTC:023887') -> None:
    """最小库：三张表 + 各自一条「形态不合规」行。"""
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY, symbol TEXT, type TEXT, family_id INTEGER,
            ledger_id INTEGER, symbol_norm TEXT
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY, symbol TEXT, asset_type TEXT, position_id INTEGER,
            family_id INTEGER, ledger_id INTEGER, symbol_norm TEXT, import_hash TEXT
        );
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY, symbol TEXT, asset_type TEXT, venue TEXT,
            family_id INTEGER, market TEXT
        );
        """
    )
    # 场外货基被套上深交所前缀 —— #1662 的真实污染形态
    con.execute(
        "INSERT INTO positions VALUES (1, '023887', 'fund', 1, 1, ?)",
        (pos_norm,),
    )
    con.execute(
        "INSERT INTO transactions VALUES (76, 'SZ011341', 'fund', 1, 1, 1, ?, ?)",
        (txn_norm, 'f' * 32),
    )
    con.commit()
    con.close()


def test_audit_skips_transactions(script, tmp_path):
    """形态审计不得把流水列为「可改写」目标 —— 这是 `--apply` 的唯一防线。"""
    db = tmp_path / 'invest.db'
    _make_db(db)

    con = sqlite3.connect(db)
    try:
        tables = {f['table'] for f in script.audit(con)}
    finally:
        con.close()

    assert 'transactions' not in tables


def test_audit_still_catches_positions(script, tmp_path):
    """排除流水不能顺手把持仓也放过 —— 持仓改写是安全且必要的（有唯一约束托底）。"""
    db = tmp_path / 'invest.db'
    _make_db(db)
    con = sqlite3.connect(db)
    con.execute("UPDATE positions SET symbol = 'SZ023887'")
    con.commit()
    try:
        findings = script.audit(con)
    finally:
        con.close()

    assert [f['table'] for f in findings] == ['positions']
    assert findings[0]['expected'] == '023887'


def test_immutable_symbols_reports_transactions(script, tmp_path):
    """被排除的流水形态要能被单独看到，否则「不修」会退化成「不知道」。"""
    db = tmp_path / 'invest.db'
    _make_db(db)
    con = sqlite3.connect(db)
    try:
        rows = script.audit_immutable_symbols(con)
    finally:
        con.close()

    assert len(rows) == 1
    assert rows[0]['table'] == 'transactions'
    assert rows[0]['symbol'] == 'SZ011341'
    assert rows[0]['expected'] == '011341'


def test_norm_audit_covers_transactions(script, tmp_path):
    """`symbol_norm` 是读侧唯一匹配键，流水里的错值必须报出来。"""
    db = tmp_path / 'invest.db'
    _make_db(db, txn_norm='BROKEN')
    con = sqlite3.connect(db)
    try:
        findings = script.audit_symbol_norm(con)
    finally:
        con.close()

    assert [(f['table'], f['pk'], f['expected']) for f in findings] == [('transactions', 76, 'OTC:011341')]


def test_repair_norm_keeps_symbol_and_hash(script, tmp_path):
    """重算派生列，**不得**碰 symbol 与 import_hash —— 这两条是本卡的全部意义。"""
    db = tmp_path / 'invest.db'
    _make_db(db, txn_norm='BROKEN')
    con = sqlite3.connect(db)
    try:
        assert script.repair_symbol_norm(con) >= 1
        con.commit()
        symbol, norm, hash_ = con.execute(
            'SELECT symbol, symbol_norm, import_hash FROM transactions WHERE id = 76'
        ).fetchone()
    finally:
        con.close()

    assert symbol == 'SZ011341', '流水 symbol 是快照，被改写了'
    assert hash_ == 'f' * 32, 'import_hash 被重算了 —— 历史指纹无法复现，重算即写错'
    assert norm == 'OTC:011341'


def test_apply_does_not_touch_transactions(script, tmp_path, monkeypatch):
    """端到端：`--apply` 跑完，流水的 symbol / import_hash 原样，symbol_norm 已修正。"""
    db = tmp_path / 'invest.db'
    _make_db(db, txn_norm='BROKEN')
    monkeypatch.setattr(sys, 'argv', ['audit', '--db', str(db), '--apply'])

    exit_code = script.main()

    con = sqlite3.connect(db)
    try:
        row = con.execute('SELECT symbol, symbol_norm, import_hash FROM transactions WHERE id = 76').fetchone()
    finally:
        con.close()

    assert row[0] == 'SZ011341'
    assert row[2] == 'f' * 32
    assert row[1] == 'OTC:011341'
    # 流水形态债不计入退出码：它是可接受的快照形态，不是待修缺陷
    assert exit_code == 0
