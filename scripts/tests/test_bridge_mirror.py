"""`scripts/bridge/` 镜像脚本的回归用例（#120）。

## WHY 有这份文件

两个脚本都做**有外部副作用**的事：`github_cnb_issues.py` 往 CNB 建卡，
`mirror_correction.py` 往 CNB 镜像卡写更正评论。写错一条就是：
- 镜像卡正文明明是「建卡快照」却长得像权威事实（#120 的问题本身）；
- 更正评论重复刷屏，或写到**人工卡**上（后者比静默漏写更糟）。

故这里钉的是三类边界，而不是「函数跑得动」：

1. **时效声明必须真的进正文**，且带上建卡时刻与「以 GitHub 为准」——这是方案 A 的全部内容，
   它退回成旧文案就等于本卡没做；
2. **更正评论必须真的进评论区**（能 POST 到 CNB 接口，不是只打印），且**幂等键被写进正文**
   ——否则重复执行会反复刷同一条；
3. **挡住在非镜像卡上写更正**——避免脚本被误用到人工卡。

## 怎么跑

    python -m unittest discover -s scripts/tests -p "test_*.py"

零新依赖（只用标准库）；网络层全部打桩，纯离线。
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'bridge'))

import github_cnb_issues as mirror  # noqa: E402
import mirror_correction as correction  # noqa: E402


def _gh_issue(**over) -> dict:
    issue = {
        'number': 2034,
        'state': 'open',
        'milestone': {'title': 'M2 免费核心'},
        'user': {'login': 'imoyao'},
        'created_at': '2026-10-10T12:00:00Z',
        'comments': 3,
        'labels': [{'name': 'bug'}],
        'body': '正文示例',
    }
    issue.update(over)
    return issue


# ---------------------------------------------------------------------------
# 一、方案 A：时效声明（正文里必须能看出「这是快照、以 GitHub 为准」）
# ---------------------------------------------------------------------------


class TestStalenessNotice(unittest.TestCase):
    def test_正文写明快照不覆盖后续变更(self):
        body = mirror.build_body(_gh_issue())
        self.assertIn('建卡时快照', body)
        self.assertIn('不覆盖后续变更', body)
        # 只写「只读镜像」不够 —— 读者看不出它可能已过期（#120 报的正是这一点）
        self.assertIn('以 GitHub 为准', body)

    def test_正文带生成时刻与建卡日期(self):
        body = mirror.build_body(_gh_issue())
        self.assertIn('镜像生成时间：', body)
        self.assertRegex(body, r'建卡时快照\*\*（截至 \d{4}-\d{2}-\d{2}）')

    def test_幂等键仍在正文里(self):
        """时效声明是往溯源块里加行，别把幂等键挤掉。"""
        body = mirror.build_body(_gh_issue())
        self.assertEqual(mirror.extract_github_number(body), 2034)

    def test_正文含可执行的更正路径说明(self):
        """方案 A 与方案 B 的接口：正文要告诉读者去评论区按什么格式写更正。

        判据只截取**溯源块**（正文第一段），不整篇搜关键词 —— 原书的正文本身可能提到
        「更正」，整篇搜会假绿。溯源块以 `\n---\n` 与原文分界。
        """
        header = mirror.build_body(_gh_issue()).split('\n---\n')[0]
        self.assertIn('📝 **更正**：', header, '更正路径要是独立一行，不能只并进别的说明里')
        self.assertIn('追加一条更正评论', header)
        self.assertIn('## 更正（{日期}）', header)
        self.assertIn('mirror_correction.py', header, '要给出可执行的命令入口')


# ---------------------------------------------------------------------------
# 二、方案 B：更正台账
# ---------------------------------------------------------------------------


class TestCorrectionKey(unittest.TestCase):
    def test_同日期同内容键相同(self):
        a = correction.make_key(106, '2026-10-11', ['❌ A → ✅ B'])
        b = correction.make_key(106, '2026-10-11', ['❌ A → ✅ B'])
        self.assertEqual(a, b)

    def test_与条目顺序无关(self):
        a = correction.make_key(106, '2026-10-11', ['甲', '乙'])
        b = correction.make_key(106, '2026-10-11', ['乙', '甲'])
        self.assertEqual(a, b)

    def test_卡片或日期或内容变了键就变(self):
        base = correction.make_key(106, '2026-10-11', ['甲'])
        self.assertNotEqual(base, correction.make_key(107, '2026-10-11', ['甲']))
        self.assertNotEqual(base, correction.make_key(106, '2026-10-12', ['甲']))
        self.assertNotEqual(base, correction.make_key(106, '2026-10-11', ['乙']))


class TestCorrectionComment(unittest.TestCase):
    def test_评论标题与格式固定(self):
        body = correction.build_comment('2026-10-11', ['❌ 正文「x」→ ✅ 实际「y」'], 'deadbeef0000')
        self.assertTrue(body.startswith('## 更正（2026-10-11）'))
        self.assertIn('- ❌ 正文「x」→ ✅ 实际「y」', body)

    def test_键写进正文且能被解析回来(self):
        body = correction.build_comment('2026-10-11', ['甲'], 'deadbeef0000')
        key = correction.make_key(3, '2026-01-01', ['x'])
        body = correction.build_comment('2026-10-11', ['甲'], key)
        self.assertEqual(correction.existing_keys([{'id': '1', 'body': body}]), {key})

    def test_普通评论不产生键(self):
        self.assertEqual(correction.existing_keys([{'id': '1', 'body': '随便聊聊'}]), set())


class TestCorrectionAdd(unittest.TestCase):
    """add 路径：先打桩掉网络，再看它到底往 CNB 发了什么。"""

    def _patch(self, *, comments=None, is_mirror=True, post_calls=None):
        calls = post_calls if post_calls is not None else []
        return (
            mock.patch.object(correction, 'list_issue_comments', return_value=comments or []),
            mock.patch.object(correction, 'is_mirror_card', return_value=is_mirror),
            mock.patch.object(correction, 'post_comment', side_effect=lambda n, b, repo=None: calls.append((n, b))),
            calls,
        )

    def test_apply_真的把评论发到指定卡(self):
        p1, p2, p3, calls = self._patch()
        with p1, p2, p3:
            rc = correction.run_add(106, '2026-10-11', ['❌ x → ✅ y'], repo=None, apply=True, force=False)
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)
        number, body = calls[0]
        self.assertEqual(number, 106)
        self.assertIn('## 更正（2026-10-11）', body)
        self.assertIn('❌ x → ✅ y', body)

    def test_dry_run_不发评论(self):
        p1, p2, p3, calls = self._patch()
        with p1, p2, p3:
            correction.run_add(106, '2026-10-11', ['❌ x → ✅ y'], repo=None, apply=False, force=False)
        self.assertEqual(calls, [])

    def test_已发布过的键不重发(self):
        key = correction.make_key(106, '2026-10-11', ['❌ x → ✅ y'])
        published = [{'id': '1', 'body': correction.build_comment('2026-10-11', ['❌ x → ✅ y'], key)}]
        p1, p2, p3, calls = self._patch(comments=published)
        with p1, p2, p3:
            rc = correction.run_add(106, '2026-10-11', ['❌ x → ✅ y'], repo=None, apply=True, force=False)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [], '幂等：同一条更正重复执行不该再发一次')

    def test_force_可重发(self):
        key = correction.make_key(106, '2026-10-11', ['❌ x → ✅ y'])
        published = [{'id': '1', 'body': correction.build_comment('2026-10-11', ['❌ x → ✅ y'], key)}]
        p1, p2, p3, calls = self._patch(comments=published)
        with p1, p2, p3:
            correction.run_add(106, '2026-10-11', ['❌ x → ✅ y'], repo=None, apply=True, force=True)
        self.assertEqual(len(calls), 1)

    def test_非镜像卡拒绝写入(self):
        p1, p2, p3, calls = self._patch(is_mirror=False)
        with p1, p2, p3:
            rc = correction.run_add(999, '2026-10-11', ['❌ x → ✅ y'], repo=None, apply=True, force=False)
        self.assertEqual(rc, 1, '写到人工卡上是比漏写更贵的错，必须拒绝')
        self.assertEqual(calls, [])

    def test_非法日期被拒(self):
        p1, p2, p3, calls = self._patch()
        with p1, p2, p3:
            rc = correction.run_add(106, '2026/10/11', ['❌ x → ✅ y'], repo=None, apply=True, force=False)
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])

    def test_没有任何更正条目被拒(self):
        p1, p2, p3, calls = self._patch()
        with p1, p2, p3:
            rc = correction.run_add(106, '2026-10-11', [], repo=None, apply=True, force=False)
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])


class TestMirrorCardDetection(unittest.TestCase):
    def test_按标签识别镜像卡(self):
        detail = {'labels': [{'name': mirror.MIRROR_LABEL}]}
        with mock.patch.object(correction, 'cnb_api', return_value=detail):
            self.assertTrue(correction.is_mirror_card(106))

    def test_无标签但正文有幂等键也算(self):
        detail = {'labels': [], 'body': '> - GitHub 编号：`#2034`'}
        with mock.patch.object(correction, 'cnb_api', return_value=detail):
            self.assertTrue(correction.is_mirror_card(106))

    def test_人工卡不算(self):
        detail = {'labels': [{'name': 'enhancement'}], 'body': '一张人工开的卡'}
        with mock.patch.object(correction, 'cnb_api', return_value=detail):
            self.assertFalse(correction.is_mirror_card(999))


class TestFetchCompleteness(unittest.TestCase):
    """`fetch_github_open_issues()` 必须能区分「0 张」与「没拉到」（源 CNB #179 / #171）。

    WHY：建卡作业里最坏的失败形态不是「漏建几张」，而是**漏建 + 报告「无新增，两侧已对齐」**
    —— 错误结论 + 红灯不可见。这与 #171（状态回流拉不到就报「已对齐」）是同一个假绿，
    只是换了个作业。故这里钉住「数据不完整」这个信号本身，以及调用方会把它变成红灯。
    """

    def _fake(self, batches):
        it = iter(batches)

        def fake(url, **kw):
            try:
                return json.dumps(next(it)).encode('utf-8')
            except StopIteration:
                return b'[]'

        return fake

    def test_空仓库_零张且可信(self):
        with mock.patch.object(mirror, '_request', self._fake([[]])):
            issues, complete = mirror.fetch_github_open_issues()
        self.assertEqual(issues, [])
        self.assertTrue(complete, '空仓库是「真的没有」，不能报成不完整')

    def test_满页后接空页_判为不完整(self):
        """满页之后又来一个空页 ⇒ 分页中途断了，**不得**当成拉全了。"""
        full = [{'number': i, 'title': 'x'} for i in range(100)]
        with mock.patch.object(mirror, '_request', self._fake([full, []])):
            issues, complete = mirror.fetch_github_open_issues()
        self.assertEqual(len(issues), 100)
        self.assertFalse(complete, '满页后空页说明分页中断，必须报不完整')

    def test_不满页收尾_判为完整(self):
        with mock.patch.object(mirror, '_request', self._fake([[{'number': 1, 'title': 'x'}], []])):
            issues, complete = mirror.fetch_github_open_issues()
        self.assertEqual(len(issues), 1)
        self.assertTrue(complete)

    def test_翻页触顶_判为不完整(self):
        """每页都满 ⇒ 翻到 `MAX_ISSUE_PAGES` 仍未收尾 ⇒ 触顶，必须报不完整。"""
        full = [{'number': i, 'title': 'x'} for i in range(100)]
        batches = [full] * (mirror.MAX_ISSUE_PAGES + 5)
        with mock.patch.object(mirror, '_request', self._fake(batches)):
            _issues, complete = mirror.fetch_github_open_issues()
        self.assertFalse(complete, '翻页触顶说明数据被截断，必须报不完整')

    def test_无新增但不完整_退回码1且不宣称对齐(self):
        """`run()` 在「零待建 + 数据不完整」时**不得**打印「无新增，两侧已对齐」。"""
        out = io.StringIO()
        state = {'mirrored': {}}
        with (
            mock.patch.object(mirror, 'load_state', return_value=state),
            mock.patch.object(mirror, 'harvest_existing', return_value={}),
            mock.patch.object(mirror, 'fetch_github_open_issues', return_value=([], False)),
            mock.patch.object(mirror, 'save_state'),
            redirect_stdout(out),
        ):
            rc = mirror.run(dry_run=True, limit=None)
        text = out.getvalue()
        self.assertEqual(rc, 1, '数据不完整时不得以 0 退出（那是「一切正常」）')
        self.assertNotIn('无新增，两侧已对齐', text, text)
        self.assertIn('数据不完整', text, text)


if __name__ == '__main__':
    unittest.main()
