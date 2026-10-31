#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：错误响应必须走统一信封 `{data, message, error_code}`（#1610）。

背景（issue #1610）
-------------------
`main.py` 的全局异常处理器（`abort()` / `HTTPException` / `ValueError` / 兜底 `Exception`）
一律返回三字段信封，但**视图内自建的错误响应**大量只有 `{data, message}`（实测 63 处），
`temperature/views.py` 三处连 `data` 都缺。前端一旦用 `error_code` 分支就会拿到 `undefined`，
且 `conventions.md` §2.4 的「契约一经定型不得私改」事实上不成立（同一语义两种结构）。
无守卫必然回潮（#1611 的教训），故本脚本同时作为**CI 守卫**与**一次性修复器**。

判定口径
--------
只认**可静态验证**的形态：`return jsonify({...}), <status>` 且 `status >= 400`（含 409/500 等），
检查 dict **字面量**是否含 `error_code`（缺 `data` 一并报出）。非字面量（变量 / 函数调用）
无法静态判定，跳过——这类由 `tests/test_error_envelope.py` 的信封不变量兜底。

第二条判据（2026-10-30 加）：**5xx 的 `message` 不得拼接异常对象**（f-string 里出现 `{}`，
或直接 `str(e)`）。起因是一次真实泄漏——`summary/views.py` 各端点自建的
``except Exception → f'服务器内部错误: {str(e)}'`` 把 ``IntegrityError`` 的 SQL 全文、
绑定参数（含 family_id / ledger_id / 金额）与 sqlalche.me 链接原样送到浏览器；而异常
被视图吞掉后 `main.py` 的全局处理器（固定文案 + 堆栈留痕）根本没机会执行。
只判 5xx：4xx 的 `str(e)` 是业务校验文案，属正常用法。修法见
``app/core/exceptions.py::internal_error_message``（固定文案 + 留痕绑成一个动作）。

error_code 值用 **int**（`ErrorCode.code`），与 `main.py::_HTTP_STATUS_TO_ERROR_CODE`、
`SBException` 完全一致；前端契约类型为 `number | string`（`api/search.ts`），int 合法。

事故记录（为什么不用 `ast.unparse` 整体替换 dict）
--------------------------------------------------
本脚本首版（`scripts/audit_error_envelope.py`）用 `ast.unparse(dict)` 重写 dict 文本，
结果**写坏 8 个 views.py**：`ast` 的 `col_offset` / `end_col_offset` 是 **UTF-8 字节偏移**，
而首版按「字符偏移」拼接，含中文的文件一律错位，把 dict 之后的源码整段吃掉
（有的行变成 `... 'error_code': 5004}et('/summary/sankey/')`），且解析失败被 `[SKIP]`
吞掉 → 扫描反而报 `OK`（**假绿**）。现版本据此改为：
1. **字节级**偏移（read bytes + splitlines(keepends=True)）；
2. **只插入**（在最后一个键值对之后追加 `, 'error_code': N`），不重排既有格式；
3. 写盘前**自校验**（重新解析 + 复扫该文件），校验不过即报错不写；
4. 解析失败**不再 SKIP**，直接判失败（防止同样的事故再次假绿）。

用法
----
    python scripts/guard_error_envelope.py                 # 只读扫描（CI / pre-commit），退出码 0/1
    python scripts/guard_error_envelope.py --fix           # 就地补齐 error_code(+data)，幂等
    python scripts/guard_error_envelope.py --app-dir <path>
退出码：0 = 干净；1 = 发现违规或文件不可解析；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# HTTP 状态 → ErrorCode.code（与 main.py::_HTTP_STATUS_TO_ERROR_CODE 逐项一致）
HTTP_STATUS_TO_CODE: dict[int, int] = {
    400: 1001,  # INVALID_PARAMS
    401: 1005,  # UNAUTHORIZED
    403: 1006,  # FORBIDDEN
    404: 1002,  # RESOURCE_NOT_FOUND
    409: 1003,  # DUPLICATE_ENTRY
    422: 1001,  # INVALID_PARAMS
    429: 1004,  # OPERATION_FAILED（全局处理器 .get 的默认值）
    500: 5004,  # INTERNAL_ERROR
    503: 5001,  # DATA_SOURCE_ERROR
    504: 5002,  # DATA_SOURCE_TIMEOUT
}
DEFAULT_CODE = 1004  # OPERATION_FAILED

APP_DIR = Path(__file__).resolve().parent.parent / 'backend' / 'app'


def _is_jsonify(node: ast.AST) -> bool:
    """`jsonify(...)` / `flask.jsonify(...)` 判定。"""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == 'jsonify') or (
        isinstance(func, ast.Attribute) and func.attr == 'jsonify'
    )


def _targets(tree: ast.Module) -> list[tuple[ast.Dict, int]]:
    """取出所有 `return jsonify({...}), <status>=400+` 的 dict 字面量与状态码。"""
    out: list[tuple[ast.Dict, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Tuple):
            continue
        elts = node.value.elts
        if len(elts) < 2:
            continue
        call, status_node = elts[0], elts[1]
        if not _is_jsonify(call) or not isinstance(status_node, ast.Constant):
            continue
        if not isinstance(status_node.value, int) or status_node.value < 400:
            continue
        if not call.args or not isinstance(call.args[0], ast.Dict):
            continue
        out.append((call.args[0], status_node.value))
    return out


def _keys_of(d: ast.Dict) -> set[str]:
    return {k.value for k in d.keys if isinstance(k, ast.Constant)}


def _message_leaks_exception(d: ast.Dict) -> bool:
    """`message` 是否把异常对象拼进了响应体（会把 SQL / 参数送到浏览器）。

    只认两种可静态验证的形态：f-string 里出现 `{...}`、或对 `str(...)` 的直接调用。
    判据只覆盖 5xx（见 `_violations`）——4xx 的 `str(e)` 是业务校验文案，属于正常用法。
    """
    for k, v in zip(d.keys, d.values):
        if not (isinstance(k, ast.Constant) and k.value == 'message'):
            continue
        if isinstance(v, ast.JoinedStr) and any(isinstance(item, ast.FormattedValue) for item in v.values):
            return True
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == 'str':
            return True
    return False


def _violations(tree: ast.Module, path: Path) -> list[dict]:
    """两类违规：缺 `error_code`（信封不完整）、5xx message 泄漏异常细节。"""
    found: list[dict] = []
    for d, status in _targets(tree):
        keys = _keys_of(d)
        if 'error_code' not in keys:
            found.append(
                {
                    'kind': 'missing_error_code',
                    'path': path,
                    'lineno': d.lineno,
                    'status': status,
                    'missing_data': 'data' not in keys,
                }
            )
        if status >= 500 and _message_leaks_exception(d):
            found.append(
                {
                    'kind': 'leaks_exception',
                    'path': path,
                    'lineno': d.lineno,
                    'status': status,
                    'missing_data': False,
                }
            )
    return found


def scan_file(path: Path) -> tuple[list[dict], str | None]:
    """返回 (违规清单, 解析错误信息)。解析错误不再静默跳过（防假绿）。"""
    src = path.read_text(encoding='utf-8')
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return [], f'{exc.__class__.__name__}: {exc.msg} (line {exc.lineno})'
    return _violations(tree, path), None


def _byte_index(lines_bytes: list[bytes], lineno: int, col_offset: int) -> int:
    """(lineno, col_offset) → 源码**字节**绝对下标。

    `ast` 的 col_offset / end_col_offset 是 UTF-8 字节偏移（不是字符偏移），
    故必须在 bytes 上计算——首版正是栽在这里（见模块 docstring「事故记录」）。
    """
    return sum(len(line) for line in lines_bytes[: lineno - 1]) + col_offset


def fix_file(path: Path) -> int:
    """就地补齐 `error_code`(+`data`)；返回修复处数。

    只做**插入**：在 dict 最后一个键值对之后追加 `, 'error_code': N[, 'data': None]`，
    不改动任何既有文本（不 unparse、不重排、不动注释与换行）。
    """
    src_bytes = path.read_bytes()
    try:
        tree = ast.parse(src_bytes.decode('utf-8'), filename=str(path))
    except SyntaxError as exc:  # 解析不了就不动它（由 scan 报错）
        print(f'  [SKIP-BROKEN] {path}: {exc.msg} (line {exc.lineno})', file=sys.stderr)
        return 0

    lines_bytes = src_bytes.splitlines(keepends=True)
    edits: list[tuple[int, bytes]] = []
    for d, status in _targets(tree):
        keys = _keys_of(d)
        if 'error_code' in keys and 'data' in keys:
            continue
        parts = []
        if 'error_code' not in keys:
            parts.append(f", 'error_code': {HTTP_STATUS_TO_CODE.get(status, DEFAULT_CODE)}")
        if 'data' not in keys:
            parts.append(", 'data': None")
        insert_at = _byte_index(lines_bytes, d.values[-1].end_lineno, d.values[-1].end_col_offset)
        edits.append((insert_at, ''.join(parts).encode('utf-8')))

    if not edits:
        return 0

    # 从后往前插入，保证前面的下标不被位移破坏
    for insert_at, payload in sorted(edits, reverse=True):
        src_bytes = src_bytes[:insert_at] + payload + src_bytes[insert_at:]

    # 写盘前自校验：必须仍可解析，且本文件已无「缺 error_code」的违规
    # （`leaks_exception` 不是 `--fix` 能修的，不参与此处判定，由扫描单独报）
    fixed_src = src_bytes.decode('utf-8')
    try:
        ast.parse(fixed_src, filename=str(path))
    except SyntaxError as exc:
        print(f'  [ERROR] {path}: 补齐后语法错误（{exc.msg}，line {exc.lineno}），已放弃写入', file=sys.stderr)
        return 0
    leftover = [v for v in scan_file_contents(fixed_src, path)[0] if v['kind'] == 'missing_error_code']
    if leftover:
        print(f'  [ERROR] {path}: 补齐后仍缺 error_code，已放弃写入', file=sys.stderr)
        return 0

    path.write_bytes(src_bytes)
    return len(edits)


def scan_file_contents(src: str, path: Path) -> tuple[list[dict], str | None]:
    """扫描「内存中的源码」（fix 后自校验用，避免落盘再读）。"""
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return [], f'{exc.__class__.__name__}: {exc.msg} (line {exc.lineno})'
    return _violations(tree, path), None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='错误信封 error_code 守卫 / 修复器（#1610）')
    parser.add_argument('--fix', action='store_true', help='就地补齐 error_code(+data)，幂等')
    parser.add_argument('--app-dir', default=str(APP_DIR), help='backend/app 路径')
    # `argv` 显式传入时按它解析：测试里直接调 `main([])` 才能真扫仓库，
    # 否则 `parse_args()` 会去读 pytest 自己的 `sys.argv` 并当场 SystemExit。
    args = parser.parse_args(argv)

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f'ERROR: app 目录不存在：{app_dir}', file=sys.stderr)
        return 2

    py_files = sorted(app_dir.rglob('*.py'))
    if args.fix:
        total = sum(fix_file(p) for p in py_files)
        print(f'OK: 补齐 {total} 处 error_code(+data)（幂等，可重复执行）')
        return 0

    violations: list[dict] = []
    broken: list[str] = []
    for path in py_files:
        found, parse_error = scan_file(path)
        violations.extend(found)
        if parse_error:
            broken.append(f'{path.relative_to(app_dir.parent.parent)}: {parse_error}')

    if broken:
        print('FAIL: 以下文件不可解析（守卫不做静默跳过，详见脚本 docstring「事故记录」）：', file=sys.stderr)
        for item in broken:
            print(f'  - {item}', file=sys.stderr)
        return 1

    if not violations:
        print(f'OK: 错误路径均含 error_code 且 5xx message 未泄漏异常细节（扫描 {len(py_files)} 个文件）')
        return 0

    root = app_dir.parent.parent
    missing = [v for v in violations if v['kind'] == 'missing_error_code']
    leaks = [v for v in violations if v['kind'] == 'leaks_exception']
    print(f'FAIL: 发现 {len(violations)} 处违规（{len(missing)} 处缺 error_code / {len(leaks)} 处 5xx 泄漏异常细节）：')
    for v in missing:
        extra = '（另缺 data）' if v['missing_data'] else ''
        print(f'  {v["path"].relative_to(root)}:{v["lineno"]}  status={v["status"]}{extra}')
    for v in leaks:
        print(
            f'  {v["path"].relative_to(root)}:{v["lineno"]}  status={v["status"]}'
            '  5xx message 拼接了异常对象，应改用 app.core.exceptions.internal_error_message(...)'
        )
    print('\n修复：python scripts/guard_error_envelope.py --fix（只补 error_code；泄漏需手工改）')
    return 1


if __name__ == '__main__':
    sys.exit(main())
