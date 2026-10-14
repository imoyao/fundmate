# -*- coding: utf-8 -*-
"""分层保留清理的**只读预演**（#2120 P1 dry-run）。

不写任何数据（mode=ro），只回答：按「热集全留 / 冷集留 1 年」清理会删掉什么。
危险边界：某只冷集基金若全部净值点都早于 1 年前，按字面执行会**整只清空**——
§5.4 已点名 5 只这种基金并明确「属该补不该删」，故本脚本单列**危险清单**，
并给出「每只至少保留 N 个点」下限保护前后的对比。

用法：
  pdm run python scripts/preview_daily_worth_retention.py
  pdm run python scripts/preview_daily_worth_retention.py --keep-days 365 --floor 2 --top 30
"""

import argparse
import os
import sqlite3
import sys
from datetime import date, timedelta

DOC_FLAGGED = ('001046', '003443', '003451', '003572', '003868')
# 热集口径：持仓 ∪ 自选 ∪ 流水的 6 位纯数字代码。场内 ETF 也是 6 位，但 daily_worth
# 只在场外基金，代码即便重叠也会被保护——属保守方向，不构成风险。
HOT_PARTS = (
    "SELECT DISTINCT symbol FROM positions WHERE LENGTH(symbol)=6 AND symbol NOT GLOB '*[^0-9]*'",
    "SELECT DISTINCT symbol FROM watchlist WHERE LENGTH(symbol)=6 AND symbol NOT GLOB '*[^0-9]*'",
    "SELECT DISTINCT symbol FROM transactions WHERE LENGTH(symbol)=6 AND symbol NOT GLOB '*[^0-9]*'",
)
W = 84


def _has(conn, table):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def preview(conn, keep_days, floor, top):
    out = []
    today = date.today()
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    parts = [s for s in HOT_PARTS if _has(conn, s.split('FROM ')[1].split()[0])]
    # 缺表直接报错，不静默跳过——错表名会让热集少算，把「仅自选」的基金误判为冷集。
    # 2026-10-13 实测：`watchlist_items` 是错表名（真名 `watchlist`），静默跳过导致
    # 7 只仅自选的基金被误删 10,714 行，而 dry-run 与真删数字完全一致、断言全过，
    # **没有任何现有检查能发现它**。
    missing = [s.split('FROM ')[1].split()[0] for s in HOT_PARTS if not _has(conn, s.split('FROM ')[1].split()[0])]
    if missing:
        raise SystemExit('热集来源表缺失: %s（热集口径 = 持仓 ∪ 自选 ∪ 流水，少算任一来源都会误删）' % missing)
    hot_codes = {r[0] for r in conn.execute(' UNION '.join(parts)).fetchall()}

    def w(s=''):
        out.append(s)

    w('=' * W)
    w('分层保留清理 · 只读预演（#2120 P1）')
    w('=' * W)
    w('基准日 %s | 保留窗口 近 %d 天（cutoff=%s）| 每只下限 floor=%d 个点' % (today, keep_days, cutoff, floor))
    w('本报告不含任何写操作（数据库以 mode=ro 打开）')
    w('')
    w('热集口径：持仓 ∪ 自选 ∪ 流水的 6 位数字代码 = %d 只' % len(hot_codes))
    w('')
    for table, label in (('daily_worth', '普通基金净值'), ('money_fund_daily_worth', '货基万份收益')):
        if not _has(conn, table):
            w('[%s] 表不存在，跳过\n' % table)
            continue
        rows = conn.execute(
            'SELECT fund_code, COUNT(*), MIN(date), MAX(date), SUM(date >= ?) FROM %s GROUP BY fund_code' % table,
            (cutoff,),
        ).fetchall()
        total = sum(r[1] for r in rows)
        hot = [r for r in rows if r[0] in hot_codes]
        cold = [r for r in rows if r[0] not in hot_codes]
        hot_rows = sum(r[1] for r in hot)
        cold_del = sum(r[1] - (r[4] or 0) for r in cold)
        floored, cold_del_f = [], 0
        for code, n, _a, _b, rec in cold:
            rec = rec or 0
            if rec >= floor:
                cold_del_f += n - rec
            else:
                keep = min(floor, n)
                floored.append((code, n, keep))
                cold_del_f += n - keep

        w('-' * W)
        w('[%s] %s' % (table, label))
        w('-' * W)
        w('  总量    %9d 行 / %d 只基金' % (total, len(rows)))
        w(
            '  热集    %9d 行 / %d 只（%.2f%% 行占比）← 全留，不删一行'
            % (hot_rows, len(hot), 100.0 * hot_rows / max(total, 1))
        )
        w('  冷集    %9d 行 / %d 只' % (total - hot_rows, len(cold)))
        w('')
        w(
            '  字面执行（冷集删 cutoff 之前的行）：保留 %d (%.2f%%) / 删除 %d (%.2f%%)'
            % (total - cold_del, 100.0 * (total - cold_del) / max(total, 1), cold_del, 100.0 * cold_del / max(total, 1))
        )
        w(
            '  加下限保护（每只至少留 %d 个点）：保留 %d (%.2f%%) / 删除 %d (%.2f%%) / 多留 %d 行'
            % (
                floor,
                total - cold_del_f,
                100.0 * (total - cold_del_f) / max(total, 1),
                cold_del_f,
                100.0 * cold_del_f / max(total, 1),
                cold_del - cold_del_f,
            )
        )
        w('')

        # 校验：恒等式 + 删除集合只取自冷集。**不要**写成「热集若按同规则会删多少」——
        # 删除集合本就只从冷集取，那个数字恒为正且无意义（会被误读成异常）。
        keep_total = hot_rows + sum(r[4] or 0 for r in cold)
        w(
            '  [校验] 恒等式：保留 %d + 删除 %d = 总量 %d → %s'
            % (keep_total, cold_del, total, 'OK' if keep_total + cold_del == total else '!! 不成立，报告有误')
        )
        w(
            '  [校验] 热集保护：删除集合仅取自冷集（%d 只）；热集 %d 行（%d 只）全部保留 → OK'
            % (len(cold), hot_rows, len(hot))
        )
        w('')

        wiped = [(c, n, a, b) for c, n, a, b, r in cold if not r]
        wiped_ids = {x[0] for x in wiped}
        wiped_floored = [f for f in floored if f[0] in wiped_ids]
        w(
            '  [危险清单] 字面执行后会**整只清空**的冷集基金：%d 只（合计 %d 行）'
            % (len(wiped), sum(x[1] for x in wiped))
        )
        if wiped:
            w('    这些基金全部净值点都早于 cutoff —— §5.4 明确「属该补不该删」')
            w(
                '    下限保护 floor=%d 可保住其中 %d 只（%d 行）'
                % (floor, len(wiped_floored), sum(x[2] for x in wiped_floored))
            )
            for code, n, a, b in wiped[:15]:
                w('      %-8s %5d 行  %s ~ %s%s' % (code, n, a, b, '  ← §5.4 点名' if code in DOC_FLAGGED else ''))
            if len(wiped) > 15:
                w('      …另有 %d 只' % (len(wiped) - 15))
        by_code = {r[0]: r for r in rows}
        w('    §5.4 点名 5 只的当前状态：')
        for code in DOC_FLAGGED:
            r = by_code.get(code)
            if not r:
                w('      %-8s 本库无净值行' % code)
            else:
                w(
                    '      %-8s %5d 行  %s ~ %s  近窗口 %d 行 → %s'
                    % (code, r[1], r[2], r[3], r[4] or 0, '会被清空' if not r[4] else '保留近窗口 %d 行' % (r[4] or 0))
                )
        w('')

        ranked = sorted(cold, key=lambda r: r[1] - (r[4] or 0), reverse=True)[:top]
        w('  [删除量 Top %d 冷集基金]' % len(ranked))
        w('    %-8s %8s %8s %8s  %s' % ('代码', '总行数', '近窗口', '将删', '最新净值日'))
        for code, n, _a, b, rec in ranked:
            w('    %-8s %8d %8d %8d  %s' % (code, n, rec or 0, n - (rec or 0), b))
        w('')
    return out


def main():
    p = argparse.ArgumentParser(description='分层保留清理的只读预演（#2120 P1）')
    p.add_argument('--db', default='invest.db')
    p.add_argument('--keep-days', type=int, default=365)
    p.add_argument('--floor', type=int, default=2)
    p.add_argument('--top', type=int, default=20)
    p.add_argument('--out', default=None)
    args = p.parse_args()
    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print('找不到库文件: %s' % db_path)
        return 1
    conn = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
    try:
        text = '\n'.join(preview(conn, args.keep_days, args.floor, args.top))
    finally:
        conn.close()
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
        print('OK -> %s' % args.out)
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
