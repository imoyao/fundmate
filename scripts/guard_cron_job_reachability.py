#!/usr/bin/env python3
"""守门：作业的目标分支必须在**它自己的**检出里存在（源 CNB #578 / #585）。  <!-- cross-repo-ref-allow -->

WHY（实测，不是推断）
---------------------
构建 `cnb-ri6-1k57q4k9b`（`crontab: 30 * * * *`，作业「同步到 GitHub（每小时兜底，仅 dev）」）
报了 **6 个半小时以来同一个错**，而它长得完全不像错误：

    $ git fetch -v --force … origin "refs/heads/dev"
    $ git checkout -f -B "dev" "a9d050b2…"
    $ git push … target dev
    To https://github.com/imoyao/fundmate.git
     ! [rejected]        dev -> dev (fetch first)
    error: failed to push some refs to 'https://github.com/imoyao/fundmate.git'

```
cnb-ri6-1k57q4k9b  17:30  error   crontab: 30 * * * *
cnb-0e0-1k57ntnhb  16:30  error   crontab: 30 * * * *
…
```

它**每小时红一次、每次都红在同一行**，而原因不是「GitHub 多了一笔」——
CNB `dev`（`a9d050b2`）与 GitHub `dev`（`3504cb8f`）**双向分叉**：
CNB 独有 19 笔、GitHub 独有 7 笔（2026-10-18 实测，`git cherry` 补丁等价口径）。

于是这条 cron **结构上不可能成功**：git-sync 的 push 刻意不开 `force`（反向护栏，对的），
而「让 CNB `dev` 追上 GitHub」这件事**不在它的能力范围内**——它只会推 CNB 自己那份。

#### 更贵的一层：它的「绿色」也是假的

本卡与 **CNB #269** 是同一条依赖链的两端，而 #269 当时看到的形态是**反的**：

| 卡 | 观察到的形态 | 真实情况 |
|---|---|---|
| #269 | `Warning: Branch dev does not exist locally, skipping push` 后 **success** | 作业挂错分支键 ⇒ 检出的是 `main`，插件找不到 `dev` 就跳过 |
| **#578** | `! [rejected] … (fetch first)` ⇒ **error** | 挂载位置对了（`dev:` 之下），但**两侧内容分叉** ⇒ 非快进 |

也就是说：**同一个作业，改对挂载位置之后就由「假绿」变成了「真红」，而红的原因换成它真正的问题。**
把「绿了」读成「推上去了」，在这条链上已经栽过一次；这次不过是失败态换了个方向。

判据（静态、不拉网络）
----------------------
1. 取 `.cnb.yml` 里**定时事件**（`crontab: …` / `cron: …`）下的每个 job，抽出它要作用的目标分支：
   - git-sync 插件任务的 `settings.branch`（**驱动同步的作业**）；
   - 脚本任务里 `<脚本>.py --branch <名>`（如 `machine_branch.py` / `check_*_divergence.py`）。
2. **目标分支必须等于该事件所挂的分支键**（`dev` / `main` / `$` 通配）。
   CNB runner 的检出口径是（构建日志原文）：

       git fetch origin "refs/heads/<分支键>"
       git checkout -f -B "<分支键>" <sha>

   ⇒ 定时构建的检出里**只有分支键那一条**。作业若指向别处，要么静默跳过（#269 的假绿），
   要么拿一条注定推不上去的 ref 去推（本卡的恒红）。
3. `$`（任何分支）下出现**指向具体分支**的同步作业 ⇒ 报红：`$` 下没有「当前分支」上下文，
   `CNB_BRANCH` 不可靠（`.cnb.yml` 里已有同款纪律，本条把它机械化）。

边界（有意为之）
----------------
- **不判断「两侧内容分叉了没有」**：那是 `scripts/bridge/check_cross_repo_dev_divergence.py`
  的事（要联网、要凭据），本守卫只保证「作业的目标分支与它自己的检出对得上」。
- **不判断 git-sync 会不会真的推成功**：分支保护、非快进、凭据都读不到，也不该猜。
- **不校验事件是否触发**：那是 `scripts/check_cnb_events.py`（挂载位置）的事。
- 重复键遮蔽 ⇒ 直接判「输入不可信」（`safe_load` 会把被覆盖段的 job 吃掉，本守卫会对它一无所知）。

判据 4（`push` / `pull_request` 等**非定时**事件，源 CNB #585，2026-10-19）  <!-- cross-repo-ref-allow -->
----------------------------------------------------------------------------------------------
`${CNB_BRANCH}` **只能**挂在多分支的键下（`$` 或 glob 段）。挂在 `dev:` / `main:` 这类
**单分支**键下时，runner 只检出那一条分支（同判据 1 的检出口径），于是：

    $ git fetch -v --force … origin "refs/heads/dev"     ← 分支键是 dev
    $ git push … target chore/564-cron-on-dev
     ! [rejected]  chore/564-cron-on-dev -> … (fetch first)

`CNB_BRANCH` 此刻解析成**本地唯一存在的那条 `dev`**，等于拿 `dev` 去顶功能分支的名字——
非快进，必拒。而 job/stage 名仍叫「同步当前功能分支到 GitHub」，读起来完全对（实测即此）。

> 判据 1 当时只管 `crontab:`，判据 4 补的是**同一个「挂在哪就只能推哪」**在 push 事件上的形态。
> `"**/!(main|dev)"` 这样的 glob 键与 `$` 一样是多分支的，故放行。

判据 5（glob 段里**不许推固定分支**）  <!-- cross-repo-ref-allow -->
-----------------------------------------------------------------
这条是对判据 2 的补洞：glob 段检出的可能是**任何**分支，若那里把 `branch` 写死成 `dev`，
推的仍是「拿 dev 顶当前分支」——形态与判据 4 等价，只是方向相反。

用法
----
    python scripts/guard_cron_job_reachability.py            # 检查仓库根 .cnb.yml
    python scripts/guard_cron_job_reachability.py --file x   # 检查指定文件
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用（**不得**退化成「没问题」，#171）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# 定时事件的键名。CNB 里写作 `"crontab: 30 * * * *"`（也有 `"cron: …"` 的写法）。
# ⚠️ 先剥掉**外层引号**再匹配：`.cnb.yml` 里的写法是 `"crontab: 30 * * * *":`（带引号，
# 因为键里含冒号与空格）。首版正则直接匹配 `^\s*(crontab|cron)\s*:`，被开头的 `"` 挡掉，
# `check_text()` 拿去替换原文键名的映射于是**恒为空**——守卫自身仍判对（判据不依赖该映射），
# 但报错信息会退回到 `crontab: 30 * * * *` 这种「原文里搜不到」的形态。
_CRON_KEY = re.compile(r'^\s*[\'\"]?\s*((?:crontab|cron)\s*:.*)$', re.IGNORECASE)

# `$` = 任何分支：没有「当前分支」上下文，故不能指向具体分支。
ANY_BRANCH_KEYS = {'$', '*'}

# 脚本任务里的 `--branch <名>`（machine_branch.py / check_*_divergence.py 都是这个形态）。
# ⚠️ 取值字符集必须含 `$` `{` `}`：`--branch ${CNB_BRANCH}` 首版被截成 `${CNB_BRANCH`
# （停在 `{` 前），判据 4 于是看不见它 —— 「拿不到输入」被读成「没有动态值」。
_CLI_BRANCH = re.compile(r'--branch[=\s]+([\w./${}-]+)')


class _DupKeyLoader(yaml.SafeLoader):
    """保留重复键的 SafeLoader（与 `guard_cnb_script_task_git.py` 同源、各自持有）。

    重复键下 `safe_load` 会用后者覆盖前者，被覆盖段的 job **根本不在解析结果里**——
    本守卫会对它一无所知，报出的「全部合规」是假绿灯。故先探、再判。
    """

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


def find_duplicate_keys(text: str) -> list[tuple[str, int]]:
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


def _cron_keys(text: str) -> list[str]:
    """按**原文**抓出定时事件的键名（`safe_load` 之后它们只是普通 dict 键，形态已丢）。"""
    names: list[str] = []
    for line in text.splitlines():
        m = _CRON_KEY.match(line)
        if not m:
            continue
        # 取值：从 `crontab`/`cron` 开始到行尾（去掉结尾的 `:` 与外层引号），
        # 这样原文里能直接搜到，报错信息才指得动人。
        names.append(m.group(1).rstrip().rstrip(':').strip().strip('"').strip("'").strip())
    return names


def _is_branch_scoped(key: str) -> bool:
    return key not in ANY_BRANCH_KEYS


def target_branches(job: dict) -> list[tuple[str, str]]:
    """抽出一个 job 里「要作用的目标分支」：`[(来源说明, 分支名), …]`。

    只认两种形态（本仓真实用过的）：
      - git-sync 插件任务的 `settings.branch`（**驱动同步**的那一类）；
      - 脚本任务 `script` 里的 `--branch <名>`。
    `${CNB_BRANCH}` 之类**不猜运行时值**，直接跳过（那是 `$` 段的合法写法）。
    """
    out: list[tuple[str, str]] = []
    for stage in job.get('stages') or []:
        if not isinstance(stage, dict):
            continue
        settings = stage.get('settings')
        if isinstance(settings, dict):
            branch = settings.get('branch')
            if isinstance(branch, str) and branch and '$' not in branch:
                out.append((f'stage「{stage.get("name") or "?"}」的 settings.branch', branch))
        for key in ('script', 'commands'):
            body = stage.get(key)
            if not isinstance(body, str):
                continue
            for m in _CLI_BRANCH.finditer(body):
                name = m.group(1)
                if '$' in name:  # `${CNB_BRANCH}`：不猜
                    continue
                out.append((f'stage「{stage.get("name") or "?"}」的 `--branch`', name))
    return out


def dynamic_branch_origins(job: dict) -> list[tuple[str, str]]:
    """抽出「用了动态分支变量」的位置：`[(说明, 变量名), …]`。

    动态值不能在这里求值，但**它能被挂在哪**是静态可判的（见判据 4）：
    runner 只检出分支键那一条，`$` 与 glob 键则是「任何分支」。
    """
    out: list[tuple[str, str]] = []
    for stage in job.get('stages') or []:
        if not isinstance(stage, dict):
            continue
        settings = stage.get('settings')
        if isinstance(settings, dict):
            branch = settings.get('branch')
            if isinstance(branch, str) and '$' in branch:
                out.append((f'stage「{stage.get("name") or "?"}」的 settings.branch', branch.strip()))
        for key in ('script', 'commands'):
            body = stage.get(key)
            if not isinstance(body, str):
                continue
            for m in _CLI_BRANCH.finditer(body):
                if '$' in m.group(1):
                    out.append((f'stage「{stage.get("name") or "?"}」的 `--branch`', m.group(1)))
    return out


def check_dynamic_scope(data: dict) -> list[str]:
    """判据 4：`${CNB_BRANCH}` 只能挂在**多分支**的键下（`$` / glob 段）。

    挂在 `dev:` / `main:` 这类单分支键下 ⇒ 检出里只有那一条，`CNB_BRANCH` 解析成本地
    仅有的分支名，推出去就是「拿 `dev` 顶别人名字」⇒ 非快进必拒（源 CNB #585）。  <!-- cross-repo-ref-allow -->
    """
    problems: list[str] = []
    if not isinstance(data, dict):
        return problems
    for branch_key, events in data.items():
        if is_multibranch_key(branch_key) or not isinstance(events, dict):
            continue
        for event_key, jobs in events.items():
            if not isinstance(jobs, list):
                continue
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                job_name = job.get('name') or '?'
                for origin, expr in dynamic_branch_origins(job):
                    where = f'`{branch_key}` / `{event_key}` / job「{job_name}」/ {origin}'
                    problems.append(
                        f'{where} 用了 `{expr}`，而该事件挂在**单分支**键 `{branch_key}` 下。'
                        f'runner 只检出 `{branch_key}` 这一条（`git fetch origin refs/heads/{branch_key}` + '
                        f'`git checkout -f -B "{branch_key}"`），于是 `{expr}` 解析成本地仅有的 `{branch_key}`，'
                        '推出去就是「拿它顶别人的分支名」⇒ 非快进必拒'
                        '（源 CNB #585 实测：`! [rejected] chore/564-cron-on-dev -> … (fetch first)`）。'
                        '动态分支只允许挂在 `$` 或 glob 段（如 `"**/!(main|dev)"`）；'
                        '若本意就是推固定分支，请写成字面量并挂到同名分支键下。'
                    )
    return problems


def check_multibranch_fixed_target(data: dict) -> list[str]:
    """判据 5：glob 段（`**/!(main|dev)`）里的同步作业**不得**推固定分支。

    glob 段检出的可能是任何分支；把 `branch` 写死成 `dev` 就变成「拿 dev 顶当前分支」，
    与判据 4 等价（方向相反）。`$` 段已有同款判据（判据 3），这里补上 glob 段。
    """
    problems: list[str] = []
    if not isinstance(data, dict):
        return problems
    for branch_key, events in data.items():
        if not is_multibranch_key(branch_key) or branch_key in ANY_BRANCH_KEYS:
            continue
        if not isinstance(events, dict):
            continue
        for event_key, jobs in events.items():
            if not isinstance(jobs, list):
                continue
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                for origin, target in target_branches(job):
                    problems.append(
                        f'`{branch_key}` / `{event_key}` / job「{job.get("name") or "?"}」/ {origin}'
                        f' 指向固定分支 `{target}`，而该段的检出可能是**任何**分支。'
                        '推固定分支会拿它去顶当前分支的名字 ⇒ 非快进必拒（源 CNB #585）。'
                        '这里应写 `${CNB_BRANCH}`（推当前分支），固定分支的同步请挂到同名分支键下。'
                    )
    return problems


def is_multibranch_key(branch_key: str) -> bool:
    """`$` / `*` / 含 glob 的键（`**/!(main|dev)`）都表示「不止一条分支」。"""
    key = str(branch_key or '').strip()
    if key in ANY_BRANCH_KEYS:
        return True
    return '*' in key or '?' in key or '!' in key or '[' in key


def check_data(data: dict, cron_keys: dict[str, str] | None = None) -> list[str]:
    """判据：定时事件下的作业，目标分支必须等于该事件所挂的分支键。

    `cron_keys` 把 `safe_load` 之后的键名映射回原文（`crontab: 30 * * * *`），
    只为让报错信息指向人真的能搜到的那一行。
    """
    problems: list[str] = []
    if not isinstance(data, dict):
        return problems
    for branch_key, events in data.items():
        if not isinstance(events, dict):
            continue
        for event_key, jobs in events.items():
            label = (cron_keys or {}).get(str(event_key), str(event_key))
            if 'crontab:' not in label.lower() and 'cron:' not in label.lower():
                continue
            if not isinstance(jobs, list):
                continue
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                job_name = job.get('name') or '?'
                for origin, target in target_branches(job):
                    where = f'`{branch_key}` / `{label}` / job「{job_name}」/ {origin}'
                    if branch_key in ANY_BRANCH_KEYS:
                        problems.append(
                            f'{where} 指向具体分支 `{target}`，但该事件挂在 `{branch_key}`（任何分支）下。'
                            '`$` 段没有「当前分支」上下文（`CNB_BRANCH` 在 cron/push 形态下不可靠），'
                            '误推 `main` 就是分叉。定时同步请显式挂在具体分支键下。'
                        )
                    elif target != branch_key:
                        problems.append(
                            f'{where} 指向 `{target}`，而该事件挂在 `{branch_key}` 下 —— '
                            f'定时构建的检出里**只有 `{branch_key}`**：'
                            f'runner 执行的是 `git fetch origin refs/heads/{branch_key}` + '
                            f'`git checkout -f -B "{branch_key}" <sha>`。'
                            f'作业要么静默跳过（源 CNB #269 的假绿：'
                            f'`Warning: Branch {target} does not exist locally, skipping push` 后仍报 success），'
                            f'要么拿一条注定推不上去的 ref 去推（源 CNB #578 的恒红：'
                            f'`! [rejected] {target} -> {target} (fetch first)`）。'
                            f'改法：把该作业挂到 `{target}:` 分支键下（“定时任务必须挂在具体分支下”）。'
                        )
    problems.extend(check_dynamic_scope(data))
    problems.extend(check_multibranch_fixed_target(data))
    return problems


def check_text(text: str) -> list[str]:
    dups = find_duplicate_keys(text)
    if dups:
        seen = ', '.join(f'`{k}`（第 {ln} 行起）' for k, ln in dups)
        return [
            f'输入不可信：`.cnb.yml` 存在重复键 {seen}。'
            '`yaml.safe_load` 用后者覆盖前者，被覆盖段的 job **不会进入本次检查**'
            '—— 本守卫在遮蔽状态下给出的「全部可及」是假绿灯。'
            '先跑 `python scripts/guard_cnb_yml_duplicate_keys.py` 修掉重复键再复检。'
        ]
    data = yaml.safe_load(text)
    raw_keys = _cron_keys(text)
    cron_keys = {k: k for k in raw_keys}
    return check_data(data, cron_keys)


def self_check() -> list[str]:
    """正反探针：判据写坏了会全绿（本仓老规矩）。"""
    errors: list[str] = []

    bad = {
        'main': {
            'crontab: 30 * * * *': [
                {
                    'name': 'job',
                    'stages': [{'name': 's', 'settings': {'branch': 'dev'}}],
                }
            ]
        }
    }
    if not check_data(bad):
        errors.append('自检失败：`main` 下的 cron 指向 `dev` 没被拦（正是源 CNB #578 的形态）。')  # cross-repo-ref-allow

    good = {
        'dev': {
            'crontab: 30 * * * *': [
                {
                    'name': 'job',
                    'stages': [{'name': 's', 'settings': {'branch': 'dev'}}],
                }
            ]
        }
    }
    if check_data(good):
        errors.append('自检失败：挂在 `dev` 下、推 `dev` 的作业被误报（判据过宽）。')

    cli = {
        'main': {'crontab: 0 18 * * *': [{'name': 'j', 'stages': [{'name': 's', 'script': 'python x.py --branch dev'}]}]}
    }
    if not check_data(cli):
        errors.append('自检失败：脚本任务的 `--branch dev` 在 `main` 下没被拦。')

    dollar = {
        '$': {'crontab: 0 18 * * *': [{'name': 'j', 'stages': [{'name': 's', 'settings': {'branch': 'dev'}}]}]}
    }
    if not check_data(dollar):
        errors.append('自检失败：`$` 段里指向具体分支没被拦。')

    # ⚠️ 2026-10-19 修正（源 CNB #585）：`dev:` + `${CNB_BRANCH}` 由「放行」改为**报红**。
    # 旧探针把「不猜运行时值」理解成「一律放行」，于是功能分支的 git-sync 被写进 `dev:`
    # 段这一形态**两重豁免**（非 cron + 动态值），一条 push 构建红了却没人知道原因。
    # 不猜值 ≠ 不管挂在哪：`dev:` 下检出里只有 `dev`，`CNB_BRANCH` 必然解成 `dev`。
    dynamic_bad = {
        'dev': {
            'crontab: 30 * * * *': [
                {'name': 'j', 'stages': [{'name': 's', 'settings': {'branch': '${CNB_BRANCH}'}}]}
            ]
        }
    }
    if not check_dynamic_scope(dynamic_bad):
        errors.append('自检失败：单分支键下用 `${CNB_BRANCH}` 没被拦（源 CNB #585 的形态）。')

    dynamic_good = {
        'dev': {
            'crontab: 30 * * * *': [
                {'name': 'j', 'stages': [{'name': 's', 'settings': {'branch': '${CNB_BRANCH}'}}]}
            ]
        }
    }
    # 同一份数据，键换成 glob 就是合法的（功能分支同步的正确挂法）。
    dynamic_good = {'**/!(main|dev)': dynamic_good['dev']}
    if check_dynamic_scope(dynamic_good):
        errors.append('自检失败：glob 段里的 `${CNB_BRANCH}` 被误报（判据过宽）。')

    glob_fixed = {
        '**/!(main|dev)': {
            'push': [{'name': '功能分支同步', 'stages': [{'name': 's', 'settings': {'branch': 'dev'}}]}]
        }
    }
    if not check_multibranch_fixed_target(glob_fixed):
        errors.append('自检失败：glob 段里写死推 `dev` 没被拦（判据 5）。')

    # 非 cron 事件不该被本判据管（那是 check_cnb_events 的职责）。
    not_cron = {'main': {'push': [{'name': 'j', 'stages': [{'name': 's', 'settings': {'branch': 'dev'}}]}]}}
    if check_data(not_cron):
        errors.append('自检失败：`push` 事件被误判（本判据只管定时作业）。')
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='检查定时作业的目标分支是否在它自己的检出里存在（源 CNB #578）')  # cross-repo-ref-allow
    ap.add_argument('--file', default=None, help='要检查的 .cnb.yml（默认仓库根）')
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    path = Path(args.file) if args.file else root / '.cnb.yml'
    if not path.is_file():
        print(f'❌ 输入不可用：读不到 {path} —— 本轮结论不可信', file=sys.stderr)
        return 2
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        print(f'❌ 输入不可用：{path} 读不出来（{exc}）—— 本轮结论不可信', file=sys.stderr)
        return 2

    errors = self_check()
    if errors:
        for e in errors:
            print(f'❌ {e}', file=sys.stderr)
        return 2

    problems = check_text(text)
    if problems:
        print('❌ 定时作业可及性检查未通过：', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        return 1
    print('✅ 定时作业的目标分支都在它自己的检出里（挂载位置与目标一致）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
