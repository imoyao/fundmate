# -*- coding: utf-8 -*-
"""只读巡检：份额被流水「反证」的持仓（#3135 常驻判据的可执行入口）。

## 与 #3127 一次性脚本的区别

``fix_phantom_position_shares.py`` 是**一次性修数据**，判据是「此刻派生份额恰好为 0」；
本脚本是**常驻巡检**，判据与 ``reconciliation_service._finalize_run`` 每次收尾调用的
``position_share_audit.scan_disproved_shares`` 完全同源（复用
``reconciliation_theory.flow_disproves_position``）。它不写库、不重算、不建卡，
只把命中的持仓连同**可执行的重算入口**一起列出来：

- 接口：``POST /api/positions/<id>/recompute/``（#3128，带改前/改后审计）；
- 界面：持仓详情 → 「按流水重算份额」；
- ``--json`` 供定时作业消费、``--strict`` 命中即非零退出（发现即建卡用）。

判据会把「净额归零」与「超卖（净额为负）」分开标注：后者多半缺买入腿，
#3127 明确只报数交人工、不要无脑重算清仓。脚本不写业务数据；``create_app()``
会跑幂等 migration 与调度器初始化，与仓库其它巡检脚本一致。

真库 2026-11-15 现场：``positions#944``（SZ159981 能源化工）账上 1000 份、名下流水
净额 0、无锚点、active ⇒ 命中。14:14 那次 #3127 批量扫描时净额还是 +3000 份，
没进名单；当晚补录卖出后才落到判据上，而一次性脚本不会回头再跑 —— 这正是本卡
要「常驻」的原因。

用法（在 backend/ 目录下跑）：
    python scripts/audit_share_integrity.py
    python scripts/audit_share_integrity.py --family 1 --limit 50
    python scripts/audit_share_integrity.py --json
    python scripts/audit_share_integrity.py --strict
"""

import argparse
import json
import os
import sys

# 用 append 而不是 insert(0)：跨 worktree 跑时 PYTHONPATH 指的代码必须优先于脚本目录。
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

# 只读巡检，不监听端口，不该与 dev server 抢单实例锁
os.environ.setdefault('APP_INSTANCE_GUARD', '0')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def _curl_hint(row, base_url: str) -> str:
    """给出可直接复制的命令；登录态由调用方补（-H 'Cookie: ...'）。"""
    endpoint = row['remedy']['endpoint']
    body = json.dumps({'reason': '巡检(#3135)：份额与流水不自洽'}, ensure_ascii=False)
    return f"curl -X POST '{base_url.rstrip('/')}{endpoint}' -H 'Content-Type: application/json' -d '{body}'"


def main() -> int:
    parser = argparse.ArgumentParser(description='只读巡检「份额与流水不自洽」的持仓（#3135）')
    parser.add_argument('--family', type=int, default=1, help='家庭 id（默认 1）')
    parser.add_argument('--limit', type=int, default=20, help='最多打印多少条明细（默认 20）')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000', help='拼 curl 示例用的后端地址')
    parser.add_argument('--json', action='store_true', help='只输出 JSON（供定时作业消费）')
    parser.add_argument('--strict', action='store_true', help='有命中时返回退出码 1（发现即建卡）')
    args = parser.parse_args()

    from app.core.database import get_db
    from app.core.db_factory import app_database_url
    from app.main import create_app
    from app.services.position_share_audit import scan_disproved_shares

    app = create_app()
    with app.app_context(), get_db() as db:
        found = scan_disproved_shares(db, args.family)

    if args.json:
        print(json.dumps({'family_id': args.family, 'count': len(found), 'items': found}, ensure_ascii=False))
        return 1 if args.strict and found else 0

    print(f'代码来源: {__import__("app").__file__}')
    print(f'目标库  : {app_database_url()}')
    print(f'家庭    : {args.family}    模式: 只读（不写库、不重算）\n')
    print(f'命中 {len(found)} 条「active + 份额>0 + 无锚点 + 名下流水净额 ≤ 0」的持仓\n')
    for row in found[: args.limit]:
        risk = (
            '⚠ 超卖：净额为负，多半缺买入腿，重算会清仓，请先核对流水'
            if row['flow_state'] == 'oversold'
            else '净额归零：流水齐全即可重算清仓'
        )
        print(
            f'  #{row["position_id"]} {row["symbol"]} {row["name"] or ""} ledger={row["ledger_id"]}\n'
            f'    账上 {row["quantity_now"]:g} 份 / 按流水派生 {row["quantity_if_recomputed"]:g} 份'
            f' / 差 {row["diff"]:+g} 份 / 流水净额 {row["flow_net"]:g} 份\n'
            f'    判读    : {risk}\n'
            f'    修复入口: {row["remedy"]["method"]} {row["remedy"]["endpoint"]}\n'
            f'    界面    : 持仓详情 → 「按流水重算份额」\n'
            f'    命令    : {_curl_hint(row, args.base_url)}  （需带登录 Cookie）\n'
        )
    if len(found) > args.limit:
        print(f'  …另有 {len(found) - args.limit} 条（--limit 调大或 --json 取全）\n')
    if found:
        print('提示：本脚本只报数，是否重算由用户决定；超卖条目请先核对买入腿是否缺失。')
    return 1 if args.strict and found else 0


if __name__ == '__main__':
    sys.exit(main())
