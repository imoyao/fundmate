#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：给用户看的话里不许出现「给开发看」的东西（源 2026-11-16 用户反馈）。

WHY
---
份额巡检的提示曾经这么写（#3135 首版，2026-11-16 被用户当面指出）：

    超卖（流水净额为负）多半缺买入腿，重算会直接清仓：……再到持仓详情点「按流水重算份额」
    或调用 POST /api/positions/39/recompute/（需带登录态）

这句话是**渲染在页面上**的：`ShareIntegrityPanel` 直接把 `remedy.hint` 铺给用户看。
用户的原话是「提示文案是给用户看的，你说的这是给前端开发看的」——接口路径、HTTP 方法、
`（需带登录态）` 这类信息对用户零价值，只会让人以为要自己发请求。

判据（AST 静态，纯标准库，零依赖）：
只扫**会出现在响应里的字符串**——`abort(N, description=...)`、`raise XxxError(...)`、
以及字典里 `hint` / `message` / `description` / `detail` 的值。命中下列任一即红：

| 标记 | 为什么是它 |
|---|---|
| `/api/` | 接口路径只属于路由与文档 |
| `endpoint` / `curl` | 同上，且暗示「自己去调」 |
| `登录态` / `Cookie` 头 | 用户不该知道请求怎么鉴权 |
| `HTTP 4xx` / `HTTP 5xx` / `status_code` | 状态码是实现细节 |

`logger.*` 的文案**不在扫描范围**：日志是给开发看的，那里保留原始技术信息是对的
（`console.warn(err)` 同源）。

用法
----
    python scripts/guard_user_facing_copy.py            # 校验（CI）
    python scripts/guard_user_facing_copy.py --report    # 只打印命中，不判红

退出码：0 = 无命中；1 = 命中；2 = 拿不到输入（结论不可信，不得当成通过）。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "backend" / "app"

#: 技术标记 → 面向用户的说法。判定只看前者，后者写在提示里教怎么改。
TECH_MARKERS: dict[str, str] = {
    "/api/": "接口路径",
    "endpoint": "接口路径（改成「去某页面做某事」）",
    "curl": "命令行调用",
    "登录态": "鉴权细节（用户不需要知道）",
    "status_code": "状态码",
}

#: `POST /api/...` 这类「方法 + 路径」也要拦；单独出现的方法名（如「DELETE 按钮」）不拦。
_METHOD_WITH_PATH = re.compile(r"\b(?:POST|GET|PUT|PATCH|DELETE)\s+/")

#: 会作为响应正文 / 提示显示的字典键（小写比较）。
_VISIBLE_DICT_KEYS = {"hint", "message", "description", "detail", "msg"}

#: 会作为响应正文显示的调用关键字参数。
_VISIBLE_CALL_KWARGS = {"description", "message", "detail", "hint", "msg"}

#: `raise` 的左值里出现这些后缀时，异常文本会进信封 `message`。
_RAISE_SUFFIXES = ("Error", "Exception")


def _iter_strings(node: ast.AST):
    """收集节点下所有字符串常量（f-string 的模板片段也算）。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            yield sub.lineno, sub.value


def _visible_strings(tree: ast.AST):
    """挑出「会显示给用户」的字符串，附带行号。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name == "abort" or name.endswith(_RAISE_SUFFIXES):
                for arg in node.args:
                    yield from _iter_strings(arg)
                for kw in node.keywords:
                    if kw.arg in _VISIBLE_CALL_KWARGS:
                        yield from _iter_strings(kw.value)
            # logger.* / console.* 不扫：日志归开发
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if key.value.lower() in _VISIBLE_DICT_KEYS:
                        yield from _iter_strings(value)


def _call_name(func: ast.AST) -> str:
    """取 `abort` / `ValueError` 这类被调用方的末段名。"""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def scan_text(text: str) -> list[tuple[int, str, str]]:
    """返回 [(行号, 命中的标记, 文案片段)]；语法错误抛 SyntaxError 由调用方处理。"""
    tree = ast.parse(text)
    hits: list[tuple[int, str, str]] = []
    for lineno, message in _visible_strings(tree):
        markers = [m for m in TECH_MARKERS if m in message]
        if _METHOD_WITH_PATH.search(message):
            markers.append("HTTP 方法 + 路径")
        if markers:
            hits.append((lineno, "、".join(markers), message.strip()))
    return hits


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    return scan_text(path.read_text(encoding="utf-8"))


def iter_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="用户可见文案不许出现接口路径 / 鉴权细节")
    parser.add_argument("--report", action="store_true", help="只打印命中，不判红")
    parser.add_argument("--root", default=str(APP_DIR), help="扫描根目录（默认 backend/app）")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"ERROR: 扫描目录不存在：{root}", file=sys.stderr)
        return 2
    files = iter_py_files(root)
    if not files:
        print(f"ERROR: {root} 下没有 .py 文件，结论不可信", file=sys.stderr)
        return 2

    total = 0
    for path in files:
        try:
            hits = scan_file(path)
        except SyntaxError as exc:  # 拿不到输入就明说，别当成「没违规」
            print(f"ERROR: 语法错误，无法判定：{path}（{exc}）", file=sys.stderr)
            return 2
        for lineno, marker, snippet in hits:
            total += 1
            rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
            print(f"{rel}:{lineno}: [{marker}] {snippet}")

    if not total:
        print(f"OK: {len(files)} 个文件，用户可见文案里没有接口路径 / 鉴权细节")
        return 0
    print(f"\n命中 {total} 处：上面这些字符串会直接显示给用户。")
    print("改法：写成用户要做的事（「去交易记录核对流水」「用改成账单份额填 0」），")
    print("接口路径 / HTTP 方法 / 登录态留在 docstring 或日志里。")
    return 0 if args.report else 1


if __name__ == "__main__":
    sys.exit(main())
