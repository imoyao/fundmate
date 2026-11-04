#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dependabot 分支重建：把「撞锁冲突」变成「以 dev 为底的单 commit」（#2434 第二阶段）。

## WHY：重生成锁只修了「锁是坏的」，没修「锁是好但分支撞在一起」

`scripts/regen_pnpm_lockfile.mjs` 以 `origin/dev` 的锁为基线重生成，解决了
`ERR_PNPM_LOCKFILE_MISSING_DEPENDENCY`（#2394 形态）。但 2026-10-26 的实测暴露第二形态：

| PR | 形态 | 结果 |
|---|---|---|
| #2646（parser 8.72.0）、#2648（typescript-eslint 8.72.0） | 各自只改一个包、**都重写同一份 `frontend/pnpm-lock.yaml`** ⇒ 双双 `mergeable=CONFLICTING` | 锁已被重生成通道修好，仍需人用 #2659 一次性收口 |

两个关键事实叠加，让这条通道「修好了锁却依然要人」：

1. **重生成只改锁内容，不把分支挪到 dev 之上**。分支仍落后于 dev，GitHub 判冲突；
2. **冲突状态下 `pull_request` 类工作流不触发**（CI 根本不跑）——所以连红灯都没有，
   没人会被叫醒；冲突只能靠人发现。

而手工配方（#2394 / #2395 / #2397 三次验证）早已给出正解：**以最新 dev 为底，
只把 PR 的 manifest 改动搬过去，锁用 dev 基线重生成，单 commit 强推**。
本脚本就是把这条配方机器化——它不发明新口径，只是不再依赖人的 15 分钟。

## 什么情况下适用（栅栏）

只处理**改动仅限 `package.json` / `pnpm-lock.yaml`** 的分支。dependabot 的 bump PR
天然满足；一旦出现别的文件（改了源码、改了 workflow），说明这不是纯依赖升级，
锁怎么生成都不该由脚本替 PR 决定 —— 退出码 3，交回调用方走「只重生成锁」的旧路径。

## 为什么不 `git rebase`，而 `checkout -B dev` + 搬 manifest

因为冲突的**就是锁文件**：`git rebase` 到 dev 上一定在 `pnpm-lock.yaml` 里冲突，
而那份冲突解没有任何价值（锁的唯一正解是「pnpm 按 manifest 重算」）。
rebuild 把「搬 manifest」与「重算锁」分开：manifest 的改动是 PR 的意图，要保留；
锁的改动是 dependabot 的错误重写，应当丢弃重来。这也解释了为什么提交是**一个**——
不是追加一个修补提交，而是把 PR 重建成「dev + 该 PR 的 manifest 意图」。

## 幂等

重建完成后再跑一次：dev 已是分支祖先 ⇒ 调用方走旧路径；即便走到这里，
重算出的锁与已有内容一致 ⇒ `git diff --cached` 为空 ⇒ 不提交（`applied=no reason=no_diff`），
于是「rebuild → push → synchronize → 再 rebuild」不会自激。

## 退出码

| 码 | 含义 | 调用方该做什么 |
|---|---|---|
| 0 | 已重建并提交（或已是最新、无差异） | 推送（若 HEAD 变了）+ 批准新 runs |
| 2 | 拿不到输入 / 无法安全重建（git 失败、manifest 补丁打不上、重生成自证失败） | **不得推送**，报红或降级 |
| 3 | 不适用（改动超出 manifest / 锁） | 走「只重生成锁」的旧路径 |

## 用法

    python scripts/rebuild_dependabot_branch.py --branch <分支名> --base origin/dev --apply

默认 dry-run（`--apply` 才真的 checkout / 提交）——与 `regen_pnpm_lockfile.mjs`、
`commit_changes.py` 同一条纪律：试跑不该有副作用。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

MANIFEST = 'package.json'
LOCK = 'pnpm-lock.yaml'

#: 只允许这两类文件：前者是 PR 的意图，后者是 dependabot 的错误重写。
ALLOWED_BASENAMES = frozenset({MANIFEST, LOCK})

#: manifest 里可能承载版本声明的四个依赖组（与 regen 脚本、`changedSpecifiers` 同口径）。
DEP_GROUPS = ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies')

EXIT_OK = 0
EXIT_UNSAFE = 2
EXIT_NOT_APPLICABLE = 3

_COMMIT_MSG = """chore(deps): 重建 dependabot 分支并重生成 pnpm 锁（撞锁冲突自动收口，#2434）

原生 dependabot 只改一个包，却重写整份 pnpm-lock.yaml。同一批发布里开出的两个 PR
会在同一份锁上互撞（mergeable=CONFLICTING），而冲突状态下 pull_request 类工作流
不触发，连红灯都不会亮——只能靠人开一张汇总 PR 收口（#2646 / #2648 → #2659）。

本提交由 .github/workflows/dependabot-lockfile-regen.yml 生成：
以 origin/dev 为底，只搬运本 PR 的 package.json 改动，锁按 dev 基线用 pnpm 重生成，
收尾已跑 --frozen-lockfile 自证。因此分支是 dev 的直接后代，不会再判冲突。
"""


class GitError(RuntimeError):
    """git 命令非零退出——一律按「拿不到输入」，不得当成「无需处理」。"""


def rebuild_scope(changed_paths: Sequence[str]) -> Tuple[bool, List[str]]:
    """判断这批改动能否安全重建。

    返回 ``(适用?, 待处理的目录列表)``。目录用 pnpm 的 `--dir` 口径：仓库根是 ``'.'``，
    子目录是相对路径（如 ``frontend``）。只要出现一个非 manifest / 非锁的文件，
    就整体判「不适用」——不做「部分文件一起搬」的猜测。
    """
    dirs = set()
    for raw in changed_paths:
        path = raw.strip()
        if not path:
            continue
        name = path.rsplit('/', 1)[-1]
        if name not in ALLOWED_BASENAMES:
            return False, []
        parent = path.rsplit('/', 1)[0] if '/' in path else '.'
        dirs.add(parent)
    return bool(dirs), sorted(dirs)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ['git', *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    if proc.returncode != 0:
        raise GitError(f'git {" ".join(args)} 失败（rc={proc.returncode}）：{proc.stderr.strip()}')
    return proc.stdout


def _git_with_file(repo: Path, args: Sequence[str], content: str, suffix: str) -> str:
    """把内容写成临时文件再交给 git。

    ⚠️ 不走 stdin：Windows 上 `subprocess` 的文本模式会把 `\\n` 翻成 `\\r\\n`，
    补丁的上下文行被污染后 `git apply` 只会报「patch does not apply」——
    看着像「分支搬不动」，实际是编码被改了（本地首次实测即踩到）。
    提交信息同理：中文走文件才不会被控制台代码页改坏（AGENTS.md 既有约定）。
    """
    handle = tempfile.NamedTemporaryFile(
        'w', encoding='utf-8', newline='\n', suffix=suffix, delete=False
    )
    try:
        with handle:
            handle.write(content)
        return _git(repo, *args, handle.name)
    finally:
        Path(handle.name).unlink(missing_ok=True)


def _line(branch: str, base: str, dirs: Sequence[str], applied: str, reason: str, commit: str = '-') -> str:
    """自证行：日志里必须能回答「跑没跑、为什么、结论是什么」。"""
    return (
        f'DEPENDABOT_REBUILD branch={branch} base={base} '
        f'dirs={",".join(dirs) or "-"} applied={applied} reason={reason} commit={commit}'
    )


def _manifest(repo: Path, ref: str, directory: str) -> dict:
    path = MANIFEST if directory == '.' else f'{directory}/{MANIFEST}'
    try:
        return json.loads(_git(repo, 'show', f'{ref}:{path}'))
    except (GitError, json.JSONDecodeError) as exc:
        raise GitError(f'取不到 {ref}:{path} 的 manifest：{exc}') from exc


def _dep_groups(manifest: dict) -> dict:
    return {
        group: manifest.get(group) or {}
        for group in DEP_GROUPS
        if isinstance(manifest.get(group), dict)
    }


def changed_specs(base: dict, other: dict) -> List[Tuple[str, str, str, str]]:
    """``(group, name, 旧 spec, 新 spec)``——只认 spec 真的变了的条目。"""
    out = []
    base_groups, other_groups = _dep_groups(base), _dep_groups(other)
    for group in DEP_GROUPS:
        before, after = base_groups.get(group, {}), other_groups.get(group, {})
        for name, spec in after.items():
            if before.get(name) != spec:
                out.append((group, name, str(before.get(name)), str(spec)))
    return out


def non_dependency_changes(base: dict, other: dict) -> List[str]:
    """依赖组之外被动过的顶层键——那种 PR 不是纯 bump，交给旧路径。"""
    out = []
    for key in set(base) | set(other):
        if key in DEP_GROUPS:
            continue
        if base.get(key) != other.get(key):
            out.append(key)
    return sorted(out)


def _bump_manifest_text(dev_text: str, changes: Sequence[Tuple[str, str, str, str]]) -> Optional[str]:
    """在 dev 的 manifest **原文**上逐条替换 spec，保住原有格式与排序。

    为什么不用 `git apply -3` 打补丁：两边都在同一行位置插入依赖（JSON 里还牵扯逗号），
    文本层必然冲突——实测 `UU package.json`。而 bump PR 的意图本来就窄到「这个包的
    spec 换成那个」，所以只换那一个字符串是对意图最忠实的搬运，也不会碰 dev 的其它改动。
    任一条对不上（dev 已改过同一个包 / 该行被重排）就返回 None，交回旧路径。
    """
    text = dev_text
    for _group, name, old_spec, new_spec in changes:
        target = re.compile(r'"' + re.escape(name) + r'"\s*:\s*"' + re.escape(new_spec) + r'"')
        if target.search(text):
            # dev 上已经是目标版本（同批两个 PR 撞同一个包时常见）：无需再改。
            continue
        if not old_spec:
            return None
        pattern = re.compile(r'("' + re.escape(name) + r'"\s*:\s*")' + re.escape(old_spec) + r'(")')
        text, count = pattern.subn(lambda m: f'{m.group(1)}{new_spec}{m.group(2)}', text, count=1)
        if count != 1:
            return None
    return text


def _read_ref_file(repo: Path, ref: str, directory: str) -> str:
    path = MANIFEST if directory == '.' else f'{directory}/{MANIFEST}'
    return _git(repo, 'show', f'{ref}:{path}')


def _merge_manifest(repo: Path, base: str, branch_ref: str, directory: str) -> Optional[str]:
    """返回「dev 的 manifest 原文 + 本 PR 的 spec 变更」；无需改动时返回 None。"""
    merge_base = _git(repo, 'merge-base', base, branch_ref).strip()
    base_manifest = _manifest(repo, merge_base, directory)
    branch_manifest = _manifest(repo, branch_ref, directory)

    outside = non_dependency_changes(base_manifest, branch_manifest)
    if outside:
        raise GitError(f'{directory} 的 manifest 动了依赖组之外的键：{outside}')

    changes = changed_specs(base_manifest, branch_manifest)
    if not changes:
        return None

    merged = _bump_manifest_text(_read_ref_file(repo, base, directory), changes)
    if merged is None:
        raise GitError(
            f'{directory} 的 {[name for _g, name, _o, _n in changes]} 在 dev 上已被改过，'
            '无法安全搬运（不猜该保留哪个版本）'
        )
    return merged


def rebuild(
    repo: Path,
    branch: str,
    base: str = 'origin/dev',
    regen_script: Optional[Path] = None,
    apply: bool = False,
) -> Tuple[int, str]:
    """执行重建，返回 ``(退出码, 自证行)``。"""
    base_branch = base.split('/')[-1] if '/' in base else base
    branch_ref = f'origin/{branch}'
    dirs: List[str] = []

    _git(repo, 'fetch', '--no-tags', 'origin', branch, base_branch)
    # 工作区不干净就别动手：`checkout -B` 会把未提交改动一起卷进来，
    # 之后无论是提交还是回退都说不清「这条分支上到底有什么」。
    if _git(repo, 'status', '--porcelain').strip():
        return EXIT_UNSAFE, _line(branch, base, dirs, 'no', 'dirty_worktree')
    changed = _git(repo, 'diff', '--name-only', f'{base}...{branch_ref}').splitlines()
    if not changed:
        return EXIT_OK, _line(branch, base, dirs, 'no', 'no_change')

    applicable, dirs = rebuild_scope(changed)
    if not applicable:
        return EXIT_NOT_APPLICABLE, _line(branch, base, dirs, 'no', 'non_manifest_change')

    if not apply:
        return EXIT_OK, _line(branch, base, dirs, 'no', 'dry_run')

    # 已是 dev 祖先：branch 上没有「落后的历史」可丢，调用方该走「只重生成锁」的路径。
    ancestor = subprocess.run(
        ['git', 'merge-base', '--is-ancestor', base, branch_ref],
        cwd=str(repo),
    )
    if ancestor.returncode == 0:
        return EXIT_NOT_APPLICABLE, _line(branch, base, dirs, 'no', 'already_current')

    # 底做成 dev：这一步就把「落后 dev」与「锁冲突」同时消掉。
    _git(repo, 'checkout', '--quiet', '-B', branch, base)

    try:
        for directory in dirs:
            merged = _merge_manifest(repo, base, branch_ref, directory)
            if merged is not None:
                target = Path(repo) / (MANIFEST if directory == '.' else f'{directory}/{MANIFEST}')
                target.write_text(merged, encoding='utf-8', newline='\n')
    except GitError as exc:
        # 搬不动 = 这次不适合重建（dev 对同一份 manifest 动过别的手脚）。
        # 不是「输入拿不到」，交回调用方走「只重生成锁」的旧路径，并留下可查的原因。
        _git(repo, 'checkout', '--quiet', '-B', branch, base)
        return EXIT_NOT_APPLICABLE, (
            f'{_line(branch, base, dirs, "no", "manifest_merge_failed")} error={exc}'
        )

    script = regen_script or Path(__file__).resolve().parent / 'regen_pnpm_lockfile.mjs'
    for directory in dirs:
        proc = subprocess.run(
            ['node', str(script), '--dir', directory, '--base-ref', base, '--apply'],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding='utf-8',
        )
        sys.stdout.write(proc.stdout)
        if proc.returncode != 0:
            # 脚本内部已回滚锁文件；这里再退到 dev，确保不留半成品分支。
            _git(repo, 'checkout', '--quiet', '-B', branch, base)
            return EXIT_UNSAFE, (
                f'{_line(branch, base, dirs, "no", "regen_failed")} '
                f'rc={proc.returncode} dir={directory}'
            )

    if not _git(repo, 'status', '--porcelain').strip():
        return EXIT_OK, _line(branch, base, dirs, 'no', 'no_diff')

    _git(repo, 'add', '--', *[MANIFEST if d == '.' else f'{d}/{LOCK}' for d in dirs])
    _git(repo, 'add', '--', *[f'{d}/{MANIFEST}' if d != '.' else MANIFEST for d in dirs])
    _git_with_file(repo, ('commit', '--quiet', '-F'), _COMMIT_MSG, '.msg')
    sha = _git(repo, 'rev-parse', 'HEAD').strip()
    return EXIT_OK, _line(branch, base, dirs, 'yes', 'rebuilt', sha[:9])


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description='以 dev 为底重建 dependabot 分支（#2434）')
    parser.add_argument('--branch', required=True, help='PR 的 head 分支名')
    parser.add_argument('--base', default='origin/dev', help='基分支引用（默认 origin/dev）')
    parser.add_argument('--repo', default='.', help='仓库根目录')
    parser.add_argument('--regen-script', default=None, help='regen_pnpm_lockfile.mjs 路径')
    parser.add_argument('--apply', action='store_true', help='真的执行（默认 dry-run）')
    args = parser.parse_args(argv)

    try:
        code, line = rebuild(
            repo=Path(args.repo).resolve(),
            branch=args.branch,
            base=args.base,
            regen_script=Path(args.regen_script) if args.regen_script else None,
            apply=args.apply,
        )
    except GitError as exc:
        print(f'::error::分支重建失败（{args.branch}）：{exc}')
        return EXIT_UNSAFE

    print(line)
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
