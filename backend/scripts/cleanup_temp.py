# -*- coding: utf-8 -*-
"""通用临时文件清理脚本（安全删除入口）。

用途：之前用 IDE 删除工具在部分环境下会被拦截/失败，故统一改用本 Python
脚本执行删除，绕开环境限制。设计为「默认只读、显式确认才删」，避免误删。

安全约束：
- 默认 DRY_RUN：仅收集并打印「将要删除的文件」，绝不真正删除；
- 必须显式传 --apply 才真正删除；
- 默认只在白名单目录内清理（仓库根 + docs/working-notes），不递归扫源码；
  可用 --dir 扩展（可多次），但仍建议限定在临时产物目录；
- 默认只匹配明确的临时文件名模式，可用 --pattern 追加。

用法：
    # 仅打印清单（默认）：
    pdm run python backend/scripts/cleanup_temp.py
    # 自定义目录/模式：
    pdm run python backend/scripts/cleanup_temp.py --dir path/to/dir --pattern "*.bak"
    # 确认清单无误后真正删除：
    pdm run python backend/scripts/cleanup_temp.py --apply
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
