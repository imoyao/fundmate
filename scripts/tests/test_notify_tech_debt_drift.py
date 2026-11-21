# -*- coding: utf-8 -*-
"""`notify_tech_debt_drift.py` 的回归网（源 TD-021 / TD-025 状态回流，2026-11-21）。

## 钉什么

这个脚本由**每周定时任务无人值守**驱动，做的是「台账已经漂了，但 CI 看不出来」这件事。
它自己有两条会静默失效的路：

  1. **幂等判定失效** —— 每周刷一条一样的红，第三周开始没人看（噪音比没提醒更糟）；
  2. **接线漂移** —— workflow 忘了 `--online` / 检出成默认分支 / 忘了传 `--status`，
     脚本再好也白搭，而且**照样绿**。

所以这里既测纯函数（marker / 卡面 / 找卡 / 跳过），也钉 workflow 的四处接线。
全程零网络：所有 `gh` 调用都换成记录用的假 runner。

**为什么是 unittest 而不是 pytest 风格**：CI 的 scripts job 用
`python -m unittest discover -s scripts/tests -p "test_*.py"` 收集，裸函数不会被执行
（只会被 import）—— pytest 风格写在别处有先例，但那是「只求 import 通过」的特例，
回归网必须真的跑起来。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import notify_tech_debt_drift as m  # noqa: E402

WORKFLOW = ROOT / '.github/workflows/tech-debt-drift.yml'
CARD = 'RED: 台账与事实不符'


class FakeGh:
    """记录调用并按前缀返回预设输出的假 runner。"""

    def __init__(self, issues: list[dict] | None = None, comments: list[dict] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.issues = issues or []
        self.comments = comments or []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if args[:2] == ['issue', 'list']:
            return json.dumps(self.issues)
        if args[0] == 'api':
            return json.dumps(self.comments)
        return ''

    @property
    def writes(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] in (['issue', 'comment'], ['issue', 'create'], ['issue', 'close'])]


def _run(status: str, report: str, gh: FakeGh, dry_run: bool = False) -> int:
    return m.execute(status, report, 'imoyao/fundmate', dry_run=dry_run, run=gh, echo=lambda _: None)


class MarkerTest(unittest.TestCase):
    def test_follows_content_not_run_count(self) -> None:
        self.assertEqual(m.marker(CARD), m.marker(CARD + '\n'))
        self.assertNotEqual(m.marker(CARD), m.marker('RED: #2803 已 CLOSED'))


class BodyTest(unittest.TestCase):
    def test_drift_body_carries_report_and_three_choices(self) -> None:
        body = m.build_body(CARD, 'drift')
        self.assertIn(CARD, body)
        self.assertIn(m.MARKER_RE.format(m.marker(CARD)), body)
        for word in ('open', 'done', 'wontfix'):
            self.assertIn(word, body, f'卡面缺处置选项 {word}')
        self.assertNotIn(m.TITLE, body, '标题由 issue 标题承担，正文不复述')

    def test_ok_body_says_recovered(self) -> None:
        body = m.build_body('OK：27 条债务状态均可判定', 'ok')
        self.assertIn('已恢复', body)
        self.assertIn('27 条债务状态均可判定', body)


class FindTrackerTest(unittest.TestCase):
    def test_matches_exact_title_only(self) -> None:
        rows = [
            {'number': 9, 'title': m.TITLE + '补充说明'},
            {'number': 11, 'title': m.TITLE},
        ]
        self.assertEqual(m.find_tracker(json.dumps(rows)), 11)
        self.assertIsNone(m.find_tracker('[]'))

    def test_rejects_broken_json(self) -> None:
        with self.assertRaises(SystemExit):
            m.find_tracker('not json')


class ExecuteTest(unittest.TestCase):
    def test_drift_without_tracker_creates_card(self) -> None:
        gh = FakeGh(issues=[])
        self.assertEqual(_run('drift', CARD, gh), 0)
        created = [c for c in gh.calls if c[:2] == ['issue', 'create']]
        self.assertEqual(len(created), 1)
        self.assertIn(m.TITLE, created[0])
        self.assertTrue(any(CARD in arg for arg in created[0]))

    def test_drift_with_same_report_is_skipped(self) -> None:
        gh = FakeGh(
            issues=[{'number': 42, 'title': m.TITLE}],
            comments=[{'body': f'旧报告\n{m.MARKER_RE.format(m.marker(CARD))}'}],
        )
        self.assertEqual(_run('drift', CARD, gh), 0)
        self.assertEqual(gh.writes, [], '同一份报告不得重复评论（噪音会让人开始无视这张卡）')

    def test_drift_with_new_report_comments_existing_card(self) -> None:
        gh = FakeGh(
            issues=[{'number': 42, 'title': m.TITLE}],
            comments=[{'body': '旧报告 <!-- tech-debt-drift: 000000000000 -->'}],
        )
        self.assertEqual(_run('drift', CARD, gh), 0)
        self.assertEqual([c[:2] for c in gh.writes], [['issue', 'comment']])
        self.assertTrue(any(CARD in arg for arg in gh.writes[0]))

    def test_ok_closes_open_tracker(self) -> None:
        gh = FakeGh(issues=[{'number': 42, 'title': m.TITLE}])
        self.assertEqual(_run('ok', 'OK：27 条债务状态均可判定', gh), 0)
        self.assertEqual([c[:2] for c in gh.writes], [['issue', 'comment'], ['issue', 'close']])

    def test_ok_without_tracker_touches_nothing(self) -> None:
        gh = FakeGh(issues=[])
        self.assertEqual(_run('ok', 'OK：27 条债务状态均可判定', gh), 0)
        self.assertEqual(gh.writes, [])

    def test_empty_report_is_untrusted_input(self) -> None:
        gh = FakeGh()
        self.assertEqual(_run('ok', '   \n', gh), 2, '判据没跑出结论时不得当作「已恢复」')
        self.assertEqual(gh.calls, [])

    def test_dry_run_never_writes(self) -> None:
        gh = FakeGh(issues=[{'number': 42, 'title': m.TITLE}], comments=[{'body': '旧'}])
        self.assertEqual(_run('drift', CARD, gh, dry_run=True), 0)
        self.assertEqual(gh.writes, [])


class WorkflowWiringTest(unittest.TestCase):
    """接线四处缺一都会静默失效 —— 这里逐条钉住。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding='utf-8')
        cls.doc = yaml.safe_load(cls.text)

    def test_runs_online_judgement(self) -> None:
        self.assertIn('guard_tech_debt_register.py --online', self.text, '只跑离线判据等于没巡检')

    def test_schedule_exists(self) -> None:
        # PyYAML 按 YAML 1.1 把裸 on: 解析成布尔 True —— 两种键都认
        trigger = self.doc.get('on') or self.doc.get(True)
        self.assertIn('schedule', trigger, '没有 schedule 就不会定期跑')

    def test_checkout_ref_is_not_default_branch(self) -> None:
        steps = self.doc['jobs']['drift']['steps']
        checkout = [s for s in steps if str(s.get('uses', '')).startswith('actions/checkout')]
        self.assertTrue(checkout, '定时任务必须显式检出代码')
        ref = checkout[0].get('with', {}).get('ref', '')
        self.assertTrue(
            'SCAN_REF' in ref or ref not in ('', 'main', 'master'),
            'schedule 默认检出默认分支 ⇒ 拿 main 的旧台账判今天的账（#1434 同款坑）',
        )

    def test_passes_status_to_notifier(self) -> None:
        self.assertIn('notify_tech_debt_drift.py', self.text)
        self.assertIn('--status "$STATUS"', self.text, '不传 status 就只剩「建卡」，恢复时不会关单')


if __name__ == '__main__':
    unittest.main()
