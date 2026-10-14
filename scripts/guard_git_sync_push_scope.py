#!/usr/bin/env python3
"""守门：git-sync 的**两个方向**都只能作用在 `dev` / 功能分支上，`main` 一律不碰
（源 CNB #172 / #167，2026-10-13 ~ 10-14）。

WHY：**CNB 的 `main` 与 GitHub 的 `main` 没有任何关系**（用户口径，CNB #167）。cross-repo-ref-allow
CNB `main` 只由 CNB 自己的发版 PR 推进，不是 GitHub `main` 的镜像，也不向 GitHub 外推。
两条方向各有一个「默认行为会碰 `main`」的陷阱：

- **push 方向**：不指定 `branch` ⇒ 插件执行 `git push target --all`，把 CNB 的 `main`
  一并推给 GitHub。两侧各自长出独有提交 ⇒ `main` 分叉（实测 2026-10-13：CNB 31 /
  GitHub 27，**交集 0**）。
- **pull 方向**（CNB #167 收尾新增）：**不指定 `branch` 同样会碰 `main`**——
  插件 `entrypoint.sh` 的 pull 分支在不写 `branch` 时取 target 的**全部**分支，
  逐个 `git pull --rebase target <b>` 后 `git push origin <b> --force`
  ⇒ **把 GitHub 的 `main` force 覆盖到 CNB 的 `main`**（不看是否 fast-forward）。
  「pull 只拉不推、不会分叉」是**直觉错误**：它会 force 写回本地 origin。

判据（四条，静态、不拉网络）
----------------------------
1. **两个方向的插件任务都必须显式写 `branch`**。不写 = `--all`（push）或「全分支
   force 写回 origin」（pull），两者都会碰 `main`，一律报错。
2. **`branch` 的值不得是 `main` / `*` / `--all`**（等价于推/覆盖 main 的几种写法）。
3. **顶层分支键不得只写 `main` 就套 push 任务**——本仓 `main` 在外推路径上必须被排除，
   显式推 `main` 的字段（`"main":` 下挂 push 插件任务）一律报错。
4. **每一个 job 必须带 `name`**（列表形态 `- name: ...` + `stages:`，不能把 `stages:` 直接
   裸挂在事件下）。裸 `stages:` 的 job 在构建详情页**查不到 stage**：外部看是绿的，
   实际推没推上去无从判断 —— 比红灯更危险的「假绿」（CNB #172 实测：
   `crontab: 30` 的兜底 push 长期显示绿，但 `sha` 一直停在旧提交，从未推上去）。
5. **git-sync 任务的挂载分支键必须与它 `settings.branch` 的目标分支一致**，
   或该分支键是能覆盖目标分支的 glob（如 `**/!(main|dev)` 覆盖功能分支）。
   —— **判据 1~4 全是「配置形状」，这一条判「跑在什么地方」。** 前四条都通过、这条
   不过的形态，实测绿了三天（CNB #269）：

   | 项 | 值 |
   |---|---|
   | `branch: dev` | ✅ 写对了（判据 1/2 通过） |
   | 挂载位置 | ❌ 挂在 `main:` 键下 |
   | 后果 A | `dev` 的 push 构建**根本不含这个 job**（`get-build-stage` 返回「没有查询到该stage信息」） |
   | 后果 B | `main` 的 cron 构建里工作区只有 `main`，插件打 `Warning: Branch dev does not exist locally, skipping push` 后跳过 |
   | 构建状态 | ✅ **success**（三天零信号） |

   根因是 runner 的检出行为：`git fetch origin "refs/heads/<分支键>"` +
   `git checkout -f -B "<分支键>" <sha>` —— **工作区里只有那个分支键对应的分支**，
   而 git-sync 只推「工作区里存在的分支」。放错分支键 ⇒ 要么不含 job、要么找不到分支。

边界（有意为之）
----------------
- **只看 `.cnb.yml`、不拉网络**：判断配置形状，不判断 push 实际会不会成功；
- **不猜 `${VAR}` 的运行时值**：`branch: ${CNB_BRANCH}` 这类**放行**（它的取值由段所在
  分支的 glob 决定，而 glob 段本身已由判据 3 的「排除 main」语义覆盖）；
  本守卫只拦「字面写出 main / 把 main 当推送（或覆盖）目标」的确定形态。
- **判据 5 只比字面量**：`branch: ${...}` 跳过（无从静态求值），`branch: dev` 这类字面量
  才比。它判的是「配置里挂载位置 vs 目标分支是否自洽」，**不拉网络**、不验真实构建。
- **判据 1 对 pull 方向豁免的只有「拉取后不写回 origin」这一种**——而插件源码里
  pull **总会** `push origin --force`，故本仓口径是不设豁免：pull 也必须写 `branch`。

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


# 两个方向的「不写 branch 会怎样」——报错文案要各自说清，别让读者猜。
_NO_BRANCH_REASON = {
    'push': (
        '插件在不指定时执行 `git push target --all`，会把 `main` 一并推给 GitHub，'
        '而 `main` 的权威源是 GitHub（只由发版 PR 推进）⇒ 两侧 `main` 分叉（#172）。'
        '请显式写明要推的分支（本仓为 `dev` / `${CNB_BRANCH}`）。'
    ),
    'pull': (
        '插件在不指定时取 target 的**全部**分支，逐个 `git pull --rebase` 后执行 '
        '`git push origin <b> --force` —— 会**把 GitHub 的 `main` force 覆盖到 CNB 的 `main`**'
        '（不看是否 fast-forward）。而 CNB 的 `main` 与 GitHub 的 `main` 没有任何关系'
        '（用户口径，CNB #167）。请显式写 `branch: dev`，只拉 dev。'
    ),
}


def check_push_scope(data: dict) -> list[str]:
    """判据 1 + 2：**两个方向**的 git-sync 任务都必须显式、且非 main 地指定 `branch`。

    pull 方向同样受限（CNB #167）：插件源码里 pull 分支**总会** `git push origin --force`
    写回本地 origin，不写 `branch` 时就是「GitHub `main` force 覆盖 CNB `main`」。
    """
    problems: list[str] = []
    for branch_key, event, stage in _walk_stage_items(data):
        if not _is_git_sync(stage):
            continue
        settings = stage.get('settings') or {}
        if not isinstance(settings, dict):
            continue
        direction = 'pull' if _is_pull(stage) else 'push'
        target = str(settings.get('branch') or '').strip()
        if not target:
            problems.append(
                f'`{branch_key}` → `{event}` 的 git-sync {direction} 任务**没有指定 `branch`**。'
                + _NO_BRANCH_REASON[direction]
            )
            continue
        if target in FORBIDDEN_BRANCHES:
            problems.append(
                f'`{branch_key}` → `{event}` 的 git-sync {direction} 目标分支是 `{target}`，'
                '而 `main` 不得由 CNB 侧外推、也不得被 GitHub 侧覆盖'
                '（CNB `main` 与 GitHub `main` 无关系，见 AGENTS.md「双端协作」）。'
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


def _walk_jobs(data: dict):
    """产出 (顶层分支键, 事件名, job 对象, job 是否带 name)。"""
    for branch, events in (data or {}).items():
        if not isinstance(events, dict) or branch in ('.mirror-job',):
            continue
        for event, jobs in events.items():
            if not isinstance(jobs, list):
                # 事件值不是列表 = 裸 `stages:` 直接挂在事件下（无 job 包裹）⇒ 假绿形态。
                yield branch, event, jobs, False
                continue
            for job in jobs:
                if isinstance(job, dict):
                    yield branch, event, job, bool(str(job.get('name') or '').strip())


def check_named_jobs(data: dict) -> list[str]:
    """判据 4：每个 job 必须带 `name`，且必须包在列表里。

    不带 name 的 job（裸 `stages:`）在构建详情页查不到 stage，绿了也不知道推没推上去。
    """
    problems: list[str] = []
    for branch_key, event, job, named in _walk_jobs(data):
        if named:
            continue
        # 只对真正带 stages 的节点报错，避免误伤 `.mirror-job:` 之类锚点（已在 _walk_jobs 跳过）。
        has_stages = isinstance(job, dict) and 'stages' in job
        if not isinstance(job, dict) or has_stages:
            problems.append(
                f'`{branch_key}` → `{event}` 的 job **没有 `name`**（`stages:` 直接裸挂在事件下）。'
                '这种形态的 job 在构建详情页查不到 stage：外部显示绿也无从判断实际有没有跑/推成功'
                '—— 即「假绿」（CNB #172）。请改成列表形态：`- name: <作业名>` 换行缩进 `stages:`。'
            )
    return problems


# 能覆盖任意分支的 glob 形态（`**/!(main|dev)`、`**` 等）：目标分支落在 glob 之内即放行。
def _glob_covers_branch(branch_key: str, target: str) -> bool:
    """`branch_key` 是否能覆盖 `target` 分支（仅处理本仓会用到的两种形态）。"""
    key = branch_key.strip().strip('"').strip("'")
    if key == target:
        return True
    # `**/!(main|dev)` 形态：排除 main/dev ⇒ 功能分支（含 feat/*、fix/*）都在其内。
    if '!(' in key and ')' in key:
        inner = key.split('!(', 1)[1].split(')', 1)[0]
        excluded = {x.strip() for x in inner.split('|') if x.strip()}
        if target not in excluded:
            return True
    # `**` / `*` 兜底：覆盖一切。
    if key in ('**', '*', '$'):
        return True
    return False


def check_branch_key_matches_target(data: dict) -> list[str]:
    """判据 5：git-sync 挂在哪个分支键下，决定 runner 检出哪个分支。

    判据 1~4 只判「配置的形状」；这条判「它跑在什么地方」。CNB #269 实测的形态是
    两条都合法、合起来致命：
      - `settings.branch: dev` 写对了；
      - 但作业挂在 `main:` 键下 ⇒ `dev` 的 push 不含它，
        `main` 的 cron 里工作区没有 `dev` ⇒ 插件 `Warning: ... skipping push` 后跳过，
        **构建报 success**（三天零信号）。

    根因写在 runner 日志里：`git fetch origin "refs/heads/<分支键>"` +
    `git checkout -f -B "<分支键>" <sha>` —— 工作区里只有分支键对应的分支。
    """
    problems: list[str] = []
    for branch_key, event, stage in _walk_stage_items(data):
        if not _is_git_sync(stage):
            continue
        settings = stage.get('settings') or {}
        if not isinstance(settings, dict):
            continue
        target = str(settings.get('branch') or '').strip()
        # `${VAR}` / 空值由判据 1 负责，这里只比「字面目标分支 vs 挂载分支键」。
        if not target or target.startswith('${'):
            continue
        if _glob_covers_branch(branch_key, target):
            continue
        direction = 'pull' if _is_pull(stage) else 'push'
        problems.append(
            f'`{branch_key}` → `{event}` 的 git-sync {direction} 要操作 `{target}`，'
            f'但作业**挂在 `{branch_key}` 分支键下** —— runner 只检出「挂载分支键」对应的分支'
            f'（`git fetch origin refs/heads/{branch_key}` + `git checkout -f -B "{branch_key}"`），'
            f'工作区里没有 `{target}` ⇒ 插件打一行 '
            f'`Warning: Branch {target} does not exist locally, skipping push` 就跳过，'
            f'**而构建仍报 success**；若挂错的是 `main`，则 `{target}` 的 push 构建里'
            f'**根本不含这个 job**（`get-build-stage` 查不到 stage）。'
            f'请把作业挂到 `{target}:` 键下（或能覆盖它的 glob，如 `"**/!(main|dev)"`）。'
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
    # 合法：pull 显式只拉 dev（#167 起 pull 也必须写 branch）。
    if check_push_scope(push_task('dev', 'pull')):
        errors.append('自检探针失败：`sync_mode: pull` + `branch: dev` 被判为不合规。')
    # 合法：glob 段里用 ${CNB_BRANCH}。
    if check_push_scope(push_task('${CNB_BRANCH}', key='**/!(main|dev)')):
        errors.append('自检探针失败：glob 段的 `${CNB_BRANCH}` 被判为不合规。')
    # 判据 1：不写 branch（push）。
    if not check_push_scope(push_task(None)):
        errors.append('自检探针失败：push 任务不写 `branch`（= `--all`，会推 main）没被拦。')
    # 判据 1（#167）：不写 branch（pull）—— 会「GitHub main force 覆盖 CNB main」。
    if not check_push_scope(push_task(None, 'pull')):
        errors.append(
            '自检探针失败：pull 任务不写 `branch`（= 全分支 `push origin --force`，'
            '会覆盖 CNB main）没被拦 —— CNB #167 的病。'
        )
    # 判据 2：显式推 main。
    for bad in ('main', '*', '--all'):
        if not check_push_scope(push_task(bad)):
            errors.append(f'自检探针失败：`branch: {bad}` 没被拦。')
    # 判据 2（#167）：pull 方向也不得显式写 main。
    if not check_push_scope(push_task('main', 'pull')):
        errors.append('自检探针失败：pull 方向 `branch: main` 没被拦。')
    # 判据 3：main 键 + ${CNB_BRANCH}。
    if not check_top_level_main(push_task('${CNB_BRANCH}', key='main')):
        errors.append('自检探针失败：`main` 键下用 `${CNB_BRANCH}` 推分支没被拦。')
    # 判据 4：命名 job 合法；裸 stages 报错。
    if check_named_jobs({'dev': {'push': [{'name': 'x', 'stages': []}]}}):
        errors.append('自检探针失败：带 name 的 job 被判为不合规。')
    if not check_named_jobs({'dev': {'push': {'stages': []}}}):
        errors.append('自检探针失败：裸 `stages:`（无 name 的 job）没被拦——假绿形态漏网。')

    # 判据 5（CNB #269）：挂载分支键必须与 settings.branch 一致，否则 runner 检不出目标分支。
    # 合法：挂在 dev 下、推 dev。
    if check_branch_key_matches_target(push_task('dev', key='dev')):
        errors.append('自检探针失败：`dev` 键下推 `dev` 被判为不合规。')
    # 合法：glob 段（排除 main/dev）推功能分支。
    if check_branch_key_matches_target(push_task('${CNB_BRANCH}', key='**/!(main|dev)')):
        errors.append('自检探针失败：glob 段的 `${CNB_BRANCH}` 被判为不合规。')
    # ❌ 本仓真实形态：挂在 main 下、推 dev（绿了三天的那个）。
    if not check_branch_key_matches_target(push_task('dev', key='main')):
        errors.append(
            '自检探针失败：作业挂在 `main` 键下却推 `dev` 没被拦 —— 正是 CNB #269 的病'
            '（runner 只检出 main，插件找不到 dev，跳过却报 success）。'
        )
    # ❌ pull 方向同理。
    if not check_branch_key_matches_target(push_task('dev', 'pull', key='main')):
        errors.append('自检探针失败：挂 `main` 键下 pull `dev` 没被拦。')
    # ❌ 挂 dev 下推 main（判据 2 也会拦，这里保证判据 5 同样认得）。
    if not check_branch_key_matches_target(push_task('main', key='dev')):
        errors.append('自检探针失败：挂 `dev` 键下推 `main` 没被拦。')
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description='检查 git-sync 两个方向都只作用在 dev/功能分支，main 不被外推也不被覆盖（CNB #167/#172）'
    )
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
    problems += check_named_jobs(data)
    problems += check_branch_key_matches_target(data)

    if problems:
        print(f'❌ {path} 的 git-sync 分支范围检查未通过：')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('✅ git-sync 两个方向的分支范围合规（main 不外推、也不被覆盖）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
