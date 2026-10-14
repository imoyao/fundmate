"""`scripts/bridge/local_card_promote.py` 的回归用例（CNB `#172`）。

## WHY 有这份文件

本脚本是**唯一**会「从 CNB 往 GitHub 建卡」的作业——其它桥接脚本都只读 GitHub。
写错的后果与前几次踩过的坑同族，且都不可逆（GitHub 建卡会通知关注者）：

1. **把镜像卡当成本地卡推广** → GitHub 上多出一张重复卡，且它讲的还是 CNB 语义；
2. **重复建卡**（幂等键写歪 / 重跑）→ 同一件事在 GitHub 出现两张卡，讨论劈成两半；
3. **留链用了裸引用**（`imoyao/fundmate#N` 而非完整 URL）→
   `cnb_github_backfill.py` 的 `resolve_github_number` 只认完整 URL，
   评论会被**静默跳过**，于是「卡建了、链没留」，下一个人仍然找不到（CNB `#117` 实测）；
4. **缺 `GITHUB_TOKEN` 时静默跑完** → 401 被吞、退出码 0，机制从此隐身
   （`mirror_state_sync.py` 的 #171 就是「拿不到数据还报已对齐」）。

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

import local_card_promote as promote  # noqa: E402


def _detail(**over) -> dict:
    """一张**本地卡**的详情载荷（声明在正文顶部）。"""
    card = {
        'number': 172,
        'state': 'open',
        'title': 'git-sync 双向同步分叉处置',
        'comment_count': 7,
        'labels': [],
        'body': '> 📍 **CNB 本地卡**（只对 CNB 有效，不进 GitHub）\n\n正文…',
    }
    card.update(over)
    return card


# ---------------------------------------------------------------------------
# 一、幂等键
# ---------------------------------------------------------------------------


class TestPromoteKey(unittest.TestCase):
    def test_同一张卡同一个GitHub编号得到同一个键(self):
        self.assertEqual(promote.make_key(172, 2100), promote.make_key(172, 2100))

    def test_不同GitHub编号键不同(self):
        self.assertNotEqual(promote.make_key(172, 2100), promote.make_key(172, 2101))

    def test_占位键与正式键不同(self):
        """推广**之前**写占位键、之后写正式键——两者必须不同，否则没法区分两个阶段。"""
        self.assertNotEqual(promote.make_key(172), promote.make_key(172, 2100))

    def test_键能从评论正文里抠回来(self):
        comment = promote.build_promote_comment(
            2100, 'imoyao/fundmate', promote.make_key(172, 2100), today='2026-10-14'
        )
        found = {m.group(1) for m in promote.PROMOTE_KEY_RE.finditer(comment)}
        self.assertEqual(found, {promote.make_key(172, 2100)})

    def test_推广说明本身不会把自己的键当成新键(self):
        """评论里出现「推广键」这三个字（讲机制）不该被解析成另一条键。"""
        comment = (
            promote.build_promote_comment(2100, 'imoyao/fundmate', promote.make_key(172, 2100), today='2026-10-14')
            + '\n\n（说明：上面那行 `推广键：` 是隐藏标记）'
        )
        found = {m.group(1) for m in promote.PROMOTE_KEY_RE.finditer(comment)}
        self.assertEqual(len(found), 1)


# ---------------------------------------------------------------------------
# 二、留链：必须是完整 URL、必须点明「不是镜像」
# ---------------------------------------------------------------------------


class TestPromoteComment(unittest.TestCase):
    def test_链接是完整URL(self):
        """裸引用会被回写作业静默跳过 —— 这是本脚本最容易犯且最难发现的错。"""
        comment = promote.build_promote_comment(2100, 'imoyao/fundmate', 'a' * 12, today='2026-10-14')
        self.assertIn('https://github.com/imoyao/fundmate/issues/2100', comment)

    def test_说明这是另开卡而不是镜像(self):
        """读者要能分清「本地卡 + 另开一张」与「把本地卡镜像过去」。"""
        comment = promote.build_promote_comment(2100, 'imoyao/fundmate', 'a' * 12, today='2026-10-14')
        self.assertIn('本地卡', comment)
        self.assertIn('不是把本卡镜像过去', comment)

    def test_带标题时显示标题(self):
        comment = promote.build_promote_comment(
            2100, 'imoyao/fundmate', 'a' * 12, today='2026-10-14', gh_title='回流通道'
        )
        self.assertIn('回流通道', comment)

    def test_无标题时不留下空括号(self):
        comment = promote.build_promote_comment(2100, 'imoyao/fundmate', 'a' * 12, today='2026-10-14')
        self.assertNotIn('（）', comment)


# ---------------------------------------------------------------------------
# 三、读路径用同一套本地卡判据（不在这里复写一份）
# ---------------------------------------------------------------------------


class TestLocalCardGate(unittest.TestCase):
    def test_判定复用公共实现(self):
        """本模块不该自己实现本地卡判据 —— 口径分两处实现，迟早长出两种结论。"""
        source = (ROOT / 'scripts' / 'bridge' / 'local_card_promote.py').read_text(encoding='utf-8')
        self.assertIn('local_card_kind', source)
        # 不该自己拼「有没有 GitHub 编号」的正则
        self.assertNotIn("'GitHub 编号：`#'", source)

    def test_声明过的本地卡被判为本地卡(self):
        import github_cnb_issues as mirror

        self.assertEqual(mirror.local_card_kind(_detail()), 'body')

    def test_镜像卡不会被判成本地卡(self):
        import github_cnb_issues as mirror

        mirror_card = _detail(
            body='> - 来源：https://github.com/imoyao/fundmate/issues/2034\n> - GitHub 编号：`#2034`',
            labels=[{'name': 'GitHub 同步'}],
        )
        self.assertEqual(mirror.local_card_kind(mirror_card), '')


# ---------------------------------------------------------------------------
# 四、缺 token 必须显式失败，不许静默空跑
# ---------------------------------------------------------------------------


class TestGithubTokenRequired(unittest.TestCase):
    def test_缺token时直接抛错(self):
        with mock.patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                promote._github_headers()
        self.assertIn('GITHUB_TOKEN', str(ctx.exception))

    def test_有token时带上Bearer头(self):
        with mock.patch.dict('os.environ', {'GITHUB_TOKEN': 'x'}, clear=True):
            headers = promote._github_headers()
        self.assertEqual(headers['Authorization'], 'Bearer x')


# ---------------------------------------------------------------------------
# 五、非本地卡拒绝推广 + dry-run 不写任何东西
# ---------------------------------------------------------------------------


class TestPromoteFlow(unittest.TestCase):
    def _run(self, detail, *, apply=False, body='正文', existing_gh=None):
        calls: dict[str, list] = {'cnb_comment': [], 'gh_create': [], 'refresh': []}

        def fake_get_cnb_issue(number):
            return detail

        def fake_find(title):
            return existing_gh

        def fake_create(title, gh_body, labels):
            calls['gh_create'].append((title, gh_body, labels))
            return 2100

        def fake_post_comment(number, body_text, **kw):
            calls['cnb_comment'].append((number, body_text))

        def fake_refresh():
            calls['refresh'].append(True)
            return 0

        with (
            mock.patch.object(promote, 'get_cnb_issue', fake_get_cnb_issue),
            mock.patch.object(promote, 'find_existing_github_card', fake_find),
            mock.patch.object(promote, 'create_github_card', fake_create),
            mock.patch.object(promote, 'post_comment', fake_post_comment),
            mock.patch.object(promote, 'existing_promote_keys', lambda n: set()),
            mock.patch.object(promote, '_refresh_mirror', fake_refresh),
            mock.patch.object(promote, '_github_repo', lambda: 'imoyao/fundmate'),
        ):
            tmp = Path(self._tmp_body(body))
            rc = promote.run_promote(172, '新卡标题', str(tmp), apply=apply, labels=[], refresh=True)
        return rc, calls

    def _tmp_body(self, text: str) -> str:
        import tempfile

        fd = tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8')
        fd.write(text)
        fd.close()
        return fd.name

    def test_镜像卡被拒绝(self):
        mirror_card = _detail(
            body='> - 来源：https://github.com/imoyao/fundmate/issues/2034\n> - GitHub 编号：`#2034`',
            labels=[{'name': 'GitHub 同步'}],
        )
        rc, calls = self._run(mirror_card, apply=True)
        self.assertEqual(rc, 1)
        self.assertEqual(calls['gh_create'], [])
        self.assertEqual(calls['cnb_comment'], [])

    def test_dry_run不建卡不发评论(self):
        rc, calls = self._run(_detail(), apply=False)
        self.assertEqual(rc, 0)
        self.assertEqual(calls['gh_create'], [])
        self.assertEqual(calls['cnb_comment'], [])
        self.assertEqual(calls['refresh'], [])

    def test_apply时三步都执行(self):
        rc, calls = self._run(_detail(), apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls['gh_create']), 1)
        self.assertEqual(len(calls['cnb_comment']), 1, '留链评论必须真的发出去')
        self.assertEqual(calls['refresh'], [True], '镜像刷新必须被调用')

    def test_同名卡已存在时复用而不重复建(self):
        rc, calls = self._run(_detail(), apply=True, existing_gh=2100)
        self.assertEqual(rc, 0)
        self.assertEqual(calls['gh_create'], [], '存在同名卡时不得再建')
        self.assertEqual(len(calls['cnb_comment']), 1)

    def test_正文文件为空时拒绝(self):
        rc, calls = self._run(_detail(), apply=True, body='   ')
        self.assertEqual(rc, 1)
        self.assertEqual(calls['gh_create'], [])
