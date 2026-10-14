#!/usr/bin/env python3
"""守门：git-sync 的 push 目标分支**不得包含 `main`**（源 CNB #172，2026-10-13）。

WHY：本仓的权威源是 GitHub，`main` 只由 GitHub 的发版 PR 推进。而 git-sync 插件在
**不指定 `branch`** 时执行 `git push target --all` —— 把 CNB 的 `main` 一并推给 GitHub。
两侧各自长出独有提交，`main` 就此分叉（实测 2026-10-13：CNB `main` 独有 31 /
GitHub `main` 独有 27，**交集 0**）。分叉不是理论风险：`crontab` 只能挂在具体分支下，
`.cnb.yml` 挂在 `main` ⇒ 真正执行的可能是别人那份。

判据（三条，静态、不拉网络）
----------------------------
1. **push 形态的插件任务必须显式写 `branch`**。不写 = `--all` = 会推 `main`，报错。
   `sync_mode: pull` 的任务不受此约束（它拉不推）。
2. **`branch` 的值不得是 `main` / `*` / `--all`**（等价于推 main 的几种写法）。
3. **顶层分支键不得只写 `main` 就套 push 任务**——本仓 `main` 在外推路径上必须被排除，
   显式推 `main` 的字段（`"main":` 下挂 push 插件任务）一律报错。

边界（有意为之）
----------------
- **只看 `.cnb.yml`、不拉网络**：判断配置形状，不判断 push 实际会不会成功；
- **不猜 `${VAR}` 的运行时值**：`branch: ${CNB_BRANCH}` 这类**放行**（它的取值由段所在
  分支的 glob 决定，而 glob 段本身已由判据 3 的「排除 main」语义覆盖）；
  本守卫只拦「字面写出 main / 把 main 当推送目标」的确定形态。

用法
----
    python scripts/guard_git_sync_push_scope.py            # 检查仓库根 .cnb.yml
    python scripts/guard_git_sync_push_scope.py --file x   # 检查指定文件
退出码 0 = 通过，1 = 发现问题。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# git-sync 插件任务的识别：用了这个镜像，或调用同名插件。
GIT_SYNC_IMAGE = 'tencentcom/git-sync'

# 能表达「推 main」的几种写法。`branch` 命中即报错。
FORBIDDEN_BRANCHES = {'main', '*', '--all', 'refs/heads/main'}

# glob 段里显式排除 main 的形态（`**/!(main|dev)` 等）。顶层键命中即认为「已排除 main」。
EXCLUDE_HINT = '!(main'


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    return data if isinstance(data, dict) else {}


def _walk_stage_items(data: dict):
    """产出 (顶层分支键, 事件名, 插件任务对象)。与 guard_secret_imports.py 同形。"""
    for branch, events in (data or {}).items():
        if not isinstance(events, dict) or branch in ('.mirror-job',):
            continue
        for event, jobs in events.items():
            for job in jobs or []:
                if not isinstance(job, dict):
                    continue
                for stage in job.get('stages') or []:
                    if isinstance(stage, dict):
                        yield branch, event, stage


def _is_git_sync(stage: dict) -> bool:
    return GIT_SYNC_IMAGE in str(stage.get('image') or '')


def _is_pull(stage: dict) -> bool:
    return str((stage.get('settings') or {}).get('sync_mode') or '').lower() == 'pull'


def check_push_scope(data: dict) -> list[str]:
    """判据 1 + 2：push 形态的 git-sync 任务必须显式、且非 main 地指定 `branch`。"""
    problems: list[str] = []
    for branch_key, event, stage in _walk_stage_items(data):
        if not _is_git_sync(stage):
            continue
        if _is_pull(stage):
            # 拉取方向不推 GitHub，不受本判据约束。
            continue
        settings = stage.get('settings') or {}
        if not isinstance(settings, dict):
            continue
        target = str(settings.get('branch') or '').strip()
        if not target:
            problems.append(
                f'`{branch_key}` → `{event}` 的 git-sync push 任务**没有指定 `branch`**。'
                '插件在不指定时执行 `git push target --all`，会把 `main` 一并推给 GitHub，'
                '而 `main` 的权威源是 GitHub（只由发版 PR 推进）⇒ 两侧 `main` 分叉（#172）。'
                '请显式写明要推的分支（本仓为 `dev` / `${CNB_BRANCH}`）。'
            )
            continue
        if target in FORBIDDEN_BRANCHES:
            problems.append(
                f'`{branch_key}` → `{event}` 的 git-sync push 目标分支是 `{target}`，'
                '而 `main` 不得由 CNB 侧外推（GitHub 为权威源，见 AGENTS.md「双端协作」）。'
            )
    return problems


def check_top_level_main(data: dict) -> list[str]:
    """判据 3：`main` 这个顶层分支键下不得挂 git-sync push 任务。

    本仓把外推任务分两处：`main` 下的 `push:`（推 dev）与 `"**/!(main|dev)"` 下的
    `push:`（推当前功能分支）。若有人把 git-sync push 挂到 `main` 键下并想借此推 main，
    判据 1/2 可能被 `branch: ${CNB_BRANCH}` 绕过——故这里单独拦「`main` 键 + push 插件」。
    """
    problems: list[str] = []
    main_node = data.get('main')
    if not isinstance(main_node, dict):
        return problems
    for event, jobs in main_node.items():
        for job in jobs or []:
            if not isinstance(job, dict):
                continue
            for stage in job.get('stages') or []:
                if isinstance(stage, dict) and _is_git_sync(stage) and not _is_pull(stage):
                    settings = stage.get('settings') or {}
                    if str(settings.get('branch') or '').strip() == '${CNB_BRANCH}':
                        problems.append(
                            f'`main` → `{event}` 的 git-sync push 用了 `branch: ${{CNB_BRANCH}}`。'
                            '该值在 `main` 键下解析为 `main` 本身，等于把 `main` 推给 GitHub。'
                            '功能分支的推送请放到 `"**/!(main|dev)"` 段（#172）。'
                        )
    return problems


def self_check() -> list[str]:
    """探针：判据写坏了守卫会全绿，故用最小真实形态一正一反验证。"""
    errors: list[str] = []

    def push_task(branch=None, sync_mode=None, key='dev'):
        settings = {'target_url': 'https://github.com/o/r.git'}
        if branch is not None:
            settings['branch'] = branch
        if sync_mode:
            settings['sync_mode'] = sync_mode
        return {
            key: {
                'push': [
                    {
                        'stages': [
                            {'image': GIT_SYNC_IMAGE, 'imports': ['x.yml'], 'settings': settings}
                        ]
                    }
                ]
            }
        }

    # 合法：显式只推 dev。
    if check_push_scope(push_task('dev')):
        errors.append('自检探针失败：合法的 `branch: dev` 被判为不合规。')
    # 合法：pull 不加 branch。
    if check_push_scope(push_task(None, 'pull')):
        errors.append('自检探针失败：`sync_mode: pull` 被判为不合规。')
    # 合法：glob 段里用 ${CNB_BRANCH}。
    if check_push_scope(push_task('${CNB_BRANCH}', key='**/!(main|dev)')):
        errors.append('自检探针失败：glob 段的 `${CNB_BRANCH}` 被判为不合规。')
    # 判据 1：不写 branch。
    if not check_push_scope(push_task(None)):
        errors.append('自检探针失败：push 任务不写 `branch`（= `--all`，会推 main）没被拦。')
    # 判据 2：显式推 main。
    for bad in ('main', '*', '--all'):
        if not check_push_scope(push_task(bad)):
            errors.append(f'自检探针失败：`branch: {bad}` 没被拦。')
    # 判据 3：main 键 + ${CNB_BRANCH}。
    if not check_top_level_main(push_task('${CNB_BRANCH}', key='main')):
        errors.append('自检探针失败：`main` 键下用 `${CNB_BRANCH}` 推分支没被拦。')
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='检查 git-sync 的 push 目标分支不含 main（CNB #172）')
    ap.add_argument('--file', default=None, help='待检查文件（默认仓库根 .cnb.yml）')
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    path = Path(args.file) if args.file else root / '.cnb.yml'
    if not path.exists():
        print(f'⚠️ 找不到 {path}，跳过')
        return 0

    problems = self_check()
    try:
        data = _load(path)
    except yaml.YAMLError as exc:
        print(f'❌ {path} 不是合法 YAML：{exc}')
        return 1

    problems += check_push_scope(data)
    problems += check_top_level_main(data)

    if problems:
        print(f'❌ {path} 的 git-sync push 目标分支检查未通过：')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('✅ git-sync push 目标分支合规（不含 main）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
