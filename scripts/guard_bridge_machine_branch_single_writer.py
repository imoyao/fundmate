#!/usr/bin/env python3
"""守门：`bridge/github-dev`（机器分支）**只能有一个写者**（源 CNB #574，2026-10-19）。  <!-- cross-repo-ref-allow -->

WHY：这条分支上有两个写者，而它们互相砸了几天

| 写者 | 触发 | 写法 | 开 PR 吗 |
|---|---|---|---|
| GitHub `.github/workflows/dev-reconcile.yml` | 每日 `cron: 37 18 * * *` | `push --force-with-lease`，`merge -X ours cnb/dev` | **开**（并挂 `automerge`） |
| CNB `.cnb.yml` 的「跨仓同步」stage | 每次推 `dev` | 每轮换 base 重新合，普通 `push`（非 force） | 不开 |

后果不是「偶尔红」，是**结构性的**：

1. 归一化 base 变了 ⇒ 结果不是 GitHub 那条 ref 的快进 ⇒
   `! [rejected] HEAD -> bridge/github-dev (fetch first)` —— 推 `dev` 的构建**天天红**；
2. 即便侥幸快进成功，也会**改写 reconcile 刚铺好的合并结果**，而**它开的那张 PR 还开着**
   ⇒ PR 内容与分支内容不符（比红灯危险：外观一切正常）。

判据（三条，静态、不拉网络）
----------------------------
1. **`.cnb.yml` 里调 `machine_branch.py` 的 stage 不得把 `MACHINE_BRANCH_WRITER` 设成 `cnb`**
   —— 设了就是「第二个写者」，而 GitHub reconcile 那边还在跑，两者并存即冲突。
2. **`machine_branch.py` 的 `DEFAULT_WRITER` 必须是 `github`**
   —— 默认值一旦翻成 `cnb`，等于**静默**把写权搬回 CNB，而 `.cnb.yml` 一个字都没改。
   这是本判据唯一防不住的场景（配置看起来完全正常），故必须单独钉。
3. **`dev-reconcile.yml` 必须仍然是「推 + 开 PR」的那条通道**
   —— 若哪天它被删掉/停用，CNB 侧降级为只读就变成了**没人写**：
   分支永远停在旧内容，而**两边都绿**（本卡同族的假绿形态）。

边界（有意为之）
----------------
- **不判断「谁先跑」**：`--force-with-lease` 是原子检验，不是可协商的锁；
  任何「先比 SHA 再推」都是检查-使用之间的竞态，故本判据只认**静态角色分配**。
- **不读 GitHub 侧 workflow 的启用状态**：Actions 是否被关只有 API 知道，
  判据只确认那份文件仍然表达「写者」语义（`push` + 开 PR）。
- **不管 `MACHINE_BRANCH_WRITER` 之外的接管方式**：要接管就得改这里，跑一遍守卫即暴露。

用法
----
    python scripts/guard_bridge_machine_branch_single_writer.py            # 检查仓库根
    python scripts/guard_bridge_machine_branch_single_writer.py --root x   # 指定仓库根
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用（**不得**退化成「没问题」，#171）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MACHINE_SCRIPT = 'scripts/bridge/machine_branch.py'
RECONCILE_WORKFLOW = '.github/workflows/dev-reconcile.yml'
WRITER_ENV = 'MACHINE_BRANCH_WRITER'

# CNB 侧 stage 里出现这些写法即视为「把写权设成 cnb」。
_CNB_WRITER_RE = re.compile(
    r'(?:export\s+)?' + WRITER_ENV + r'\s*[=:]\s*["\']?cnb\b',
    re.IGNORECASE,
)

# `machine_branch.py` 里 `DEFAULT_WRITER = 'github'`
_DEFAULT_WRITER_RE = re.compile(r"^DEFAULT_WRITER\s*=\s*['\"](\w+)['\"]", re.MULTILINE)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def check_cnb_yml(text: str) -> list[str]:
    """判据 1：`.cnb.yml` 里凡调用 `machine_branch.py` 的段落，都不得把自己设成写者。"""
    problems: list[str] = []
    if MACHINE_SCRIPT.rsplit('/', 1)[-1] not in text:
        # 没有调用点 ⇒ 判据不适用。但**必须显式说明**：静默返回 [] 时，
        # 「文件被改名 / 调用被挪走」与「合规」长得一模一样（#171 的失败态纪律）。
        print(
            f'ℹ️ {MACHINE_SCRIPT} 未在 .cnb.yml 中被调用 —— 判据 1 不适用（调用点挪走了请一起改守卫）',
            file=sys.stderr,
        )
        return problems
    # 逐段看：把文件按行扫，命中 `machine_branch.py` 的行往上找同一条脚本块里的写者赋值。
    # 简化口径：整份文件里出现 `MACHINE_BRANCH_WRITER=cnb` 即报 —— 本仓只有这一处调它，
    # 而「在某处设过」本身就是「有人打算让 CNB 当写者」，不该被段落/缩进差异放过。
    for m in _CNB_WRITER_RE.finditer(text):
        line_no = text[: m.start()].count('\n') + 1
        problems.append(
            f'`.cnb.yml` 第 {line_no} 行把 `{WRITER_ENV}` 设成 `cnb` —— '
            '这会让 CNB 成为 `bridge/github-dev` 的**第二个写者**。'
            'GitHub `.github/workflows/dev-reconcile.yml` 仍在每日 `--force-with-lease` 重建它，'
            '两者并存 ⇒ 非快进被拒（构建天天红）+ 冲掉 reconcile 的合并结果（PR 内容与分支不符）。'
            '要接管，必须先停掉 reconcile 的推送步骤，并同步改本守卫。'
        )
    return problems


def check_script_default(text: str) -> list[str]:
    """判据 2：脚本默认写者必须是 github（默认值翻转 = 静默搬走写权）。"""
    m = _DEFAULT_WRITER_RE.search(text)
    if not m:
        return [f'`{MACHINE_SCRIPT}` 里找不到 `DEFAULT_WRITER = ...` —— 判据失去锚点，不得当作通过。']
    if m.group(1).lower() != 'github':
        return [
            f'`{MACHINE_SCRIPT}` 的 `DEFAULT_WRITER` 是 `{m.group(1)}`，应为 `github` —— '
            + 'CNB 默认必须是**只读探针**，否则它又成了第二个写者（源 CNB #574）。'
        ]
    return []


def check_reconcile_still_writes(text: str) -> list[str]:
    """判据 3：被降级的那一侧，必须确认另一侧**真的还在写**（否则变成「没人写」）。"""
    problems: list[str] = []
    if 'bridge/github-dev' not in text:
        problems.append(
            f'`{RECONCILE_WORKFLOW}` 里已经没有 `bridge/github-dev` —— '
            'CNB 侧已降级为只读，若 GitHub 侧也不再重建这条分支，就**没有任何写者**了。'
            '（这种形态两边都绿，分支却永远停在旧内容。）'
        )
    if not re.search(r'git\s+push\s+origin\s+bridge/github-dev', text):
        problems.append(
            f'`{RECONCILE_WORKFLOW}` 里找不到 `git push origin bridge/github-dev` —— '
            '被降级的一侧若无对侧接手，机器分支会永久停更。'
        )
    return problems


def self_check() -> list[str]:
    """正反探针：判据写坏了会全绿，故每次跑都自证一次。"""
    errors: list[str] = []

    bad_cnb = f'          python {MACHINE_SCRIPT} --apply --push\n          export {WRITER_ENV}=cnb\n'
    if not check_cnb_yml(bad_cnb):
        errors.append('自检失败：`.cnb.yml` 设 `MACHINE_BRANCH_WRITER=cnb` 没被拦。')
    if check_cnb_yml(f'          python {MACHINE_SCRIPT} --apply --push\n'):
        errors.append('自检失败：没设写者的样本被误报（判据过宽）。')

    if not check_script_default("DEFAULT_WRITER = 'cnb'\n"):
        errors.append('自检失败：脚本默认写者翻成 cnb 没被拦（这是「静默搬走写权」）。')
    if check_script_default("DEFAULT_WRITER = 'github'\n"):
        errors.append('自检失败：合法的 `DEFAULT_WRITER = github` 被误报。')
    if not check_script_default('WRITER_ENV = "X"\n'):
        errors.append('自检失败：找不到 DEFAULT_WRITER 时未报「锚点丢失」（会退化成假绿）。')

    good_wf = 'git push origin bridge/github-dev --force-with-lease\n'
    if check_reconcile_still_writes(good_wf):
        errors.append('自检失败：仍在推 bridge/github-dev 的 workflow 被误报。')
    if not check_reconcile_still_writes('on:\n  schedule: []\n'):
        errors.append('自检失败：写者消失的 workflow 没被拦（会变成「没人写」）。')
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='检查 bridge/github-dev 只有一个写者（源 CNB #574）')  # cross-repo-ref-allow
    ap.add_argument('--root', default=None, help='仓库根（默认本文件上两级）')
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    errors = self_check()
    if errors:
        for e in errors:
            print(f'❌ {e}', file=sys.stderr)
        return 2

    cnb_yml = _read(root / '.cnb.yml')
    script = _read(root / MACHINE_SCRIPT)
    workflow = _read(root / RECONCILE_WORKFLOW)
    missing = [
        name
        for name, text in (('.cnb.yml', cnb_yml), (MACHINE_SCRIPT, script), (RECONCILE_WORKFLOW, workflow))
        if text is None
    ]
    if missing:
        # 读不到输入 ≠ 没问题（#171 的失败态纪律）。
        print(f'❌ 输入不可用：读不到 {", ".join(missing)} —— 本轮结论不可信', file=sys.stderr)
        return 2

    problems = check_cnb_yml(cnb_yml) + check_script_default(script) + check_reconcile_still_writes(workflow)
    if problems:
        print('❌ 机器分支写者检查未通过：', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        return 1
    print('✅ `bridge/github-dev` 保持单写者（GitHub reconcile 写，CNB 只读探针）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
