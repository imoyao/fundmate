#!/usr/bin/env python3
"""dependabot 锁重生成通道守卫（#2434）。

## WHY：这条通道有三个「写了但不会发生」的典型死法

1. **没人调用**：脚本躺在 `scripts/` 里、单测全绿，但 workflow 从没调用它
   —— 这正是 #564 的形态（分诊脚本三周没落一张标签）。
2. **调用了却是 dry-run**：脚本默认 dry-run（与 `commit_changes.py` 一致的纪律），
   workflow 忘了传 `--apply` ⇒ 每次都成功、每次都什么都不写，日志一片绿。
3. **生成了却没推回**：重生成写完就结束，`git push` 不在，PR 的锁依旧是坏的。

外加两个「失败态被吞」的形态：调用行带 `|| true`（#171 / #450 同族：空 ≠ 没拿到，
失败 ≠ 通过），以及把 `pull_request_target` 改成 `pull_request`
——dependabot PR 在 `pull_request` 下拿到的是**只读** token，push 必然失败，
于是「修锁」变成「每天红一次且什么都没修」（#578 同族：位置错了，怎么都不可能成功）。

所以本守卫不检查「脚本写得好不好」，只检查**这条通道会不会真的发生**。

## 判据（任一不满足即红，并入 ci.yml 的 scripts_test，阻断）

1. `.github/workflows/dependabot-lockfile-regen.yml` 存在；
2. 触发方式是 `pull_request_target`（**不得**用 `pull_request`：dependabot 下 token 只读），
   且 types 覆盖 `opened` / `synchronize`；
3. job 的 `if` 同时含 `dependabot[bot]` 与 `base.ref == 'dev'`（否则要么对所有人跑、
   要么对 CNB 分支跑）；
4. 某个 `run:` 真的调用 `scripts/regen_pnpm_lockfile.mjs`；
5. 该调用带 `--apply`；
6. workflow 里有 `git push`（重生成必须推回去）；
7. 调用脚本的那一行不得带 `|| true`（失败态不许吞）。

## 边界（刻意不查）

- 不验证脚本产出的锁是否正确——那需要 pnpm + 网络，属端到端验证，
  由 PR #2441 的实测记录与 `scripts/tests/test_dependabot_lockfile_regen.py`
  的纯函数单测分担；
- 不检查 `pnpm/action-setup` 的版本号（它读根 `packageManager`，改版本是另一件事）。

## 用法

    python scripts/guard_dependabot_lockfile_regen.py            # 校验（CI）
    python scripts/guard_dependabot_lockfile_regen.py --report   # 打印通过项

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

WORKFLOW_REL = '.github/workflows/dependabot-lockfile-regen.yml'
SCRIPT_REL = 'scripts/regen_pnpm_lockfile.mjs'


def _triggers(doc: Dict[str, Any]) -> Dict[str, Any]:
    """取 `on:`。PyYAML 按 YAML 1.1 把裸 `on` 解析成布尔 True —— 两种都认。"""
    for key in ('on', True):
        val = doc.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _run_texts(doc: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    jobs = doc.get('jobs') or {}
    if not isinstance(jobs, dict):
        return out
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get('steps') or []:
            if isinstance(step, dict) and isinstance(step.get('run'), str):
                out.append(step['run'])
    return out


def _job_conditions(doc: Dict[str, Any]) -> List[str]:
    jobs = doc.get('jobs') or {}
    if not isinstance(jobs, dict):
        return []
    return [str(j.get('if') or '') for j in jobs.values() if isinstance(j, dict)]


def check(repo: Path) -> List[str]:
    """返回违规项列表（空 = 通过）。纯读文件，无网络、无 git。"""
    yaml = _import_yaml()
    wf_path = repo / WORKFLOW_REL
    script_path = repo / SCRIPT_REL
    problems: List[str] = []

    if not wf_path.is_file():
        return [f'{WORKFLOW_REL} 不存在——重生成通道没有入口']
    if not script_path.is_file():
        problems.append(f'{SCRIPT_REL} 不存在——workflow 会调用到空气')

    try:
        doc = yaml.safe_load(wf_path.read_text(encoding='utf-8')) or {}
    except Exception as exc:  # noqa: BLE001 —— YAML 坏了就是「拿不到输入」
        return [f'{WORKFLOW_REL} 无法解析：{exc}']

    trig = _triggers(doc)
    if 'pull_request_target' not in trig:
        problems.append(
            '触发方式必须是 pull_request_target：dependabot 在 pull_request 下拿到只读 token，'
            'push 必然失败（#578 同族）'
        )
    if 'pull_request' in trig:
        problems.append('不得同时挂 pull_request：它与 pull_request_target 并存时读不到写权限那条也会跑')
    types = (trig.get('pull_request_target') or {}).get('types') if isinstance(trig.get('pull_request_target'), dict) else None
    types = types or []
    for need in ('opened', 'synchronize'):
        if need not in types:
            problems.append(f'pull_request_target.types 缺 {need}（PR 打开 / 后续更新时都不会触发）')

    conds = ' '.join(_job_conditions(doc))
    if 'dependabot[bot]' not in conds:
        problems.append("job 的 if 未限定 dependabot[bot]（会对普通 PR 也跑，等于给任意人开写权限）")
    if "base.ref == 'dev'" not in conds and 'base.ref == "dev"' not in conds:
        problems.append('job 的 if 未限定 base=dev（本仓只有 dev 是集成分支）')

    runs = _run_texts(doc)
    # 只认**执行**行：`git show origin/dev:scripts/regen_pnpm_lockfile.mjs > /tmp/x`
    # 也含脚本名，但那是「取一份副本」，删掉后面的 `node` 调用它照样命中——
    # 若按「文本里出现脚本名」判，守卫会被自己的备份行骗过去（本文件首版即如此）。
    invocations = [
        line
        for text in runs
        for line in text.splitlines()
        if 'regen_pnpm_lockfile.mjs' in line and 'node ' in line
    ]
    if not invocations:
        problems.append(
            'workflow 未执行 scripts/regen_pnpm_lockfile.mjs——脚本存在但没人调用等于从没跑过（#564）'
        )
    else:
        if not any('--apply' in line for line in invocations):
            problems.append('调用未带 --apply：脚本默认 dry-run，通道会「每次都成功、每次都什么都不写」')
        for line in invocations:
            if '|| true' in line:
                problems.append('调用行带 `|| true`：失败态被吞成绿灯（#171）')
    if not any('git push' in r for r in runs):
        problems.append('workflow 里没有 git push：重生成写了却不推回，PR 的锁仍然是坏的')

    return problems


def _import_yaml():
    try:
        import yaml
    except ImportError:  # pragma: no cover - CI 里由 setup-python + pip 提供
        raise SystemExit('缺少 pyyaml：本判据依赖 YAML 解析（ci.yml 的 scripts_test 已安装）')
    return yaml


def main(argv: List[str]) -> int:
    repo = Path(__file__).resolve().parent.parent
    try:
        problems = check(repo)
    except SystemExit:
        raise
    if problems:
        for p in problems:
            print(f'✗ {p}')
        print(f'\n{WORKFLOW_REL} 的通道不成立：{len(problems)} 项')
        return 1
    if '--report' in argv:
        print('✓ workflow 存在且按 dependabot + base=dev 设闸')
        print('✓ 触发为 pull_request_target，覆盖 opened / synchronize')
        print('✓ 真的调用脚本、带 --apply、有 git push、无 `|| true`')
    else:
        print('OK: dependabot 锁重生成通道成立。')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
