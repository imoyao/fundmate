#!/usr/bin/env python3
"""`llm_health_probe.py` 的 429 分类回归网（2026-11-12，排查 #3056 时立）。

背景：#3056 的 `deep-review` 连续多轮 `verdict=upstream_unavailable`，日志只有一行
「429 限流/额度用尽」。而这两个含义的**处置完全不同**——额度用尽要等额度恢复或换 key，
限流过几分钟重跑就行——历史实现把响应体扔掉、揉成一个标签，于是「额度到底够不够」
无法从日志回答，排查只能靠猜。这份文件钉四件事：

1. 429 的响应体能被读出来并分成 `quota` / `rate_limit`；
2. 分类真的接在 `probe()` 上（不是写了个没人调用的纯函数）；
3. `all_throttled` 的语义（workflow 的 `if:` 直接吃它）；
4. `main()` 写进 `GITHUB_OUTPUT` 的新增键（`fail_reason` / `all_throttled`）确实存在——
   键名漂了就静默失效。

⚠️ 必须写成 `unittest.TestCase`：CI 的 `scripts_test` job 用
`python -m unittest discover -s scripts/tests -p "test_*.py"` 收这些文件，
**pytest 风格的裸函数只被导入、不会执行**（ci.yml 里已注明这一点）。
写成裸函数等于交了一份永不运行的回归网。
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
import llm_health_probe as probe_mod


def _body(code: str, message: str = "") -> str:
    return json.dumps({"error": {"code": code, "message": message or code}})


class Classify429Test(unittest.TestCase):
    """判据 1：429 响应体 → quota / rate_limit。"""

    def test_quota_code_is_classified_as_quota(self):
        status, detail = probe_mod._classify_429(_body("QuotaExceeded"))
        self.assertEqual(status, "quota")
        self.assertIn("QuotaExceeded", detail)

    def test_model_level_set_limit_is_quota_not_rate_limit(self):
        """`SetLimitExceeded` 是单模型被限额（方舟「安全体验模式」），不是限流。"""
        status, detail = probe_mod._classify_429(_body("SetLimitExceeded"))
        self.assertEqual(status, "quota")
        self.assertIn("SetLimitExceeded", detail)

    def test_rate_limit_code_is_classified_as_rate_limit(self):
        status, detail = probe_mod._classify_429(_body("RateLimitExceeded"))
        self.assertEqual(status, "rate_limit")
        self.assertIn("RateLimitExceeded", detail)

    def test_non_json_too_many_requests_text_is_rate_limit(self):
        """非 JSON 响应体也要认：有的网关只回一行纯文本。"""
        status, detail = probe_mod._classify_429("Too many requests, please slow down")
        self.assertEqual(status, "rate_limit", detail)

    def test_empty_body_falls_back_to_legacy_quota_label(self):
        """读不到响应体时保留历史标签，不把「未知」伪装成「已知的限流」。"""
        status, detail = probe_mod._classify_429("")
        self.assertEqual(status, "quota")
        self.assertIn("不可读", detail)

    def test_unknown_code_defaults_to_quota(self):
        status, detail = probe_mod._classify_429(_body("SomeBrandNewCode"))
        self.assertEqual(status, "quota", detail)
        self.assertIn("SomeBrandNewCode", detail)


class ProbeWiringTest(unittest.TestCase):
    """判据 2：分类真的接在 probe() 上，而不是一个没人调用的纯函数。"""

    def test_probe_reads_429_body_instead_of_discarding_it(self):
        """urlopen 抛带 QuotaExceeded 响应体的 429 ⇒ probe 必须报 quota 并带上错误码。

        旧实现只 `return ("quota", "429 限流/额度用尽")`，响应体根本不读，
        本用例会因 detail 里没有错误码而红。
        """
        payload = _body("QuotaExceeded", "request quota exhausted").encode("utf-8")

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 429, "Too Many Requests", {}, io.BytesIO(payload)
            )

        with (
            mock.patch.dict(
                os.environ, {"ARK_API_KEY_CODEREVIEW": "test-key"}, clear=False
            ),
            mock.patch.object(probe_mod.urllib.request, "urlopen", fake_urlopen),
        ):
            status, detail = probe_mod.probe("ark", "doubao-seed-2-1-pro-260915")
        self.assertEqual(status, "quota")
        self.assertIn("QuotaExceeded", detail)

    def test_probe_without_key_does_not_touch_network(self):
        env = {k: v for k, v in os.environ.items() if k != "ARK_API_KEY_CODEREVIEW"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                probe_mod.probe("ark", "whatever"),
                ("no_key", "未配置 ARK_API_KEY_CODEREVIEW"),
            )


class AllThrottledTest(unittest.TestCase):
    """判据 3：all_throttled 语义——整池 429 才算 true，混进 ok / no_key 一律 false。"""

    def test_semantics(self):
        cases = [
            ([], False),
            (["quota", "quota"], True),
            (["quota", "rate_limit"], True),
            (["quota", "ok"], False),
            (["no_key", "no_key"], False),
            (["quota", "excluded"], False),
        ]
        for statuses, expected in cases:
            with self.subTest(statuses=statuses):
                results = [{"status": s} for s in statuses]
                self.assertIs(probe_mod._all_throttled(results), expected)


class MainOutputContractTest(unittest.TestCase):
    """判据 4：main() 必须写出 fail_reason / all_throttled（键名漂了 if 就静默失效）。"""

    def test_main_writes_fail_reason_and_all_throttled_outputs(self):
        """无 key ⇒ 全部 no_key：仍要写出两个新键，且 all_throttled=false（≠ 429）。"""
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "gh_output"
            out.write_text("", encoding="utf-8")
            with (
                mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}, clear=True),
                self.assertRaises(SystemExit) as ctx,
            ):
                probe_mod.main()
            self.assertEqual(ctx.exception.code, 0)
            written = dict(
                line.split("=", 1)
                for line in out.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )
        self.assertEqual(written["all_throttled"], "false")
        self.assertEqual(written["fail_reason"], "no_key")
        self.assertEqual(written["selected_ok"], "false")
        self.assertTrue(json.loads(written["status_json"]), "status_json 不能是空数组")


if __name__ == "__main__":
    unittest.main()
