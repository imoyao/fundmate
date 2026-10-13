# -*- coding: utf-8 -*-
"""#2120 P1 回归测试：分层清理脚本的护栏。

真删 800 万行不可逆，故每条护栏都要有用例兜住：
1. 热集一行不删（误删会让持仓基金 5 年历史消失）；
2. floor 下限保护（否则残缺冷集被整只清空）；
3. --apply 必须配快照（没快照就没有回滚手段）；
4. 幂等（重跑一次 affected=0）；
5. dry-run 真不写库。
"""

import json
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'clean_daily_worth_retention.py'
CUTOFF = (date.today() - timedelta(days=365)).isoformat()


def _make_db(tmp_path, rows, hot_codes=('000002',)):
    """建一个最小库：daily_worth + 三张热集来源表。"""
    db = tmp_path / 't.db'
    conn = sqlite3.connect(db)
    conn.executescript(
        'CREATE TABLE daily_worth (fund_code TEXT, date TEXT, unit_nav REAL);'
        'CREATE TABLE positions (symbol TEXT);'
        'CREATE TABLE watchlist_items (symbol TEXT);'
        'CREATE TABLE transactions (symbol TEXT);'
    )
    conn.executemany('INSERT INTO daily_worth VALUES (?,?,?)', rows)
    for t in ('positions', 'watchlist_items', 'transactions'):
        conn.executemany('INSERT INTO %s VALUES (?)' % t, [(c,) for c in hot_codes])
    conn.commit()
    conn.close()
    return db


def _make_snapshot(tmp_path, name='snap.db', tables=('daily_worth', 'money_fund_daily_worth')):
    """造一份能通过 `validate_snapshot` 的最小快照。

    dry-run 会回滚，所以**无法断言删除后的数据**——要测真实删除结果必须走 `--apply`，
    而 `--apply` 强制要求快照。这份 fixture 顺带把快照护栏的正向路径也测了。
    """
    path = tmp_path / name
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE snapshot_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    meta = {
        'format_version': '1',
        'created_at': '2026-10-13 00:00:00',
        'source': 'test.db',
        'tables': json.dumps(sorted(tables)),
        'counts': json.dumps({t: 1 for t in tables}),
        'missing_tables': '[]',
    }
    conn.executemany('INSERT INTO snapshot_meta VALUES (?,?)', list(meta.items()))
    for t in tables:
        conn.execute('CREATE TABLE "%s" (fund_code TEXT, date TEXT)' % t)
        conn.execute('INSERT INTO "%s" VALUES (?,?)' % t, ('000000', '2026-01-01'))
    conn.commit()
    conn.close()
    return path


def _run(db, *args):
    return subprocess.run([sys.executable, str(SCRIPT), '--db', str(db), *args], capture_output=True, text=True)


def _rows(db):
    conn = sqlite3.connect(db)
    out = conn.execute('SELECT fund_code, date FROM daily_worth ORDER BY fund_code, date').fetchall()
    conn.close()
    return out


@pytest.fixture
def seeded(tmp_path):
    """000002=热集、000001=冷集各 400 天；000003 只剩 2 行且都在 cutoff 之前。"""
    start = date.today() - timedelta(days=400)
    rows = []
    for code in ('000001', '000002'):
        for i in range(400):
            rows.append((code, (start + timedelta(days=i)).isoformat(), 1.0 + i * 0.001))
    rows.append(('000003', '2016-01-04', 1.0))
    rows.append(('000003', '2016-01-05', 1.0))
    return _make_db(tmp_path, rows)


class TestHotSetProtection:
    def test_hot_fund_keeps_all_rows(self, seeded):
        """热集 000002 的 400 行必须一行不少（它有 34 行早于 cutoff）。"""
        assert _run(seeded).returncode == 0
        assert len([r for r in _rows(seeded) if r[0] == '000002']) == 400

    def test_cold_fund_is_trimmed(self, seeded, tmp_path):
        """冷集 000001 只留近 1 年窗口内的行（400 天里 cutoff 之后 365 天）。

        走 `--apply` 才能断言删除后的状态——dry-run 会回滚。
        """
        snap = _make_snapshot(tmp_path)
        assert _run(seeded, '--table', 'daily_worth', '--snapshot', str(snap), '--apply').returncode == 0
        rows = [r for r in _rows(seeded) if r[0] == '000001']
        assert len(rows) == 365
        assert all(d >= CUTOFF for _c, d in rows)

    def test_hot_fund_survives_apply(self, seeded, tmp_path):
        """真删后热集 400 行仍一行不少（这是本脚本最要紧的不变量）。"""
        snap = _make_snapshot(tmp_path)
        assert _run(seeded, '--table', 'daily_worth', '--snapshot', str(snap), '--apply').returncode == 0
        assert len([r for r in _rows(seeded) if r[0] == '000002']) == 400


class TestFloorProtection:
    def test_residual_cold_fund_not_wiped(self, seeded, tmp_path):
        """000003 只剩 2 行且都在 cutoff 之前——无 floor 保护就会被整只清空。"""
        snap = _make_snapshot(tmp_path)
        assert _run(seeded, '--table', 'daily_worth', '--snapshot', str(snap), '--apply').returncode == 0
        assert len([r for r in _rows(seeded) if r[0] == '000003']) == 2

    def test_floor_zero_rejected(self, seeded):
        """`--floor 0` 必须被拒：§5.4 禁止整只清空，且断言 3 也会拦下。

        刻意不提供「关掉保护」的开关——那会让人以为保护可关，实际只是让断言失败、
        整轮回滚，是个比没有更糟的选项。
        """
        r = _run(seeded, '--floor', '0')
        assert r.returncode != 0
        assert '--floor' in (r.stdout + r.stderr)
        assert len(_rows(seeded)) == 802

    def test_floor_three_keeps_three_rows(self, tmp_path):
        """残缺基金有 5 行时，`--floor 3` 应保住最近 3 行（证明 floor 真的按量生效）。"""
        start = date.today() - timedelta(days=400)
        rows = [(f'00000{i}', (start + timedelta(days=j)).isoformat(), 1.0) for i in (1, 2) for j in range(400)]
        rows += [('000003', d, 1.0) for d in ('2016-01-04', '2016-01-05', '2016-01-06', '2016-01-07', '2016-01-08')]
        db = _make_db(tmp_path, rows)
        snap = _make_snapshot(tmp_path)
        r = _run(db, '--table', 'daily_worth', '--floor', '3', '--snapshot', str(snap), '--apply')
        assert r.returncode == 0, r.stdout + r.stderr
        kept = [r for r in _rows(db) if r[0] == '000003']
        assert len(kept) == 3
        assert kept[-1][1] == '2016-01-08', '应保留最近的 3 行'


class TestSnapshotGuard:
    def test_apply_without_snapshot_rejected(self, seeded):
        """--apply 必须同时给 --snapshot（§8.1 硬要求）。"""
        r = _run(seeded, '--apply')
        assert r.returncode != 0
        assert '--snapshot' in (r.stdout + r.stderr)
        assert len(_rows(seeded)) == 802, '被拒绝时不该动任何数据'

    def test_apply_with_missing_snapshot_rejected(self, seeded):
        r = _run(seeded, '--apply', '--snapshot', str(seeded.parent / 'nope.db'))
        assert r.returncode != 0
        assert len(_rows(seeded)) == 802


class TestDryRunAndIdempotency:
    def test_dry_run_does_not_write(self, seeded):
        before = _rows(seeded)
        assert _run(seeded).returncode == 0
        assert _rows(seeded) == before

    def test_apply_is_idempotent(self, seeded, tmp_path):
        """真删两次：第二次 affected 应为 0（行数不再变、退出码仍为 0）。"""
        snap = _make_snapshot(tmp_path)
        args = ('--table', 'daily_worth', '--snapshot', str(snap), '--apply')
        assert _run(seeded, *args).returncode == 0
        after_first = _rows(seeded)
        second = _run(seeded, *args)
        assert second.returncode == 0, second.stdout + second.stderr
        assert '实际删除 0 行' in second.stdout
        assert _rows(seeded) == after_first

    def test_unknown_table_rejected(self, seeded):
        r = _run(seeded, '--table', 'daily_worths')
        assert r.returncode != 0
        assert 'daily_worths' in (r.stdout + r.stderr)
