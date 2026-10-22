#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守门：备份类数据库文件必须被 gitignore 忽略（私有数据入库防线）。

WHY（实测事故，不是假想）
------------------------
本仓的数据库忽略规则写在 `backend/.gitignore`：

    *.db
    *.db-shm
    *.db-wal
    *.db.backup*

问题在 `*.db` **只匹配「以 .db 结尾」的文件名**。于是另一种同样常见的备份命名
——`invest.db.bak_20261018_anchor`（日期 + 标签）——**不被任何规则命中**。
2026-10-19 实测：`git check-ignore -v --no-index backend/invest.db.bak_probe`
退出码 **1**（= 没被忽略），而一个 **145MB** 的 `invest.db.bak_20261018_anchor`
就以未跟踪文件躺在 `backend/` 里。

后果很具体：一次 `git add -A` 就会把**用户私有数据**（持仓、流水、账户）提交进仓库。
仓库是公开可见的——这类东西一旦入库，撤不干净（历史里还在）。

判据
----
1. **探针必须被忽略**：合成一批「可能出现的备份文件名」，逐个用
   `git check-ignore --no-index -q` 判定；任一未被忽略 ⇒ 红。
   探针覆盖 `.db` / `.db.bak*` / `.db.backup*` / `.db-wal` / `.db-shm` / `.sqbpro`，
   且**根目录与 backend/ 两个位置都测**（根目录漏了就等于没修）。
2. **工作区不得有漏网的未跟踪 db 文件**：`git status --porcelain --untracked-files=all`
   里 `??` 开头、且文件名命中上述模式的条目 ⇒ 红并列出。
   这条抓的是「规则被改掉 / 新命名方式出现」——探针只验证规则，工作区这条验证现实。

退出码
------
0 通过 / 1 有漏网 / 2 输入不可信（不是 git 仓库、git 不可用、拿不到 status 输出）。

边界
----
- 只管**文件名模式**，不管文件内容；
- 不检查已跟踪文件（已入库的东西不在本守卫范围内，撤除要人工处理）；
- 不检查 GitHub 侧的历史（已经推上去的备份要人工清历史）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

#: 必须被忽略的合成文件名（相对仓库根）。
PROBE_PATHS: tuple[str, ...] = (
    'backend/invest.db',
    'backend/invest.db-wal',
    'backend/invest.db-shm',
    'backend/invest.db.bak_probe',
    'backend/invest.db.backup_probe',
    'backend/invest.sqbpro',
    'invest.db.bak_probe',
    'invest.db',
)

#: 工作区里出现即报红的文件名模式（`git add -A` 会把它们塞进仓库）。
DANGEROUS_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\.db$'),
    re.compile(r'\.db-bak.*$'),
    re.compile(r'\.db\.bak.*$'),
    re.compile(r'\.db\.backup.*$'),
    re.compile(r'\.db-wal$'),
    re.compile(r'\.db-shm$'),
    re.compile(r'\.sqbpro$'),
)


def is_dangerous_name(name: str) -> bool:
    """文件名是否属于「数据库 / 备份」类（会被 `git add -A` 卷进仓库）。"""
    base = name.rsplit('/', 1)[-1]
    return any(pattern.search(base) for pattern in DANGEROUS_NAME_PATTERNS)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['git', *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )


def check_probes(root: Path) -> list[str]:
    """探针检查：返回未忽略的探针列表。

    一次 ``git check-ignore`` 调用传全部探针（逐个调用的话，每次探针都要起一个
    git 进程，本机实测 8 个探针要多花好几秒）。
    """
    result = _git(root, 'check-ignore', '--no-index', '-v', *PROBE_PATHS)
    # 输出格式：``<来源>:<行号>:<规则>\t<路径>``（每个被忽略的路径一行）
    ignored: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split('\t', 1)
        if len(parts) == 2:
            ignored.add(parts[1].strip())
    return [path for path in PROBE_PATHS if path not in ignored]


def check_worktree(root: Path) -> list[str]:
    """工作区检查：返回「未被忽略、又会被 add -A 卷进去」的未跟踪文件。"""
    status = _git(root, 'status', '--porcelain', '--untracked-files=all')
    if status.returncode != 0:
        raise RuntimeError(f'git status 失败：{status.stderr.strip()}')
    leaked: list[str] = []
    for line in status.stdout.splitlines():
        if not line.startswith('?? '):
            continue
        path = line[3:].strip().strip('"')
        if is_dangerous_name(path):
            leaked.append(path)
    return leaked


def run(root: Path) -> int:
    _ensure_utf8_stdio()
    inside = _git(root, 'rev-parse', '--is-inside-work-tree')
    if inside.returncode != 0 or inside.stdout.strip() != 'true':
        print(f'❌ 不是 git 仓库：{root}', file=sys.stderr)
        return 2

    findings: list[str] = []

    try:
        leaked = check_worktree(root)
    except RuntimeError as exc:
        print(f'❌ 输入不可信：{exc}', file=sys.stderr)
        return 2
    for path in leaked:
        findings.append(f'工作区里有未忽略的数据库/备份文件：{path}（git add -A 会把它提交进仓库）')

    for probe in check_probes(root):
        findings.append(f'该路径没有被 gitignore 忽略：{probe}（补 backend/.gitignore 与 .gitignore 的规则）')

    if findings:
        print(f'❌ 数据库备份文件未受 ignore 保护（{len(findings)} 处）：', file=sys.stderr)
        for item in findings:
            print(f'  - {item}', file=sys.stderr)
        return 1

    print(f'✅ 数据库/备份文件保护正常：{len(PROBE_PATHS)} 个探针全部被忽略，工作区无漏网文件')
    return 0


def _ensure_utf8_stdio() -> None:
    """Windows 控制台默认 GBK，直接 print 中文/符号会 UnicodeEncodeError 崩掉——
    守门在本地跑崩 = 守门失效。统一把输出流切到 UTF-8（同 guard_job_schedule_coverage.py）。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8')
            except (AttributeError, ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()

    parser = argparse.ArgumentParser(description='数据库备份文件 ignore 守门')
    parser.add_argument('--root', default=None, help='仓库根目录，默认取本脚本的上一级')
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    return run(root)


if __name__ == '__main__':
    sys.exit(main())
