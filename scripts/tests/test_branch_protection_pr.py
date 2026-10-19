#!/usr/bin/env python3
"""`branch_protection_pr.py` 的回归网（源 CNB #586，2026-10-19）。  <!-- cross-repo-ref-allow -->

这份脚本只在一种情况下被调用：**合并成功、但直推被分支保护拒绝**。它要钉住三件事：

1. **幂等**：同一 head 已有 open PR ⇒ 复用，不再开一张（否则每轮都能开一张，看板变垃圾）；
2. **拿不到输入不得读成「不需要开」**：列 PR 失败 ⇒ 退 2 且明说结论不可信（#171 假绿纪律）；
3. **没有 token ≠ 什么都没发生**：合并结果**已经**在分支上了，要说清「现在只能人工开 PR」，
   而不是含糊地报一句失败（那是 2026-10-16 来回试两轮的老坑）。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "bridge" / "branch_protection_pr.py"


def _load():
    spec = importlib.util.spec_from_file_location("branch_protection_pr", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["branch_protection_pr"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load()


def test_reuses_existing_open_pr(mod, monkeypatch):
    """已有同 head 的 open PR ⇒ 直接复用，**不发 POST**（幂等键 = head 分支）。

    探针：把 `ensure_pr` 里的 `if existing:` 删掉 ⇒ 本用例转红（会去 POST 开第二张）。
    """
    calls: list[tuple[str, str]] = []

    def fake_api(path, *, token, method="GET", payload=None):
        calls.append((method, path))
        if method == "GET":
            return [{"number": 42, "html_url": "https://github.com/o/r/pull/42"}]
        raise AssertionError("已有 open PR 时不得再 POST 开新卡")

    monkeypatch.setattr(mod, "api", fake_api)
    res = mod.ensure_pr(
        repo="o/r",
        head="fix/cnb-dev-merge",
        base="dev",
        reason="GH006",
        sha="abc123",
        token="t",
        apply=True,
    )
    assert res["ok"] and "42" in res["detail"], res
    assert [m for m, _ in calls] == ["GET"], calls


def test_no_token_still_reports_where_the_result_is(mod, monkeypatch):
    """没 token 时：结论是「分支上已有结果、请人工开 PR」，不是含糊的失败。

    探针：把那条 detail 改成 `"失败"` ⇒ 本用例转红。
    """
    monkeypatch.setattr(mod, "api", lambda *a, **kw: [])
    res = mod.ensure_pr(
        repo="o/r",
        head="fix/cnb-dev-merge",
        base="dev",
        reason="",
        sha="",
        token="",
        apply=True,
    )
    assert res["ok"] is False
    assert "fix/cnb-dev-merge" in res["detail"], res["detail"]
    assert "手工开 PR" in res["detail"], res["detail"]


def test_list_failure_is_inconclusive_not_ok(mod, monkeypatch):
    """列 PR 失败 ⇒ `main()` 退 2（结论不可信），**不得**退化成「没 PR ⇒ 去开一张」。"""

    def boom(path, *, token, method="GET", payload=None):
        raise RuntimeError("503 Service Unavailable")

    monkeypatch.setattr(mod, "api", boom)
    rc = mod.main(["--repo", "o/r", "--head", "h", "--base", "dev", "--apply"])
    assert rc == 2


def test_dry_run_never_posts(mod, monkeypatch):
    """默认只报告：没有 `--apply` 时一次 POST 都不发。"""
    calls: list[str] = []
    monkeypatch.setattr(
        mod,
        "api",
        lambda path, *, token, method="GET", payload=None: calls.append(method) or [],
    )
    res = mod.ensure_pr(
        repo="o/r",
        head="h",
        base="dev",
        reason="",
        sha="",
        token="t",
        apply=False,
    )
    assert res["ok"] and "演练" in res["detail"], res
    assert calls == ["GET"], calls
