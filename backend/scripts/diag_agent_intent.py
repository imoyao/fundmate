# -*- coding: utf-8 -*-
"""账本精灵「第二轮答非所问」复现 / 诊断（#1718，源自 #1121 学习主线）。

用法（`invest.db` 按 cwd 解析，故**必须在 `backend/` 下执行**；`.env` 取脚本所在 backend 目录）：

    pdm run python scripts/diag_agent_intent.py
    DIAG_RUNS=3 pdm run python scripts/diag_agent_intent.py          # 多次采样看稳定性
    DIAG_DUMP=logs/agent_intent.txt pdm run python scripts/diag_agent_intent.py  # 抓 prompt

做什么：
- 离线直调 `run_agent`（不走 HTTP / 鉴权），跑固定的两轮对话；
- 打印每轮的决策结果（type / 叙事文本），用于判断第二轮是否选对工具、是否覆盖用户子问题；
- `DIAG_DUMP` 有值时，把每次模型调用的 system prompt、真实 prompt 与模型原始输出追加写入该文件。

为什么需要它（#1718 教训）：
- 答非所问的根因只能靠**决策轮真实 prompt + 模型原话**定案，看代码倒推会得出错误归因；
- doubao-mini 在 temperature=0.1 下仍有漂移，**单次通过不代表修复稳定**，需 DIAG_RUNS>=3 采样。

产出只读（不写库）；工具执行会查本地市场域 / 用户域数据。
"""

import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

# 显式加载**本脚本所在 backend/ 下的 .env**（与 check_jsl_cookie.py 同口径）：
# python-dotenv 默认从调用文件向上查找，而 `llm.py` 的 `load_dotenv()` 走 cwd——
# 在 worktree / 从别的目录起进程时 cwd 的 .env 未必命中，写死路径最稳。
load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from app.domains.agent.models import AgentSession  # noqa: E402
from app.services.ai_recognizer import agent_loop, session_store  # noqa: E402

DEFAULT_Q1 = '现在市场温度是多少？'
DEFAULT_Q2 = '为什么数据没有更新？现在还是 9 月 24 号的数据。数据来源是什么？同时我想知道，贪恐指数是多少？'


def _pick_family_id():
    """取库内一个真实 family_id，让需要它的工具（资产 / 组合 / 自选）能真实执行。"""
    db_path = os.path.join(os.getcwd(), 'invest.db')
    if not os.path.exists(db_path):
        return None
    con = sqlite3.connect(db_path)
    try:
        row = con.execute('select family_id from positions where family_id is not null limit 1').fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _install_dump(path: str) -> None:
    """monkeypatch agent_loop.llm.call_llm，把每次调用的入参出参追加写入 path。"""
    if os.path.exists(path):
        os.remove(path)
    original = agent_loop.llm.call_llm
    seq = [0]

    def wrapped(*args, **kwargs):
        raw = original(*args, **kwargs)
        seq[0] += 1
        content = kwargs.get('content') or (args[0] if args else '')
        prompt = ''
        if isinstance(content, list):
            prompt = '\n'.join(c.get('text', '') for c in content if isinstance(c, dict))
        elif isinstance(content, str):
            prompt = content
        with open(path, 'a', encoding='utf-8') as f:
            f.write(f'\n{"=" * 78}\nCALL #{seq[0]}\n')
            f.write('--- SYSTEM ---\n' + str(kwargs.get('system_prompt', '')) + '\n')
            f.write('--- PROMPT ---\n' + prompt + '\n')
            f.write('--- RAW MODEL OUTPUT ---\n' + str(raw) + '\n')
        return raw

    agent_loop.llm.call_llm = wrapped


def main() -> int:
    q1 = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_Q1
    q2 = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_Q2
    runs = int(os.environ.get('DIAG_RUNS', '1'))

    dump = os.environ.get('DIAG_DUMP')
    if dump:
        _install_dump(dump)
        print(f'prompt dump -> {os.path.abspath(dump)}')

    family_id = _pick_family_id()
    print(f'family_id = {family_id}（None 时需要 family_id 的工具会按缺省口径执行）')
    print(f'runs = {runs}')

    summary = []
    for run in range(1, runs + 1):
        # 按生产口径构造：load_or_create 给新会话写入 DEFAULT_GOAL
        session = AgentSession(
            session_id=f'diag-{run}',
            user_id=0,
            goal=session_store.DEFAULT_GOAL,
            state={},
            messages=[],
            turn_count=0,
        )
        server_ctx = {'family_id': family_id} if family_id else None
        r1 = agent_loop.run_agent(q1, session, server_ctx=server_ctx)
        r2 = agent_loop.run_agent(q2, session, server_ctx=server_ctx)
        print(f'run{run} R1 type={r1.get("type")}')
        print(f'run{run} R2 type={r2.get("type")} tool={r2.get("tool_name")}')
        print(f'run{run} R2 content={str(r2.get("content", "")).replace(chr(10), " / ")}')
        summary.append((run, r2.get('type'), r2.get('tool_name')))

    print('-' * 76)
    for run, typ, tool in summary:
        print(f'  run{run}: 第二轮 type={typ} tool={tool}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
