#!/usr/bin/env python3
"""守门：**定时作业**跑仓库脚本时，必须显式检出活跃分支（源 CNB #586，2026-10-19）。

WHY（实测，不是推断）
---------------------
`schedule` 事件有两个默认行为，叠在一起就是「每夜跑一个月前的代码」：

1. GitHub **只读取默认分支（`main`）上的 workflow 定义**；
2. `actions/checkout` 在 `schedule` 下**默认检出的也是那个分支**。

而本仓 `main` 只由发版 PR（`dev` → `main`）推进 —— 实测 2026-10-19 它落后 `dev`
**124 个提交**。于是「每夜捕捉悄悄回归」捕捉的是很久以前的代码。

实证（前端 E2E，连续三夜）：

| 日期 | 结论 | `head_sha` |
|---|---|---|
| 10-16 | failure | `1068135f` |
| 10-17 | failure | `1068135f` |
| 10-18 | failure | `1068135f` |

三次都是 `main` 的 tip，而 10-16~10-18 之间 `dev` 上已经合了 **#2346 / #2288** 两轮
E2E 修复（`bdb96223` / `8dc80e7c` / `a070c071`）——**每夜都在重跑同一个已被修好的失败**。
同一形态在 `daily-snapshot.yml`（#1434）已经记过一次：「workflow 定义读 main，
执行代码必须显式取 dev」。那是**手动修好的一条**，没有判据，于是换了个文件又犯一次。

判据（静态、不拉网络）
----------------------
1. 扫 `.github/workflows/*.yml`，取 `on.schedule` 存在的文件；
2. 若某个 step 的 `run:` 里执行**仓库内的脚本**（`python … scripts/…`、
   `node … scripts/…`、`bash scripts/…`、`./scripts/…`）⇒ 该 job 的执行内容
   依赖仓库代码；
3. 该 job 的 `actions/checkout` step 必须显式写 `with.ref`，且值**不得**是默认分支
   （`main` / `master` / `refs/heads/main` …）——写成 `${...}` 表达式放行
   （静态读不出运行时值，与 `guard_cnb_script_task_python.py` 同口径）；
4. 该 job 里**没有** checkout step ⇒ 报红（连代码都没检出，却要跑仓库脚本）。

豁免：行内含 `schedule-ref-allow`（讲机制本身、或该 job 刻意要 main 的版本）。
豁免是**行级**的，写在 checkout step 的 `ref` 那一行或该 step 上方注释均可。

边界（有意为之）
----------------
- **不判断「该不该跑」**：只回答「跑的代码是不是它以为的那一版」；
- **不查 `workflow_dispatch`**：手动触发时可以自己选分支，且 `checkout` 默认取触发分支；
- **不验证表达式取值**：`ref: ${{ env.X }}` 放行 —— 静态判据不该猜运行时值。
  代价是「env.X 其实等于 main」看不见，收益是不用维护一套 YAML 求值器。

用法
----
    python scripts/guard_schedule_checkout_ref.py            # 扫 .github/workflows
    python scripts/guard_schedule_checkout_ref.py --root x   # 指定仓库根
退出码 0 = 通过；1 = 发现问题；2 = 输入不可用（**不得**退化成「没问题」，#171）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# 「跑仓库内代码」的三种写法。判据要回答的是「这个 job 的行为取决于仓库内容的哪一版」，
# 所以三类都算：
#   ① 入仓脚本 `python scripts/xxx.py`；
#   ② 仓库里定义的包脚本 `pnpm test:e2e` / `npm run build`（**排除** install / ci / exec
#      —— 那些只是装依赖或调外部二进制，不跑仓库代码）；
#   ③ 本地 composite action `./.github/actions/xxx`（它本身就是仓库里的代码）。
_REPO_SCRIPT = re.compile(
    r'(?:^|[\s;&|(])'
    r'(?:python3?|node|bash|sh|pnpm\s+(?:exec\s+)?\w+)?\s*'
    r'(?:\./)?(scripts/[\w./-]+)'
)

# ② 包脚本：`pnpm <script>` / `npm run <script>` / `yarn <script>`。
# 排除 install 家族（装依赖不跑仓库代码）与 `exec`（调外部二进制）。
_PKG_SCRIPT = re.compile(
    r'\b(?:pnpm|npm|yarn)\s+(?:run\s+)?(?!install\b|ci\b|add\b|exec\b|i\b)'
    r'(?P<name>[\w:.-]+)'
)

# ③ 本地 composite action。
_LOCAL_ACTION = re.compile(r'uses:\s*(?P<path>\./\.github/actions/[\w./-]+)')

# 默认分支的几种写法（写成这些就等于「跑 main 的代码」）。
_DEFAULT_BRANCH = {'main', 'master', 'refs/heads/main', 'refs/heads/master'}

ALLOW_MARK = 'schedule-ref-allow'


def _steps(job: dict) -> list[dict]:
    return [s for s in (job.get('steps') or []) if isinstance(s, dict)]


def _runs_repo_script(job: dict) -> str | None:
    """该 job 里有没有 step 跑**仓库内的代码**？返回第一个命中的东西（便于报错定位）。

    三类都算（见 `_REPO_SCRIPT` / `_PKG_SCRIPT` / `_LOCAL_ACTION` 上方注释）。
    ⚠️ 只认 `scripts/` 是不够的 —— 首版就漏了 `pnpm test:e2e`（前端 E2E 正是它），
    而那恰恰是本次最贵的那个实例。判据漏掉自己的第一个案例，是最难发现的一种空转。
    """
    for step in _steps(job):
        run = str(step.get('run') or '')
        # 去掉整行注释：注释里提到脚本不算执行（本仓判据被自己的说明文字咬过多次）。
        body = '\n'.join(
            ln for ln in run.splitlines() if not ln.lstrip().startswith('#')
        )
        m = _REPO_SCRIPT.search(body)
        if m:
            return m.group(1)
        m = _PKG_SCRIPT.search(body)
        if m:
            return f'包脚本 {m.group("name")}'
        m = _LOCAL_ACTION.search(str(step.get('uses') or ''))
        if m:
            return m.group('path')
    return None


def _checkout_ref(job: dict) -> tuple[bool, str]:
    """返回 (有没有 checkout step, ref 值)。多个 checkout 时取第一个。"""
    for step in _steps(job):
        uses = str(step.get('uses') or '')
        if not uses.startswith('actions/checkout'):
            continue
        with_ = step.get('with') or {}
        return True, str((with_ or {}).get('ref') or '').strip()
    return False, ''


def _allows(step_or_text: object) -> bool:
    return ALLOW_MARK in str(step_or_text or '')


def check_workflow(text: str) -> list[str]:
    """单个 workflow 文件的问题清单。"""
    problems: list[str] = []
    if ALLOW_MARK in text.split('\n')[0]:
        return problems
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [f'__PARSE_ERROR__:{exc}']
    if not isinstance(data, dict):
        return problems
    on = data.get('on') or data.get(True)  # PyYAML 把裸 `on:` 解析成 True
    if not isinstance(on, dict) or 'schedule' not in on:
        return problems
    for name, job in (data.get('jobs') or {}).items():
        if not isinstance(job, dict):
            continue
        script = _runs_repo_script(job)
        if not script:
            continue
        has_checkout, ref = _checkout_ref(job)
        if not has_checkout:
            problems.append(
                f'job「{name}」定时跑 `{script}`，却**没有 checkout 步骤** —— '
                '连代码都没检出就跑仓库脚本。'
            )
            continue
        if ref in _DEFAULT_BRANCH:
            problems.append(
                f'job「{name}」定时跑 `{script}`，但 checkout 的 `ref: {ref}` 是**默认分支**。'
                '`schedule` 下默认就检出默认分支，显式写成它等于没写 —— 而 `main` 只由'
                '发版 PR 推进（实测落后 `dev` 上百个提交）⇒ 每夜跑的是旧代码。'
                '修法：`ref: dev`（或 `${{ env.<名字> }}`，与 daily-snapshot 同形）。'
            )
        elif not ref:
            problems.append(
                f'job「{name}」定时跑 `{script}`，但 checkout **没写 `ref`** —— '
                '`schedule` 下默认落在默认分支（`main`），而它落后 `dev` 上百个提交。'
                '修法：显式 `with: ref: dev`。'
            )
    return problems


def check_file(path: Path) -> tuple[list[str], bool]:
    if not path.is_file():
        return [f'__MISSING__:{path}'], False
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        return [f'__UNREADABLE__:{path}: {exc}'], False
    return check_workflow(text), True


# ---- 自检探针：判据没接上时它会全绿，故每次都要跑 ----

_PROBE_BAD = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''

_PROBE_BAD_MAIN = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          ref: main
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''

_PROBE_GOOD = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          ref: dev
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''

_PROBE_EXPR = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          ref: ${{ env.SOME_REF }}
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''

# `pnpm <script>` 也算跑仓库代码（前端 E2E 的真实形态）。
_PROBE_PKG_SCRIPT = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  e2e:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v5
      - name: 安装
        run: pnpm install --frozen-lockfile
      - name: 跑
        run: pnpm test:e2e
'''

# 不跑仓库脚本的定时作业（如只 curl / 只 git push）不归本判据管。
_PROBE_NO_SCRIPT = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: ping
        run: curl -fsS https://example.com/ping
'''

# 非定时作业（PR / push）不归本判据管：它们检出的本来就是触发分支。
_PROBE_NOT_SCHEDULED = '''on:
  pull_request: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''


def self_check() -> list[str]:
    errors: list[str] = []
    if not check_workflow(_PROBE_BAD):
        errors.append('自检失败：定时跑仓库脚本却没写 ref 的样本没被报出来（判据恒绿）。')
    if not check_workflow(_PROBE_BAD_MAIN):
        errors.append('自检失败：`ref: main` 的样本没被报出来（等于没写）。')
    if check_workflow(_PROBE_GOOD):
        errors.append('自检失败：`ref: dev` 被误报。')
    if check_workflow(_PROBE_EXPR):
        errors.append('自检失败：`ref: ${{ … }}` 被误报（静态判据不该猜运行时值）。')
    if not check_workflow(_PROBE_PKG_SCRIPT):
        errors.append(
            '自检失败：定时跑 `pnpm test:e2e` 却没写 ref 的样本没被报出来'
            '（判据只认 `scripts/`，漏掉包脚本 —— 前端 E2E 正是这个形态）。'
        )
    if check_workflow(_PROBE_NO_SCRIPT):
        errors.append('自检失败：不跑仓库脚本的定时作业被误报（判据过宽）。')
    if check_workflow(_PROBE_NOT_SCHEDULED):
        errors.append('自检失败：非定时作业被误报（判据过宽）。')
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description='检查定时作业是否显式检出了活跃分支（源 CNB #586）'
    )
    ap.add_argument('--root', default=None, help='仓库根（默认本文件上两级）')
    ap.add_argument('--no-self-check', action='store_true', help='跳过自检探针（不建议）')
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    if not args.no_self_check:
        errors = self_check()
        if errors:
            for e in errors:
                print(f'❌ {e}', file=sys.stderr)
            return 2

    wf_dir = root / '.github' / 'workflows'
    if not wf_dir.is_dir():
        print(f'❌ 找不到 {wf_dir} —— 结论不可信（不得当成「没有问题」）', file=sys.stderr)
        return 2

    problems: list[str] = []
    checked = 0
    for path in sorted(wf_dir.glob('*.yml')):
        found, usable = check_file(path)
        if not usable:
            for p in found:
                print(f'❌ 输入不可用：{p}', file=sys.stderr)
            return 2
        checked += 1
        problems += [f'{path.name}: {p}' for p in found]

    if problems:
        print(f'❌ {len(problems)} 处定时作业会跑到旧代码：', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        print(
            '\n背景：`schedule` 只读默认分支上的 workflow 定义，`checkout` 默认也落在默认分支；'
            '而本仓 `main` 只由发版 PR 推进。详见 docs/dev/github-cnb-mirror.md §28.4。',
            file=sys.stderr,
        )
        return 1
    print(f'✅ {checked} 个 workflow 里，定时跑仓库脚本的都显式检出了活跃分支')
    return 0


if __name__ == '__main__':
    sys.exit(main())
