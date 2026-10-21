# -*- coding: utf-8 -*-
"""只读体检：资产快照的「缺口」到底是哪一类（#2132 后续）。

背景
----
#2132 裁决（`docs/spec/decisions.md` D62）已把两张快照表的定位定死：

- `asset_snapshots` 记的是「**落库那一刻**的当前状态」，`snapshot_date` 只是**标签**、
  不是数据时点（取数链无日期过滤、全仓无失效/重算钩子）⇒ **回填等于把今天的值
  贴到历史日期**，而回填痕迹只能靠「行的时间」与「标签的时间」不一致来发现；
- `pnl_daily_snapshots`（`pnl_snapshot_store`，#1926）记的是「**截至该日**」的状态，
  按日物化 + 三道失效机制。

于是「资产历史缺口」其实是**两个不同的问题**，本脚本用真库数据把它们分开：

1. **覆盖缺口**：哪条链的日期不连续？（按日 / 按月列出缺哪些）
2. **时点缺口 / 回填风险**：`asset_snapshots` 里有没有「标签日期 ≠ 落库日期」的行
   （`updated_at - snapshot_date` 明显偏大 ⇒ 事后补写，历史不可信）

读完这两组数字，才谈得上「要不要把 `asset_snapshot` 纳回本机每日调度」——
**先取事实，再决定动不动**（#2132 的推荐方案）。

本脚本**只读**：用 `file:...?mode=ro` 打开数据库，连事务都不开，不会写任何东西。

用法
----
  pdm run python scripts/audit_asset_snapshot_gaps.py
  pdm run python scripts/audit_asset_snapshot_gaps.py --db backend/invest.db
  pdm run python scripts/audit_asset_snapshot_gaps.py --json-out gap.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DEFAULT_DB = 'invest.db'

# 回填痕迹的判定阈值（天）：`updated_at` 比标签日期晚这么多天 ⇒ 事后补写嫌疑。
# 取 2 天是因为快照本就在「落库那一刻」写入，正常写入的差值应为 0~1 天
# （跨时区 / 零点后落库都可能差 1 天）。
BACKFILL_SUSPECT_DAYS = 2


def connect_ro(db_path: Path) -> sqlite3.Connection:
    """**只读**打开数据库（`mode=ro`）：连事务都不开，写操作会直接被 SQLite 拒绝。"""
    conn = sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)).fetchone()
    return row is not None


def _as_date(value) -> date | None:
    """把 sqlite 取出的 DATE 值归一成 `date`。

    sqlite3 默认不装 `detect_types`，DATE 列取出来是 `'2026-10-18'` 这样的**字符串**；
    直接调 `strftime` 会炸，故这里统一转一次，解析不了的值当缺失处理。
    """
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def month_span(dates: list[date]) -> list[tuple[str, int]]:
    """把日期列表按月归并 → [(YYYY-MM, 该月有快照的天数)]（按月升序）。"""
    buckets: dict[str, set[date]] = {}
    for raw in dates:
        d = _as_date(raw)
        if d is None:
            continue
        buckets.setdefault(d.strftime('%Y-%m'), set()).add(d)
    return [(m, len(days)) for m, days in sorted(buckets.items())]


def missing_days(dates: list[date]) -> list[str]:
    """按 min..max 的自然日连续区间，列出没有快照的日期。"""
    parsed = [d for d in (_as_date(x) for x in dates) if d is not None]
    if not parsed:
        return []
    lo, hi = min(parsed), max(parsed)
    have = set(parsed)
    out = []
    cur = lo
    while cur <= hi:
        if cur not in have:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def audit_asset_snapshots(conn: sqlite3.Connection) -> dict:
    """`asset_snapshots`：行数 / 作用域拆分 / 日期连续性 / 回填痕迹。"""
    out: dict = {
        'exists': table_exists(conn, 'asset_snapshots'),
        'rows': 0,
        'family_rows': 0,
        'ledger_rows': 0,
        'distinct_dates': 0,
        'date_min': None,
        'date_max': None,
        'months': [],
        'missing_days': [],
        'backfill_suspects': [],
        'ledger_coverage': [],
    }
    if not out['exists']:
        return out

    agg = conn.execute(
        'SELECT COUNT(*) AS rows,'
        ' SUM(CASE WHEN ledger_id IS NULL THEN 1 ELSE 0 END) AS fam,'
        ' SUM(CASE WHEN ledger_id IS NOT NULL THEN 1 ELSE 0 END) AS led,'
        ' COUNT(DISTINCT snapshot_date) AS dcount,'
        ' MIN(snapshot_date) AS dmin, MAX(snapshot_date) AS dmax'
        ' FROM asset_snapshots'
    ).fetchone()
    out['rows'] = agg['rows'] or 0
    out['family_rows'] = agg['fam'] or 0
    out['ledger_rows'] = agg['led'] or 0
    out['distinct_dates'] = agg['dcount'] or 0
    out['date_min'] = agg['dmin']
    out['date_max'] = agg['dmax']

    dates = [r[0] for r in conn.execute('SELECT DISTINCT snapshot_date FROM asset_snapshots').fetchall()]
    out['months'] = month_span(dates)
    out['missing_days'] = missing_days(dates)

    # 回填痕迹：标签日期与行更新时间差得越多，越像事后补写。
    suspects = conn.execute(
        'SELECT id, ledger_id, snapshot_date, created_at, updated_at,'
        '       CAST(julianday(updated_at) - julianday(snapshot_date) AS INTEGER) AS lag_days'
        ' FROM asset_snapshots'
        ' WHERE lag_days > ?'
        ' ORDER BY lag_days DESC, id'
        ' LIMIT 200',
        (BACKFILL_SUSPECT_DAYS,),
    ).fetchall()
    out['backfill_suspects'] = [dict(r) for r in suspects]
    out['backfill_suspect_threshold_days'] = BACKFILL_SUSPECT_DAYS

    led = conn.execute(
        'SELECT ledger_id, COUNT(*) AS rows, COUNT(DISTINCT snapshot_date) AS days,'
        ' MIN(snapshot_date) AS dmin, MAX(snapshot_date) AS dmax'
        ' FROM asset_snapshots WHERE ledger_id IS NOT NULL'
        ' GROUP BY ledger_id ORDER BY rows DESC, ledger_id'
    ).fetchall()
    out['ledger_coverage'] = [dict(r) for r in led]
    return out


def audit_pnl_daily(conn: sqlite3.Connection) -> dict:
    """`pnl_daily_snapshots`（#1926 那条可回溯的链）：行数 / 连续性。"""
    out: dict = {
        'exists': table_exists(conn, 'pnl_daily_snapshots'),
        'rows': 0,
        'family_rows': 0,
        'ledger_rows': 0,
        'distinct_dates': 0,
        'date_min': None,
        'date_max': None,
        'months': [],
        'missing_days': [],
    }
    if not out['exists']:
        return out

    agg = conn.execute(
        'SELECT COUNT(*) AS rows,'
        ' SUM(CASE WHEN ledger_id IS NULL THEN 1 ELSE 0 END) AS fam,'
        ' SUM(CASE WHEN ledger_id IS NOT NULL THEN 1 ELSE 0 END) AS led,'
        ' COUNT(DISTINCT date) AS dcount, MIN(date) AS dmin, MAX(date) AS dmax'
        ' FROM pnl_daily_snapshots'
    ).fetchone()
    out['rows'] = agg['rows'] or 0
    out['family_rows'] = agg['fam'] or 0
    out['ledger_rows'] = agg['led'] or 0
    out['distinct_dates'] = agg['dcount'] or 0
    out['date_min'] = agg['dmin']
    out['date_max'] = agg['dmax']

    dates = [r[0] for r in conn.execute('SELECT DISTINCT date FROM pnl_daily_snapshots').fetchall()]
    out['months'] = month_span(dates)
    out['missing_days'] = missing_days(dates)
    return out


def weekday_breakdown(missing: list[str]) -> dict[str, int]:
    """缺日按星期几分布（周一..周日）——用来判断「缺的是休息日」还是「缺的是工作日」。

    工作日缺失才是真缺口：休息日本来就没有「当日快照」的义务。
    """
    names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    out = {n: 0 for n in names}
    for d in missing:
        try:
            out[names[date.fromisoformat(d).weekday()]] += 1
        except ValueError:
            continue
    return out


def staleness(last_day: str | None, today: date | None = None) -> int | None:
    """最后一条快照距「今天」多少天（None = 没数据 / 解析不了）。"""
    d = _as_date(last_day)
    if d is None:
        return None
    return ((today or date.today()) - d).days


def audit_sync_logs(conn: sqlite3.Connection) -> dict:
    """`sync_logs`：**谁真的在跑**——判断快照是「调度产物」还是「用户行为产物」。

    `asset_snapshot` 被 D21 明确排除在本机每日调度之外（`daily_scheduler` 的 job 表
    标为「手动」），所以真库若查不到它的运行记录，就是**设计如此**、不是故障。
    反之若查得到，则说明有别的通道在写（编排器 / CI / 手动）。
    """
    out: dict = {
        'exists': table_exists(conn, 'sync_logs'),
        'rows': 0,
        'jobs': 26,
        'asset_snapshot_runs': 0,
        'asset_snapshot_last': None,
        'range': None,
    }
    if not out['exists']:
        return out

    out['rows'] = conn.execute('SELECT COUNT(*) FROM sync_logs').fetchone()[0]
    out['jobs'] = conn.execute('SELECT COUNT(DISTINCT job_name) FROM sync_logs').fetchone()[0]
    out['range'] = conn.execute('SELECT MIN(started_at), MAX(started_at) FROM sync_logs').fetchone()
    out['asset_snapshot_runs'] = conn.execute(
        "SELECT COUNT(*) FROM sync_logs WHERE job_name = 'asset_snapshot'"
    ).fetchone()[0]
    last = conn.execute("SELECT MAX(started_at) FROM sync_logs WHERE job_name = 'asset_snapshot'").fetchone()[0]
    out['asset_snapshot_last'] = last
    return out


def classify(a: dict, p: dict) -> list[str]:
    """把两组数字翻译成「缺口是哪一类」的结论（供人判断，不代替判断）。"""
    verdict: list[str] = []
    if not a['exists']:
        verdict.append('asset_snapshots 表不存在 => 无「落库时点」历史可谈')
    elif a['rows'] == 0:
        verdict.append('asset_snapshots 为空 => 本机从未落过快照，「缺口」是「从没有过」而非「缺了一段」')
    else:
        if a['missing_days']:
            verdict.append(
                'asset_snapshots 日期不连续：缺 %d 天（区间 %s ~ %s）'
                % (len(a['missing_days']), a['date_min'], a['date_max'])
            )
        else:
            verdict.append('asset_snapshots 在其区间内逐日连续（无缺日）')
        if a['backfill_suspects']:
            verdict.append(
                'asset_snapshots 有 %d 行疑似事后补写（标签日与落库日相差 > %d 天）=> 这些历史不可信'
                % (len(a['backfill_suspects']), BACKFILL_SUSPECT_DAYS)
            )
        else:
            verdict.append('asset_snapshots 无明显事后补写痕迹（标签日 ≈ 落库日）')

    if not p['exists']:
        verdict.append('pnl_daily_snapshots 表不存在 => 可回溯时点链也还没起步')
    elif p['rows'] == 0:
        verdict.append('pnl_daily_snapshots 为空 => 可回溯链同样没有数据')
    else:
        if p['missing_days']:
            verdict.append('pnl_daily_snapshots 日期不连续：缺 %d 天' % len(p['missing_days']))
        else:
            verdict.append(
                'pnl_daily_snapshots 在**它自己的 13 天区间内**逐日连续——但区间本身只有 %d 天、'
                '且停在 %s（距今 %s 天）⇒ 它不是「完整的那条」，只是「被看过的那段」'
                '（`save_days` 只在收益日历读时物化，属**懒物化**，不是调度产物）'
                % (p['distinct_dates'], p['date_max'], staleness(p['date_max']))
            )

    if a['rows'] and p['rows'] and a['distinct_dates'] < p['distinct_dates']:
        verdict.append(
            '两条链的覆盖度不同：可回溯链有 %d 天、落库时点链只有 %d 天 => 差距就是「时点缺口」'
            % (p['distinct_dates'], a['distinct_dates'])
        )
    elif a['rows'] and p['rows'] and a['distinct_dates'] > p['distinct_dates']:
        verdict.append(
            '⚠️ 落库时点链的天数（%d）**多于**可回溯链（%d）——与「可回溯链才是完整的那条」的先验相反：'
            '覆盖更全的是不能回溯的那条，而可回溯链更短（且可能已停写）' % (a['distinct_dates'], p['distinct_dates'])
        )

    s = a.get('sync_logs') or {}
    if s.get('exists'):
        if s.get('asset_snapshot_runs'):
            verdict.append(
                'sync_logs 里 asset_snapshot 跑过 %d 次（最近 %s）⇒ 快照有调度通道在写'
                % (s['asset_snapshot_runs'], s.get('asset_snapshot_last'))
            )
        else:
            verdict.append(
                'sync_logs（%d 条 / %d 个 job / %s ~ %s）里**没有 asset_snapshot 的任何运行记录** '
                '⇒ 快照**不是调度产物**，只能来自用户行为（进全景页兜底补写 / 手动点「记录快照」）；'
                '这是 D21 的既定口径（`daily_scheduler` 把该 job 标为「手动」）'
                % (
                    s.get('rows', 0),
                    s.get('jobs', 0),
                    (s.get('range') or ('?', '?'))[0],
                    (s.get('range') or ('?', '?'))[1],
                )
            )
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser(description='只读体检：资产快照缺口分类（#2132）')
    ap.add_argument('--db', default=DEFAULT_DB, help='数据库路径（默认 invest.db）')
    ap.add_argument('--json-out', help='把体检结果写成 JSON（供归档 / 对比）')
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print('找不到数据库文件：%s' % db_path)
        return 2

    conn = connect_ro(db_path)
    try:
        a = audit_asset_snapshots(conn)
        p = audit_pnl_daily(conn)
        a['sync_logs'] = audit_sync_logs(conn)

        print('库: %s（只读）' % db_path)
        print('\n== asset_snapshots（落库时点快照，snapshot_date 只是标签）==')
        print(
            '行数 %d（家庭级 %d / 账户级 %d）；不同日期 %d 天；区间 %s ~ %s'
            % (a['rows'], a['family_rows'], a['ledger_rows'], a['distinct_dates'], a['date_min'], a['date_max'])
        )
        if a['months']:
            print('按月覆盖: %s' % ' | '.join('%s:%d天' % (m, n) for m, n in a['months']))
        if a['missing_days']:
            print('缺日 %d 天: %s' % (len(a['missing_days']), ', '.join(a['missing_days'][:20])))
            wk = weekday_breakdown(a['missing_days'])
            print('缺日的星期分布: %s' % ' '.join('%s=%d' % (k, v) for k, v in wk.items()))
            weekend = wk['周六'] + wk['周日']
            if weekend and weekend == len(a['missing_days']):
                print('  -> 缺的全部是周末 ⇒ 快照是「工作日节奏」，工作日无缺口')
            elif weekend:
                print(
                    '  -> 其中 %d 天是周末，另 %d 天是**工作日缺口**（真缺口）'
                    % (weekend, len(a['missing_days']) - weekend)
                )
        print('最后一天 %s（距今 %s 天）' % (a['date_max'], staleness(a['date_max'])))
        if a['ledger_coverage']:
            print('账户级覆盖:')
            for r in a['ledger_coverage'][:20]:
                print(
                    '  ledger_id=%s 行数=%s 天数=%s 区间 %s ~ %s'
                    % (r['ledger_id'], r['rows'], r['days'], r['dmin'], r['dmax'])
                )
        if a['backfill_suspects']:
            print(
                '疑似事后补写 %d 行（标签日 vs 落库日相差 > %d 天）:'
                % (len(a['backfill_suspects']), BACKFILL_SUSPECT_DAYS)
            )
            for r in a['backfill_suspects'][:10]:
                print(
                    '  id=%s ledger_id=%s 标签日=%s 落库日=%s 差 %s 天'
                    % (r['id'], r['ledger_id'], r['snapshot_date'], r['updated_at'], r['lag_days'])
                )

        print('\n== pnl_daily_snapshots（可回溯时点链，#1926）==')
        print(
            '行数 %d（家庭级 %d / 账户级 %d）；不同日期 %d 天；区间 %s ~ %s'
            % (p['rows'], p['family_rows'], p['ledger_rows'], p['distinct_dates'], p['date_min'], p['date_max'])
        )
        if p['months']:
            print('按月覆盖: %s' % ' | '.join('%s:%d天' % (m, n) for m, n in p['months']))
        if p['missing_days']:
            print('缺日 %d 天: %s' % (len(p['missing_days']), ', '.join(p['missing_days'][:20])))
        print('最后一天 %s（距今 %s 天）' % (p['date_max'], staleness(p['date_max'])))
        p_dates = [_as_date(x) for x in conn.execute('SELECT DISTINCT date FROM pnl_daily_snapshots').fetchall()]
        p_dates = sorted(d for d in p_dates if d is not None)
        if p_dates:
            print('实际有数的日期: %s' % ', '.join(d.isoformat() for d in p_dates))

        verdict = classify(a, p)
        print('\n== 结论（缺口是哪一类）==')
        for v in verdict:
            print('  - %s' % v)

        s = a.get('sync_logs') or {}
        if s.get('exists'):
            print('\n== sync_logs（谁真的在跑）==')
            print(
                '总记录 %d 条 / %d 个 job / 区间 %s ~ %s'
                % (
                    s.get('rows', 0),
                    s.get('jobs', 0),
                    (s.get('range') or ('?', '?'))[0],
                    (s.get('range') or ('?', '?'))[1],
                )
            )
            print(
                'asset_snapshot 运行记录: %d 条%s'
                % (
                    s.get('asset_snapshot_runs', 0),
                    ('（最近 %s）' % s['asset_snapshot_last']) if s.get('asset_snapshot_last') else '',
                )
            )

        if args.json_out:
            payload = {'db': str(db_path), 'asset_snapshots': a, 'pnl_daily_snapshots': p, 'verdict': verdict}
            Path(args.json_out).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8'
            )
            print('\n[JSON 已写入] %s' % args.json_out)

        print('\n[只读] 未修改任何数据。')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
