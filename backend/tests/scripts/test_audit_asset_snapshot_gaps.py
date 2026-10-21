# -*- coding: utf-8 -*-
"""只读体检脚本 `audit_asset_snapshot_gaps` 的单测（#2132 后续）。

覆盖五类：
- 日期归一：sqlite 取出的 DATE 是**字符串**（无 `detect_types`），必须能转成 `date`；
- 连续性：缺日按自然日区间算，跨月不错位；
- 星期分布：缺日里周末与工作日分开算（这决定「真缺口」的判定）；
- 结论分类：几条关键结论必须能被数据触发（覆盖缺口 / 回填痕迹 / 停写 / 非调度产物）；
- 只读性：跑完 CLI 后库文件**逐字节不变**（体检绝不能改数据）。
"""

import os
import sqlite3
import subprocess
import sys
from datetime import date

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import audit_asset_snapshot_gaps as m  # noqa: E402

_ASSET_COLS = (
    'id, family_id, ledger_id, snapshot_date, total_assets, total_liabilities, net_worth,'
    ' realized_pnl_cents, unrealized_pnl_cents, total_pnl_cents, money_fund_income_cents,'
    ' created_at, updated_at'
)
_PNL_COLS = (
    'id, family_id, ledger_id, date, daily_pnl_cents, net_worth_cents, state, caliber_version, created_at, updated_at'
)


def _make_db(tmp_path, *, asset_rows=(), pnl_rows=(), sync_rows=()):
    """造一个最小库：三张表各自装入给定行。"""
    path = tmp_path / 't.db'
    conn = sqlite3.connect(path)
    conn.execute(f'CREATE TABLE asset_snapshots ({_ASSET_COLS})')
    conn.execute(f'CREATE TABLE pnl_daily_snapshots ({_PNL_COLS})')
    conn.execute(
        'CREATE TABLE sync_logs (id, job_name, status, full_sync, stats, error_detail,'
        ' data_source, data_source_version, started_at, finished_at, duration_seconds)'
    )
    for r in asset_rows:
        conn.execute(
            'INSERT INTO asset_snapshots (id, family_id, ledger_id, snapshot_date, total_assets,'
            ' total_liabilities, net_worth, realized_pnl_cents, unrealized_pnl_cents,'
            ' total_pnl_cents, money_fund_income_cents, created_at, updated_at)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            r,
        )
    for r in pnl_rows:
        conn.execute(
            'INSERT INTO pnl_daily_snapshots (id, family_id, ledger_id, date, daily_pnl_cents,'
            ' net_worth_cents, state, caliber_version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            r,
        )
    for r in sync_rows:
        conn.execute('INSERT INTO sync_logs (id, job_name, status, started_at) VALUES (?,?,?,?)', r)
    conn.commit()
    conn.close()
    return path


def _asset_row(rid, day, ledger_id=None, created=None, updated=None):
    ts = created or ('%s 21:30:00' % day)
    return (rid, 1, ledger_id, day, 100, 0, 100, 0, 0, 0, None, ts, updated or ts)


class TestDateHelpers:
    def test_as_date_accepts_string_and_date(self):
        assert m._as_date('2026-10-18') == date(2026, 10, 18)
        assert m._as_date(date(2026, 10, 18)) == date(2026, 10, 18)
        assert m._as_date('2026-10-18 08:00:00') == date(2026, 10, 18)
        assert m._as_date('') is None
        assert m._as_date(None) is None
        assert m._as_date('not-a-date') is None

    def test_month_span_groups_by_month(self):
        days = ['2026-09-30', '2026-10-01', '2026-10-02', '2026-10-02']
        assert m.month_span(days) == [('2026-09', 1), ('2026-10', 2)]

    def test_missing_days_spans_month_boundary(self):
        assert m.missing_days(['2026-09-30', '2026-10-02']) == ['2026-10-01']

    def test_missing_days_empty_when_contiguous(self):
        assert m.missing_days(['2026-10-01', '2026-10-02', '2026-10-03']) == []

    def test_missing_days_empty_input(self):
        assert m.missing_days([]) == []

    def test_weekday_breakdown_separates_weekend(self):
        # 2026-10-03 周六、2026-10-05 周一
        wk = m.weekday_breakdown(['2026-10-03', '2026-10-05'])
        assert wk['周六'] == 1
        assert wk['周一'] == 1
        assert wk['周二'] == 0

    def test_staleness_days(self):
        assert m.staleness('2026-10-18', date(2026, 10, 21)) == 3
        assert m.staleness(None) is None


class TestAudit:
    def test_counts_split_family_and_ledger(self, tmp_path):
        path = _make_db(
            tmp_path,
            asset_rows=[
                _asset_row(1, '2026-10-01'),
                _asset_row(2, '2026-10-01', ledger_id=3),
                _asset_row(3, '2026-10-02', ledger_id=3),
            ],
        )
        conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        out = m.audit_asset_snapshots(conn)
        conn.close()
        assert out['rows'] == 3
        assert out['family_rows'] == 1
        assert out['ledger_rows'] == 2
        assert out['distinct_dates'] == 2
        assert out['ledger_coverage'][0]['ledger_id'] == 3

    def test_backfill_suspect_detected_by_lag(self, tmp_path):
        path = _make_db(
            tmp_path,
            asset_rows=[
                _asset_row(1, '2026-10-01'),
                # 标签日 10-01、落库日 10-15 ⇒ 事后补写嫌疑
                _asset_row(2, '2026-10-01', created='2026-10-15 10:00:00', updated='2026-10-15 10:00:00'),
            ],
        )
        conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        out = m.audit_asset_snapshots(conn)
        conn.close()
        assert len(out['backfill_suspects']) == 1
        assert out['backfill_suspects'][0]['id'] == 2
        assert out['backfill_suspects'][0]['lag_days'] == 14

    def test_sync_logs_reports_asset_snapshot_absence(self, tmp_path):
        path = _make_db(tmp_path, sync_rows=[(1, 'fund_nav', 'success', '2026-10-20 21:30:00')])
        conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        out = m.audit_sync_logs(conn)
        conn.close()
        assert out['exists'] is True
        assert out['asset_snapshot_runs'] == 0
        assert out['jobs'] == 1

    def test_sync_logs_reports_asset_snapshot_runs(self, tmp_path):
        path = _make_db(tmp_path, sync_rows=[(1, 'asset_snapshot', 'success', '2026-10-20 23:00:00')])
        conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        out = m.audit_sync_logs(conn)
        conn.close()
        assert out['asset_snapshot_runs'] == 1
        assert out['asset_snapshot_last'] == '2026-10-20 23:00:00'


class TestClassify:
    def test_verdict_flags_non_scheduled_provenance(self):
        a = {
            'exists': True,
            'rows': 3,
            'distinct_dates': 2,
            'date_min': '2026-10-01',
            'date_max': '2026-10-03',
            'missing_days': ['2026-10-02'],
            'backfill_suspects': [],
            'sync_logs': {
                'exists': True,
                'rows': 5,
                'jobs': 2,
                'asset_snapshot_runs': 0,
                'asset_snapshot_last': None,
                'range': ('a', 'b'),
            },
        }
        p = {
            'exists': True,
            'rows': 0,
            'distinct_dates': 0,
            'date_min': None,
            'date_max': None,
            'missing_days': [],
        }
        v = m.classify(a, p)
        assert any('没有 asset_snapshot 的任何运行记录' in x for x in v)
        assert any('日期不连续' in x for x in v)

    def test_verdict_flags_more_days_in_landing_chain(self):
        a = {
            'exists': True,
            'rows': 10,
            'distinct_dates': 9,
            'date_min': '2026-10-01',
            'date_max': '2026-10-09',
            'missing_days': [],
            'backfill_suspects': [],
            'sync_logs': {
                'exists': True,
                'rows': 1,
                'jobs': 1,
                'asset_snapshot_runs': 3,
                'asset_snapshot_last': '2026-10-09 23:00:00',
                'range': ('a', 'b'),
            },
        }
        p = {
            'exists': True,
            'rows': 4,
            'distinct_dates': 3,
            'date_min': '2026-10-01',
            'date_max': '2026-10-03',
            'missing_days': [],
        }
        v = m.classify(a, p)
        assert any('多于' in x for x in v)

    def test_verdict_flags_backfill_suspects(self):
        a = {
            'exists': True,
            'rows': 3,
            'distinct_dates': 2,
            'date_min': '2026-10-01',
            'date_max': '2026-10-02',
            'missing_days': [],
            'backfill_suspects': [{'id': 9, 'lag_days': 20}],
            'sync_logs': {'exists': False},
        }
        p = {'exists': False, 'rows': 0, 'distinct_dates': 0, 'date_min': None, 'date_max': None, 'missing_days': []}
        v = m.classify(a, p)
        assert any('疑似事后补写' in x for x in v)


class TestReadOnly:
    def test_cli_does_not_modify_db(self, tmp_path):
        path = _make_db(
            tmp_path,
            asset_rows=[_asset_row(1, '2026-10-01'), _asset_row(2, '2026-10-02', ledger_id=3)],
            pnl_rows=[(1, 1, None, '2026-10-01', 0, 100, 'ok', 'v1', '2026-10-01 23:00:00', '2026-10-01 23:00:00')],
            sync_rows=[(1, 'fund_nav', 'success', '2026-10-01 21:30:00')],
        )
        before = path.read_bytes()
        r = subprocess.run(
            [
                sys.executable,
                os.path.join(_SCRIPTS_DIR, 'audit_asset_snapshot_gaps.py'),
                '--db',
                str(path),
            ],
            capture_output=True,
            text=True,
            # 脚本输出是 UTF-8；Windows 默认按 GBK 解码会炸（stdout 变 None），
            # 故这里显式指定编码 + 给子进程喂 PYTHONIOENCODING。
            encoding='utf-8',
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )
        assert r.returncode == 0, r.stderr
        assert path.read_bytes() == before, '体检脚本改了数据库！'
        assert '[只读]' in r.stdout
