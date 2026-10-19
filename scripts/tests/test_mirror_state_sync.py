"""`mirror_state_sync.py` 的回归用例（CNB #117 硬要求 ②）。

## WHY 有这份文件

本脚本做的是**有外部副作用**的事：往 CNB 镜像卡**写评论 + 挂标签 + 关闭卡片**。
它一旦判错方向，后果不是「少标记一张」，而是：

  - **把人工关掉的卡又标记成「已关闭」**（CNB 侧主动关卡是因为讨论结束，
    GitHub 后来重开原卡不代表那些讨论又活了）——这会让人以为「脚本在建议重开」；
  - **重复发同一批状态评论**（幂等键写歪）→ 107 张卡的评论区各刷一屏；
  - **写到人工卡上**（不是镜像卡）——比漏写更贵，与 #120 同一条闸门；
  - **把不该关的卡关掉**（B 口径下这是最贵的错，因为关卡比评论难撤回）——
    判据必须收在「GitHub 已关 + CNB 还开着」，且写前必须过「这是镜像卡」闸门。

故这里钉四类边界：

1. **漂移只认一个方向**：GitHub 关 / CNB 开 ⇒ 漂移；CNB 关 / GitHub 开 ⇒ 不漂移（人做的决定）；
2. **幂等键**：同一事实只发一次，但「关→开→再关」要能各发一条（键带 gh_updated）；
3. **评论正文**：必须写明「本卡不会被自动关闭」，且幂等键能被原样解析回来；
4. **写前闸门**：非镜像卡拒绝写入；dry-run 不发任何东西。
5. **评论与关卡分开判**（B 口径，2026-10-13）：发过评论却仍开着的卡必须补关——
   否则「口径改了、那些卡还漂着」。

## 怎么跑

    python -m unittest discover -s scripts/tests -p "test_*.py"

零新依赖（只用标准库）；网络层全部打桩，纯离线。
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
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
    def _body(self, gh_updated: str = '2026-10-11T00:00:00Z', closed: bool = True, **over):
        kw = {'repo': 'imoyao/fundmate', 'today': '2026-10-11', 'closed': closed}
        kw.update(over)
        return sync.build_state_comment(2034, 'closed', gh_updated, 'deadbeef0000', **kw)

    def test_标题与事实固定(self):
        body = self._body()
        self.assertTrue(body.startswith('## 状态回流（2026-10-11）'))
        self.assertIn('GitHub 原卡 #2034 **已关闭**', body)  # cross-repo-ref-allow（断言的是本仓生成的评论正文）
        self.assertIn('https://github.com/imoyao/fundmate/issues/2034', body)

    def test_明示已随_GitHub_关闭(self):
        """B 口径的可见落点：读者必须知道「这张卡已经关了、怎么再开」。

        D48 时代这里断言的是「不会被自动关闭」——口径已由用户在 CNB #171 改为 B，
        故断言反向：卡**是**被自动关的，且要给出重新打开的入口。
        """
        body = self._body()
        self.assertIn('**已随 GitHub 同步关闭**', body)
        self.assertIn('cnb issues open', body, '要给出重新打开的入口，否则讨论就真被埋了')
        self.assertNotIn('不会被自动关闭', body, 'B 口径下这句是错的')

    def test_逃生阀下不得谎称已关闭(self):
        """`--no-close` 时卡其实还开着——正文绝不能说「已自动关闭」，那是又一种假绿。"""
        body = self._body(closed=False)
        self.assertNotIn('已随 GitHub 同步关闭', body)
        self.assertIn('未自动关闭', body)
        self.assertIn('cnb issues close', body, '没关的卡要给出人工关卡入口')

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
        closes: list = []
        return (
            mock.patch.object(
                sync, 'load_state', return_value={'mirrored': {str(c['gh']): {'cnb': c['cnb']} for c in cards}}
            ),
            mock.patch.object(sync, 'mirrored_cards', return_value=cards),
            mock.patch.object(sync, 'fetch_github_issues_by_number', return_value=(gh, True)),
            mock.patch.object(sync, 'list_issue_comments', return_value=comments or []),
            mock.patch.object(sync, 'is_mirror_card', return_value=is_mirror),
            mock.patch.object(sync, 'post_comment', side_effect=lambda n, b, repo=None: posts.append((n, b))),
            mock.patch.object(sync, 'add_status_label', side_effect=lambda n, repo=None: labels.append(n)),
            mock.patch.object(sync, 'close_issue', side_effect=lambda n, repo=None: closes.append(n)),
            posts,
            labels,
            closes,
        )

    def test_apply_发评论挂标签并关闭卡片(self):
        """B 口径的三件套：评论 + 标签 + 关闭。缺一件这张网就没闭环。"""
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        posts, labels, closes = p[8], p[9], p[10]
        self.assertEqual(rc, 0)
        self.assertEqual([n for n, _ in posts], [106])
        self.assertIn('## 状态回流（', posts[0][1])
        self.assertEqual(labels, [106], '标签要挂，否则看板筛不出来')
        self.assertEqual(closes, [106], 'B 口径的核心：GitHub 关了，CNB 也要关')

    def test_dry_run_不写任何东西(self):
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
            sync.run(apply=False, only_cnb=None, repo=None)
        self.assertEqual(p[8], [])
        self.assertEqual(p[9], [])
        self.assertEqual(p[10], [], 'dry-run 尤其不能关卡（关卡比评论难撤回）')

    def test_已回流过的键不重发但必须补关(self):
        """D48 时代的存量卡：评论早发过、卡还开着。切到 B 口径后**必须补关**，
        否则就是「口径改了、那些卡继续漂」——正是本卡要消灭的形态。
        """
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
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(rc, 0)
        self.assertEqual(p[8], [], '幂等：同一事实重复执行不该再发评论')
        self.assertEqual(p[10], [106], '评论已发 ≠ 卡已关，必须补关')

    def test_已关闭的卡不再重复关(self):
        """两侧都关 = 已对齐，不该产生任何写操作（也不该有卡片的无谓 PATCH）。

        **幂等的保证在 `plan()`**：`state_drift()` 已排除「两侧都关」，所以关过的卡
        根本进不了 `todo`。`run()` 里不再重复这一判（重复即成死代码，守门咬不住——
        实测 S5 探针查出来的）。故这条用例钉的是 `plan()` 的契约。
        """
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'closed'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(rc, 0)
        self.assertEqual(p[8], [])
        self.assertEqual(p[10], [], '已对齐的卡不该被再关一次')

    def test_plan_永不交出已关闭的卡(self):
        """上一条用例的**真正支柱**：`plan()` 的契约必须独立钉住。

        否则一旦有人改宽 `state_drift()`（比如为了「同步重开」），
        `run()` 里那条「已关过的卡不再关」的隐式前提会静默消失。
        """
        cards = [{'cnb': 106, 'gh': 2034, 'cnb_state': 'closed'}]
        gh = {2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}}
        self.assertEqual(sync.plan(cards, gh), [], '两侧都关的卡不该进待办')

    def test_no_close_逃生阀只标记不关(self):
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
            rc = sync.run(apply=True, only_cnb=None, repo=None, auto_close=False)
        self.assertEqual(rc, 0)
        self.assertEqual([n for n, _ in p[8]], [106], '逃生阀下评论照发')
        self.assertEqual(p[10], [], '--no-close 就是不关')
        self.assertIn('未自动关闭', p[8][0][1], '没关就不能说已关')

    def test_非镜像卡拒绝写入_也不关(self):
        p = self._patch(
            cards=[{'cnb': 999, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
            is_mirror=False,
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
            sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(p[8], [], '写到人工卡上是比漏写更贵的错，必须拒绝')
        self.assertEqual(p[10], [], '闸门必须在关卡之前——关错卡最难撤回')

    def test_挂标签失败不影响评论与关卡(self):
        """标签是辅助产物；它失败不该把评论和关卡一起丢。"""
        p = list(
            self._patch(
                cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
                gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
            )
        )
        boom = mock.patch.object(sync, 'add_status_label', side_effect=RuntimeError('400'))
        with p[0], p[1], p[2], p[3], p[4], p[5], boom, p[7]:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(rc, 0)
        self.assertEqual([n for n, _ in p[8]], [106])
        self.assertEqual(p[10], [106], '挂标签失败不该连关卡一起丢')

    def test_关卡失败显式报错不静默(self):
        """关卡是本作业的核心副作用，失败必须可见（否则又是「看着绿、其实没干活」）。"""
        p = list(
            self._patch(
                cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
                gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},
            )
        )
        boom = mock.patch.object(sync, 'close_issue', side_effect=RuntimeError('403'))
        buf = io.StringIO()
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], boom, redirect_stdout(buf):
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertIn('关闭失败', buf.getvalue(), '关卡失败必须打印，不能静默吞掉')
        self.assertEqual(p[8] and [n for n, _ in p[8]], [106], '评论已发、关卡失败：不因关卡失败而回滚评论')

    def test_无漂移时不发任何东西(self):
        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'open', 'updated_at': '2026-10-11T00:00:00Z'}},
        )
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(rc, 0)
        self.assertEqual(p[8], [])
        self.assertEqual(p[10], [])

    def test_指定的卡不在映射里报错(self):
        p = self._patch(cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}], gh={})
        with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
            rc = sync.run(apply=True, only_cnb=999, repo=None)
        self.assertEqual(rc, 1, '指定了一张不在映射里的卡应当明确报错，而不是默默什么都不做')


# ---------------------------------------------------------------------------
# 四之二、`close_issue` 的端点形状（B 口径的新增副作用，最贵的一处）
# ---------------------------------------------------------------------------


class TestCloseIssueEndpoint(unittest.TestCase):
    """关卡是本作业**最难撤回**的副作用（评论可忽略，卡片变灰是状态变更）。

    端点写错的失败形态特别隐蔽：**不报错、也不生效**——脚本打印「✅ 已关闭」，
    卡其实还开着，于是又回到「看着绿、其实没干活」。故这里把方法 / 路径 / 请求体
    逐项钉死（形状经 `cnb-cli` 的 `dist/index.js` 核实：
    `PATCH /{repo}/-/issues/{number}`，与 `cnb issues close` 同路）。
    """

    def test_用_PATCH_而不是_POST(self):
        calls: list = []

        def fake(path, *, method='GET', payload=None):
            calls.append((path, method, payload))
            return {}

        with (
            mock.patch.object(sync, 'cnb_api', side_effect=fake),
            mock.patch('github_cnb_issues._cnb_repo', return_value='duoduobei/fundmate'),
        ):
            sync.close_issue(106)
        path, method, payload = calls[0]
        self.assertEqual(method, 'PATCH', 'CNB 关闭 issue 走 PATCH，不是 POST')
        self.assertEqual(path, '/duoduobei/fundmate/-/issues/106')
        self.assertEqual(payload, {'state': 'closed', 'state_reason': 'completed'})

    def test_显式_repo_覆盖环境(self):
        calls: list = []

        def fake(path, *, method='GET', payload=None):
            calls.append((path, method, payload))
            return {}

        with mock.patch.object(sync, 'cnb_api', side_effect=fake):
            sync.close_issue(7, repo='someone/else')
        self.assertEqual(calls[0][0], '/someone/else/-/issues/7')


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
        """一页响应 = `(body, headers)` —— 翻页读 `Link` 头（源 CNB #586）。"""
        import json as _json

        return _json.dumps(items).encode(), {}

    def test_限额用尽返回已抓到的部分(self):
        import urllib.error

        # 满页（100）才会继续翻页，进而撞上第 2 页的 403——这正是线上形态。
        page1 = [{'number': i, 'state': 'open'} for i in range(1, 101)]
        pages = [
            self._page(page1),
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
            mock.patch('github_cnb_issues._request_with_headers', side_effect=fake_request),
        ):
            got, complete = sync.fetch_github_issues_by_number()
        self.assertEqual(sorted(got), list(range(1, 101)), '限额中断时应返回已拿到的部分，而不是抛异常')
        self.assertFalse(complete, '限额中断 = 数据不完整，必须如实报告（issue #171）')

    def test_PULL_REQUEST混入时被剔除(self):
        page = self._page([{'number': 1}, {'number': 9, 'pull_request': {}}])

        with (
            mock.patch.object(sync, '_github_headers', return_value={}),
            mock.patch('github_cnb_issues._request_with_headers', return_value=page),
        ):
            got, complete = sync.fetch_github_issues_by_number()
        self.assertEqual(sorted(got), [1], 'GitHub 的 /issues 会混入 PR，必须剔除')
        self.assertTrue(complete, '拉到底了（不足一页）⇒ 数据完整')

    def test_非403的HTTP错误同样降级(self):
        import urllib.error

        err = urllib.error.HTTPError('u', 500, 'boom', {}, None)
        with (
            mock.patch.object(sync, '_github_headers', return_value={}),
            mock.patch('github_cnb_issues._request_with_headers', side_effect=err),
        ):
            got, complete = sync.fetch_github_issues_by_number()
        self.assertEqual(got, {}, '一次性网络错不该把作业带崩')
        self.assertFalse(complete, '非 403 的错误同样意味着数据不完整')


# ---------------------------------------------------------------------------
# 六、假绿防线（issue #171）：拿不到数据时**不得**宣称「两侧已对齐」
# ---------------------------------------------------------------------------


class TestIncompleteDataNotGreen(unittest.TestCase):
    """这是本文件里最贵的一组用例。

    上线时的失败形态不是「漏标一张卡」，而是：**一张 GitHub issue 都拉不到却打印
    `✅ 无状态漂移，两侧已对齐`**。实测（2026-10-13）它真的发生了——匿名限额被建卡
    job 耗尽，`state=all` 第 3 页 403 ⇒ 空映射 ⇒ 由于 `not todo` 为真，报告「已对齐」。

    一个「永远绿、永远不干活」的机制比没有机制更坏：它让人以为网在，实际上一次都没织成。
    """

    def _patch(self, *, cards, gh, complete, is_mirror=True):
        posts: list = []
        closes: list = []
        return (
            mock.patch.object(
                sync, 'load_state', return_value={'mirrored': {str(c['gh']): {'cnb': c['cnb']} for c in cards}}
            ),
            mock.patch.object(sync, 'mirrored_cards', return_value=cards),
            mock.patch.object(sync, 'fetch_github_issues_by_number', return_value=(gh, complete)),
            mock.patch.object(sync, 'list_issue_comments', return_value=[]),
            mock.patch.object(sync, 'is_mirror_card', return_value=is_mirror),
            mock.patch.object(sync, 'post_comment', side_effect=lambda n, b, repo=None: posts.append((n, b))),
            mock.patch.object(sync, 'add_status_label'),
            mock.patch.object(sync, 'close_issue', side_effect=lambda n, repo=None: closes.append(n)),
            posts,
            closes,
        )

    def test_全空且不完整不得报已对齐(self):
        """核心回归网：0 张 issue + 数据不完整 ⇒ 非 0 退出，且不得出现「已对齐」。"""
        import contextlib
        import io

        p = self._patch(cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}], gh={}, complete=False)
        buf = io.StringIO()
        with (
            p[0],
            p[1],
            p[2],
            p[3],
            p[4],
            p[5],
            p[6],
            p[7],
            contextlib.redirect_stdout(buf),
        ):
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        out = buf.getvalue()
        self.assertEqual(rc, 1, '数据不完整 ⇒ 非 0 退出，让 cron 侧看得出这次没跑成')
        self.assertNotIn('已对齐', out, '拿不全就不能说已对齐——这正是 #171 的假绿')
        self.assertIn('数据不完整', out)
        self.assertEqual(p[9], [], '空映射下没有任何卡可关，不该产生写操作')

    def test_不完整但有漂移时照做但不背书(self):
        """部分数据仍能安全回流（plan 对拿不到的卡是跳过），故「照做但不背书」。"""
        import contextlib
        import io

        p = self._patch(
            cards=[
                {'cnb': 106, 'gh': 2034, 'cnb_state': 'open'},
                {'cnb': 107, 'gh': 2037, 'cnb_state': 'open'},
            ],
            gh={2034: {'state': 'closed', 'updated_at': '2026-10-11T00:00:00Z'}},  # 2037 拉不到
            complete=False,
        )
        buf = io.StringIO()
        with (
            p[0],
            p[1],
            p[2],
            p[3],
            p[4],
            p[5],
            p[6],
            p[7],
            contextlib.redirect_stdout(buf),
        ):
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual([n for n, _ in p[8]], [106], '拿得到的漂移照样回流')
        self.assertEqual(rc, 1, '但不完整的事实必须如实反映为退出码')
        self.assertEqual(p[9], [106], '数据不完整不该妨碍「已判定的漂移」被关掉')

    def test_完整且无漂移才报已对齐(self):
        import contextlib
        import io

        p = self._patch(
            cards=[{'cnb': 106, 'gh': 2034, 'cnb_state': 'open'}],
            gh={2034: {'state': 'open', 'updated_at': '2026-10-11T00:00:00Z'}},
            complete=True,
        )
        buf = io.StringIO()
        with (
            p[0],
            p[1],
            p[2],
            p[3],
            p[4],
            p[5],
            p[6],
            p[7],
            contextlib.redirect_stdout(buf),
        ):
            rc = sync.run(apply=True, only_cnb=None, repo=None)
        self.assertEqual(rc, 0)
        self.assertIn('已对齐', buf.getvalue(), '数据完整时的「已对齐」才是可信的')
        self.assertEqual(p[9], [])


# ---------------------------------------------------------------------------
# 六、镜像卡的识别不能只靠状态文件（源 CNB #564，2026-10-18）
# ---------------------------------------------------------------------------


class TestMirrorCardDiscovery(unittest.TestCase):
    """状态文件是**缓存**，不是全集。

    实测（2026-10-18）：CNB 侧 198 张 open 卡里 **48 张**带 `GitHub 同步` 标签却
    不在 `github_cnb_state.json` 里。它们进不了 `mirrored_cards()`，于是
    `plan()` 永远看不到它们 —— 一条永远不会被执行的代码，被读成了「已经对齐」。
    这正是 CNB `#450`（224 张重复卡）的同一形态：缓存被当成了边界。
    """

    BODY_URL = '> - 来源：https://github.com/imoyao/fundmate/issues/2213\n> - GitHub 编号：`#2213`\n\n---\n\n正文'
    BODY_NUM_ONLY = '> - GitHub 编号：`#2130`\n\n---\n\n正文'
    BODY_FAKE_NUMBER = '> - 来源：https://github.com/imoyao/fundmate/issues/888888\n> - GitHub 编号：`#888888`\n'

    def _patch(self, open_items, closed_items=(), bodies=None):
        bodies = bodies or {}
        return [
            mock.patch.object(
                sync, 'list_cnb_issues', side_effect=lambda st: list(open_items if st == 'open' else closed_items)
            ),
            mock.patch.object(sync, 'get_cnb_issue', side_effect=lambda n: {'body': bodies.get(n, '')}),
        ]

    def test_card_missing_from_state_file_is_still_found(self):
        item = {'number': 513, 'state': 'open', 'labels': [{'name': sync.MIRROR_LABEL}]}
        p = self._patch([item], bodies={513: self.BODY_URL})
        with p[0], p[1]:
            cards = sync.mirrored_cards(repo=None, state={'mirrored': {}})
        self.assertEqual([(c['cnb'], c['gh']) for c in cards], [(513, 2213)])

    def test_resolve_body_false_keeps_old_behaviour(self):
        # 反证：只走状态文件时会漏掉它们——这就是修之前的真实行为，用用例钉住它不再是默认
        item = {'number': 513, 'state': 'open', 'labels': [{'name': sync.MIRROR_LABEL}]}
        p = self._patch([item], bodies={513: self.BODY_URL})
        with p[0], p[1]:
            cards = sync.mirrored_cards(repo=None, state={'mirrored': {}}, resolve_body=False)
        self.assertEqual(cards, [])

    def test_number_line_fallback_when_url_missing(self):
        # 两种卡面形态并存（实测 CNB #187 只有编号行、没有来源 URL）
        item = {'number': 187, 'state': 'open', 'labels': [{'name': sync.MIRROR_LABEL}]}
        p = self._patch([item], bodies={187: self.BODY_NUM_ONLY})
        with p[0], p[1]:
            cards = sync.mirrored_cards(repo=None, state={'mirrored': {}})
        self.assertEqual([c['gh'] for c in cards], [2130])

    def test_self_check_card_not_chased_into_nowhere(self):
        """自检卡（CNB #113）的编号行写着 `#888888`，URL 一致，故仍被认成 888888。

        要点不是「它一定认错」，而是：**认得出就必须能被下游处理**。
        这里钉的是「URL 与编号行同为假编号时不会抛异常」——真去追它是 `plan()` 的事
        （GitHub 侧拉不到就跳过，不猜）。
        """
        item = {'number': 113, 'state': 'open', 'labels': [{'name': sync.MIRROR_LABEL}]}
        p = self._patch([item], bodies={113: self.BODY_FAKE_NUMBER})
        with p[0], p[1]:
            cards = sync.mirrored_cards(repo=None, state={'mirrored': {}})
        self.assertEqual([c['gh'] for c in cards], [888888])

    def test_unresolved_card_is_reported_not_silently_dropped(self):
        import contextlib
        import io

        item = {'number': 4, 'state': 'open', 'labels': [{'name': sync.MIRROR_LABEL}]}
        p = self._patch([item], bodies={4: '没有编号的卡'})
        buf = io.StringIO()
        with p[0], p[1], contextlib.redirect_stdout(buf):
            cards = sync.mirrored_cards(repo=None, state={'mirrored': {}})
        self.assertEqual(cards, [])
        self.assertIn('认不出 GitHub 编号', buf.getvalue(), '认不出必须说出来，不得静默丢弃')

    def test_closed_unknown_cards_do_not_drown_the_warning(self):
        import contextlib
        import io

        open_item = {'number': 4, 'state': 'open', 'labels': [{'name': sync.MIRROR_LABEL}]}
        closed_items = [
            {'number': n, 'state': 'closed', 'labels': [{'name': sync.MIRROR_LABEL}]} for n in range(20, 30)
        ]
        bodies = {4: '没有编号的卡', **{n: '没有编号的卡' for n in range(20, 30)}}
        p = self._patch([open_item], closed_items, bodies)
        buf = io.StringIO()
        with p[0], p[1], contextlib.redirect_stdout(buf):
            sync.mirrored_cards(repo=None, state={'mirrored': {}})
        out = buf.getvalue()
        self.assertIn('[4]', out)
        self.assertIn('已关闭', out, '已关的无编号卡只需计数，不该混进待处理清单')


if __name__ == '__main__':
    unittest.main()
