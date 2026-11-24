# -*- coding: utf-8 -*-
"""数据修复：删除货基 004369 前海开源聚财宝B 的两条脏净值 + 作废物化缓存。

背景（2026-11-22 排查微众银行账本收益日历斜线格）：
- 004369 是货基（is_money_fund=1），单位净值应恒为 1.0，且其余 20 只货基
  daily_worth 均为 0 行；它却有两行 10-15=2.0、10-16=2.1（同秒写入，脏数据）。
- 这两条错误净值让它变成「有价格序列但 11 月初缺价」，在收益日历的状态判定里
  被当作 partial 源；又因账户级日历的「数据不完整」判定用家庭级全量决策集，
  把微众银行账本 11/02~11/04 也拖成斜线格（partial）。
- 物化缓存按 (family_id, ledger_id, date) 存 state，年视图/长区间请求落下的
  partial 会污染日视图，故需整表作废重建。

安全：先备份受影响行到 data/backups，再删除；物化缓存纯可重建。
"""
import datetime as dt
import os
import sqlite3
import sys

sys.path.insert(0, r'd:\codes\fundmate\backend')
sys.stdout.reconfigure(encoding='utf-8')

DB = r'd:\codes\fundmate\backend\invest.db'
BACKUP_DIR = r'd:\codes\fundmate\backend\data\backups'
os.makedirs(BACKUP_DIR, exist_ok=True)
stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
backup_path = os.path.join(BACKUP_DIR, f'backup_fix_004369_dirty_nav_{stamp}.sql')

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

# 1) 备份要删的两条脏净值
rows = con.execute(
    "select * from daily_worth where fund_code='004369' and date in ('2026-10-15','2026-10-16')"
).fetchall()
print('待删除的脏净值行数:', len(rows))
for r in rows:
    print('  ', dict(r))

with open(backup_path, 'w', encoding='utf-8') as f:
    for r in rows:
        cols = ','.join(r.keys())
        vals = ','.join("'" + str(v).replace("'", "''") + "'" if v is not None else 'NULL' for v in r)
        f.write(f"INSERT INTO daily_worth ({cols}) VALUES ({vals});\n")
print('已备份到:', backup_path)

# 2) 删除脏数据
cur = con.execute("delete from daily_worth where fund_code='004369' and date in ('2026-10-15','2026-10-16')")
print('删除行数:', cur.rowcount)

# 3) 作废物化缓存（收益日历快照，纯缓存，整表重建）
n = con.execute('select count(*) c from pnl_daily_snapshots').fetchone()['c']
con.execute('delete from pnl_daily_snapshots')
print(f'物化缓存作废: 删除 {n} 行')

con.commit()

# 4) 验证：删除后 004369 是否回到「无净值行」（与其它货基一致）
left = con.execute("select count(*) c from daily_worth where fund_code='004369'").fetchone()['c']
print('删除后 004369 daily_worth 行数:', left)
con.close()

# 5) 引擎验证：微众银行账本（ledger_id=3）11 月现算，11-02/03/04 应为 updown
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

eng = create_engine(f'sqlite:///{DB}', connect_args={'check_same_thread': False})
from app.services import pnl_calendar as P

with Session(eng) as db:
    start, end = P._resolve_range('2026-11-01', None)
    end = P._clamp_to_today(end)
    positions = P._positions(db, 1, 3, start)
    decision_positions = P._positions(db, 1, None, start)
    no_price_ids, _ = P._price_presence(db, decision_positions, start, end)
    shares, txns = P._as_of_shares(db, 1, end)
    computed = P._compute_days(
        db, 1, positions, decision_positions, start, end, 3,
        loop_start=start, no_price_ids=no_price_ids, shares=shares, txns=txns,
    )
    for m in computed:
        if m['date'] in ('2026-11-02', '2026-11-03', '2026-11-04', '2026-11-20'):
            print('验证', m['date'], 'state=', m['state'])
print('修复完成')
