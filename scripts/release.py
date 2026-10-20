#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发版助手：打 tag → 推 tag → 建 GitHub Release（默认 dry-run）。

WHY（#1996）
-----------
#1996 的病根不是代码，而是**没有可重复的发版动作**：仓库当时只有一个孤 tag `v0.1`，
Release 为空，`release: published` 通道从未被触发，于是 `/changelog` 一直是空的。
把动作固化成脚本，是为了让「下一次发版」不依赖某个人记得步骤。

设计要点
--------
- **默认 dry-run**：只打印将执行的命令，显式 `--apply` 才真正执行
  （与 `commit_changes.py` / `cleanup_temp.py` 同一纪律）。
- **tag 指向 `origin/main`**（默认，可用 `--ref` 改）：发版对象是合入 main 的那份代码。
  脚本用 `git tag <tag> <sha>` 指定提交，**不需要切换分支**——主仓库常驻 `dev`，
  切换分支会打断 dev server（见 AGENTS.md「主仓库只跑 dev server」）。
- **先推 tag、再建 Release**：`gh release create --verify-tag` 强制要求远端已有该 tag，
  避免 GitHub 从默认分支自行取一个你没看过的提交。
- 校验失败一律非零退出：不猜、不自动修正、不重试。

用法
----
    # 1) 写面向用户的 release notes（见 docs/dev/release-process.md 的模板）
    # 2) 预演（默认 dry-run）
    python scripts/release.py --tag v0.1.1 --notes-file release-notes-v0.1.1.md
    # 3) 真正执行
    python scripts/release.py --tag v0.1.1 --notes-file release-notes-v0.1.1.md --apply

退出码
------
0 成功 / 1 校验失败 / 2 执行失败（git / gh 返回非零）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

#: 版本号规范：0.x 阶段用 `vMAJOR.MINOR.PATCH`，预发布用 `-beta.1` 这类后缀。
#: 刻意**不接受**裸 `0.1.0`——本仓既有 tag 均带 `v` 前缀，混用会让 `gh release`
#: 与文档里的链接对不上。
TAG_PATTERN = re.compile(r'^v\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?$')

CHANGELOG_URL = 'https://feedback.duoduobei.com/changelog'


def validate_tag(tag: str) -> str | None:
    """返回错误信息；合法时返回 None。"""
    if not tag:
        return '缺少 --tag（例：v0.1.1）'
    if not TAG_PATTERN.match(tag):
        return f'tag 不合规范：{tag!r}（要求 vMAJOR.MINOR.PATCH，可带 -beta.1 之类后缀）'
    return None


def validate_notes(path: Path) -> tuple[str | None, str | None]:
    """读 notes 文件：返回 (内容, 错误信息)。空文件视为失败（有标题没内容 = 发了等于没发）。"""
    if not path.is_file():
        return None, f'找不到 notes 文件：{path}'
    text = path.read_text(encoding='utf-8').strip()
    if not text:
        return None, f'notes 文件为空：{path}'
    return text, None


def build_commands(tag: str, title: str, notes_file: Path, sha: str) -> list[list[str]]:
    """构造「打 tag → 推 tag → 建 Release」三条命令（dry-run 直接打印它们）。"""
    return [
        # -a 带注释 tag；-F 从文件读说明（避免命令行内联中文在 Windows GBK 控制台被写坏）
        ['git', 'tag', '-a', tag, sha, '-F', str(notes_file)],
        ['git', 'push', 'origin', f'refs/tags/{tag}'],
        # --verify-tag：远端没有这个 tag 就失败，不替我们猜提交
        ['gh', 'release', 'create', tag, '--verify-tag', '--title', title, '--notes-file', str(notes_file)],
    ]


def _run(command: list[str], dry_run: bool) -> int:
    printable = ' '.join(command)
    print(f'  $ {printable}')
    if dry_run:
        return 0
    result = subprocess.run(command, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        print(f'❌ 命令失败（退出码 {result.returncode}）：{printable}', file=sys.stderr)
        return 2
    return 0


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['git', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8')
            except (AttributeError, ValueError, OSError):
                pass

    parser = argparse.ArgumentParser(description='发版助手（默认 dry-run）')
    parser.add_argument('--tag', required=True, help='版本 tag，如 v0.1.1')
    parser.add_argument('--notes-file', required=True, type=Path, help='面向用户的 release notes（UTF-8）')
    parser.add_argument('--title', default=None, help='Release 标题，默认等于 tag')
    parser.add_argument('--ref', default='origin/main', help='tag 指向的提交，默认 origin/main')
    parser.add_argument('--apply', action='store_true', help='真正执行（默认只打印命令）')
    args = parser.parse_args(argv)

    error = validate_tag(args.tag)
    if error:
        print(f'❌ {error}', file=sys.stderr)
        return 1

    notes, error = validate_notes(args.notes_file)
    if error:
        print(f'❌ {error}', file=sys.stderr)
        return 1

    fetch = _git('fetch', 'origin', 'main', '--tags')
    if fetch.returncode != 0:
        print(f'❌ git fetch 失败，无法确认 {args.ref}：\n{fetch.stderr.strip()}', file=sys.stderr)
        return 2

    sha = _git('rev-parse', '--verify', f'{args.ref}^{{commit}}')
    if sha.returncode != 0:
        print(f'❌ 解析不到 {args.ref}：{sha.stderr.strip()}', file=sys.stderr)
        return 2
    commit = sha.stdout.strip()

    local_tag = _git('rev-parse', '--verify', '--quiet', f'refs/tags/{args.tag}')
    if local_tag.returncode == 0:
        print(f'❌ 本地已存在 tag {args.tag}，拒绝覆盖（删 tag 是破坏性操作，请人工判断）', file=sys.stderr)
        return 1

    remote_tag = _git('ls-remote', '--tags', 'origin', f'refs/tags/{args.tag}')
    if remote_tag.returncode != 0:
        print(f'❌ 查询远端 tag 失败：{remote_tag.stderr.strip()}', file=sys.stderr)
        return 2
    if remote_tag.stdout.strip():
        print(f'❌ 远端已存在 tag {args.tag}，拒绝覆盖', file=sys.stderr)
        return 1

    print(f'发版计划（{"执行" if args.apply else "dry-run"}）')
    print(f'  tag     : {args.tag}')
    print(f'  提交    : {args.ref} → {commit}')
    print(f'  标题    : {args.title or args.tag}')
    print(f'  notes   : {args.notes_file}（{len(notes.splitlines())} 行）')
    print('将执行：')

    for command in build_commands(args.tag, args.title or args.tag, args.notes_file, commit):
        code = _run(command, dry_run=not args.apply)
        if code:
            return code

    if args.apply:
        print('\n已发布，按以下顺序验证：')
        print('  1. gh run list --workflow=bridge-feedback.yml --event=release --limit 1')
        print(f'  2. 打开 {CHANGELOG_URL} 确认新条目可见且不是 draft')
    else:
        print('\n这是 dry-run；确认无误后加 --apply。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
