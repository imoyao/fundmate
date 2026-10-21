# -*- coding: utf-8 -*-
"""`scripts/daily_run_alert.py` 的回归网（#2457）。

核心判据只有一条，但很贵：**「摘要文件不存在」不等于「没有失败 job」**。
两者必须能被区分，否则「拿不到输入」会被读成「一切正常」——那正是 #171 那一族
（「空 ≠ 没拿到」）在告警链路上的形态。
"""

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / 'scripts' / 'daily_run_alert.py'

sys.path.insert(0, str(_REPO_ROOT / 'scripts'))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location('daily_run_alert', _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


class TestRenderDetail(unittest.TestCase):
    def _write(self, tmp, payload):
        path = tmp / 'last_run_summary.json'
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return path

    def test_missing_summary_says_cannot_confirm(self):
        """摘要不存在 ⇒ 必须说「无法确认 job 级结果」，而不是「无失败」。"""
        text = _mod.render_detail(None, Path('/nonexistent/last_run_summary.json'))
        self.assertIn('无法确认', text)
        self.assertNotIn('无失败 job', text)

    def test_empty_failed_list_says_no_failure(self):
        payload = {'total': 3, 'failed': [], 'jobs': {'a': 'success', 'b': 'success', 'c': 'success'}}
        text = _mod.render_detail(payload)
        self.assertIn('无失败 job', text)

    def test_body_lists_failed_jobs(self):
        """有失败 ⇒ 正文必须点名是哪几个 job。"""
        payload = {
            'total': 4,
            'failed': ['fund_nav', 'price_history'],
            'jobs': {
                'fund_nav': 'failed',
                'price_history': 'manual_intervention',
                'stock_list': 'success',
                'asset_snapshot': 'success',
            },
            'elapsed_seconds': 42.0,
            'started_at': '2026-10-21T09:00:00+08:00',
        }
        text = _mod.render_detail(payload)
        self.assertIn('`fund_nav`', text)
        self.assertIn('`price_history`', text)
        self.assertIn('manual_intervention', text)
        self.assertNotIn('`stock_list`', text)  # 成功的 job 不进「失败」清单

    def test_corrupted_summary_treated_as_missing(self):
        """坏 JSON ⇒ 与「不存在」同义（拿不到就是拿不到），不能崩。"""
        self.assertIsNone(_mod.load_summary(Path('/nonexistent/x.json')))
        broken = Path(__file__).with_name('_broken_summary_tmp.json')
        broken.write_text('{not json', encoding='utf-8')
        try:
            self.assertIsNone(_mod.load_summary(broken))
        finally:
            broken.unlink(missing_ok=True)


class TestLoadSummary(unittest.TestCase):
    def test_reads_valid_summary(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.json'
            path.write_text(json.dumps({'failed': ['x'], 'jobs': {'x': 'failed'}}), encoding='utf-8')
            data = _mod.load_summary(path)
            self.assertEqual(data['failed'], ['x'])


if __name__ == '__main__':
    unittest.main()
