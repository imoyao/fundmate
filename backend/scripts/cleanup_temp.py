# -*- coding: utf-8 -*-
"""通用临时文件清理脚本（安全删除入口）。

=====================================================================
为什么需要这个工具（WHY）
=====================================================================
在本仓库的协作中，曾发现直接用 IDE / 编码助手的「删除文件」工具在部分
环境下会被系统拦截或静默失败（报 workspace boundary / 调用异常），导致
临时文件越积越多、且删除动作不可靠。为绕开这一限制、并把「删除」这一
破坏性操作统一收口，约定：**以后所有临时文件清理都走本 Python 脚本**，
不再依赖 IDE 删除工具。

它与 AGENTS.md「禁止武断执行」一节同源：删除属于破坏性操作，必须
「先列清单 → 给人判断 → 确认后才删」，绝不允许擅自静默删除可能有价值的文件。

=====================================================================
怎么执行（HOW — 给 AI / 人 的操作 SOP）
=====================================================================
前置：后端用 PDM 管理，必须从 backend/ 目录运行（路径相对仓库根）。

最安全方式 — AI/人传入精确文件清单（推荐，逐项列出要删的文件）：
    cd backend
    pdm run python backend/scripts/cleanup_temp.py --file ../_foo.ps1 --file ../_bar.txt
    # 确认无误后删除：
    pdm run python backend/scripts/cleanup_temp.py --file ../_foo.ps1 --file ../_bar.txt --apply

按模式方式 — 仅用于明显的临时文件命名（默认即 .tmp_* 等）：
    pdm run python backend/scripts/cleanup_temp.py
    pdm run python backend/scripts/cleanup_temp.py --pattern "_close*" --apply

步骤：
1. 先 dry-run 看清单（默认即 dry-run，不传 --apply 绝不删）。清单中每个文件
   会标注 [untracked] 或 [TRACKED-将跳过]——只有 untracked 的才会被删。
2. 把清单呈现给用户，说明要删哪些、为什么（临时调试/commit/issue 产物），
   等用户确认。
3. 用户确认后，才 --apply 真正删除。

=====================================================================
安全约束（SAFETY — 强制）
=====================================================================
- 默认 DRY_RUN：仅收集并打印「将要删除的文件」，绝不真正删除；
- 必须显式传 --apply 才真正删除；
- **删除前二次核验 git 跟踪状态**：对每个待删文件执行 `git status --porcelain`，
  只有状态为未跟踪（??）的文件才允许删除；已跟踪（含已修改/已暂存/入库）的
  文件一律跳过并标红警告 [TRACKED-跳过]，绝不删除。这是防止误删业务代码 /
  配置 / 入库资产的最后一道闸。
- 精准优先：能用 --file 精确列出要删的文件，就不要依赖宽模式（如 *.json）；
  宽模式曾误匹配到 package.json / vercel.json 等配置，已通过二次核验拦截。
- 默认只在白名单目录内清理（仓库根 + docs/working-notes），不递归扫源码；
  可用 --dir 扩展（可多次），但仍建议限定在临时产物目录；
- 绝不用本脚本删除源码 / 配置 / 文档 / 入库资产（如 all_pb.csv）。

用法速查：
    pdm run python backend/scripts/cleanup_temp.py --file ../x.ps1 --file ../y.txt   # 仅打印
    pdm run python backend/scripts/cleanup_temp.py --file ../x.ps1 --apply            # 确认后删
    pdm run python backend/scripts/cleanup_temp.py            # 默认模式仅打印清单
"""

import argparse
import fnmatch
import os
import subprocess
import sys

# 仓库根目录推断：scripts/cleanup_temp.py -> 上两级即仓库根。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# 默认只允许在以下目录内清理，防止误伤业务代码。
DEFAULT_DIRS = [
    REPO_ROOT,
    os.path.join(REPO_ROOT, 'docs', 'working-notes'),
]

# 默认文件名匹配模式（fnmatch 风格）。
DEFAULT_PATTERNS = ['.tmp_*', '_commit_*', '_commit_msg_*', '_cleanup_*']


def collect(dirs, patterns):
    found = []
    for base in dirs:
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            full = os.path.join(base, name)
            if not os.path.isfile(full):
                continue
            if any(fnmatch.fnmatch(name, pat) for pat in patterns):
                found.append(full)
    return sorted(found)


def is_untracked(path):
    """判断文件是否「未被 git 跟踪」——只有未跟踪（含被 .gitignore 忽略）才允许删。

    关键：不能用 `git status --porcelain`，因为它对「已跟踪且无变更」的文件也
    返回空，会与「未跟踪」混淆导致误删业务文件。改用索引查询：
      - `git ls-files --error-unmatch <path>` 成功退出 → 已在索引（已跟踪）→ 不删；
      - 失败 → 未跟踪或被忽略 → 可按临时文件删除。
    git 不可用时保守返回 False（不删），宁可漏删也不误删。
    """
    if not os.path.exists(path):
        return False
    try:
        r = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
        )
    except Exception:
        return False
    # 退出码 0 = 文件在索引中（已跟踪）；非 0 = 未跟踪/被忽略。
    return r.returncode != 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='通用临时文件清理（默认 dry-run，删除前核验 git 未跟踪）')
    ap.add_argument('--dir', action='append', default=None, help='额外允许清理的目录（可多次）；默认仅白名单目录')
    ap.add_argument('--pattern', action='append', default=None, help='额外匹配的文件名模式（可多次）；默认 .tmp_* 等')
    ap.add_argument(
        '--file',
        action='append',
        default=None,
        help='精确文件路径（可多次）；最安全，AI 应优先用此方式逐项列出要删文件',
    )
    ap.add_argument('--apply', action='store_true', help='真正删除（默认仅打印清单）')
    args = ap.parse_args(argv)

    files = []
    if args.file:
        for f in args.file:
            f = os.path.abspath(f)
            if os.path.isfile(f):
                files.append(f)
            else:
                print(f'[warn] 文件不存在，跳过：{f}', file=sys.stderr)
    else:
        dirs = args.dir if args.dir else DEFAULT_DIRS
        patterns = args.pattern if args.pattern else DEFAULT_PATTERNS
        files = collect(dirs, patterns)

    if not files:
        print('[cleanup] 没有可清理的临时文件。')
        return

    # 逐一标注 git 跟踪状态，供人/AI 判断。
    annotated = []
    for f in sorted(files):
        tracked = not is_untracked(f)
        tag = '[TRACKED-将跳过]' if tracked else '[untracked]'
        annotated.append((f, tracked, tag))

    print(f'[cleanup] 匹配到 {len(annotated)} 个文件：')
    for f, tracked, tag in annotated:
        print(f'  {tag} {f}')

    removable = [f for f, tracked, _ in annotated if not tracked]
    if not removable:
        print('\n[cleanup] 没有未跟踪文件可删（全部已跟踪，已自动跳过，未删除任何文件）。')
        return

    if not args.apply:
        print('\n[cleanup] DRY-RUN 模式：未删除任何文件。确认以上 [untracked] 清单无误后加 --apply 执行。')
        return

    removed = 0
    for f in removable:
        try:
            os.remove(f)
            removed += 1
            print(f'[removed] {f}')
        except OSError as e:
            print(f'[error] 删除失败 {f}: {e}', file=sys.stderr)
    print(f'\n[cleanup] 已删除 {removed}/{len(removable)} 个未跟踪文件（已跟踪文件已跳过）。')


if __name__ == '__main__':
    main()
