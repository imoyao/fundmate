# -*- coding: utf-8 -*-
# File : agent_eval.py
"""账本精灵回归评估跑批（#1736 S4）：真实链路 → 四指标报告。

用法（在 backend/ 目录下）：
    pdm run python scripts/agent_eval.py                    # 全量 45 条
    pdm run python scripts/agent_eval.py --tag adversarial  # 只跑对抗 8 条
    pdm run python scripts/agent_eval.py --tag confusion    # 只跑跨工具混淆 3 条
    pdm run python scripts/agent_eval.py --limit 5          # 冒烟前 5 条
    pdm run python scripts/agent_eval.py --id basic-03      # 单条复跑（Bad Case 归因）
    pdm run python scripts/agent_eval.py --keep             # 保留全部评估会话/trace
    pdm run python scripts/agent_eval.py --json out.json    # 额外导出机器可读报告
    pdm run python scripts/agent_eval.py --delay 5 --retries 3  # 撞 429 时放慢并加打

指标（issue #1736 验收口径）：**通过率 / 平均轮次 / 平均 token / 被拦截数**。
- 每案例独立新会话（fresh agent_session），按 turns 顺序直调 run_agent
  （离线直调口径：server_ctx=None，工具按回退口径取默认家庭）；
- 判定读该会话的**最后一条 agent_trace**（status + tool_name），期望定义在
  tests/agent_eval/cases.yaml；
- 平均轮次 = 各案例 trace 行数均值（拦截轮也占一行，故 ≥1 的案例才是「真跑了模型」）；
- 平均 token = 各案例 trace token 合计的均值；
- 被拦截数 = 全程 blocked=True 的 trace 行数。

**429 与重试口径（#2621）**：实测 2026-10-25 跑到第 14 条起全部 429（`turns=0`），17 条假 FAIL。
429 有两种来源，处置不同：
- **RPM 限流**（响应头带 ratelimit）→ 加 delay 有效：案例间默认休眠 `--delay 2.5` 秒节流；
- **账号额度上限**（body 为 `SetLimitExceeded ... model service has been paused`，多见于
  「安全体验模式」）→ 加 delay/重试都无效，只能换模型档或控制台提额；此时应 `--retries 0`
  快速暴露，而不是用重试刷出 17 条假 PASS。
- `turns==0`（一行 trace 都没落）在处理上视为**设施故障**，指数退避重试 `--retries 2` 次；
- **选错工具不重试** —— 重试等于用采样次数掩盖真实退化。

设计取舍：**这不是 CI 门禁**（退出码恒 0）——bad case 是信号不是红灯，
报告的用法是「改 prompt / 改工具 schema / 换模型前后各跑一遍，看通过率漂移」
（学习计划 §S4：没有评估集的 prompt 迭代是盲改）。CI 侧的静态判据
（45 条 / 对抗 8 / 混淆 3 / 工具名合法）由 tests/agent_eval/test_cases.py 覆盖，不依赖模型。

会话清理：默认只清 PASS 的会话，**Bad Case 会话保留**（否则报告里给的 agent_replay
命令回放不出东西）；`--purge-bad` 连 Bad Case 一起清，`--keep` 全留。
清理排在报告与 `--json` 之后、走独立 session —— cleanup 曾是这条链上唯一会抛
StaleDataError 的点（未提交的 delete 撞 still-persistent 行），异常会把四指标与
JSON 一起吞掉。

环境：backend/.env 的 ARK_API_KEY（真实模型走 ARK_MODEL_AGENT）；库表经 init_db 幂等补齐
（含新表 agent_trace）。评估会话默认不污染 dev 库。

**token 预算（实测 2026-10-25）**：护栏 `ARK_DAILY_TOKEN_BUDGET` 默认 300k，是**进程级**
计数（每次运行从 0 起算）。推理模型单案例约 10k token（决策 2.5k + 叙事最高 19k），
45 条 ≈ 450k，跑到 30 条左右会被熔断，余下全变 `turns=0` 的假 FAIL。全量跑批**必须**
显式抬高：

    ARK_DAILY_TOKEN_BUDGET=1500000 pdm run python scripts/agent_eval.py --json out.json

熔断特征：日志出现「今日 AI 识别费用额度已耗尽」，且该案例 turns=0 —— 属于预算问题，
不是模型退化，别把它记成 bad case。

**假 FAIL 防线（#2621）**：`--max-blank N`（默认 3）—— 连续 N 条零 trace 即中止跑批，
剩余用例记 `skipped` 且**不计入通过率分母**，报告的 `aborted` 字段写明原因。额度耗尽时
继续跑只会产出几十条假 FAIL，那种"通过率"比没有更糟。
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
from app.services.ai_recognizer.llm import ARK_MODEL_AGENT  # noqa: E402

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
        # 异常后 session 处于不可用事务态，不 rollback 会让后续案例连环报
        # PendingRollbackError（实测 2026-10-25：429 之后 17 条全灭）。
        try:
            db.rollback()
        except Exception:  # noqa: BLE001  回滚本身失败时保持原错误，不覆盖
            pass

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


def run_case_with_retry(db, case, delay, retries):
    """跑单案例；`turns==0` 视为**设施故障**（模型调用 429 / 异常），按指数退避重跑。

    只重试「一行 trace 都没落」的案例：那是链路没跑通，不是模型选错工具。
    选错工具（turns>0 但 tool 不符）**不重试** —— 重试等于用采样次数掩盖真实退化。
    """
    result = None
    for attempt in range(retries + 1):
        result = run_case(db, case)
        if result['turns'] > 0 or attempt == retries:
            return result
        wait = delay * (2 ** (attempt + 1))
        print(f'  ↻ {case["id"]} 无 trace（{result["why"]}），{wait:.1f}s 后重试 {attempt + 1}/{retries}')
        time.sleep(wait)
    return result


def cleanup(db, session_ids):
    """删除指定评估会话与其 trace，保持 dev 库干净。

    调用方在**独立 session** 里调用（见 main 的清理段）：早期版本与跑批共用
    session，`delete(synchronize_session=False)` 后 commit 会撞上 identity map 里
    仍为 persistent 的 AgentSession 行，抛 StaleDataError 把四指标与 --json 一起吞掉。
    """
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
    parser.add_argument(
        '--delay',
        type=float,
        default=2.5,
        help='案例之间休眠秒数（默认 2.5）：连续调用会撞 ARK 429，退避由本参数兜底',
    )
    parser.add_argument(
        '--retries',
        type=int,
        default=2,
        help='「一行 trace 都没落」时的重试次数（默认 2，指数退避）；选错工具不重试',
    )
    parser.add_argument(
        '--purge-bad',
        action='store_true',
        help='连 Bad Case 的会话一起清理（默认保留，便于 agent_replay 归因）',
    )
    parser.add_argument(
        '--max-blank',
        type=int,
        default=3,
        help='连续 N 条零 trace 即中止跑批（默认 3）：额度耗尽/服务暂停时不再产出假 FAIL',
    )
    args = parser.parse_args()

    cases = load_cases(args.cases, tag=args.tag, limit=args.limit, ids=args.ids)
    if not cases:
        print('没有匹配的用例（检查 --tag / --limit / cases 路径）')
        return 1

    init_db()
    started = time.time()
    results = []
    session_ids = []

    print(f'=== 账本精灵评估（#1736 S4）：{len(cases)} 条 | model={ARK_MODEL_AGENT} ===')
    aborted = ''
    consecutive_blank = 0
    with user_session() as db:
        for i, case in enumerate(cases, 1):
            if i > 1 and args.delay > 0:
                time.sleep(args.delay)
            t0 = time.time()
            r = run_case_with_retry(db, case, args.delay, args.retries)
            r['elapsed_s'] = round(time.time() - t0, 1)
            results.append(r)
            session_ids.append(r['session_id'])
            mark = 'PASS' if r['ok'] else 'FAIL'
            print(
                f'[{i}/{len(cases)}] {mark} {r["id"]} turns={r["turns"]} '
                f'tokens={r["tokens"]} blocked={r["blocked"]} {r["elapsed_s"]}s'
            )
            # 连续零 trace = 链路整体不可用（多为账号额度 SetLimitExceeded / 服务暂停），
            # 不是模型退化。继续跑只会把剩余用例全部记成假 FAIL（实测两次：17 条、21 条），
            # 那种"通过率"比没有更糟——故此处直接中止，剩余用例标记 skipped 且不计入分母。
            if r['turns'] == 0:
                consecutive_blank += 1
                if consecutive_blank >= args.max_blank:
                    aborted = (
                        f'连续 {consecutive_blank} 条零 trace（最近一条：{r["why"]}）；'
                        '多为账号额度/模型服务暂停，非模型退化'
                    )
                    print(f'\n⚠️ 跑批中止：{aborted}')
                    break
            else:
                consecutive_blank = 0
        # 先落库：清理走独立 session（见下方），不 commit 的话 close 时静默丢弃（#1640 口径）。
        db.commit()

    total = len(results)
    passed = sum(1 for r in results if r['ok'])
    bad = [r for r in results if not r['ok']]
    report = {
        'model': ARK_MODEL_AGENT,
        'total': total,
        'planned': len(cases),
        'skipped': len(cases) - total,
        'aborted': aborted,
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
    if aborted:
        print(f'⚠️ 本次不完整：{report["skipped"]}/{len(cases)} 条未跑（不计入分母）')
    print(f'通过率   : {passed}/{total} = {report["pass_rate"] * 100:.1f}%')
    print(f'平均轮次 : {report["avg_turns"]}')
    print(f'平均 token : {report["avg_tokens"]}')
    print(f'被拦截数 : {report["blocked_count"]}')
    # 会话保留/清理状态在 cleanup 之后单独打印（本脚本清理排在报告之后，此处还未知结果）
    print(f'耗时     : {report["elapsed_s"]}s | model={ARK_MODEL_AGENT}')
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

    # 清理排在报告与 --json 之后：cleanup 曾是这条链上唯一会抛 StaleDataError 的点
    # （delete 后 commit 撞上 still-persistent 的 session 行，异常把四指标与 JSON 一起吞掉）。
    # 两处一起修：换独立 session（identity map 全新）+ 排在报告之后（再炸也不丢结果）。
    kept = session_ids
    if not args.keep:
        bad_sessions = {r['session_id'] for r in results if not r['ok']}
        drop = [s for s in session_ids if args.purge_bad or s not in bad_sessions]
        kept = [s for s in session_ids if s not in drop]
        try:
            with user_session() as db:
                cleanup(db, drop)
        except Exception as exc:  # noqa: BLE001  清理失败不该盖掉本次评估结果
            print(f'⚠️ 会话清理失败（结果不受影响）：{exc!r}')
            kept = session_ids
    if kept:
        print(f'会话保留 {len(kept)} 个（Bad Case 可用 agent_replay 回放归因；--purge-bad 一并清理）')

    # 报告工具不是门禁：bad case 是信号不是红灯，退出码恒 0（CI 静态判据见 test_cases.py）
    return 0


if __name__ == '__main__':
    sys.exit(main())
