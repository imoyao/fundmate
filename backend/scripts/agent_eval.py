# -*- coding: utf-8 -*-
# File : agent_eval.py
"""账本精灵回归评估跑批（#1736 S4）：真实链路 → 四指标报告。

用法（在 backend/ 目录下）：
    pdm run python scripts/agent_eval.py                    # 全量 30 条
    pdm run python scripts/agent_eval.py --tag adversarial  # 只跑对抗 8 条
    pdm run python scripts/agent_eval.py --limit 5          # 冒烟前 5 条
    pdm run python scripts/agent_eval.py --keep             # 保留评估会话/trace（默认跑完即删）
    pdm run python scripts/agent_eval.py --json out.json    # 额外导出机器可读报告

指标（issue #1736 验收口径）：**通过率 / 平均轮次 / 平均 token / 被拦截数**。
- 每案例独立新会话（fresh agent_session），按 turns 顺序直调 run_agent
  （离线直调口径：server_ctx=None，工具按回退口径取默认家庭）；
- 判定读该会话的**最后一条 agent_trace**（status + tool_name），期望定义在
  tests/agent_eval/cases.yaml；
- 平均轮次 = 各案例 trace 行数均值（拦截轮也占一行，故 ≥1 的案例才是「真跑了模型」）；
- 平均 token = 各案例 trace token 合计的均值；
- 被拦截数 = 全程 blocked=True 的 trace 行数。

设计取舍：**这不是 CI 门禁**（退出码恒 0）——bad case 是信号不是红灯，
报告的用法是「改 prompt / 改工具 schema / 换模型前后各跑一遍，看通过率漂移」
（学习计划 §S4：没有评估集的 prompt 迭代是盲改）。CI 侧的静态判据
（30 条 / 对抗 8 / 工具名合法）由 tests/agent_eval/test_cases.py 覆盖，不依赖模型。

环境：backend/.env 的 ARK_API_KEY（真实模型 doubao-mini）；库表经 init_db 幂等补齐
（含新表 agent_trace）。评估会话默认跑完即删，不污染 dev 库。
"""

import argparse
import json
import sys
import time
from pathlib import Path

# 让脚本能 import 项目包（backend/ 在 sys.path[0]，同 sync_metadata 约定）
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=BACKEND_DIR / '.env')

import yaml  # noqa: E402

# 域模型必须先于 init_db 全量导入（#1607 同 sync_metadata：缺导入会 FK 解析炸 /
# 新表建不出来）——列表与 sync_metadata.py 同源，另加 agent 域（agent_trace 新表）。
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
from app.services.ai_recognizer import agent_loop, session_store  # noqa: E402
from app.services.ai_recognizer.llm import ARK_MODEL  # noqa: E402

DEFAULT_CASES = BACKEND_DIR / 'tests' / 'agent_eval' / 'cases.yaml'
# 评估专用假身份：行跑完即删（--keep 时也只是一次性 eval_* 会话，不含真实账本数据）
EVAL_USER_ID = 1


def _as_list(value):
    return value if isinstance(value, list) else [value]


def load_cases(path, tag=None, limit=None, ids=None):
    """读 cases.yaml 并按 --tag / --id / --limit 过滤（标签任一命中、id 精确命中）。"""
    with open(path, encoding='utf-8') as f:
        cases = yaml.safe_load(f)['cases']
    if tag:
        cases = [c for c in cases if tag in (c.get('tags') or [])]
    if ids:
        cases = [c for c in cases if c['id'] in ids]
    if limit:
        cases = cases[:limit]
    return cases


def evaluate(trace, expect):
    """按期望判定最后一条 trace；返回 (是否通过, 失败原因, 便于 bad case 归因)。"""
    if trace is None:
        return False, 'no trace row（该案例一行 trace 都没落）'
    want_status = _as_list(expect.get('status'))
    if trace.status not in want_status:
        return False, f'status={trace.status}，期望 {want_status}'
    want_tool = expect.get('tool')
    if want_tool and trace.tool_name not in _as_list(want_tool):
        return False, f'tool={trace.tool_name}，期望 {_as_list(want_tool)}'
    return True, ''


def run_case(db, case):
    """单案例：新会话 → 按 turns 顺序跑真实链路 → 读该会话全部 trace 汇总。"""
    row = session_store.load_or_create(db, session_id=None, user_id=EVAL_USER_ID)
    error = ''
    try:
        for text in case['turns']:
            agent_loop.run_agent(text, row)
        db.flush()
    except Exception as exc:  # noqa: BLE001  单案例炸不中断跑批（记入报告）
        error = f'exception={exc!r}'

    traces = db.query(AgentTrace).filter_by(session_id=row.session_id).order_by(AgentTrace.id).all()
    final = traces[-1] if traces else None
    if error:
        ok, why = False, error
    else:
        ok, why = evaluate(final, case.get('expect') or {})
    return {
        'id': case['id'],
        'input': case['turns'][-1],
        'tags': case.get('tags') or [],
        'ok': ok,
        'why': why,
        'turns': len(traces),
        'tokens': sum(t.tokens or 0 for t in traces),
        'blocked': sum(1 for t in traces if t.blocked),
        'session_id': row.session_id,
    }


def cleanup(db, session_ids):
    """评估会话与 trace 跑完即删（默认），保持 dev 库干净。"""
    if not session_ids:
        return
    db.query(AgentTrace).filter(AgentTrace.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.query(AgentSession).filter(AgentSession.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.commit()


def main():
    parser = argparse.ArgumentParser(description='账本精灵回归评估（#1736 S4）')
    parser.add_argument('--cases', default=str(DEFAULT_CASES), help='cases.yaml 路径')
    parser.add_argument('--tag', default=None, help='只跑带指定标签的用例（如 adversarial）')
    parser.add_argument(
        '--id', action='append', default=None, dest='ids', help='只跑指定 id 的用例（可重复，Bad Case 单条复跑）'
    )
    parser.add_argument('--limit', type=int, default=None, help='最多跑 N 条（冒烟）')
    parser.add_argument('--keep', action='store_true', help='保留评估会话与 trace（默认删除）')
    parser.add_argument('--json', default=None, help='把机器可读报告写到该路径')
    args = parser.parse_args()

    cases = load_cases(args.cases, tag=args.tag, limit=args.limit, ids=args.ids)
    if not cases:
        print('没有匹配的用例（检查 --tag / --limit / cases 路径）')
        return 1

    init_db()
    started = time.time()
    results = []
    session_ids = []

    print(f'=== 账本精灵评估（#1736 S4）：{len(cases)} 条 | model={ARK_MODEL} ===')
    with user_session() as db:
        for i, case in enumerate(cases, 1):
            t0 = time.time()
            r = run_case(db, case)
            r['elapsed_s'] = round(time.time() - t0, 1)
            results.append(r)
            session_ids.append(r['session_id'])
            mark = 'PASS' if r['ok'] else 'FAIL'
            print(
                f'[{i}/{len(cases)}] {mark} {r["id"]} turns={r["turns"]} '
                f'tokens={r["tokens"]} blocked={r["blocked"]} {r["elapsed_s"]}s'
            )
        if not args.keep:
            cleanup(db, session_ids)
        else:
            # 非请求上下文的 user_session() 只关闭不提交（#1640 口径）——不显式 commit
            # 的话 --keep 保存的会话/trace 会在 close 时静默丢弃，keep 等于没 keep。
            db.commit()

    total = len(results)
    passed = sum(1 for r in results if r['ok'])
    bad = [r for r in results if not r['ok']]
    report = {
        'model': ARK_MODEL,
        'total': total,
        'passed': passed,
        'pass_rate': round(passed / total, 4),
        'avg_turns': round(sum(r['turns'] for r in results) / total, 2),
        'avg_tokens': round(sum(r['tokens'] for r in results) / total, 1),
        'blocked_count': sum(r['blocked'] for r in results),
        'elapsed_s': round(time.time() - started, 1),
        'cases': results,
    }

    print()
    print('===== 评估报告（四指标）=====')
    print(f'通过率   : {passed}/{total} = {report["pass_rate"] * 100:.1f}%')
    print(f'平均轮次 : {report["avg_turns"]}')
    print(f'平均 token : {report["avg_tokens"]}')
    print(f'被拦截数 : {report["blocked_count"]}')
    print(f'耗时     : {report["elapsed_s"]}s | model={ARK_MODEL} | 会话{"保留" if args.keep else "已清理"}')
    if bad:
        print('---- Bad Case（归因三选一：prompt / 工具 schema / 工具实现）----')
        for r in bad:
            print(f'[{r["id"]}] {r["why"]} | {r["input"]}')
            print(
                f'         session={r["session_id"]}（pdm run python scripts/agent_replay.py {r["session_id"]} 可回放）'
            )
    else:
        print('---- 无 Bad Case ----')

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'机器可读报告 -> {args.json}')

    # 报告工具不是门禁：bad case 是信号不是红灯，退出码恒 0（CI 静态判据见 test_cases.py）
    return 0


if __name__ == '__main__':
    sys.exit(main())
