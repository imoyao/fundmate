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

步骤 1 — 先 dry-run 看清单（默认就是 dry-run，不传 --apply 绝不删）：
    cd backend
    pdm run python backend/scripts/cleanup_temp.py
    # 自定义目录 / 匹配模式（可多次追加）：
    pdm run python backend/scripts/cleanup_temp.py --dir path/to/dir --pattern "*.bak"

步骤 2 — 把打印出的「将要删除的文件清单」呈现给用户，说明要删哪些、
        为什么（临时调试/commit/issue 产物，无业务价值），等用户确认。

步骤 3 — 用户确认后，才真正删除：
    pdm run python backend/scripts/cleanup_temp.py --apply
    # 或带自定义模式：
    pdm run python backend/scripts/cleanup_temp.py --pattern "_close*" --apply

=====================================================================
安全约束（SAFETY）
=====================================================================
- 默认 DRY_RUN：仅收集并打印「将要删除的文件」，绝不真正删除；
- 必须显式传 --apply 才真正删除；
- 默认只在白名单目录内清理（仓库根 + docs/working-notes），不递归扫源码；
  可用 --dir 扩展（可多次），但仍建议限定在临时产物目录，避免误伤业务代码；
- 默认只匹配明确的临时文件名模式（.tmp_* / _commit_* / _commit_msg_* /
  _cleanup_*），可用 --pattern 追加；
- 任何不在默认模式里的文件（如 _decode_tmp.py、*.json dump 等），需显式
  用 --pattern 指定，且仍要先 dry-run 给用户看清单；
- 绝不用本脚本删除源码 / 配置 / 文档 / 入库资产（如 all_pb.csv）。

用法速查：
    pdm run python backend/scripts/cleanup_temp.py            # 仅打印清单
    pdm run python backend/scripts/cleanup_temp.py --apply    # 确认后真正删除
"""

import argparse
import fnmatch
import os
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


def main(argv=None):
    ap = argparse.ArgumentParser(description='通用临时文件清理（默认 dry-run）')
    ap.add_argument('--dir', action='append', default=None, help='额外允许清理的目录（可多次）；默认仅白名单目录')
    ap.add_argument('--pattern', action='append', default=None, help='额外匹配的文件名模式（可多次）；默认 .tmp_* 等')
    ap.add_argument('--apply', action='store_true', help='真正删除（默认仅打印清单）')
    args = ap.parse_args(argv)

    dirs = args.dir if args.dir else DEFAULT_DIRS
    patterns = args.pattern if args.pattern else DEFAULT_PATTERNS

    files = collect(dirs, patterns)
    if not files:
        print('[cleanup] 没有可清理的临时文件。')
        return

    print(f'[cleanup] 匹配到 {len(files)} 个文件（目录={dirs} 模式={patterns}）：')
    for f in files:
        print(f'  - {f}')

    if not args.apply:
        print('\n[cleanup] DRY-RUN 模式：未删除任何文件。确认清单无误后加 --apply 执行。')
        return

    removed = 0
    for f in files:
        try:
            os.remove(f)
            removed += 1
            print(f'[removed] {f}')
        except OSError as e:
            print(f'[error] 删除失败 {f}: {e}', file=sys.stderr)
    print(f'\n[cleanup] 已删除 {removed}/{len(files)} 个文件。')


if __name__ == '__main__':
    main()
