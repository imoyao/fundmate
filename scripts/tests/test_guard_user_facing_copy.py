# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_user_facing_copy.py``（用户可见文案不许出现开发信息）。

钉死三个容易静默失效的点：

1. **真的会红**——`abort(description=...)` / `raise ValueError(...)` / `{'hint': ...}`
   里的接口路径、HTTP 方法、登录态必须被判出来（防「永远绿」的假绿）；
2. **只拦用户可见的**——`logger.*` 的文案是给开发看的，不能误红；
3. **证伪探针**——把字典分支的扫描关掉，第 2 类命中的用例必须随之漏报，
   证明这条判据不是抄来的摆设。

⚠️ 用 ``unittest.TestCase`` 写法：``scripts_test`` job 跑 ``unittest discover``，
pytest 风格的裸函数不会被收集。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / "scripts" / "guard_user_facing_copy.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("guard_user_facing_copy", _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GuardUserFacingCopyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="user-copy-"))
        self.guard = _load_guard()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, body: str, name: str = "sample.py") -> tuple[int, str]:
        (self.tmp / name).write_text(body, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.guard.main(["--root", str(self.tmp)])
        return code, buf.getvalue()

    def test_raise_with_api_path_turns_red(self) -> None:
        code, out = self._run(
            "def f(v):\n"
            "    raise ValueError(f'非法取值 {v}；见 /api/utils/enums/ 的枚举')\n"
        )
        self.assertEqual(code, 1, out)
        self.assertIn("/api/", out)

    def test_abort_description_with_auth_detail_turns_red(self) -> None:
        code, out = self._run(
            "def f():\n"
            "    abort(400, description='到持仓详情点按钮，或调用接口（需带登录态）')\n"
        )
        self.assertEqual(code, 1, out)
        self.assertIn("登录态", out)

    def test_dict_hint_with_method_and_path_turns_red(self) -> None:
        code, out = self._run(
            "def f():\n"
            "    return {'hint': '请调用 POST /api/positions/39/recompute/ 修复'}\n"
        )
        self.assertEqual(code, 1, out)
        self.assertIn("HTTP 方法 + 路径", out)

    def test_logger_text_is_allowed(self) -> None:
        """日志归开发：里面写 /api/ 是对的，不能误红。"""
        code, out = self._run(
            "def f():\n"
            "    logger.debug('POST /api/x 返回 500，原始错误见上')\n"
        )
        self.assertEqual(code, 0, out)
        self.assertIn("OK", out)

    def test_mutation_dropping_dict_scan_misses_hint(self) -> None:
        """证伪探针：关掉字典分支后，hint 里的技术信息必须漏报（判据真的在起作用）。"""
        body = "def f():\n    return {'hint': '调用 POST /api/positions/39/recompute/'}\n"
        code, _ = self._run(body)
        self.assertEqual(code, 1)

        with mock.patch.object(self.guard, "_VISIBLE_DICT_KEYS", set()):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = self.guard.main(["--root", str(self.tmp)])
        self.assertEqual(code, 0, "变异后仍报红 ⇒ 说明命中不是走字典分支，探针失效")

    def test_missing_root_exits_two(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = self.guard.main(["--root", str(self.tmp / "nope")])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
