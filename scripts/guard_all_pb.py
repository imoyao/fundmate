#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：防止 all_pb.csv（全A中位PB历史基线）被清空/误删后提交。

该文件是行业拥挤度分母兜底数据，误删会导致温度计整组标灰。
曾因误判为 "cache" 被清空到 2 行（见 #821），故加此硬守卫：
pre-commit 在提交前检查行数，低于阈值即拒绝。

重新生成：cd backend && pdm run python scripts/prefetch_all_pb.py
"""

import sys
from pathlib import Path

# 相对仓库根（pre-commit 在 repo root 运行）
TARGET = Path("backend/app/services/thermometer/data/all_pb.csv")
# 完整历史约 5000+ 行，低于此值视为被清空/截断
MIN_ROWS = 1000


def main() -> int:
    if not TARGET.is_file():
        print("ERROR: 缺失必要基线数据：%s" % TARGET, file=sys.stderr)
        print(
            "      禁止删除；请用 scripts/prefetch_all_pb.py 重新抓取后提交",
            file=sys.stderr,
        )
        return 1
    rows = sum(1 for _ in TARGET.open("r", encoding="utf-8"))
    if rows < MIN_ROWS:
        print(
            "ERROR: %s 行数异常(%d < %d)，疑似被清空/截断，提交被拒绝。"
            % (TARGET, rows, MIN_ROWS),
            file=sys.stderr,
        )
        print(
            "      重新生成：cd backend && pdm run python scripts/prefetch_all_pb.py",
            file=sys.stderr,
        )
        return 1
    print("OK: all_pb.csv 基线数据完整(%d 行)" % rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
