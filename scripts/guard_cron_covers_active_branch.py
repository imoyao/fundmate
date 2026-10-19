#!/usr/bin/env python3
"""守门：定时作业必须挂在**活跃分支**上（源 CNB #564，2026-10-18）。  <!-- cross-repo-ref-allow -->

WHY（用户的原话，比任何推导都准）
--------------------------------
> 「直接在 DEV 分支上面进行分诊不行吗？为什么非得在 main 分支上面？因为我们的 DEV 分支是
> 我们日常活跃分支，main 分支唯一做的事情就是从 DEV 到 main 分支进行发版。」

用户说得对，而当时 `.cnb.yml` 里**整组定时作业**（建卡 / 状态回流 / 分诊 / 三节自检）
都挂在 `main:` 下，理由只有一句「cron 只能挂具体分支下，故这里显式写 main」——
**这条平台限制说的是「必须是个具体分支」，从来没有说「必须是 `main`」**。
一句话被读偏一格，代价是这个仓反复付：

| 代价 | 实测代价 |
|---|---|
| 脚本要等发版才换 | `main` 只在发版时前进 ⇒ 在 `dev` 上验过的修复，下一次发版前**不执行** |
| 逼出绕 `dev` 的提交 | 为「让 cron 用上新脚本」，连续 5 个 PR 以 `main` 为 base（CNB #114 / #122 / #124 / #126）⇒ 两侧 `main` 互不包含 |

本守卫把这句「被读偏一格的话」钉成判据：**定时作业（`crontab:` / `cron:`）只允许挂在
`ACTIVE_BRANCH`（= `dev`）下**。

判据（静态、不拉网络）
----------------------
1. 顶层出现 `main:` 段，且其下**有任何**定时事件 ⇒ 报红，并指出如何迁移（挂到 `dev:`）；
2. 顶层出现 `main:` 段时，若 `dev:` 段里**没有**任何一个定时事件 ⇒ 报红：
   那等于「定时作业全被搬去了一个不跑的地方」，是**判据失效**而不是修复；
3. **`ACTIVE_BRANCH` 必须真的存在于顶层**：本仓的分支集合变了（`dev` 改名 / 删掉）时，
   这条会先红——否则本守卫会拿着一个不存在的分支名「全绿」地放行（#171 的失败态纪律：
   **拿不到输入 ≠ 输入为空**）。

边界（有意为之）
----------------
- **不复制两份**：判据只认「挂在 `dev`」，不提供「`dev` + `main` 各一份」的放行口径。
  两份会让每轮作业跑两遍（标签 / 评论重复），且「哪份是真的」没人说得清——用户明确反对。
- **不判断作业内容**：跑什么、推哪个分支是 `guard_cron_job_reachability.py` 的事，
  本守卫只管「挂在哪个分支键下」。
- **不管 `pull_request` / `push` 事件**：它们按「事件发生在哪个分支」取配置，不按时间重复，
  与 cron 的取舍相反（`main:` 段里若只剩 PR 守卫，那是合法的——只是本仓现在连它也不留）。
- **重复键 ⇒ 直接判输入不可信**（#458：`safe_load` 会吃掉被覆盖段，判据对它一无所知）。

用法
----
    python scripts/guard_cron_covers_active_branch.py            # 检查仓库根 .cnb.yml
    python scripts/guard_cron_covers_active_branch.py --file x   # 检查指定文件
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用（**不得**退化成「没问题」）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# 本仓的活跃分支：所有定时作业都该挂在这里。
# ⚠️ 换名字要同时改这里与 `.cnb.yml`——判据 3 会检查它真的存在。
ACTIVE_BRANCH = 'dev'

# 定时事件的键名形态：`"crontab: 0 18 * * *"` / `"cron: …"`（与 guard_cron_job_reachability 同源）。
_CRON_KEY = re.compile(r'^\s*[\'\"]?\s*(?:crontab|cron)\s*:', re.IGNORECASE)


class _DupKeyLoader(yaml.SafeLoader):
    """保留重复键的 SafeLoader（与 `guard_cron_job_reachability.py` 同源、各自持有）。"""

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


def _has_cron(events: object) -> bool:
    return isinstance(events, dict) and any(_CRON_KEY.match(f'{k}:') for k in events)


def check_data(data: dict) -> list[str]:
    """判据本体：定时事件只许挂在 `ACTIVE_BRANCH` 下。"""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ['输入不可信：`.cnb.yml` 顶层不是一个映射。']

    if ACTIVE_BRANCH not in data:
        problems.append(
            f'输入不可信：顶层找不到 `{ACTIVE_BRANCH}:` 段。本守卫以它为「活跃分支」，'
            '而判据本身认不出这个名字是否还成立 ⇒ **本轮结论不可信**，'
            '不得读成「定时作业挂对了」。分支改名 / 删除时请同步更新 `ACTIVE_BRANCH`。'
        )

    for key, events in data.items():
        if key == ACTIVE_BRANCH or not _has_cron(events):
            continue
        names = [k for k in events if _CRON_KEY.match(f'{k}:')]
        shown = ', '.join(f'`{n}`' for n in names)
        problems.append(
            f'`{key}:` 段下挂了定时事件 {shown}，而活跃分支是 `{ACTIVE_BRANCH}`。'
            f'定时作业必须挂在 `{ACTIVE_BRANCH}:` 下（源 CNB #564）：'
            f'`{key}` 只在发版 / 合并时才前进 ⇒ '
            '在 `dev` 上验过的修复要等下一次发版才执行，而「为了让它生效」又会逼出'
            f'以 `{key}` 为 base 的提交（CNB #114 / #122 / #124 / #126 实测）。'
            f'迁移姿势：把整段定时事件**搬**到 `{ACTIVE_BRANCH}:` 下，'
            '**不要复制两份**（两份 = 每轮跑两遍、标签与评论重复）。'
        )

    if ACTIVE_BRANCH in data and not _has_cron(data[ACTIVE_BRANCH]):
        problems.append(
            f'`{ACTIVE_BRANCH}:` 段下没有任何定时事件 —— 定时作业等于**没在跑**。'
            '若这是刻意的（临时停用全部 cron），请在本守卫的 ACTIVE_BRANCH 旁写明原因；'
            '否则它属于「迁移做了一半」：另一段里的 cron 删掉了，这边没搬过来（#171 假绿同族）。'
        )
    return problems


def check_text(text: str) -> list[str]:
    dups = find_duplicate_keys(text)
    if dups:
        seen = ', '.join(f'`{k}`（第 {ln} 行起）' for k, ln in dups)
        return [
            f'输入不可信：`.cnb.yml` 存在重复键 {seen}。'
            '`yaml.safe_load` 用后者覆盖前者，被覆盖段的 job **不会进入本次检查**'
            '—— 遮蔽状态下报「全绿」是假绿灯。'
            '先跑 `python scripts/guard_cnb_yml_duplicate_keys.py` 修掉重复键再复检。'
        ]
    return check_data(yaml.safe_load(text))


def self_check() -> list[str]:
    """正反探针：判据写坏了会全绿（本仓老规矩）。"""
    errors: list[str] = []
    cron = 'crontab: 0 18 * * *'

    ok = {ACTIVE_BRANCH: {cron: [{'name': 'j'}], 'push': [{'name': 'p'}]}}
    if check_data(ok):
        errors.append('自检失败：挂在 `dev` 下的 cron 被误报（判据过宽）。')

    bad = {'main': {cron: [{'name': 'j'}]}, ACTIVE_BRANCH: {cron: [{'name': 'j'}]}}
    if not check_data(bad):
        errors.append('自检失败：`main` 下的 cron 没被拦（正是源 CNB #564 的形态）。')

    dup = {'main': {cron: [{'name': 'j'}]}, ACTIVE_BRANCH: {cron: [{'name': 'j'}]}}
    if len([p for p in check_data(dup) if 'main' in p]) != 1:
        errors.append('自检失败：`main` 与 `dev` 各一份没被拦（用户明确反对复制两份）。')

    missing = {'main': {'push': [{'name': 'p'}]}, ACTIVE_BRANCH: {'push': [{'name': 'p'}]}}
    if not any('没有任何定时事件' in p for p in check_data(missing)):
        errors.append('自检失败：`dev` 下没有 cron（等于全停）没被拦 —— 迁移做了一半会静默。')

    renamed = {'trunk': {cron: [{'name': 'j'}]}}
    if not any('不可信' in p for p in check_data(renamed)):
        errors.append('自检失败：活跃分支不存在时没判「结论不可信」（#171 的失败态纪律）。')

    pr_only = {'main': {'pull_request.mergeable': [{'name': 'g'}]}, ACTIVE_BRANCH: {cron: [{'name': 'j'}]}}
    if check_data(pr_only):
        errors.append('自检失败：非 cron 事件被误判（本判据只管定时作业）。')
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description='检查定时作业是否挂在活跃分支上（源 CNB #564）'  # cross-repo-ref-allow
    )
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
        print('❌ 定时作业挂载位置检查未通过：', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        return 1
    print(f'✅ 定时作业都挂在活跃分支 `{ACTIVE_BRANCH}` 下（无 `main` 副本）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
