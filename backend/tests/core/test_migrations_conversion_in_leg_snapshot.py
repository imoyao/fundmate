# -*- coding: utf-8 -*-
"""#2406 回归：转换「转入腿」positions.name / market 快照的存量收编迁移。

背景：转入腿 `in_data` 漏传 `name` / `market`（`account_name` 已由 PR #2404 收口，
同一份 dict 的同一缺陷族）。本地库实证 position 618（519771，转入腿所建）：
`name=NULL`、`market='UNKNOWN'`——后者还是 presenter 旧实现直接改 ORM 对象、
被同 session flush 落库的污染值（读函数写库，#2406 已修病根）。

验收重点是**它不许乱改**：

- 正例：name 空 + market 污染/空 → name 按 market 域基金名录回填、market 收编 'CN_A'；
- 硬边界：名录无此码 → name **保持原值不编造**（market 仍按场外惯例收编，
  这是两列不同的证据要求：name 要名录证据，market 是项目惯例）；
- market 域不可达（`resolve_fund_names` 全 None）→ name 一行不动；
- 非基金类行（stock）的 NULL market 不越权收编；
- 健康行不动；空结果幂等（第二次 SKIP 语义由 [OK] 无改动表达）。

`type` 是 asset_type 的**实际库列名**（ORM 里 `asset_type = Column('type', ...)`），
不是笔误（同 test_migrations_positions_money_fund_flag.py 的口径）。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, text

from app.core.migrations import migrate_conversion_in_leg_snapshot

pytestmark = pytest.mark.usefixtures('app')


@pytest.fixture(autouse=True)
def _clear_money_fund_cache():
    """`fund_utils._cache` 是模块级全局缓存：不清会让前一个用例的名录结论污染后一个。"""
    from app.services import fund_utils

    fund_utils._cache.clear()
    yield
    fund_utils._cache.clear()


@pytest.fixture
def market_db(app):
    """market 域会话（`app` 夹具已把它重定向到内存库）。"""
    from app.core.db_factory import market_session_factory

    session = market_session_factory()()
    yield session
    session.close()


def _seed_fund(market_db, code: str, name: str):
    from app.domains.funds.models import Fund

    market_db.add(Fund(fund_code=code, name=name))
    market_db.commit()


def _make_db(path, rows) -> None:
    """造一张「迁移前」的 positions 表（列名取真实 schema 的子集）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30) NOT NULL,
            type VARCHAR(20),
            name VARCHAR(80),
            market VARCHAR(20),
            ledger_id INTEGER,
            family_id INTEGER
        );
        """
    )
    conn.executemany(
        'INSERT INTO positions(id, symbol, type, name, market, ledger_id, family_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
        rows,
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    return create_engine(f'sqlite:///{path.as_posix()}')


def _snapshot(engine) -> dict:
    with engine.connect() as conn:
        return {r[0]: (r[1], r[2]) for r in conn.execute(text('SELECT id, name, market FROM positions')).fetchall()}


def test_backfills_name_and_reclaims_market(tmp_path, market_db):
    """正例：name 空 + market 污染/空 → 名录回填名、market 收编 'CN_A'；健康行不动。"""
    _seed_fund(market_db, '519771', '招商中证白酒指数A')
    _seed_fund(market_db, '161725', '招商中证白酒指数LOF')  # 带前缀代码按归一化后的 6 位码查名录
    db = tmp_path / 'invest.db'
    _make_db(
        db,
        [
            (1, '519771', 'fund', None, 'UNKNOWN', 16, 1),  # 618 实证形态：名空 + 污染值
            (2, '519771', 'fund', '', None, 16, 1),  # 空串名 + NULL market 双缺失
            (3, 'SH161725', 'fund', None, 'UNKNOWN', 16, 1),  # 带前缀代码按归一化查名录
            (4, '000001', 'fund', '健康基金', 'CN_A', 1, 1),  # 健康行 → 不动
            (5, 'SZ000725', 'stock', None, None, 1, 1),  # 非基金类 → 不越权
        ],
    )
    engine = _engine_for(db)

    result = migrate_conversion_in_leg_snapshot(engine)
    assert result.startswith('[OK]')

    snap = _snapshot(engine)
    assert snap[1] == ('招商中证白酒指数A', 'CN_A')
    assert snap[2] == ('招商中证白酒指数A', 'CN_A')
    assert snap[3] == ('招商中证白酒指数LOF', 'CN_A')
    assert snap[4] == ('健康基金', 'CN_A')
    assert snap[5] == (None, None)

    # 幂等：第二次无行命中 → [OK] 无改动
    assert migrate_conversion_in_leg_snapshot(engine).startswith('[OK]')
    assert _snapshot(engine) == snap


def test_undecidable_name_kept_market_still_reclaimed(tmp_path, market_db):
    """硬边界：名录无此码 → name 保持原值（不编造），market 仍按场外惯例收编。"""
    _seed_fund(market_db, '519771', '招商中证白酒指数A')  # 只seed 519771，不 seed 999999
    db = tmp_path / 'invest.db'
    _make_db(db, [(1, '999999', 'fund', None, 'UNKNOWN', 1, 1)])
    engine = _engine_for(db)

    result = migrate_conversion_in_leg_snapshot(engine)
    assert '名录无记录/不可达' in result

    snap = _snapshot(engine)
    assert snap[1] == (None, 'CN_A')  # 名不编造，market 收编


def test_market_unreachable_never_fabricates_name(tmp_path, monkeypatch):
    """market 域不可达（resolve_fund_names 全 None）：name 一行不动，market 照常收编。"""
    from app.services import fund_utils

    monkeypatch.setattr(fund_utils, 'resolve_fund_names', lambda symbols: {s: None for s in symbols})

    db = tmp_path / 'invest.db'
    _make_db(db, [(1, '519771', 'fund', None, 'UNKNOWN', 16, 1)])
    engine = _engine_for(db)

    result = migrate_conversion_in_leg_snapshot(engine)
    assert '名录无记录/不可达' in result

    snap = _snapshot(engine)
    assert snap[1] == (None, 'CN_A')


def test_no_rows_needing_fix_is_ok(tmp_path):
    """空库 / 无待修行 → [OK]（不报错、不写库）。"""
    db = tmp_path / 'invest.db'
    _make_db(db, [(1, '000001', 'fund', '健康基金', 'CN_A', 1, 1)])
    engine = _engine_for(db)

    assert migrate_conversion_in_leg_snapshot(engine).startswith('[OK]')
    assert _snapshot(engine) == {1: ('健康基金', 'CN_A')}
