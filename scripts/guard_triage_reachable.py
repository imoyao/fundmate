#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守门：分诊作业必须**真的会跑**（源 CNB #564，2026-10-19）。  <!-- cross-repo-ref-allow -->

WHY —— 用户问了两次「到底做了没有」，两次答案都是「没做」
---------------------------------------------------------
第一次（2026-10-19 00:10）：「我没有看到推进所谓的挂卡或者是归类……到底做了没有？」
当时的实况：分诊脚本已合进 `dev`、单元测试全绿，**看板上一个标签都没落**。
根因不是判据错，是**分诊 stage 不在 cron 里**（PR #584 把整组定时作业搬进 `dev:` 段时
只搬了建卡），而 cron 那次唯一的运行里三个自检还全崩在 `python:3.12-slim` 没有 git 上，
外层 `exit 0` ⇒ 构建 success。**每一处单看都「跑成功了」。**

这不是第一次：CNB #450 的 224 张重复卡、#171 / #517 的假绿都是同一形态——
**判据的失败态被吞掉之后，空转和正常在输出里长得一模一样。**

判据（静态，三问全过才算「会跑」）
----------------------------------
1. **有定时触发**：`.cnb.yml` 的**活跃分支**段下必须有 cron（挂在 `main` 下由
   `guard_cron_covers_active_branch.py` 拦，这里只管「有没有」）；
2. **那个 cron 里有个 job 真的调了 `scripts/triage/issue_triage.py`**：
   `<<: *anchor` 要能顺着 YAML 锚点追到 `script`——本仓两条触发方式共用一段
   `&mirror-job`，只认字面 `script` 会漏掉真正在跑的那一份；
3. **它写在 `stages:` 里、且每个 stage 有 `name`**（CNB #167 实测：把 `stages:` 直接挂在
   cron 下、不套一层带 `name` 的 job 对象，`get-build-stage` 查不到该 stage，
   「挂旧 sha、实际没跑、却报绿」）。

另加一条**跨仓事实**：GitHub 侧兜底通道（`.github/workflows/issue-triage.yml`）必须**有
`schedule`** —— 否则它只在手动触发时才跑，CNB 挂掉时它也不动，那不叫兜底。
至于「它 checkout 的是不是活跃分支」，**不在这里判**：`guard_schedule_checkout_ref.py`
（源 CNB #586）已经管了这件事，且本文件正在它的扫描范围内。已有判据管过的事不重开第二份。

边界（有意不做）
----------------
- **不判「作业有没有成功」**：那要联网、要凭据，且在 PR 门禁里拉外网本身就是错的；
- **不判结论判得对不对**：判据质量是 `scripts/tests/test_issue_triage.py` 的事；
- **不要求两侧都写**：两侧各自幂等（指纹在评论里），只要求「至少有一侧真的会跑」。

用法
----
    python scripts/guard_triage_reachable.py
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用（**不得**退化成「没问题」）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# 与 `guard_cron_covers_active_branch.ACTIVE_BRANCH` 同源（那里是「挂在哪」，这里是「有没有」）。
ACTIVE_BRANCH = 'dev'
TRIAGE_SCRIPT = 'scripts/triage/issue_triage.py'
GH_FALLBACK = '.github/workflows/issue-triage.yml'
_CRON_KEY = re.compile(r'^\s*[\'"]?\s*(?:crontab|cron)\s*:', re.IGNORECASE)


def _collect_scripts(node: object, seen: set[int] | None = None) -> list[str]:
    """把这个 job 对象（可能带 YAML 锚点合并）里所有 `script` 收出来。

    锚点合并（`<<: *mirror-job`）在 `safe_load` 之后**已经是展开后的 dict**，
    所以正常遍历即可；但仍防递归引用（YAML 允许，跑起来会无限展开）。
    """
    seen = seen or set()
    out: list[str] = []
    if isinstance(node, dict):
        if id(node) in seen:
            return out
        seen.add(id(node))
        for key, value in node.items():
            if key == 'script' and isinstance(value, str):
                out.append(value)
            else:
                out.extend(_collect_scripts(value, seen))
    elif isinstance(node, list):
        for item in node:
            out.extend(_collect_scripts(item, seen))
    return out


def _jobs_with_triage(node: object) -> int:
    """数一数「调了分诊脚本」的 job 个数（按 job 对象去重，不按出现次数）。"""
    count = 0
    if isinstance(node, dict):
        if _collect_scripts(node) and any(
            TRIAGE_SCRIPT in s for s in _collect_scripts(node)
        ):
            count += 1
            return count
        for value in node.values():
            count += _jobs_with_triage(value)
    elif isinstance(node, list):
        for item in node:
            count += _jobs_with_triage(item)
    return count


def _named_stages_ok(node: object) -> list[str]:
    """每个 `stages:` 项都必须是 `{name: ..., script/config: ...}` 形态。

    只判「调分诊的那个 job」——别的 job 的历史形态不由本守卫背锅。
    """
    problems: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'stages' and isinstance(value, list):
                if any(TRIAGE_SCRIPT in s for s in _collect_scripts(value)):
                    for idx, stage in enumerate(value):
                        if not isinstance(stage, dict) or not stage.get('name'):
                            problems.append(
                                f'第 {idx + 1} 个 stage 没有 `name` —— CNB #167 实测：'
                                '`stages:` 下不套带 name 的 job/stage 对象时，'
                                '`get-build-stage` 查不到该 stage，'
                                '于是「挂旧 sha、实际没跑、却报绿」。'
                            )
            problems.extend(_named_stages_ok(value))
    elif isinstance(node, list):
        for item in node:
            problems.extend(_named_stages_ok(item))
    return problems


def check_data(data: object, gh_text: str | None = None) -> list[str]:
    """判据本体。`gh_text` 为 `None` 表示读不到兜底 workflow（判「结论不可信」）。"""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ['输入不可信：`.cnb.yml` 顶层不是一个映射。']

    branch = data.get(ACTIVE_BRANCH)
    if not isinstance(branch, dict):
        return [
            f'输入不可信：顶层找不到 `{ACTIVE_BRANCH}:` 段。'
            '本守卫以它为「作业会跑的那一段」，认不出它是否还成立 ⇒ **本轮结论不可信**，'
            '不得读成「分诊会跑」。分支改名时请同步本守卫的 ACTIVE_BRANCH。'
        ]

    crons = [k for k in branch if _CRON_KEY.match(f'{k}:')]
    if not crons:
        problems.append(
            f'`{ACTIVE_BRANCH}:` 段下没有任何 cron —— 这里的作业**不会按时间跑**。'
            '分诊必须挂在定时触发下（源 CNB #564）：2026-10-18 合进 dev 之后，'
            '就因为有代码没 cron，看板上一张标签都没落，而所有人都以为「已经实现了」。'
        )
        return problems

    hits = 0
    for key in crons:
        if _jobs_with_triage(branch[key]):
            hits += 1
    if not hits:
        problems.append(
            f'`{ACTIVE_BRANCH}:` 下的 cron 里，没有任何 job 调用 `{TRIAGE_SCRIPT}` —— '
            '分诊不会跑。注意 `<<: *anchor` 共用片段也必须真的包含该脚本，'
            '「脚本在仓库里 + 有测试」都不等于「定时任务会调用它」。'
        )
    problems.extend(_named_stages_ok(branch))

    if gh_text is None:
        problems.append(
            f'输入不可信：读不到 `{GH_FALLBACK}` —— 兜底通道是否真的会跑，本轮判不出来。'
        )
    else:
        problems.extend(_check_gh_fallback(gh_text))
    return _dedup(problems)


def _check_gh_fallback(text: str) -> list[str]:
    """GitHub 兜底通道：**有 schedule** 才算兜底。

    ⚠️ 去重（2026-10-19，自己 review 出来的）：本判据**曾**还想管「checkout 是否固定到
    活跃分支」，与 `scripts/guard_schedule_checkout_ref.py`（源 CNB #586）完全重叠——
    已有判据管过的事不重开第二份，否则两处判据迟早各说各话。
    那条守卫的边界也一并认了：它只判「**定时作业**里跑仓库脚本时 checkout 落哪」，本文件
    的兜底 workflow 正好落在它的扫描范围内（`on.schedule` + `python scripts/…`），
    所以这里只问**本文件独有的那个缺口**：`schedule` 在不在。
    """
    if 'issue_triage.py' not in text:
        return []
    if not re.search(r'^\s*schedule:', text, re.MULTILINE):
        return [
            f'`{GH_FALLBACK}` 调了分诊脚本却没有 `schedule:` —— 那它只在手动触发时才跑，'
            '不能算兜底通道（CNB 挂掉时它也不动）。'
        ]
    return []


def _dedup(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def self_check() -> list[str]:
    """正反探针：判据写坏了会全绿（本仓老规矩）。"""
    errors: list[str] = []
    cron = 'crontab: 0 18 * * *'
    gh_ok = 'schedule:\n  - cron: "0 19 * * *"\nenv:\n  TRIAGE_REF: dev\nwith:\n  ref: ${{ env.TRIAGE_REF }}\nissue_triage.py'

    good = {
        ACTIVE_BRANCH: {
            cron: [
                {
                    'name': '分诊',
                    'stages': [{'name': '跑分诊', 'script': f'python {TRIAGE_SCRIPT} --apply'}],
                }
            ]
        }
    }
    if check_data(good, gh_ok):
        errors.append('自检失败：会跑的分诊被误报。')

    # ① 有脚本、有测试，但没有 cron
    if not any('没有任何 cron' in p for p in check_data({ACTIVE_BRANCH: {'push': []}}, gh_ok)):
        errors.append('自检失败：没有 cron 却放行（正是 #564 的实际形态）。')

    # ② 有 cron，但 cron 里没调分诊
    no_triage = {ACTIVE_BRANCH: {cron: [{'name': '建卡', 'stages': [{'name': 'x', 'script': 'echo hi'}]}]}}
    if not any('没有任何 job 调用' in p for p in check_data(no_triage, gh_ok)):
        errors.append('自检失败：cron 里不调分诊却放行（「写了代码」被当成「会跑」）。')

    # ③ stage 没有 name（CNB #167：查不到 stage，挂旧 sha 却报绿）
    no_name = {
        ACTIVE_BRANCH: {
            cron: [{'name': '分诊', 'stages': [{'script': f'python {TRIAGE_SCRIPT}'}]}]
        }
    }
    if not any('没有 `name`' in p for p in check_data(no_name, gh_ok)):
        errors.append('自检失败：stage 缺 name 却放行（#167 的形态）。')

    # ④ 锚点片段（`<<: *job`）里的脚本也必须被认出来
    anchor_ok = {
        '.job': {'stages': [{'name': 'n', 'script': f'python {TRIAGE_SCRIPT} --apply'}]},
        ACTIVE_BRANCH: {cron: [{'name': '分诊', 'stages': [{'name': 'n2', 'script': 'echo'}]}]},
    }
    # 锚点展开后脚本在 job 体内；这里模拟展开结果
    expanded = {ACTIVE_BRANCH: {cron: [{'name': '分诊', 'stages': [{'name': 'n', 'script': f'python {TRIAGE_SCRIPT}'}]}]}}
    if check_data(expanded, gh_ok):
        errors.append('自检失败：锚点引用的 job 里调分诊被漏判。')
    if anchor_ok.get('.job') is None:
        errors.append('自检自身构造有误')

    # ⑤ 兜底 workflow 没有 schedule（只在手动触发时才跑，不算兜底）
    if not any('没有 `schedule:`' in p for p in check_data(good, 'on:\n  workflow_dispatch:\nissue_triage.py')):
        errors.append('自检失败：兜底通道没有 schedule 却放行。')

    # ⑥ 读不到兜底 workflow ⇒ 结论不可信（不得当成「没问题」）
    if not any('不可信' in p for p in check_data(good, None)):
        errors.append('自检失败：读不到兜底 workflow 却放行（#171 的失败态纪律）。')

    # ⑦ 活跃分支不存在 ⇒ 结论不可信
    if not any('不可信' in p for p in check_data({'trunk': {cron: []}}, gh_ok)):
        errors.append('自检失败：活跃分支不存在却放行。')
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='检查分诊作业是否真的会跑（源 CNB #564）')
    ap.add_argument('--cnb', default=None, help='要检查的 .cnb.yml（默认仓库根）')
    ap.add_argument('--gh', default=None, help=f'GitHub 兜底 workflow（默认 {GH_FALLBACK}）')
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    cnb_path = Path(args.cnb) if args.cnb else root / '.cnb.yml'
    gh_path = Path(args.gh) if args.gh else root / GH_FALLBACK

    errors = self_check()
    if errors:
        for e in errors:
            print(f'❌ {e}', file=sys.stderr)
        print('守卫自身自检失败 —— 本轮结论不可信（判据写坏了会全绿）', file=sys.stderr)
        return 2

    if not cnb_path.is_file():
        print(f'❌ 输入不可用：读不到 {cnb_path} —— 本轮结论不可信', file=sys.stderr)
        return 2
    try:
        data = yaml.safe_load(cnb_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        print(f'❌ 输入不可用：{cnb_path} 解析失败（{exc}）—— 本轮结论不可信', file=sys.stderr)
        return 2

    gh_text: str | None
    try:
        gh_text = gh_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        gh_text = None

    problems = check_data(data, gh_text)
    if problems:
        for p in problems:
            print(f'❌ {p}', file=sys.stderr)
        return 1
    print(f'✅ 分诊作业会跑：`{ACTIVE_BRANCH}` 的 cron 里调用了 `{TRIAGE_SCRIPT}`，')
    print(f'   且 GitHub 兜底通道（`{GH_FALLBACK}`）有定时触发。')
    print('   （兜底 workflow checkout 的是哪条分支，由 `guard_schedule_checkout_ref.py` 判，本守卫不重复。）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
