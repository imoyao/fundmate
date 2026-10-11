"""`mirror_state_sync.py` 的回归用例（CNB #117 硬要求 ②）。

## WHY 有这份文件

本脚本做的是**有外部副作用**的事：往 CNB 镜像卡**写评论 + 挂标签**。它一旦判错方向，
后果不是「少标记一张」，而是：

  - **把人工关掉的卡又标记成「已关闭」**（CNB 侧主动关卡是因为讨论结束，
    GitHub 后来重开原卡不代表那些讨论又活了）——这会让人以为「脚本在建议重开」；
  - **重复发同一批状态评论**（幂等键写歪）→ 107 张卡的评论区各刷一屏；
  - **写到人工卡上**（不是镜像卡）——比漏写更贵，与 #120 同一条闸门；
  - **把「已关闭」当成「要自动关」**——那会推翻 #117 硬要求 ①（人工回路保留）。

故这里钉四类边界：

1. **漂移只认一个方向**：GitHub 关 / CNB 开 ⇒ 漂移；CNB 关 / GitHub 开 ⇒ 不漂移（人做的决定）；
2. **幂等键**：同一事实只发一次，但「关→开→再关」要能各发一条（键带 gh_updated）；
3. **评论正文**：必须写明「本卡不会被自动关闭」，且幂等键能被原样解析回来；
4. **写前闸门**：非镜像卡拒绝写入；dry-run 不发任何东西。

## 怎么跑

    python -m unittest discover -s scripts/tests -p "test_*.py"

零新依赖（只用标准库）；网络层全部打桩，纯离线。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'bridge'))

import mirror_state_sync as sync  # noqa: E402

# ---------------------------------------------------------------------------
# 一、漂移判定：只认「GitHub 关了、CNB 还开着」这一个方向
# ---------------------------------------------------------------------------


class TestStateDrift(unittest.TestCase):
    def test_github关cnb开算漂移(self):
        self.assertTrue(sync.state_drift('open', 'closed'))

    def test_两侧都关算对齐(self):
        self.assertFalse(sync.state_drift('closed', 'closed'))

    def test_两侧都开算对齐(self):
        self.assertFalse(sync.state_drift('open', 'open'))

    def test_cnb主动关的不算漂移(self):
        """CNB 侧关卡是**人做的决定**（讨论已结束），脚本不得回退它。

        这正是 #117 硬要求 ① 的落点：人工回路保留。若这条判据反过来，
        脚本会变成「GitHub 只要还开着，CNB 就不许关」——等于取消人工回路。
        """
        self.assertFalse(sync.state_drift('closed', 'open'))


class TestPlan(unittest.TestCase):
    def _gh(self, **over):
        base = {'state': 'open', 'updated_at': '2026-10-11T00:00:00Z'}
        base.update(over)
        return base

    def test_只挑出真漂移的卡(self):
        cards = [
            {'cnb': 106, 'gh': 2034, 'cnb_state': 'open'},
            {'cnb': 107, 'gh': 2037, 'cnb_state': 'open'},
            {'cnb': 108, 'gh': 2040, 'cnb_state': 'closed'},
        ]
        gh = {
            2034: self._gh(state='closed'),
            2037: self._gh(state='open'),
            2040: self._gh(state='open'),  # CNB 主动关的，不回流
        }
        todo = sync.plan(cards, gh)
        self.assertEqual([c['cnb'] for c in todo], [106])
        self.assertEqual(todo[0]['gh_state'], 'closed')
        self.assertEqual(todo[0]['gh_updated'], '2026-10-11T00:00:00Z')

    def test_github侧拉不到的卡跳过而不是猜(self):
        """限额 / 卡被删时拉不到载荷 —— 跳过，不要臆测状态。"""
        cards = [{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}]
        self.assertEqual(sync.plan(cards, {}), [])


# ---------------------------------------------------------------------------
# 二、幂等键
# ---------------------------------------------------------------------------


class TestStateKey(unittest.TestCase):
    def test_同事实键相同(self):
        a = sync.make_state_key(106, 2034, 'closed', '2026-10-11T00:00:00Z')
        b = sync.make_state_key(106, 2034, 'closed', '2026-10-11T00:00:00Z')
        self.assertEqual(a, b)

    def test_卡片或状态或更新时刻变了键就变(self):
        base = sync.make_state_key(106, 2034, 'closed', '2026-10-11T00:00:00Z')
        self.assertNotEqual(base, sync.make_state_key(107, 2034, 'closed', '2026-10-11T00:00:00Z'))
        self.assertNotEqual(base, sync.make_state_key(106, 2035, 'closed', '2026-10-11T00:00:00Z'))
        self.assertNotEqual(base, sync.make_state_key(106, 2034, 'open', '2026-10-11T00:00:00Z'))

    def test_关开再关各发一条(self):
        """键带 gh_updated，就是为了让「关闭 → 重开 → 再关闭」不被误判成重复。"""
        first = sync.make_state_key(106, 2034, 'closed', '2026-10-11T00:00:00Z')
        second = sync.make_state_key(106, 2034, 'closed', '2026-10-20T00:00:00Z')
        self.assertNotEqual(first, second)


# ---------------------------------------------------------------------------
# 三、评论正文
# ---------------------------------------------------------------------------


class TestStateComment(unittest.TestCase):
    def _body(self, gh_updated: str = '2026-10-11T00:00:00Z', **over):
        kw = {'repo': 'imoyao/fundmate', 'today': '2026-10-11'}
        kw.update(over)
        return sync.build_state_comment(2034, 'closed', gh_updated, 'deadbeef0000', **kw)

    def test_标题与事实固定(self):
        body = self._body()
        self.assertTrue(body.startswith('## 状态回流（2026-10-11）'))
        self.assertIn('GitHub 原卡 #2034 **已关闭**', body)
        self.assertIn('https://github.com/imoyao/fundmate/issues/2034', body)

    def test_明示不会自动关(self):
        """这条是 #117 硬要求 ① 的可见落点：读者必须知道「标记 ≠ 关卡」。"""
        body = self._body()
        self.assertIn('**不会被自动关闭**', body)
        self.assertIn('cnb issues close', body, '要给出人工关卡的入口，否则读者不知道下一步')

    def test_键写进正文且能解析回来(self):
        key = sync.make_state_key(106, 2034, 'closed', '2026-10-11T00:00:00Z')
        body = sync.build_state_comment(2034, 'closed', '2026-10-11T00:00:00Z', key, repo='imoyao/fundmate')
        self.assertEqual(sync.existing_state_keys([{'id': '1', 'body': body}]), {key})

    def test_普通评论不产生键(self):
        self.assertEqual(sync.existing_state_keys([{'id': '1', 'body': '随便聊聊'}]), set())

    def test_更新时刻缺失时不静默留空(self):
        body = self._body(gh_updated='')
        self.assertIn('未知', body)


# ---------------------------------------------------------------------------
# 四、写路径（打桩网络，看它到底往 CNB 发了什么）
# ---------------------------------------------------------------------------


class TestRunApply(unittest.TestCase):
    def _patch(self, *, cards, gh, comments=None, is_mirror=True):
        posts: list = []
        labels: list = []
        return (
            mock.patch.object(
                sync, 'load_state', return_value={'mirrored': {str(c['gh']): {'cnb': c['cnb']} for c in cards}}
            ),
            mock.patch.object(sync, 'mirrored_cards', return_value=cards),
            mock.patch.object(sync, 'fetch_github_issues_by_number', return_value=gh),
            mock.patch.object(sync, 'list_issue_comments', return_value=comments or []),
            mock.patch.object(sync, 'is_mirror_card', return_value=is_mirror),
            mock.patch.object(sync, 'post_comment', side_effect=lambda n, b, repo=None: posts.append((n, b))),
            mock.patch.object(sync, 'add_status_label', side_effect=lambda n, repo=None: labels.append(n)),
            posts,
            labels,
        )

    def test_apply_真的发评论并挂标签(self):
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        posts, labels = p[7], p[8]
        self.assertEqual(rc, 0)
        self.assertEqual([n for n, _ in posts], [106])
        self.assertIn('## 状态回流（', posts[0][1])
        self.assertEqual(labels, [106], '标记法要同时挂标签，否则看板筛不出来')

    def test_dry_run_不写任何东西(self):
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            sync.run(apply=False, only_cnb=None, repo=None)
        self.assertEqual(p[7], [])
        self.assertEqual(p[8], [])

    def test_已回流过的键不重发(self):
        key = sync.make_state_key(106, 2034, 'closed', '2026-10-11T00:00:00Z')
        published = [
            {
                'id': '1',
                'body': sync.build_state_comment(2034, 'closed', '2026-10-11T00:00:00Z', key, repo='imoyao/fundmate'),
            }
        ]
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
            comments=published,
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(rc, 0)
        self.assertEqual(p[7], [], '幂等：同一事实重复执行不该再发一次')

    def test_非镜像卡拒绝写入(self):
        p = self._patch(
            cards=[{'cnb': 999, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
            is_mirror=False,
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(p[7], [], '写到人工卡上是比漏写更贵的错，必须拒绝')

    def test_挂标签失败不影响评论(self):
        """评论是主产物、标签是辅助；挂标签失败不该把评论一起丢。"""
        p = list(
            self._patch(
                cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
                gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
            )
        )
        boom = mock.patch.object(sync, 'add_status_label', side_effect=RuntimeError('400'))
        with p[0], p[1], p[2], p[3], p[4], p[5], boom:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(rc, 0)
        self.assertEqual([n for n, _ in p[7]], [106])

    def test_无漂移时不发任何东西(self):
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'open', 'updated_at': '2026-10-11T00:00:00Z'}},
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(rc, 0)
        self.assertEqual(p[7], [])

    def test_指定的卡不在映射里报错(self):
        p = self._patch(cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}], gh={})
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
            rc = sync.run(apply=True, only_cnb=999, repo=None)
        self.assertEqual(rc, 1, '指定了一张不在映射里的卡应当明确报错，而不是默默什么都不做')


# ---------------------------------------------------------------------------
# 五、抓取降级：限额用尽不得把整个作业带崩
# ---------------------------------------------------------------------------


class TestFetchDegradation(unittest.TestCase):
    """匿名 GitHub API 只有 60 次/时/IP，而状态回流要拉 `state=all`（含已关闭卡），
    比建卡那次重得多。撞上限额时必须**返回已拿到的部分**而不是抛异常——
    否则整个 cron 阶段挂掉，连已经能做的回流一起丢。

    （`plan()` 对拿不到的卡已是「跳过而不是猜」，故少拉只是少标记，不会误标。）
    """

    def _page(self, items):
        import json as _json

        return _json.dumps(items).encode()

    def test_限额用尽返回已抓到的部分(self):
        import urllib.error

        pages = [
            self._page([{'number': 1, 'state': 'closed'}, {'number': 2, 'state': 'open'}]),
            urllib.error.HTTPError('u', 403, 'rate limited', {}, None),
        ]
        calls = {'n': 0}

        def fake_request(url, *, headers=None, **kw):
            i = calls['n']
            calls['n'] += 1
            r = pages[i] if i < len(pages) else self._page([])
            if isinstance(r, Exception):
                raise r
            return r

        with (
            mock.patch.object(sync, '_github_headers', return_value={}),
            mock.patch('github_cnb_issues._request', side_effect=fake_request),
        ):
            got = sync.fetch_github_issues_by_number()
        self.assertEqual(sorted(got), [1, 2], '限额中断时应返回已拿到的部分，而不是抛异常')

    def test_PULL_REQUEST混入时被剔除(self):
        page = self._page([{'number': 1}, {'number': 9, 'pull_request': {}}])

        with (
            mock.patch.object(sync, '_github_headers', return_value={}),
            mock.patch('github_cnb_issues._request', return_value=page),
        ):
            got = sync.fetch_github_issues_by_number()
        self.assertEqual(sorted(got), [1], 'GitHub 的 /issues 会混入 PR，必须剔除')

    def test_非403的HTTP错误同样降级(self):
        import urllib.error

        err = urllib.error.HTTPError('u', 500, 'boom', {}, None)
        with (
            mock.patch.object(sync, '_github_headers', return_value={}),
            mock.patch('github_cnb_issues._request', side_effect=err),
        ):
            got = sync.fetch_github_issues_by_number()
        self.assertEqual(got, {}, '一次性网络错不该把作业带崩')


if __name__ == '__main__':
    unittest.main()
