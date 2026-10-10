# -*- coding: utf-8 -*-
"""#1982 回归：演示基金伪数据清洗脚本。

覆盖四条边界（这个脚本会**删库里的行**，因此每条都必须被钉住）：

1. 三重限定生效：名称命中 **且** `funds` 名录无记录才算待清理；
2. **名录有记录的一律豁免** —— 名字里带「示例」也可能是真基金名的一部分，
   宁可留着让人工复核，也不能静默删掉真实品种；
3. 子表只在该代码的**全部**持仓行都命中时才清（防「同码既有伪数据又有真实持仓」）；
4. dry-run 绝不改库（默认行为），`--apply` 才落库，且删除条数校验通过。
"""

import sqlite3

from scripts.clean_demo_fund_data import collect_candidates, run, target_codes


def _make_db(path) -> sqlite3.Connection:
    """造一个最小真库：positions / funds / 两张子表。

    形态照抄 #1982 的实测：三个伪码（名录无记录）+ 一个「名字里恰好有示例」的真品种
    （名录里有），再加一条同码混合行用于验证第三条限定。
    """
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE funds (fund_code VARCHAR(10) PRIMARY KEY, name VARCHAR(100));
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30),
            name VARCHAR(100),
            type VARCHAR(20),
            quantity INTEGER DEFAULT 0,
            current_price INTEGER DEFAULT 0,
            source VARCHAR(30),
            account_name VARCHAR(100),
            created_at VARCHAR(30),
            ledger_id INTEGER,
            ownership_status VARCHAR(20)
        );
        CREATE TABLE fund_industry_allocs (
            id INTEGER PRIMARY KEY,
            fund_code VARCHAR(10),
            industry_code VARCHAR(10),
            industry_name VARCHAR(50),
            period VARCHAR(20)
        );
        CREATE TABLE fund_holdings (
            id INTEGER PRIMARY KEY,
            fund_code VARCHAR(10),
            stock_code VARCHAR(10),
            stock_name VARCHAR(50),
            period VARCHAR(20)
        );

        -- 真品种：名录有记录（名字里恰好含「示例」）
        INSERT INTO funds(fund_code, name) VALUES ('005827', '示例价值精选混合');
        INSERT INTO positions(id, symbol, name, type, source, account_name, created_at, ledger_id, ownership_status)
        VALUES (1, '005827', '示例价值精选混合', 'fund', 'manual', '账户A', '2026-09-25 14:38:50', 12, 'active');

        -- 伪数据：3 只，名录无记录（形态同 #1982 实测）
        INSERT INTO positions(id, symbol, name, type, source, account_name, created_at, ledger_id, ownership_status)
        VALUES (2, '012345', '示例红利优选混合A', 'fund', 'e_account_holding', '同花顺——银河', '2026-09-25 14:38:51', 12, 'shadow'),
               (3, '023456', '示例现金添利货币市场基金', 'fund', 'e_account_holding', '示例基金销售', '2026-09-25 14:38:52', 26, 'active'),
               (4, '034567', '示例行业精选指数C', 'fund', 'e_account_holding', '示例银行', '2026-09-25 14:38:53', 28, 'active');

        -- 同码混合：009999 有伪行 + 真实行 → 该码的子表**不得**被清（第三条限定）
        INSERT INTO positions(id, symbol, name, type, source, account_name, created_at, ledger_id, ownership_status)
        VALUES (5, '009999', '示例混合测试', 'fund', 'e_account_holding', '示例证券', '2026-09-25 14:38:54', 27, 'active'),
               (6, '009999', '某真实持仓', 'fund', 'manual', '账户A', '2026-09-26 10:00:00', 12, 'active');

        -- 子表：伪数据的行业行（含 #1982 那份伪造的「制造业 10.61%」）
        INSERT INTO fund_industry_allocs(id, fund_code, industry_code, industry_name, period)
        VALUES (11, '023456', '45', '45制造业', '2026Q2'),
               (12, '009999', '45', '45信息技术', '2026Q2'),
               (13, '005827', '45', '信息技术', '2026Q2');
        INSERT INTO fund_holdings(id, fund_code, stock_code, stock_name, period)
        VALUES (21, '023456', '600000', '某银行', '2026Q2'),
               (22, '009999', '600001', '某钢铁', '2026Q2');
        """
    )
    conn.commit()
    return conn


def test_collect_splits_two_tiers(tmp_path):
    """一级＝名录查无该码；二级＝名录有该码（真实基金被配了假名字）。"""
    conn = _make_db(tmp_path / 'invest.db')

    targets, known = collect_candidates(conn)

    assert {t['symbol'] for t in targets} == {'012345', '023456', '034567', '009999'}
    # 名录有记录 → 二级：默认不删，且在报告里列出来给人工拍板
    assert {k['symbol'] for k in known} == {'005827'}


def test_catalog_known_rows_need_explicit_opt_in_and_never_touch_children(tmp_path):
    """二级必须显式开启，且**只删持仓、绝不动子表**。

    这是 #1982 复核更正的核心：`012345` / `023456` 在名录里是**真实基金**，
    名下有几十行真实披露数据；卡里方案 (a) 的「连带删除 fund_industry_allocs /
    fund_holdings」会把真数据当垃圾清掉。
    """
    from scripts.clean_demo_fund_data import run

    db = tmp_path / 'invest.db'
    conn = _make_db(db)
    # 让 005827（二级）名下有「真实披露数据」
    conn.execute(
        "INSERT INTO fund_holdings(id, fund_code, stock_code, stock_name, period) VALUES (23, '005827', '600002', '某白酒', '2026Q2')"
    )
    conn.commit()

    rc = run(conn, apply=True, rollback_out=None)  # 不开二级
    assert rc == 0
    assert '005827' in {r[0] for r in conn.execute('SELECT symbol FROM positions').fetchall()}

    rc = run(conn, apply=True, rollback_out=None, include_catalog_known=True)
    assert rc == 0
    left = {r[0] for r in conn.execute('SELECT symbol FROM positions').fetchall()}
    assert '005827' not in left, '开启二级后假仓位应被删除'
    # 但它的披露数据必须还在
    assert conn.execute("SELECT COUNT(1) FROM fund_holdings WHERE fund_code='005827'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(1) FROM fund_industry_allocs WHERE fund_code='005827'").fetchone()[0] == 1


def test_child_tables_only_when_all_rows_are_targets(tmp_path):
    """009999 既有伪行又有真实行 → 它的子表不动（否则会删掉真实品种的披露数据）。"""
    conn = _make_db(tmp_path / 'invest.db')
    targets, _exempt = collect_candidates(conn)

    codes = target_codes(conn, targets)

    assert '009999' not in codes, '同码混合的代码不得进子表清理范围'
    assert set(codes) == {'012345', '023456', '034567'}


def test_dry_run_changes_nothing(tmp_path):
    db = tmp_path / 'invest.db'
    conn = _make_db(db)
    before = conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0]

    rc = run(conn, apply=False, rollback_out=None)

    assert rc == 0
    assert conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0] == before
    assert conn.execute('SELECT COUNT(*) FROM fund_industry_allocs').fetchone()[0] == 3


def test_apply_removes_only_demo_rows_and_their_children(tmp_path):
    db = tmp_path / 'invest.db'
    conn = _make_db(db)

    rc = run(conn, apply=True, rollback_out=None)

    assert rc == 0
    left = {r[0] for r in conn.execute('SELECT symbol FROM positions').fetchall()}
    assert left == {'005827', '009999'}, '真品种与同码混合行必须留下'
    # 伪货基的行业行必须清掉，否则穿透照样把它摊成「制造业」
    left_alloc = {r[0] for r in conn.execute('SELECT fund_code FROM fund_industry_allocs').fetchall()}
    assert left_alloc == {'009999', '005827'}
    assert {r[0] for r in conn.execute('SELECT fund_code FROM fund_holdings').fetchall()} == {'009999'}


def test_rollback_sql_restores_deleted_rows(tmp_path):
    db = tmp_path / 'invest.db'
    conn = _make_db(db)
    out = tmp_path / 'rollback.sql'

    run(conn, apply=False, rollback_out=str(out))
    sql = out.read_text(encoding='utf-8')
    assert 'INSERT INTO positions' in sql
    assert '012345' in sql

    # 真跑一次，再用回滚语句还原，条数应回到初始
    run(conn, apply=True, rollback_out=None)
    conn.executescript(sql)
    assert conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0] == 6
    assert conn.execute('SELECT COUNT(*) FROM fund_industry_allocs').fetchone()[0] == 3
