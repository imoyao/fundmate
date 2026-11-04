# -*- coding: utf-8 -*-
"""#2534 回归：启动期迁移的 **PG 分支**（本地无 PG 可连，钉「不早退 + SQL 形态」）。

## 背景

迁移曾普遍「非 SQLite 就跳过」，对应测试用「只有一个 url 的假引擎」断言返回
SKIP——那是在钉 bug 本身（#2469 / #2532 两次生产停摆的根因）。#2534 把 18 个
机械可转的迁移改为全引擎后，本文件钉新契约：

1. **每个转换过的迁移，PG 分支不再早退**（返回 `[OK]` 或真实执行结果）；
2. **加列迁移的 PG DDL 是 `ADD COLUMN IF NOT EXISTS` 精确文本**——语法错要等
   生产才发现，故在本地钉死（假引擎见 `migrations_pg_fake.PgFake`）；
3. **数据回填类迁移在 PG 上真实发起标准 SQL**（SELECT/UPDATE），不只返回跳过；
4. **索引类迁移在 PG 上建 `IF NOT EXISTS` 索引**且幂等；
5. **单一通道 helper 的自校验**：DDL 没生效必须抛错，不留半截状态。

剩余 4 个未转函数（整表重建 / SQLite 专属 SQL）不在本文件范围，其「仍允许
早退」由 `scripts/guard_migrations_pg_aware.py` 的指纹基线管。
"""

import pytest

from app.core.migrations import (
    _add_columns_if_missing,
    _ensure_index,
    _index_exists,
    migrate_account_name_snapshot,
    migrate_advisor_portfolio_metadata,
    migrate_advisor_portfolio_metrics,
    migrate_advisor_portfolio_provenance,
    migrate_asset_major_category_current_to_cash,
    migrate_channel_link_indexes,
    migrate_conversion_in_leg_snapshot,
    migrate_fee_unique_indexes,
    migrate_fund_equity_position_period,
    migrate_fund_managers_split_tenures,
    migrate_fund_rating_columns,
    migrate_fund_risk_metrics_period_returns,
    migrate_fund_style_columns,
    migrate_fund_valuation_official_columns,
    migrate_positions_cleared_at,
    migrate_positions_money_fund_flag,
    migrate_positions_price_columns,
    migrate_positions_snapshot_anchor,
    migrate_watchlist_family_scoped_unique_key,
    migrate_watchlist_name_snapshot,
    migrate_watchlist_unique_key,
    migrate_watchlist_venue_not_null,
)

from .migrations_pg_fake import PgFake

#: (迁移函数, 表, {列名: DDL}) —— PG 上应各发一条 ADD COLUMN IF NOT EXISTS。
_ADD_COLUMN_CASES = [
    (
        migrate_watchlist_name_snapshot,
        'watchlist',
        {'name': 'VARCHAR(100)'},
    ),
    (
        migrate_advisor_portfolio_metrics,
        'advisor_portfolios',
        {
            'return_1w': 'NUMERIC(7,2)',
            'return_1m': 'NUMERIC(7,2)',
            'return_1y': 'NUMERIC(7,2)',
            'return_ytd': 'NUMERIC(7,2)',
            'return_since_incep': 'NUMERIC(7,2)',
            'benchmark': 'VARCHAR(50)',
            'max_drawdown': 'NUMERIC(6,2)',
            'excess_return': 'NUMERIC(7,2)',
        },
    ),
    (
        migrate_advisor_portfolio_metadata,
        'advisor_portfolios',
        {
            'volatility': 'NUMERIC(6,2)',
            'sharpe_ratio': 'NUMERIC(6,3)',
            'allocation': 'VARCHAR(20)',
            'product_type': 'VARCHAR(20)',
            'strategy_summary': 'VARCHAR(300)',
            'source_url': 'VARCHAR(120)',
            'nav': 'NUMERIC(12,6)',
            'nav_date': 'DATE',
            'return_1d': 'NUMERIC(7,2)',
            'return_1q': 'NUMERIC(7,2)',
            'return_6m': 'NUMERIC(7,2)',
        },
    ),
    (
        migrate_advisor_portfolio_provenance,
        'advisor_portfolios',
        {'source': 'VARCHAR(20)', 'extra': 'JSON'},
    ),
    (
        migrate_positions_price_columns,
        'positions',
        {'prev_close': 'INTEGER', 'price_date': 'DATE'},
    ),
    (
        migrate_fund_valuation_official_columns,
        'fund_valuation_daily',
        {'official_nav': 'NUMERIC(18, 6)', 'deviation': 'NUMERIC(18, 6)', 'deviation_pct': 'NUMERIC(10, 4)'},
    ),
    (
        migrate_fund_risk_metrics_period_returns,
        'fund_risk_metrics',
        {'ret_1m': 'NUMERIC(10, 4)', 'ret_3m': 'NUMERIC(10, 4)', 'ret_1y': 'NUMERIC(10, 4)'},
    ),
    (
        migrate_positions_snapshot_anchor,
        'positions',
        {
            'snapshot_quantity': 'INTEGER',
            'snapshot_avg_price': 'INTEGER',
            'snapshot_date': 'DATE',
            'anchor_kind': 'VARCHAR(20)',
        },
    ),
    (
        migrate_positions_cleared_at,
        'positions',
        {'cleared_at': 'DATETIME'},
    ),
    (
        migrate_fund_equity_position_period,
        'funds',
        {'equity_position_period': 'VARCHAR(8)'},
    ),
    (
        migrate_fund_style_columns,
        'funds',
        {'dominant_style': 'VARCHAR(20)', 'style_period': 'VARCHAR(10)'},
    ),
    (
        migrate_fund_rating_columns,
        'funds',
        {
            'morningstar_rating': 'SMALLINT',
            'morningstar_rating_delta': 'SMALLINT',
            'morningstar_rating_asof': 'DATE',
        },
    ),
]


@pytest.mark.parametrize(
    ('migrate', 'table', 'columns'),
    _ADD_COLUMN_CASES,
    ids=[c[0].__name__ for c in _ADD_COLUMN_CASES],
)
def test_pg_branch_adds_columns_with_if_not_exists(monkeypatch, migrate, table, columns):
    """PG 不再早退：每个缺失列各发一条 `ADD COLUMN IF NOT EXISTS`（精确文本）。"""
    fake = PgFake({table: ['id']})
    fake.install(monkeypatch)

    result = migrate(fake.engine)

    assert result.startswith('[OK]'), f'PG 分支不许再返回跳过：{result}'
    assert '非 SQLite' not in result
    assert set(columns) <= set(fake.columns[table])
    for name, ddl in columns.items():
        expected = f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl}'
        assert expected in fake.sql, f'{name} 的 DDL 形态不对：{fake.sql}'

    # 幂等：第二次跑不发任何 DDL
    fake.sql.clear()
    second = migrate(fake.engine)
    assert second.startswith('[SKIP]'), second
    assert fake.sql == [], f'列已齐时不该发 DDL：{fake.sql}'


@pytest.mark.parametrize(
    ('migrate', 'table', 'columns'),
    _ADD_COLUMN_CASES,
    ids=[c[0].__name__ for c in _ADD_COLUMN_CASES],
)
def test_pg_branch_missing_table_skips(monkeypatch, migrate, table, columns):
    """PG 上表不存在（空库）：安全 skip，不抛错阻断启动。"""
    fake = PgFake({})
    fake.install(monkeypatch)

    assert migrate(fake.engine).startswith('[SKIP]')


def test_helper_raises_when_ddl_silently_ignored(monkeypatch):
    """单一通道自校验：DDL 没生效（假引擎不 apply）必须抛错，不返回「看起来 OK」。"""
    fake = PgFake({'t': ['id']}, apply_ddl=False)
    fake.install(monkeypatch)

    with pytest.raises(RuntimeError, match='仍缺列'):
        _add_columns_if_missing(fake.engine, 't', [('c', 'INTEGER')])


def test_helper_no_ddl_when_columns_present(monkeypatch):
    """helper 幂等：列已齐 → 不发 DDL、返回空 list。"""
    fake = PgFake({'t': ['id', 'c']})
    fake.install(monkeypatch)

    assert _add_columns_if_missing(fake.engine, 't', [('c', 'INTEGER')]) == []
    assert fake.sql == []


# ── 数据回填类：PG 上真实发起标准 SQL（不再早退） ──────────────────────────


def test_pg_venue_backfill_runs_on_pg(monkeypatch):
    """venue NULL 回填：PG 上发起 UPDATE（无行时安全 SKIP）。"""
    fake = PgFake({'watchlist': ['id', 'symbol', 'market', 'venue']})
    fake.install(monkeypatch)

    result = migrate_watchlist_venue_not_null(fake.engine)

    assert '非 SQLite' not in result
    assert result.startswith('[SKIP]')  # 无 NULL 行
    assert any("UPDATE watchlist SET venue = ''" in s for s in fake.sql), fake.sql


def test_pg_money_fund_flag_runs_on_pg(monkeypatch):
    """货基标记重算：PG 上发起 SELECT（无持仓行时安全 SKIP）。"""
    fake = PgFake({'positions': ['id', 'symbol', 'type', 'is_money_fund']})
    fake.install(monkeypatch)

    result = migrate_positions_money_fund_flag(fake.engine)

    assert '非 SQLite' not in result
    assert result.startswith('[SKIP]')
    assert any('FROM positions' in s for s in fake.sql), fake.sql


def test_pg_account_name_snapshot_runs_on_pg(monkeypatch):
    """账户名快照回填：PG 上对两表各发一条标准 UPDATE。"""
    fake = PgFake({'positions': ['id'], 'transactions': ['id'], 'ledgers': ['id', 'name']})
    fake.install(monkeypatch)

    result = migrate_account_name_snapshot(fake.engine)

    assert '非 SQLite' not in result
    updates = [s for s in fake.sql if s.startswith('UPDATE')]
    assert len(updates) == 2, f'应对 positions/transactions 各发一条 UPDATE：{fake.sql}'


def test_pg_conversion_in_leg_snapshot_runs_on_pg(monkeypatch):
    """转入腿快照收编：PG 上发起 SELECT（无待收编行时返回 OK）。"""
    fake = PgFake({'positions': ['id', 'symbol', 'type', 'name', 'market']})
    fake.install(monkeypatch)

    result = migrate_conversion_in_leg_snapshot(fake.engine)

    assert '非 SQLite' not in result
    assert any('FROM positions' in s for s in fake.sql), fake.sql


def test_pg_asset_major_category_normalization_runs_on_pg(monkeypatch):
    """major_category 归一：PG 上发起标准 UPDATE。"""
    fake = PgFake({'assets': ['id', 'major_category']})
    fake.install(monkeypatch)

    result = migrate_asset_major_category_current_to_cash(fake.engine)

    assert '非 SQLite' not in result
    assert any("UPDATE assets SET major_category='cash'" in s for s in fake.sql), fake.sql


# ── 索引类：PG 上建 IF NOT EXISTS 索引且幂等 ──────────────────────────────


def test_pg_channel_link_index_created_and_idempotent(monkeypatch):
    """channel_links.to_symbol 索引：PG 上建成；第二次不发 DDL。"""
    fake = PgFake({'channel_links': ['id', 'to_symbol']})
    fake.install(monkeypatch)

    assert migrate_channel_link_indexes(fake.engine).startswith('[OK]')
    assert 'ix_channel_links_to_symbol' in fake.indexes['channel_links']
    assert 'CREATE INDEX IF NOT EXISTS ix_channel_links_to_symbol' in fake.sql[0]

    fake.sql.clear()
    assert migrate_channel_link_indexes(fake.engine).startswith('[OK]')
    assert fake.sql == [], '索引已存在时不该再发 DDL'


def test_pg_fee_unique_indexes_created(monkeypatch):
    """费率三表表达式唯一索引：PG 上三条 `CREATE UNIQUE INDEX IF NOT EXISTS` 全建成。"""
    fake = PgFake({'fee_ratios': ['id'], 'redeem_rules': ['id'], 'purchase_rules': ['id']})
    fake.install(monkeypatch)

    result = migrate_fee_unique_indexes(fake.engine)

    assert result.startswith('[OK]')
    for name, table in (
        ('uq_fee_ratios_scope', 'fee_ratios'),
        ('uq_redeem_rules_range', 'redeem_rules'),
        ('uq_purchase_rules_quota', 'purchase_rules'),
    ):
        assert name in fake.indexes.get(table, []), f'{name} 未建成：{fake.indexes}'
        assert f'CREATE UNIQUE INDEX IF NOT EXISTS {name}' in ' '.join(fake.sql)


def test_ensure_index_raises_when_ddl_silently_ignored(monkeypatch):
    """索引自校验：DDL 没生效必须抛错。"""
    fake = PgFake({'t': ['id']}, apply_ddl=False)
    fake.install(monkeypatch)

    with pytest.raises(RuntimeError, match='校验失败'):
        _ensure_index(fake.engine, 'ix_t_c', 'CREATE INDEX IF NOT EXISTS ix_t_c ON t (c)', table='t')


def test_index_exists_uses_reflection_on_pg(monkeypatch):
    """PG 侧索引判存在走反射（get_indexes），不查 sqlite_master。"""
    fake = PgFake({'t': ['id']})
    fake.install(monkeypatch)

    assert _index_exists(fake.engine, 't', 'ix_t_c') is False
    fake.indexes.setdefault('t', []).append('ix_t_c')
    assert _index_exists(fake.engine, 't', 'ix_t_c') is True


# ── 约束类（#2689）：PG 不重建，直接建同名唯一索引且幂等 ─────────────────


def test_pg_watchlist_intermediate_unique_key_skipped_without_ddl(monkeypatch):
    """中间形态 `(symbol, market, venue)`：PG 上不建，且不误发 SQLite 专属 SQL。

    钉的是「跳过有理由、有人接盘」——终态由下一个迁移直接建，不是旧契约那种
    「谁也不管」的早退。
    """
    fake = PgFake({'watchlist': ['id', 'symbol', 'market', 'venue', 'family_id']})
    fake.install(monkeypatch)

    result = migrate_watchlist_unique_key(fake.engine)

    assert result.startswith('[SKIP]'), result
    assert '非 SQLite' not in result
    assert 'family' in result, f'跳过必须说明谁负责建终态：{result}'
    assert fake.sql == [], f'PG 上不该发任何 DDL / 不该查 sqlite_master：{fake.sql}'


def test_pg_watchlist_family_unique_key_created_and_idempotent(monkeypatch):
    """终态唯一键：PG 上建成同名唯一索引；第二次跑不再发 DDL。"""
    fake = PgFake({'watchlist': ['id', 'symbol', 'market', 'venue', 'family_id']})
    fake.install(monkeypatch)

    result = migrate_watchlist_family_scoped_unique_key(fake.engine)

    assert result.startswith('[OK]'), result
    assert '非 SQLite' not in result
    assert 'uk_watchlist_family_symbol_market_venue' in fake.indexes['watchlist']
    assert (
        'CREATE UNIQUE INDEX IF NOT EXISTS uk_watchlist_family_symbol_market_venue '
        'ON watchlist (family_id, symbol, market, venue)' in fake.sql
    ), fake.sql

    fake.sql.clear()
    assert migrate_watchlist_family_scoped_unique_key(fake.engine).startswith('[SKIP]')
    assert not any('CREATE' in s for s in fake.sql), f'索引已存在时不该再发 DDL：{fake.sql}'


def test_pg_watchlist_family_unique_key_blocks_on_duplicates(monkeypatch):
    """存量有「同家庭同标的」重复行时：显式抛错 + 修复口径，而不是让 CREATE INDEX 炸一句空话。

    注：`PgFake` 对每条 SELECT 都返回同一份 `rows`，故它同时充当 COUNT 与分组查询的结果；
    这里只有 `rows[0][0]`（family_id）与分组明细被真实读取，够钉判定逻辑。
    """
    fake = PgFake(
        {'watchlist': ['id', 'symbol', 'market', 'venue', 'family_id']},
        rows=[(1, '600519', 'CN_A', 'EXCHANGE', 2)],
    )
    fake.install(monkeypatch)

    with pytest.raises(RuntimeError) as exc:
        migrate_watchlist_family_scoped_unique_key(fake.engine)

    msg = str(exc.value)
    assert "'600519'" in msg and 'CN_A' in msg and '共 2 行' in msg
    assert 'MIN(id)' in msg
    # 抛错时不得留下半成品索引
    assert 'uk_watchlist_family_symbol_market_venue' not in fake.indexes.get('watchlist', [])


def test_pg_watchlist_unique_keys_missing_table_skips(monkeypatch):
    """空库（表还没建）：两条迁移都安全 skip，不抛错阻断启动。"""
    fake = PgFake({})
    fake.install(monkeypatch)

    assert migrate_watchlist_unique_key(fake.engine).startswith('[SKIP]')
    assert migrate_watchlist_family_scoped_unique_key(fake.engine).startswith('[SKIP]')


# ── 表重建类（#2689）：PG 原地拆表，不整表重建 ───────────────────────────

#: 拆分前的 fund_managers 列（含两个待搬走的任期列）
_MANAGERS_LEGACY_COLS = ['id', 'fund_id', 'mgr_id', 'is_classic', 'start_date', 'end_date']


def test_pg_fund_managers_split_moves_tenures_and_drops_columns(monkeypatch):
    """PG 上不重建：搬任期（`ON CONFLICT`）→ `DELETE ... USING` 去重 → 删列 → 建唯一索引。"""
    fake = PgFake(
        {
            'fund_managers': list(_MANAGERS_LEGACY_COLS),
            'manager_tenures': ['id', 'fund_id', 'mgr_id', 'start_date', 'end_date'],
        },
        rows=[
            # 同一 (fund_id, mgr_id) 两行：去重应保留 is_classic=True 的那行（id=2）
            {
                'id': 1,
                'fund_id': 10,
                'mgr_id': 100,
                'is_classic': False,
                'start_date': '2020-01-01',
                'end_date': None,
            },
            {
                'id': 2,
                'fund_id': 10,
                'mgr_id': 100,
                'is_classic': True,
                'start_date': '2020-01-01',
                'end_date': '2021-01-01',
            },
        ],
    )
    fake.install(monkeypatch)

    result = migrate_fund_managers_split_tenures(fake.engine)

    assert result.startswith('[OK]'), result
    assert '非 SQLite' not in result
    assert '去重 2 → 1 行' in result, f'去重口径应优先 is_classic=True：{result}'

    # 任期列真的删掉了、唯一索引真的建了
    assert set(fake.columns['fund_managers']) == {'id', 'fund_id', 'mgr_id', 'is_classic'}
    assert 'uq_fund_managers_fund_mgr' in fake.indexes['fund_managers']

    joined = '\n'.join(fake.sql)
    assert 'ON CONFLICT (fund_id, mgr_id, start_date) DO NOTHING' in joined, joined
    assert 'DELETE FROM fund_managers a USING fund_managers b' in joined, joined
    assert 'DROP COLUMN IF EXISTS start_date' in joined, joined
    assert 'DROP COLUMN IF EXISTS end_date' in joined, joined
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_fund_managers_fund_mgr ON fund_managers (fund_id, mgr_id)' in joined, (
        joined
    )
    # 不许出现 SQLite 整表重建的痕迹（那套在 PG 上既没必要也多一次 DROP 风险）
    assert 'PRAGMA' not in joined, joined
    assert 'RENAME TO' not in joined, joined


def test_pg_fund_managers_split_idempotent(monkeypatch):
    """已拆分完成（无任期列 + 唯一索引在）：直接 SKIP，不发任何 DDL。"""
    fake = PgFake(
        {
            'fund_managers': ['id', 'fund_id', 'mgr_id', 'is_classic'],
            'manager_tenures': ['id', 'fund_id', 'mgr_id', 'start_date'],
        }
    )
    fake.indexes['fund_managers'] = ['uq_fund_managers_fund_mgr']
    fake.install(monkeypatch)

    assert migrate_fund_managers_split_tenures(fake.engine).startswith('[SKIP]')
    assert not any('ALTER' in s or 'CREATE' in s or 'DELETE' in s for s in fake.sql), fake.sql


def test_pg_fund_managers_split_creates_missing_unique_index(monkeypatch):
    """半完成态（任期列已删、唯一索引没建）：PG 上补建索引并返回 OK。"""
    fake = PgFake(
        {
            'fund_managers': ['id', 'fund_id', 'mgr_id', 'is_classic'],
            'manager_tenures': ['id'],
        }
    )
    fake.install(monkeypatch)

    assert migrate_fund_managers_split_tenures(fake.engine).startswith('[OK]')
    assert 'uq_fund_managers_fund_mgr' in fake.indexes['fund_managers']


def test_pg_fund_managers_split_requires_manager_tenures(monkeypatch):
    """`manager_tenures` 不在（单独跑迁移 / 手修库）：显式抛错，不自建 PG 方言表。"""
    fake = PgFake({'fund_managers': list(_MANAGERS_LEGACY_COLS)})
    fake.install(monkeypatch)

    with pytest.raises(RuntimeError, match='manager_tenures 不存在'):
        migrate_fund_managers_split_tenures(fake.engine)


def test_no_bare_alter_table_in_converted_migrations():
    """转换过的迁移里不许再裸写 ALTER TABLE（单一通道纪律的静态面）。"""
    import inspect as py_inspect
    import re

    converted = [c[0] for c in _ADD_COLUMN_CASES]
    for fn in converted:
        src = py_inspect.getsource(fn)
        assert not re.search(r'conn\.execute\(text\([\'"]ALTER TABLE', src), f'{fn.__name__} 仍裸写 ALTER TABLE'
