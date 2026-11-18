# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_service_size.py``（services 层体量 / 复杂度软闸门）。

本守卫与 ``test_view_thickness_guard.py`` 同构，钉死三个容易静默失效的点：

1. **基线必须与真实文件集一致**——新增服务文件若漏登记，守卫会静默放行（没有基线
   也不在新增上限内就什么都不查？不：新文件走上限校验，但「删除文件后基线残留」这类
   漂移无人发现）；
2. **灵敏度**——守卫必须真的能报错（防「永远返回空 → 永远绿」的假绿）；
3. **基线虚胖**——基线宽于实测时，该维度的「只减不增」拦截会静默失效（同 #1606 落地后
   `commits` 维度空转了 41/44 的教训）。

守卫逻辑按路径加载复用，不重复实现（判定规则只有一份）。

``LEGACY_SERVICES`` 由 ``BASELINE`` 的键直接派生（单一真相源），故两者不可能漂移。

⚠️ 本文件用 ``unittest.TestCase`` 写法（与 ``test_detail_tables_guard.py`` 同），因为
``scripts_test`` job 跑的是 ``python -m unittest discover``，只收 ``TestCase`` 子类，
pytest 风格的裸函数不会被收集（实测会「Ran 0 tests」）。
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
_GUARD_PATH = _REPO_ROOT / "scripts" / "guard_service_size.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("guard_service_size", _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GuardServiceSizeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="svc-size-"))
        self.guard = _load_guard()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, body: str) -> Path:
        path = self.tmp / name
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def _run(guard) -> tuple[int, str, str]:
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            rc = guard.main([])
        return rc, buf_out.getvalue(), buf_err.getvalue()

    def test_guard_passes_on_current_repo(self) -> None:
        """仓库当前状态必须通过（基线取自首次落地时的实测值）。"""
        rc, _out, _err = self._run(self.guard)
        self.assertEqual(rc, 0)

    def test_baseline_covers_every_service_file(self) -> None:
        """BASELINE 必须覆盖每一个真实服务文件（防漏登记 / 防基线漂移）；
        且每个真实文件要么在冻结集内（legacy），要么作为新文件压在 NEW_FILE_LIMITS 内。

        ⚠️ 新文件**不得**塞进 BASELINE：守卫本体对非 legacy 文件一律忽略基线条目、
        只认 NEW_FILE_LIMITS（防 gaming，见 ``test_guard_blocks_new_file_with_fat_baseline_entry``）。
        故本用例对新文件校验的是上限，而不是「必须在 BASELINE 里」——否则新增服务文件
        会让守卫与回归网互相矛盾（#2944 实测踩到）。
        """
        guard = self.guard
        services = guard._iter_services()
        self.assertTrue(services, "未扫描到任何服务文件，守卫的 rglob 可能失效")
        actual = {guard._rel(p) for p in services}
        # 冻结集由 BASELINE 派生，故两者键必须一致
        self.assertEqual(set(guard.BASELINE), set(guard.LEGACY_SERVICES))
        for path in services:
            rel = guard._rel(path)
            if rel in guard.LEGACY_SERVICES:
                continue
            metrics = guard.collect_metrics(path)
            for metric, limit in guard.NEW_FILE_LIMITS.items():
                self.assertLessEqual(
                    metrics[metric],
                    limit,
                    f"新增服务文件 {rel} 的 {metric} = {metrics[metric]} 超过新增上限 {limit}",
                )
        # 反向：基线里的每个键都对应一个真实文件（防 stale 基线虚胖）
        stale = set(guard.BASELINE) - actual
        self.assertFalse(stale, f"基线里有已不存在的文件（stale）：{sorted(stale)}")

    def test_metrics_count_lines_and_complexity(self) -> None:
        """指标口径：`lines` / `max_func`（最长函数行数）/ `max_cc`（圈复杂度）必须正确。"""
        guard = self.guard
        # def f(): + a=1 + b=2 + if a: + for: + if b: + c=1 + return a = 8 行
        # 圈复杂度：base 1 + if(a) 1 + for 1 + if(b) 1 = 4
        sample = self._write(
            "svc.py",
            "def f():\n    a = 1\n    b = 2\n    if a:\n"
            "        for i in range(3):\n            if b:\n                c = 1\n    return a\n",
        )
        metrics = guard.collect_metrics(sample)
        self.assertGreaterEqual(metrics["lines"], 8)
        self.assertGreaterEqual(metrics["max_func"], 8)
        self.assertEqual(metrics["max_cc"], 4)

    def test_guard_flags_regression_against_baseline(self) -> None:
        """灵敏度：文件比基线更厚 / 更复杂必须报错（防「永远绿」的假守卫）。"""
        guard = self.guard
        thick = self._write(
            "svc.py",
            "def thick():\n" + "\n".join(f"    x{i} = {i}" for i in range(20)) + "\n",
        )
        with mock.patch.object(guard, "_iter_services", lambda: [thick]), \
             mock.patch.object(guard, "_rel", lambda _p: "backend/app/services/x/svc.py"), \
             mock.patch.object(
                 guard, "BASELINE",
                 {"backend/app/services/x/svc.py": {"lines": 5, "max_func": 5, "max_cc": 1}},
             ), \
             mock.patch.object(guard, "LEGACY_SERVICES", {"backend/app/services/x/svc.py"}):
            rc, _out, err = self._run(guard)
        self.assertEqual(rc, 1)
        self.assertIn("lines", err)
        self.assertIn("基线冻结（只减不增）", err)

    def test_guard_flags_new_file_over_limits(self) -> None:
        """灵敏度：基线外的新服务文件超上限必须报错（含「新增上限」提示）。"""
        guard = self.guard
        # 852 行函数——稳定越过新增 lines ≤ 800 / 最长函数 ≤ 120 上限
        fresh = self._write(
            "svc.py",
            "def thick():\n" + "\n".join(f"    x{i} = {i}" for i in range(850)) + "\n",
        )
        with mock.patch.object(guard, "_iter_services", lambda: [fresh]), \
             mock.patch.object(guard, "_rel", lambda _p: "backend/app/services/brandnew/svc.py"), \
             mock.patch.object(guard, "BASELINE", {}), \
             mock.patch.object(guard, "LEGACY_SERVICES", frozenset()):
            rc, _out, err = self._run(guard)
        self.assertEqual(rc, 1)
        self.assertIn("新增上限", err)

    def test_guard_blocks_new_file_with_fat_baseline_entry(self) -> None:
        """灵敏度（防 gaming / 反例）：新文件即便在 BASELINE 塞了 fat 条目（如 1500 行），
        也必须被 NEW_FILE_LIMITS 拦下——证明「给新文件开后门」这条路被堵死。"""
        guard = self.guard
        fat = self._write(
            "svc.py",
            "def thick():\n" + "\n".join(f"    x{i} = {i}" for i in range(850)) + "\n",
        )
        with mock.patch.object(guard, "_iter_services", lambda: [fat]), \
             mock.patch.object(guard, "_rel", lambda _p: "backend/app/services/brandnew/svc.py"), \
             mock.patch.object(guard, "LEGACY_SERVICES", frozenset()), \
             mock.patch.object(
                 guard, "BASELINE",
                 {"backend/app/services/brandnew/svc.py": {"lines": 1500, "max_func": 1500, "max_cc": 50}},
             ):
            rc, _out, err = self._run(guard)
        self.assertEqual(rc, 1)
        self.assertIn("新增上限", err)  # 被 NEW_FILE_LIMITS 拦，而非被（fat）基线放过
        self.assertNotIn("1500", err)  # fat 基线条目未生效

    def test_guard_allows_new_file_under_limits(self) -> None:
        """灵敏度（防过度抑制 / 正例）：压在 NEW_FILE_LIMITS 内的新文件必须放行。"""
        guard = self.guard
        ok = self._write("svc.py", "def thin():\n    return 1\n")
        with mock.patch.object(guard, "_iter_services", lambda: [ok]), \
             mock.patch.object(guard, "_rel", lambda _p: "backend/app/services/brandnew/svc.py"), \
             mock.patch.object(guard, "LEGACY_SERVICES", frozenset()), \
             mock.patch.object(guard, "BASELINE", {}):
            rc, _out, err = self._run(guard)
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")

    def test_guard_hints_loose_baseline(self) -> None:
        """防基线虚胖：实测低于基线时必须提示回写，但**不报错**（正常收敛不该红掉校验）。"""
        guard = self.guard
        thin = self._write("svc.py", "def thin():\n    return 1\n")
        with mock.patch.object(guard, "_iter_services", lambda: [thin]), \
             mock.patch.object(guard, "_rel", lambda _p: "backend/app/services/x/svc.py"), \
             mock.patch.object(
                 guard, "BASELINE",
                 {"backend/app/services/x/svc.py": {"lines": 50, "max_func": 20, "max_cc": 10}},
             ), \
             mock.patch.object(guard, "LEGACY_SERVICES", {"backend/app/services/x/svc.py"}):
            rc, out, err = self._run(guard)
        self.assertEqual(rc, 0)
        self.assertIn("收紧 BASELINE", out)
        self.assertEqual(err, "")

    def test_baseline_matches_current_metrics(self) -> None:
        """基线与实测必须**贴合**（不是「不超过」）：收敛后请在同 PR 内
        `python scripts/guard_service_size.py --report` 回写 BASELINE——基线**调大**仍会由本
        用例拦下（守卫生效的唯一方式）。"""
        guard = self.guard
        measured = {guard._rel(p): guard.collect_metrics(p) for p in guard._iter_services()}
        for rel, m in measured.items():
            if rel not in guard.BASELINE:
                continue  # 新文件不在基线内，已由 NEW_FILE_LIMITS 覆盖
            for metric, budget in guard.BASELINE[rel].items():
                self.assertLessEqual(
                    m[metric], budget, f"{rel} 的 {metric} = {m[metric]} 超过基线 {budget}（变厚）"
                )
                self.assertEqual(
                    m[metric], budget,
                    f"{rel} 的 {metric} = {m[metric]} 低于基线 {budget}，请用 --report 收紧基线",
                )


if __name__ == "__main__":
    unittest.main()
