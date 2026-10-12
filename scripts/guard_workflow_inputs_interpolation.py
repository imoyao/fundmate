#!/usr/bin/env python3
"""守门：禁止把 `inputs.*` 表达式插值进 workflow 的 `run:` shell（源 CNB #148）。

WHY：`cnb-github-backfill.yml` 从 2026-10-11 起每日 schedule 定时跑，但**每一次都红**，
而且红了整整一天没人知道「为什么只花 9 秒」：

    if [ "${{ inputs.dry_run }}" = "true" ]; then
      ARGS="$ARGS --dry-run"
    fi

GitHub 的 `inputs` 上下文**只有 `workflow_dispatch` / `workflow_call` 两种事件才定义**。
`schedule` 触发时它是**未定义上下文**——表达式不会被求值成空串，而是被**原样留下**，
于是 shell 收到的是字面量：

    if [ "${{ inputs.dry_run }}" = "true" ]; then     # bash: bad substitution

步骤在第一条语句就以退出码 1 挂掉（实测 run 38179858075：22:17:56 起跑、22:18:05 结束，
9 秒即 failure）。而 `--apply` 那条正常路径**永远没被走到过**，所以脚本里的
「4 条更正待回写」也就永远回写不出去。

✅ 正确形态：**一律经 `env:` 传值**。`env:` 里的未定义上下文会被解析成空串（不落进 shell），
脚本只读环境变量；同时**不要用 `eval`**（避免把触发输入拼进命令行）。

危险信号（判据）
----------------
1. `run:` 正文里出现 `${{ inputs.` ⇒ 报错（原文形态）。
2. `run:` 正文里出现 `eval ` ⇒ 报错（把输入拼进命令行的载体；与判据 1 常同时出现）。

`if:` / `env:` / `with:` 里用 `inputs.*` **是安全的**（表达式上下文），不在判据内。

边界
----
- 只看 `.github/workflows/*.yml` 的 `run:`，不拉网络。
- **只对 schedule 也触发本 workflow 的情形报警**？不区分——守卫按「一律经 env 传值」这条
  统一要求，因为区分需要推断事件矩阵，容易漏（`on:` 里同时有 schedule 与 dispatch 时，
  同一份 `run:` 就是坏的），而统一写法在任何事件下都对。
- 豁免：在 `run:` 上一行写 `# inputs-interpolation-allow: <理由>` 可放行（仅限讲解本机制
  的自检探针类场景）。

用法
----
    python scripts/guard_workflow_inputs_interpolation.py            # 扫 .github/workflows
    python scripts/guard_workflow_inputs_interpolation.py --file x   # 只扫指定文件
退出码 0 = 通过，1 = 发现问题。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# 在 `run:` 正文里直接出现即为危险（表达式上下文如 `if:` / `env:` 不在扫描范围）。
RE_INPUTS_EXPR = re.compile(r'\$\{\{\s*inputs\.')
RE_EVAL = re.compile(r'(^|[\s;&|(])eval\s')

ALLOW_MARKER = 'inputs-interpolation-allow'


def _iter_run_steps(data: dict):
    """产出 (job 名, step 序号, step 名, run 正文) —— 只取带 `run:` 的步骤。"""
    jobs = (data or {}).get('jobs')
    if not isinstance(jobs, dict):
        return
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        for i, step in enumerate(job.get('steps') or []):
            if not isinstance(step, dict):
                continue
            run = step.get('run')
            if isinstance(run, str):
                yield job_name, i, step.get('name') or '', run


def _allowed(step: dict, run: str) -> bool:
    """步骤级豁免：`if:`/`name:` 里或 run 上一行注释写了 allow 标记。"""
    if ALLOW_MARKER in str(step.get('name') or ''):
        return True
    return ALLOW_MARKER in run


def check_workflow(data: dict, label: str = '') -> list[str]:
    problems: list[str] = []
    for job_name, i, step_name, run in _iter_run_steps(data or {}):
        where = f'{label} jobs.{job_name}.steps[{i}]' + (f'（{step_name}）' if step_name else '')
        # 去掉 run 里的注释行，避免「注释里讲这个坑」被误判。
        code = '\n'.join(
            line for line in run.splitlines() if not line.lstrip().startswith('#')
        )
        if RE_INPUTS_EXPR.search(code):
            problems.append(
                f'{where}：`run:` 里直接插值了 `${{{{ inputs.* }}}}`。'
                '`inputs` 上下文只有 workflow_dispatch / workflow_call 才定义，'
                'schedule 触发时表达式**不被求值**、字面量落进 shell ⇒ '
                '`bash: bad substitution`，步骤首行即挂（实测 #148：9 秒 failure）。'
                '改法：经 `env:` 传值（未定义上下文在 env 里解析成空串），脚本里只读环境变量。'
            )
        if RE_EVAL.search(code):
            problems.append(
                f'{where}：`run:` 里用了 `eval`。把触发输入拼进命令行是命令注入面，'
                '也是上面那种「拼字符串再执行」写法的载体。改用 bash 数组：'
                '`args=(--apply); [ -n "$X" ] && args+=(--since "$X"); python x.py "${args[@]}"`。'
            )
    return problems


def self_check() -> list[str]:
    """探针：守门通过 ≠ 守门有效（本仓老规矩，判据写坏过一次就会全绿放行）。"""
    errors: list[str] = []

    # 合法形态：env 传值 + bash 数组，不该报错。
    ok = {
        'jobs': {
            'j': {
                'steps': [
                    {
                        'name': 'run',
                        'run': 'args=(--apply)\npython x.py "${args[@]}"\n',
                        'env': {'DRY_RUN': '${{ inputs.dry_run }}'},
                    }
                ]
            }
        }
    }
    if check_workflow(ok):
        errors.append('自检探针失败：合法的 env 传值 + 数组形态被误报。')

    # 判据 1：run 里插值 inputs。
    bad1 = {
        'jobs': {
            'j': {
                'steps': [
                    {
                        'name': 'run',
                        'run': 'if [ "${{ inputs.dry_run }}" = "true" ]; then echo x; fi\n',
                    }
                ]
            }
        }
    }
    if not check_workflow(bad1):
        errors.append('自检探针失败：`run:` 里插值 inputs 没被判据 1 报错。')

    # 判据 2：run 里用 eval。
    bad2 = {'jobs': {'j': {'steps': [{'name': 'run', 'run': 'eval python x.py $ARGS\n'}]}}}
    if not check_workflow(bad2):
        errors.append('自检探针失败：`run:` 里用 eval 没被判据 2 报错。')

    # 注释豁免：讲解这个坑的注释行不该被当成代码。
    ok_comment = {
        'jobs': {
            'j': {
                'steps': [
                    {
                        'name': 'run',
                        'run': '# 反例：${{ inputs.dry_run }} 不要插进 run\nargs=(--apply)\n',
                    }
                ]
            }
        }
    }
    if check_workflow(ok_comment):
        errors.append('自检探针失败：`run:` 里**注释掉**的反例被误报。')

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description='检查 workflow 的 run: 是否插值了 inputs.*')
    ap.add_argument('--file', default=None, help='只检查该文件（默认扫 .github/workflows/*.yml）')
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    problems = self_check()

    if args.file:
        paths = [Path(args.file)]
    else:
        paths = sorted((root / '.github/workflows').glob('*.y*ml'))

    for path in paths:
        if not path.exists():
            print(f'⚠️ 找不到 {path}，跳过')
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        except yaml.YAMLError as exc:
            problems.append(f'{path} 不是合法 YAML：{exc}')
            continue
        if not isinstance(data, dict):
            continue
        problems += check_workflow(data, label=str(path.name))

    if problems:
        print('❌ workflow `inputs` 插值检查未通过：')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('✅ workflow 的 run: 未插值 inputs.*（均经 env 传值）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
