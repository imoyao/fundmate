#!/usr/bin/env python3
"""自动合并归因守卫（#2799）。

## WHY：这条守卫守的是「门禁绿灯但下游守卫全哑」

`pr-auto-merge.yml` 用 GitHub 原生 auto-merge（`gh pr merge --auto`）合 PR。
**用哪个凭据去启用 auto-merge，决定了最终那次合并归因给谁**，而归因决定后续事件是否投递。

2026-11-01 实测（源 #2793 的 PR #2797，本仓史上第一次 native auto-merge 合并）：

| 合并归因 | `pull_request: closed` | `push` 到 dev | 后果 |
|---|---|---|---|
| `github-actions`（GITHUB_TOKEN） | **不产生 run** | **不产生 run** | issue 不自动关闭、乱码守卫 / lockfile 守卫被静默跳过 |
| `imoyao`（用户凭据） | 产生 run | 产生 run | 正常 |

GitHub 的规则：除 `workflow_dispatch` / `repository_dispatch` 外，**由 GITHUB_TOKEN 触发的事件
不创建 workflow run**。而 native auto-merge 是「排队 → 门禁转绿后由 GitHub 执行合并」，
**合并时携带的是「最后启用 auto-merge 的那个凭据」的归因**——于是 GITHUB_TOKEN 启用出来的
合并，其 `closed` / `push` 事件全部被抑制。门禁本身是绿的（`质量门禁汇总` 照常 success），
但门禁**下游**的守卫在这条路径上是哑的——这正是「假绿」最典型的形态。

外部独立实证（ebi-agent-chat-relay 仓库 2026-09-22，16 次合并 1:1 相关无例外）同结论：
「A merge attributed to GITHUB_TOKEN fires no push or pull_request event. A merge
attributed to a real user does. The token that last enables auto-merge determines the
eventual actor.」

所以本守卫不检查「auto-merge 能不能用」，只检查**「启用 auto-merge 用的凭据是不是用户凭据」**。

## 判据（任一不满足即红，并入 ci.yml 的 scripts_test，阻断）

1. `.github/workflows/pr-auto-merge.yml` 存在；
2. 该 workflow 里调用 `gh pr merge --auto` 的那一步，其 `GH_TOKEN` 来源**不得**是
   `secrets.GITHUB_TOKEN`——那正是事件被抑制的根因；
3. 该 `GH_TOKEN` 来源必须引用一个**用户 PAT secret**（本仓约定名 `AUTO_MERGE_PAT`）；
4. **不得**把用户 PAT 与 GITHUB_TOKEN 用 `||` 串起来回落——PAT 缺失时静默回落到
   GITHUB_TOKEN = 事件又被抑制 = 假绿复现。PAT 缺失必须**显式失败**（见判据 5）；
5. PAT 缺失时该步骤必须**非零退出**（`exit 1` 之类），不许把失败态吞成绿灯；
6. workflow 里必须有一句可读的说明，指出「本步骤用用户 PAT 才能让合并归因到用户、
   从而让 `pull_request: closed` / `push` 事件被投递」——否则后人「顺手改回
   `secrets.GITHUB_TOKEN`」时没有任何线索（#171 / #450 同族的配置回潮）。

## 边界（刻意不查）

- **不查 dependabot 那条路径**（`dependabot-auto-merge.yml`）：它的合并归因刻意留在 bot
  侧（依赖更新不该触发版本自增、也不该重启 bot 链），属另一条产品决策，不在本守卫范围。
- 不查 secret 的实际值（守卫只看 YAML，看不到 secret 存储）；「PAT 到底配没配」由
  步骤 5 的显式失败在运行时兜住——缺 PAT 时 workflow 自己会红，不会静默退化。
- 不验证 auto-merge 真的合得上（那需要真实 PR 与门禁转绿，属端到端验证）。

## 用法

    python scripts/guard_auto_merge_user_attribution.py            # 校验（CI）
    python scripts/guard_auto_merge_user_attribution.py --report   # 打印通过项

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

WORKFLOW_REL = '.github/workflows/pr-auto-merge.yml'
PAT_SECRET = 'AUTO_MERGE_PAT'


def _import_yaml():
    try:
        import yaml
    except ImportError:  # pragma: no cover - CI 里由 setup-python + pip 提供
        raise SystemExit('缺少 pyyaml：本判据依赖 YAML 解析（ci.yml 的 scripts_test 已安装）')
    return yaml


def _triggers(doc: Dict[str, Any]) -> Dict[str, Any]:
    """取 `on:`。PyYAML 按 YAML 1.1 把裸 `on` 解析成布尔 True —— 两种都认。"""
    for key in ('on', True):
        val = doc.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _steps(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    jobs = doc.get('jobs') or {}
    if not isinstance(jobs, dict):
        return out
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get('steps') or []:
            if isinstance(step, dict):
                out.append(step)
    return out


def _env_of(step: Dict[str, Any]) -> Dict[str, str]:
    env = step.get('env')
    if not isinstance(env, dict):
        return {}
    return {str(k): str(v) for k, v in env.items()}


def _code_lines(text: str) -> List[str]:
    """只留**真会执行**的行（剔掉 shell 注释行）。

    注释里提到 `gh pr merge --auto` 也算命中——那会让判据被自己的说明文字骗过去。
    """
    joined = text.replace('\\\n', ' ')
    return [
        line.strip()
        for line in joined.splitlines()
        if line.strip() and not line.strip().startswith('#')
    ]


def _token_empty_block(run_text: str):
    """截出「检查 GH_TOKEN 是否为空」那个分支的代码行。

    只认形如 `if [ -z "${GH_TOKEN:-}" ]; then` / `if [ -z "$GH_TOKEN" ]; then` 的写法：
    以 `-z` + `GH_TOKEN` 定位起点，向后取到配对的 `fi`（同缩进层级）。
    找不到起点返回 None（= 没有空值检查）。

    为什么要锚定这一段：判据若只看「整个 run 里有没有 exit 1」，
    别处（PAT 过期分支）的 exit 1 会替空值分支蒙混过关——把空值检查整段删掉，
    守卫照样绿，而实际行为已退化成「PAT 缺失时静默继续」（#2799 假绿复现）。
    """
    lines = run_text.replace('\\\n', ' ').splitlines()
    start = None
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '-z' in line and 'GH_TOKEN' in line and 'if' in line:
            start = idx
            break
    if start is None:
        return None

    indent = len(lines[start]) - len(lines[start].lstrip())
    block = []
    for raw in lines[start + 1:]:
        line = raw.strip()
        if not line:
            continue
        cur_indent = len(raw) - len(raw.lstrip())
        if line == 'fi' and cur_indent <= indent:
            break
        if not line.startswith('#'):
            block.append(line)
    return block


def _has_hard_failure(block) -> bool:
    """这段分支里有没有「硬失败」：**非零 exit**。

    刻意**不**把 `::error::` 算硬失败：它只是往日志里打一行标注，
    脚本会接着往下跑（`set -e` 也管不到它）——真正拦住流程的只有非零 exit。
    把 `::error::` 算进硬失败会让「打了一行警告然后继续执行」被误判成已拦截，
    而那正是本守卫要抓的形态（#2799 假绿）。
    """
    for line in block:
        parts = line.replace(';', ' ').split()
        for i, token in enumerate(parts):
            if token == 'exit' and i + 1 < len(parts):
                code = parts[i + 1].strip('"\'')
                if code.isdigit() and code != '0':
                    return True
    return False


def check(repo: Path) -> List[str]:
    """返回违规项列表（空 = 通过）。纯读文件，无网络、无 git。"""
    yaml = _import_yaml()
    wf_path = repo / WORKFLOW_REL
    problems: List[str] = []

    if not wf_path.is_file():
        return [f'{WORKFLOW_REL} 不存在——自动合并通道没有入口']

    try:
        doc = yaml.safe_load(wf_path.read_text(encoding='utf-8')) or {}
    except Exception as exc:  # noqa: BLE001 —— YAML 坏了就是「拿不到输入」
        return [f'{WORKFLOW_REL} 无法解析：{exc}']

    steps = _steps(doc)
    merge_steps = [
        step
        for step in steps
        if isinstance(step.get('run'), str)
        and any('gh pr merge' in line for line in _code_lines(step['run']))
    ]

    if not merge_steps:
        problems.append(
            'workflow 里没有执行 `gh pr merge --auto`——自动合并通道没有入口'
            '（#564 同族：脚本/workflow 写了但没人调用，等于从没跑过）'
        )
        return problems

    for step in merge_steps:
        env = _env_of(step)
        token_src = env.get('GH_TOKEN') or env.get('GITHUB_TOKEN') or ''
        where = f'步骤「{step.get("name") or "（未命名）"}」'

        if not token_src:
            problems.append(
                f'{where} 没设 GH_TOKEN/GITHUB_TOKEN 环境变量：'
                '`gh pr merge` 会因无凭据而失败'
            )
            continue

        if 'secrets.GITHUB_TOKEN' in token_src:
            problems.append(
                f'{where} 的 token 来自 secrets.GITHUB_TOKEN：'
                '用它启用 auto-merge，合并会被归因到 github-actions，其 '
                '`pull_request: closed` / `push` 事件**全部被抑制**（GitHub 规则：'
                'GITHUB_TOKEN 触发的事件不创建 workflow run）⇒ issue 不自动关闭、'
                '乱码守卫与 lockfile 守卫被静默跳过，而门禁却是绿的（假绿，#2799）。'
                '必须改用用户 PAT secret。'
            )

        if PAT_SECRET not in token_src:
            problems.append(
                f'{where} 的 token 未引用用户 PAT secret `{PAT_SECRET}`：'
                '合并归因不到用户 ⇒ 事件不投递'
            )

        if '||' in token_src:
            problems.append(
                f'{where} 的 token 表达式含 `||` 回落：'
                f'PAT 缺失时会静默退回 GITHUB_TOKEN ⇒ 事件又被抑制 ⇒ 假绿复现。'
                'PAT 缺失必须显式失败，不许回落。'
            )

        # PAT 缺失必须显式失败：把「没配 PAT」与「PR 有冲突」分开，
        # 否则前者会被当成后者一直重试，直到有人发现合并从不发生。
        #
        # 判据必须**锚定在 GH_TOKEN 空值那个分支上**，不能只看「步骤里有没有 exit 1」——
        # 否则别处（比如 PAT 过期分支）的 exit 1 会替它蒙混过关：把空值检查整段删掉，
        # 守卫照样绿，而实际行为已经退化成「PAT 缺失时静默继续」（#2799 假绿复现）。
        block = _token_empty_block(step['run'])
        if block is None:
            problems.append(
                f'{where} 没有检查 GH_TOKEN 是否为空：'
                'PAT 缺失时会把「没配 PAT」当成「PR 有冲突」一直重试，'
                '直到没人发现合并从不发生'
            )
        elif not _has_hard_failure(block):
            problems.append(
                f'{where} 的「GH_TOKEN 为空」分支没有显式失败（`exit 1` / `::error::`）：'
                'PAT 缺失时若不失败，问题会被吞成「PR 有冲突」一直重试'
            )

    # 说明必须在场：否则后人「顺手改回 secrets.GITHUB_TOKEN」时没有任何线索。
    raw = wf_path.read_text(encoding='utf-8')
    hints = ('归因', 'attribution', 'attributed')
    if not any(h in raw for h in hints):
        problems.append(
            f'{WORKFLOW_REL} 里没有一句说明「用用户 PAT 才能让合并归因到用户、'
            '从而让事件被投递」——配置回潮时（#171 / #450 同族）没有任何线索'
        )

    return problems


def main(argv: List[str]) -> int:
    repo = Path(__file__).resolve().parent.parent
    try:
        problems = check(repo)
    except SystemExit:
        raise
    if problems:
        for p in problems:
            print(f'✗ {p}')
        print(f'\n自动合并的归因不成立：{len(problems)} 项')
        return 1
    if '--report' in argv:
        print(f'✓ {WORKFLOW_REL} 存在且真的调用 gh pr merge --auto')
        print(f'✓ token 来自用户 PAT secret `{PAT_SECRET}`，不是 GITHUB_TOKEN')
        print('✓ 无 `||` 回落：PAT 缺失会显式失败，不静默退化')
        print('✓ 有「归因」说明：配置回潮时留得下线索')
    else:
        print('OK: 自动合并用用户凭据归因，事件会被投递。')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
