#!/usr/bin/env python3
"""Guard: 禁止在 backend/app 内新增 APIFlask 自动范式装饰器 @<bp>.input(...)。

回归防护（#973 / tech-debt.md §57）：消除对 APIFlask `@bp.input()` 的依赖，
违反 SPEC §1.3「不依赖自动范式，为迁移 FastAPI 预留空间」。所有请求校验已改用
`app/core/validation.parse_body()` / `parse_query()`（Pydantic 手动校验、失败
`abort(422)` 走统一信封），输入模型本身即 `pydantic.BaseModel`（FastAPI 就绪）。

允许例外：`core/validation.py` 内的说明性注释可保留 `@bp.input` 字样，故该文件
整体排除扫描（验收标准明确「仅 validation.py 注释可保留」）。

跨平台 Python 实现（无第三方依赖），替代 bash grep，兼容 Windows 本机 pre-commit。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOT = REPO_ROOT / "backend" / "app"
EXCLUDE_FILES = {REPO_ROOT / "backend" / "app" / "core" / "validation.py"}

# 匹配任意蓝图上的 @<name>.input( 装饰器，例如 @bp.input( / @blueprint.input(
DECORATOR_RE = re.compile(r"@[A-Za-z_][A-Za-z0-9_]*\.input\(")


def main() -> int:
    if not SCAN_ROOT.is_dir():
        print(f"WARN: 未找到扫描目录 {SCAN_ROOT}", file=sys.stderr)
        return 0
    violations: list[Path] = []
    for path in sorted(SCAN_ROOT.rglob("*.py")):
        if path.resolve() in EXCLUDE_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        if DECORATOR_RE.search(text):
            violations.append(path)
    if violations:
        print(
            "ERROR: 发现 APIFlask 自动范式 @<bp>.input( 装饰器，已改用 "
            "app.core.validation.parse_body / parse_query。违规文件:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1
    print("OK: backend/app 内无 @<bp>.input( 自动范式装饰器。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
