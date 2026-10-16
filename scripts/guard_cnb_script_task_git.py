#!/usr/bin/env python3
"""守门：`.cnb.yml` 里**跑 git 驱动脚本**的 stage 必须先把 git 装好。

WHY（源 CNB #517，2026-10-16 实测）
----------------------------------
`python:3.12-slim` **不含 git**（官方 slim 镜像一律不带）。而本仓多处脚本任务在跑
`scripts/**/*.py`，其中 `machine_branch` / `check_branch_divergence` /
`check_cross_repo_dev_divergence` / `dev_converge` / `check_issue_refs` 都是
`subprocess.run(['git', ...])` 驱动的。缺 git 时：

    FileNotFoundError: [Errno 2] No such file or directory: 'git'

报错**指向脚本内部某一行**（`_git(['rev-parse', ...])`），**不指向「容器里没有 git」**
—— 与 CNB #461（默认镜像没有 python，报 `sh: line N: python: command not found`）
是**同一类「执行环境缺失」**，只是深了一层。#461 补了 `docker.image`，却没问
「这个镜像里有没有 git」，于是同一个坑换了个形态又踩一次。

更坏的是它的**两种失败形态**：

| 形态 | 位置 | 表现 |
|---|---|---|
| **硬红** | `dev` push 的机器分支通道 | 构建报错，看得见（就是本卡的正文） |
| **假绿** | 镜像 job 的「分支分叉自检」 | 脚本崩了，但 stage 末尾 `exit 0` ⇒ **报绿**，自检从未真正跑过 |

后者与 #171 / #450 同族：**不是缺功能，是缺一条能问出「这段代码跑得起来吗」的判据**。

判据
----
1. 扫 `scripts/**/*.py`，凡**真的调用 git**（`subprocess.run(['git', …])` / `_git(` 家族）
   的记入「git 驱动脚本集」——**从代码里推导，不手写名单**（手写名单会随新脚本失效）；
2. 再扫 `.cnb.yml`：某 stage 的 `script` 里**调用这些脚本**（`python <相对路径>`） ⇒ 该
   stage 是 git 驱动；
3. 该 stage 的脚本必须**自带 git 供给**——正文里出现安装语句（`apt-get/apk/yum/dnf …
   install … git`）或显式 `command -v git` 自检；
4. 读不到输入（文件不存在 / 解析失败 / 重复键遮蔽）⇒ 退 2 或 1 并声明「结论不可信」，
   **不得**退化成「没问题」（#171 的失败态纪律）。

边界（有意为之）
----------------
- **只认「当前 stage 自证」**：不跨 stage 推断「前面的 stage 装过了」——CNB 里各 stage 的
  执行环境不保证共享，跨 stage 推断一旦猜错就是另一个假绿。
- **不校验镜像里到底有没有 git**：拉镜像要联网，且判据不该猜运行时内容；
  「脚本里自证」是唯一静态可查的口径。
- **`${VAR}` 形态照旧放行**（不猜运行时值），与 `guard_cnb_script_task_python.py` 同口径。
- **只认 `scripts/` 下的 `.py`**：这些是本仓入仓的脚本；`pip install` 进来的第三方包
  （如 akshare）不在此判据内（它们的 git 依赖应在镜像层解决）。

用法
----
    python scripts/guard_cnb_script_task_git.py            # 检查仓库根 .cnb.yml
    python scripts/guard_cnb_script_task_git.py --file x   # 检查指定文件
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# 脚本里调用 git 的两种写法：`subprocess.run(['git', …])` 或本仓的 `_git([…])` 包装。
# 后者覆盖面更广（`_git(['rev-parse', …])` / `_git(['push', …])`），且是各 bridge 脚本的统一入口。
_GIT_IN_SCRIPT = re.compile(
    r"subprocess\.(run|check_output|Popen)\s*\(\s*\[\s*['\"]git['\"]"
    r'|_git\s*\('
)

# `python <path>.py`（允许 `python3` 与 `./` 前缀）——从 .cnb.yml 的 script 里抽出被调脚本。
_PY_INVOKE = re.compile(r'\bpython3?\s+(\./)?(?P<path>[\w./-]+\.py)')

# 「自带 git 供给」：包管理器装 git，或显式 `command -v git` 自检。
_GIT_INSTALL = re.compile(
    r'(apt-get|apt|apk|yum|dnf|microdnf)\b[^\n]*\binstall\b[^\n]*\bgit\b'
    r'|apk\s+add\b[^\n]*\bgit\b'
)
_GIT_PROBE = re.compile(r'command\s+-v\s+git\b')


def git_driven_scripts(root: Path) -> set[str]:
    """从 `scripts/**/*.py` 里推导出「真的调用 git」的脚本（仓库相对路径，正斜杠）。"""
    found: set[str] = set()
    scripts_dir = root / 'scripts'
    if not scripts_dir.is_dir():
        return found
    for py in scripts_dir.rglob('*.py'):
        try:
            text = py.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        if _GIT_IN_SCRIPT.search(text):
            found.add(py.relative_to(root).as_posix())
    return found


def _invoked_scripts(script: str) -> set[str]:
    return {m.group('path') for m in _PY_INVOKE.finditer(str(script))}


def _provides_git(script: str) -> bool:
    s = str(script)
    return bool(_GIT_INSTALL.search(s) or _GIT_PROBE.search(s))


class _DupKeyLoader(yaml.SafeLoader):
    """保留重复键的 SafeLoader（与 `guard_cnb_script_task_python.py` 同源、各自持有）。"""

    def __init__(self, stream):
        super().__init__(stream)
        self.duplicates: list[tuple[str, int]] = []

    def construct_mapping(self, node, deep=False):
        keys: list[str] = []
        for key_node, _ in node.value:
            try:
                keys.append(str(self.construct_object(key_node, deep=True)))
            except yaml.YAMLError:
                continue
        for key in set(keys):
            if keys.count(key) > 1:
                self.duplicates.append((key, node.start_mark.line + 1))
        return super().construct_mapping(node, deep=deep)


def _find_duplicate_keys(text: str) -> list[tuple[str, int]]:
    loader = _DupKeyLoader(text)
    try:
        loader.get_single_data()
    except yaml.YAMLError:
        return []
    finally:
        try:
            loader.dispose()
        except Exception:  # noqa: BLE001 - dispose 失败不该影响判据
            pass
    return loader.duplicates


def check_text(text: str, git_scripts: set[str] | None = None, root: Path | None = None) -> list[str]:
    problems: list[str] = []
    # 先探重复键：被覆盖掉的 job 在 safe_load 后不存在，本守卫会对它一无所知、报假绿。
    dups = _find_duplicate_keys(text)
    if dups:
        seen = ', '.join(f'`{k}`（第 {ln} 行起）' for k, ln in dups)
        return [
            f'输入不可信：`.cnb.yml` 存在重复键 {seen}。'
            '`yaml.safe_load` 会用后者覆盖前者，被覆盖段的 job **不会进入本次检查**'
            '—— 本守卫在遮蔽状态下给出的「git 均已供给」是假绿灯。'
            '先跑 `python scripts/guard_cnb_yml_duplicate_keys.py` 修掉重复键再复检。'
        ]
    if git_scripts is None:
        git_scripts = git_driven_scripts(root or Path(__file__).resolve().parents[1])
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return []
    for branch, events in data.items():
        if branch.startswith('.') or not isinstance(events, dict):
            continue
        for event, jobs in events.items():
            if not isinstance(jobs, list):
                continue
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                for stage in job.get('stages') or []:
                    if not isinstance(stage, dict):
                        continue
                    script = stage.get('script') or stage.get('commands')
                    if not script:
                        continue
                    hit = _invoked_scripts(script) & git_scripts
                    if not hit:
                        continue
                    if not _provides_git(script):
                        problems.append(
                            f'`{branch}` / `{event}` / job「{job.get("name")}」'
                            f'/ stage「{stage.get("name")}」调用 git 驱动脚本 '
                            f'{sorted(hit)}，却**没有在脚本里供给 git**。'
                            '`python:3.12-slim` 不含 git ⇒ 会以 '
                            "`FileNotFoundError: … 'git'` 收场，"
                            '而报错指向脚本内部某行、不指向容器。'
                            '修法：脚本开头加 '
                            '`command -v git >/dev/null 2>&1 || '
                            'apt-get update -qq && apt-get install -y -qq '
                            '--no-install-recommends git`。'
                        )
    return problems


def check_file(path: Path, root: Path | None = None) -> tuple[list[str], bool]:
    """返回 (问题列表, 输入是否可用)。"""
    if not path.is_file():
        return [f'__MISSING__:{path}'], False
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        return [f'__UNREADABLE__:{path}: {exc}'], False
    try:
        return check_text(text, root=root), True
    except yaml.YAMLError as exc:
        return [f'__PARSE_ERROR__:{path}: {exc}'], False


# ---- 自检探针（真实源码 + 合成样本）----

_PROBE_BAD = (
    'dev:\n'
    '  push:\n'
    '    - name: bad\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: |\n'
    '            python scripts/bridge/machine_branch.py --apply\n'
)

_PROBE_GOOD = (
    'dev:\n'
    '  push:\n'
    '    - name: ok\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: |\n'
    '            command -v git >/dev/null 2>&1 || apt-get install -y -qq git\n'
    '            python scripts/bridge/machine_branch.py --apply\n'
)

# 不调 git 脚本的 stage 不该被本判据管（防判据过宽）。
_PROBE_NO_GIT = (
    'dev:\n'
    '  push:\n'
    '    - name: no-git\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/bridge/github_cnb_issues.py --apply\n'
)

# 遮蔽探针：顶层 `dev:` 出现两次时，被覆盖段的坏 job 在 safe_load 后不存在 ⇒
# 守卫对它一无所知、报出一个看起来正常的 ✅（源 #463 同款）。
_PROBE_SHADOWED = (
    'dev:\n'
    '  push:\n'
    '    - name: shadowed-bad\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/bridge/machine_branch.py --apply\n'
    'dev:\n'
    '  push:\n'
    '    - name: winner\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: echo hi\n'
)


def self_check() -> list[str]:
    """正反 + 遮蔽探针：判据没接上时守卫会全绿，故每次都要跑。"""
    errors: list[str] = []
    root = Path(__file__).resolve().parents[1]
    git_scripts = git_driven_scripts(root)
    if 'scripts/bridge/machine_branch.py' not in git_scripts:
        errors.append(
            '自检失败：无法从源码认领 `scripts/bridge/machine_branch.py` 是 git 驱动 —— '
            '推导逻辑失效，后续判据都会恒绿。'
        )
    if not check_text(_PROBE_BAD, git_scripts):
        errors.append('自检失败：调用 git 驱动脚本却不供给 git 的样本没被报出来（判据恒绿）。')
    if check_text(_PROBE_GOOD, git_scripts):
        errors.append('自检失败：合法样本（自带 git 供给）反被误报。')
    if check_text(_PROBE_NO_GIT, git_scripts):
        errors.append('自检失败：不调 git 样本被误报（判据过宽）。')
    if not check_text(_PROBE_SHADOWED, git_scripts):
        errors.append('自检失败：重复键遮蔽样本没被报出来（在看不见的输入上给了假绿灯）。')
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='检查 .cnb.yml 的 git 脚本任务是否供给 git')
    parser.add_argument('--file', default=None, help='待检查的 .cnb.yml（默认仓库根）')
    parser.add_argument('--root', default=None, help='仓库根（用于推导 git 驱动脚本，默认本文件上两级）')
    parser.add_argument('--no-self-check', action='store_true', help='跳过自检探针（不建议）')
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    if not args.no_self_check:
        errors = self_check()
        if errors:
            for e in errors:
                print(f'❌ {e}', file=sys.stderr)
            return 2

    path = Path(args.file) if args.file else root / '.cnb.yml'
    problems, usable = check_file(path, root=root)
    if not usable:
        for p in problems:
            print(f'❌ 输入不可用：{p}', file=sys.stderr)
        return 2
    if problems:
        for p in problems:
            print(f'❌ {p}', file=sys.stderr)
        return 1
    print('✅ .cnb.yml 的 git 脚本任务均自带 git 供给')
    return 0


if __name__ == '__main__':
    sys.exit(main())
