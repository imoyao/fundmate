# -*- coding: utf-8 -*-
# File : agent_replay.py
"""决策链路回放（#1736 S4）：给 session_id，按时间轴打出整条 agent_trace。

用法（在 backend/ 目录下）：
    pdm run python scripts/agent_replay.py --list            # 最近 10 个会话（找 id）
    pdm run python scripts/agent_replay.py <session_id>      # 时间轴回放
    pdm run python scripts/agent_replay.py <session_id> --messages   # 连对话原文一起打

回答的是面试题「Bad Case 怎么归因」的动作面：任何一轮失败，按 session_id 把
意图 / 工具 / 参数 / 耗时 / token / 拦截位整条摆出来，定位是 prompt 问题、
工具 schema 问题还是工具实现问题（学习计划 §S4）。与 agent_eval.py 配套：
评估报告里每条 Bad Case 都打印了它自己的回放命令。
"""

import argparse
import sys
from pathlib import Path

# 让脚本能 import 项目包（backend/ 在 sys.path[0]，同 sync_metadata 约定）
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=BACKEND_DIR / '.env')

# 域模型必须先于 init_db 全量导入（#1607，与 scripts/agent_eval.py 同一份清单）
import app.domains.agent.models  # noqa: E402,F401
import app.domains.assets.models  # noqa: E402,F401
import app.domains.families.models  # noqa: E402,F401
import app.domains.funds.models  # noqa: E402,F401
import app.domains.indices.models  # noqa: E402,F401
import app.domains.ledgers.models  # noqa: E402,F401
import app.domains.market.models  # noqa: E402,F401
import app.domains.portfolios.models  # noqa: E402,F401
import app.domains.positions.models  # noqa: E402,F401
import app.domains.price_history.models  # noqa: E402,F401
import app.domains.securities.models  # noqa: E402,F401
import app.domains.strategy.models  # noqa: E402,F401
import app.domains.summary.models  # noqa: E402,F401
import app.domains.transactions.models  # noqa: E402,F401
import app.domains.users.models  # noqa: E402,F401
import app.domains.watchlist.models  # noqa: E402,F401
import app.models.sync_log  # noqa: E402,F401
from app.core.database import init_db, user_session  # noqa: E402
from app.domains.agent.models import AgentSession, AgentTrace  # noqa: E402


def _fmt_time(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '-'


def cmd_list(db, limit):
    rows = db.query(AgentSession).order_by(AgentSession.id.desc()).limit(limit).all()
    if not rows:
        print('（库里还没有会话）')
        return 0
    print(f'最近 {len(rows)} 个会话：')
    for r in rows:
        print(
            f'  {r.session_id}  user={r.user_id} turns={r.turn_count} '
            f'msgs={len(r.messages or [])} created={_fmt_time(r.created_at)}  goal={r.goal}'
        )
    print('回放：pdm run python scripts/agent_replay.py <session_id>')
    return 0


def cmd_replay(db, session_id, show_messages):
    row = db.query(AgentSession).filter_by(session_id=session_id).first()
    traces = db.query(AgentTrace).filter_by(session_id=session_id).order_by(AgentTrace.id).all()
    if row is None and not traces:
        print(f'未找到 session={session_id}（--list 可查最近会话）')
        return 1

    if row is not None:
        print(f'=== session {session_id} ===')
        print(f'user={row.user_id} goal={row.goal!r} turn_count={row.turn_count} created={_fmt_time(row.created_at)}')
    else:
        print(f'=== session {session_id}（无会话行，仅 trace）===')
    if not traces:
        print('（该会话没有 trace 行——S4 之前的会话，或 trace 写入被旁路跳过）')
        return 0

    print(f'--- 决策链路时间轴（{len(traces)} 轮）---')
    for i, t in enumerate(traces, 1):
        ts = _fmt_time(t.created_at)
        latency = f'{t.latency_ms}ms' if t.latency_ms is not None else '-'
        hits = t.guard_hits or []
        print(
            f'[{ts}] #{i} turn={t.turn} status={t.status} intent={t.intent} '
            f'tool={t.tool_name or "-"} latency={latency} tokens={t.tokens} blocked={str(t.blocked).lower()}'
        )
        if hits:
            print(f'         hits={hits}')
        if t.tool_params:
            print(f'         params={t.tool_params}')

    if show_messages:
        msgs = (row.messages if row else None) or []
        if not msgs:
            print('--- 对话原文：（无）---')
        print(f'--- 对话原文（{len(msgs)} 轮）---')
        for i, m in enumerate(msgs, 1):
            print(f'#{i} 用户: {m.get("user", "")}')
            print(f'#{i} 精灵: {m.get("assistant", "")}')
            print()
    return 0


def main():
    parser = argparse.ArgumentParser(description='账本精灵决策链路回放（#1736 S4）')
    parser.add_argument('session_id', nargs='?', default=None, help='要回放的 session_id')
    parser.add_argument('--list', action='store_true', help='列出最近会话（找 id）')
    parser.add_argument('--limit', type=int, default=10, help='--list 的条数（默认 10）')
    parser.add_argument('--messages', action='store_true', help='连对话原文一起打印')
    args = parser.parse_args()

    init_db()
    with user_session() as db:
        if args.list or not args.session_id:
            return cmd_list(db, args.limit)
        return cmd_replay(db, args.session_id, args.messages)


if __name__ == '__main__':
    sys.exit(main())
