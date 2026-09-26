# -*- coding: utf-8 -*-
"""#1661 收尾 回归：positions.is_money_fund 存量重算迁移。

背景：PR #1663 只修了**读写路径**，已落库的历史标记不会自己变（本机实测 11 行真货基里
8 行仍为 0）。本迁移按「基金名录 + 品种」新口径重算该列，验收重点是**它不许乱改**：

- 正例：真货基（名录 `货币型`）标 0 → 回填 1；
- 反例：名录明确是「混合型」却标 1 → 纠正为 0（防过度抑制的另一面）；
- **保原值**：名录无此码 / 类型未知 / market 域不可达 → **一行都不动**（把「查不到」
  当成「不是货基」会在一次 market 域抖动里清空全库货基标记，这是本迁移的硬边界）；
- 显式非基金类型（stock / bond …）仍标 1 → 清零（历史污染，会让价格任务按面值 1.0000 回写）；
- 幂等（第二次跑 SKIP）、空库 / 非 SQLite / 缺列 SKIP。

`type` 是 asset_type 的**实际库列名**（ORM 里 `asset_type = Column('type', ...)`），不是笔误。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, text

from app.core.migrations import migrate_positions_money_fund_flag

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


def _seed_fund(market_db, code: str, name: str, type_name: str | None):
    """往 market 域名录塞一只基金；`type_name=None` 模拟 `fund_type_id` 为空。"""
    from app.domains.funds.models import Fund, FundType

    type_id = None
    if type_name is not None:
        row = market_db.query(FundType).filter_by(name=type_name).one_or_none()
        if row is None:
            row = FundType(name=type_name)
            market_db.add(row)
            market_db.flush()
        type_id = row.id
    market_db.add(Fund(fund_code=code, name=name, fund_type_id=type_id))
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
            ledger_id INTEGER,
            family_id INTEGER,
            is_money_fund BOOLEAN
        );
        """
    )
    conn.executemany(
        'INSERT INTO positions(id, symbol, type, ledger_id, family_id, is_money_fund) VALUES (?, ?, ?, ?, ?, ?)',
        rows,
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    return create_engine(f'sqlite:///{path.as_posix()}')


def _flags(engine) -> dict:
    with engine.connect() as conn:
        return dict(conn.execute(text('SELECT id, is_money_fund FROM positions')).fetchall())


def test_backfills_true_money_fund_and_clears_misflagged_rows(tmp_path, market_db):
    """正例 + 反例：真货基补 True、非货基清 False，两边都要动。"""
    _seed_fund(market_db, '004369', '前海开源聚财宝B', '货币型')
    _seed_fund(market_db, '110001', '易方达平稳增长混合', '混合型')
    db = tmp_path / 'invest.db'
    _make_db(
        db,
        [
            (1, '004369', 'fund', 1, 1, 0),  # 真货基却标 0 → 回填 1
            (2, '110001', 'fund', 1, 1, 1),  # 混合型却标 1 → 纠正 0
            (3, 'SZ000725', 'stock', 1, 1, 1),  # 股票被污染 → 清零
            (4, 'SH110081', 'bond', 1, 1, None),  # 可转债本就 None → 不动（保持 NULL）
        ],
    )
    engine = _engine_for(db)

    result = migrate_positions_money_fund_flag(engine)
    assert result.startswith('[OK]')

    flags = _flags(engine)
    assert flags[1] == 1
    assert flags[2] == 0
    assert flags[3] == 0
    assert flags[4] is None

    # 幂等：第二次跑必须 SKIP 且不再改动
    assert migrate_positions_money_fund_flag(engine).startswith('[SKIP]')


def test_undecidable_rows_keep_original_value(tmp_path, market_db):
    """硬边界：名录「没说话」（无此码 / 类型未知）时保持原值，绝不写成 False。"""
    _seed_fund(market_db, '100025', '富国天时货币A', None)  # 有记录但 fund_type_id 为空
    db = tmp_path / 'invest.db'
    _make_db(
        db,
        [
            (1, '100025', 'fund', 1, 1, 1),  # 类型未知 → 保持 1
            (2, '999999', 'fund', 1, 1, 1),  # 名录无此码 → 保持 1
        ],
    )
    engine = _engine_for(db)

    assert migrate_positions_money_fund_flag(engine).startswith('[SKIP]')
    assert _flags(engine) == {1: 1, 2: 1}


def test_market_unreachable_never_clears_existing_flags(tmp_path, monkeypatch):
    """market 域不可达：基金类一行都不许改（这是最容易写错成「清空」的分支）。"""
    from app.services import fund_utils

    def _boom(_codes):
        raise RuntimeError('market 域不可达')

    monkeypatch.setattr(fund_utils, '_lookup_market_type_names', _boom)

    db = tmp_path / 'invest.db'
    _make_db(
        db,
        [
            (1, '001010', 'fund', 1, 1, 1),  # 真货基标记，名录不可达 → 保持
        ],
    )
    engine = _engine_for(db)

    assert migrate_positions_money_fund_flag(engine).startswith('[SKIP]')
    assert _flags(engine) == {1: 1}


def test_explicit_money_fund_type_always_true(tmp_path):
    """显式 `type='money_fund'` 不查名录也必须为 True（旧库名录可能尚未初始化）。"""
    db = tmp_path / 'invest.db'
    _make_db(db, [(1, 'SH970164', 'money_fund', 1, 1, 0)])
    engine = _engine_for(db)

    migrate_positions_money_fund_flag(engine)
    assert _flags(engine) == {1: 1}


def test_skips_when_table_or_column_missing(tmp_path):
    """空库（表不存在）/ 缺 is_money_fund 列 → SKIP，不抛错、不阻断启动。"""
    empty = tmp_path / 'empty.db'
    assert migrate_positions_money_fund_flag(_engine_for(empty)).startswith('[SKIP]')

    db = tmp_path / 'no_col.db'
    conn = sqlite3.connect(str(db))
    conn.executescript('CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol VARCHAR(30), type VARCHAR(20));')
    conn.commit()
    conn.close()
    assert migrate_positions_money_fund_flag(_engine_for(db)).startswith('[SKIP]')


def test_skips_on_non_sqlite_engine():
    """非 SQLite 引擎（postgres）→ SKIP，不抛错、不阻断启动。

    构造 postgres engine 需要 psycopg2 驱动，而 pyproject 对
    psycopg2-binary 设了 `sys_platform != "win32"` 平台标记（#1434/#1514：
    Windows 本机只用 SQLite 不装）——平台标记与测试互相矛盾，全新
    Windows venv 必挂 ModuleNotFoundError（#1701）。主仓旧 venv 恰好
    装过 psycopg2 才侥幸通过，掩盖了矛盾。故缺驱动时跳过；Linux CI
    （标记允许安装）照常真跑。
    """
    pytest.importorskip('psycopg2')
    assert migrate_positions_money_fund_flag(create_engine('postgresql://u:p@h/db')).startswith('[SKIP]')
