# -*- coding: utf-8 -*-
"""CNB → GitHub 回写脚本的回归网（源 CNB `#2` 的「评论能否同步到 GitHub」）。

## WHY 有这份文件

`scripts/bridge/cnb_github_backfill.py` 由 `.github/workflows/cnb-github-backfill.yml`
每日**无人值守**驱动，且做的是**有外部副作用**的事：在 GitHub 上发评论、Ping 到人。
它一旦「静默半失效」，后果按严重度排序是：

  1. **幂等键失效** → 每天把同一批 CNB 评论重贴到 GitHub，卡片被刷屏，
     而这**不可逆**（GitHub 评论只能编辑，不能由脚本静默撤回）；
  2. **映射猜错编号** → 评论贴到**别人的卡**上。这条最贵：镜像卡正文里的 GitHub 链接
     是唯一依据，所以本文件专门钉「抠不到就不猜，返回 None」；
  3. **机器人评论刷屏** → CNB 的 NPC（OCI / CodeBuddy）输出被搬回 GitHub 铺满一屏。

2026-10-18（源 CNB #561）后，第 3 条从「拦住」改成「折叠」：机器人评论照常回写，
但默认折叠进 `<details>`；带 `<!-- conclusion -->` 标记的默认展开。故本文件除
**幂等标记**、**机器人过滤**、**评论成形**、**编号映射**、**时间过滤**五类之外，
另钉第六类 **NPC 折叠口径**，以及「存量不补」这条硬下界。
全程**零网络、零写入**；除 `TestStockNotBackfilled` 的一条接线用例（打桩全部 IO）外只跑纯函数。
"""

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / 'scripts' / 'bridge' / 'cnb_github_backfill.py'

_BACKFILL = None


def _load_backfill():
    """按路径加载脚本模块（进程内只加载一次，与 test_guard_mojibake.py 同法）。"""
    global _BACKFILL
    if _BACKFILL is None:
        spec = importlib.util.spec_from_file_location('cnb_github_backfill', _SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['cnb_github_backfill'] = module
        spec.loader.exec_module(module)
        _BACKFILL = module
    return _BACKFILL


@pytest.fixture()
def bf():
    return _load_backfill()


def _comment(cid=1001, body='结论：按方案 A 落地。', author=None, created_at='2026-10-11T03:00:00Z'):
    """造一条最小可用的 CNB 评论载荷。"""
    return {
        'id': str(cid),
        'body': body,
        'author': author
        if author is not None
        else {'username': 'cnb.dMyB1AlBAGA', 'nickname': '阿白', 'is_npc': False},
        'created_at': created_at,
    }


# ---------------------------------------------------------------------------
# 1. 幂等标记
# ---------------------------------------------------------------------------


class TestMarker:
    def test_marker_is_html_comment(self, bf):
        """标记必须是 HTML 注释 —— 渲染时不可见，否则每张卡都会多出一行机器味。"""
        m = bf.backfill_marker(2, '2109119676427591680')
        assert m.startswith('<!--') and m.endswith('-->')
        assert 'issue=2' in m and 'comment=2109119676427591680' in m

    def test_marker_round_trip(self, bf):
        """build_comment 产出的正文必须能被 collect_markers 原样抠回。"""
        c = _comment(cid='2109119676427591680')
        text = bf.build_comment(2, c)
        assert bf.collect_markers([{'body': text}]) == {(2, 2109119676427591680)}

    def test_collect_markers_multiple(self, bf):
        """一屏多条评论、每条各带标记，都要收全（漏收 = 重复发）。"""
        bodies = [{'body': bf.build_comment(2, _comment(cid=i))} for i in (11, 22, 33)]
        assert bf.collect_markers(bodies) == {(2, 11), (2, 22), (2, 33)}

    def test_collect_markers_ignores_foreign(self, bf):
        """无关评论里的 `<!-- ... -->` 不该被当标记 —— 正则要足够窄。"""
        bodies = [
            {'body': '<!-- 这是别人写的普通注释 -->'},
            {'body': '<!-- cnb-backfill: 格式不对 -->'},
            {'body': None},
            {},
        ]
        assert bf.collect_markers(bodies) == set()

    def test_marker_tolerates_spacing(self, bf):
        """标记两侧空格变了仍要认出来（防「有人手改了一下就全部重发」）。"""
        box = [{'body': 'x <!--cnb-backfill:   issue=7   comment=99 --> y'}]
        assert bf.collect_markers(box) == {(7, 99)}


# ---------------------------------------------------------------------------
# 2. 机器人过滤
# ---------------------------------------------------------------------------


class TestBotFilter:
    def test_is_npc_flag(self, bf):
        """CNB 的 NPC 用 is_npc 明示 —— 这是最可靠的一条判据。"""
        assert bf.is_bot({'username': 'CodeBuddy', 'is_npc': True}) is True
        assert bf.is_bot({'username': '阿白', 'is_npc': False}) is False

    @pytest.mark.parametrize(
        'name, expect',
        [
            ('OCI', True),
            ('CodeBuddy', True),
            ('some-app[bot]', True),
            (None, None),
        ],
    )
    def test_known_bot_names(self, bf, name, expect):
        """历史数据里 NPC 的 is_npc 不一定都填了，故按名字兜底。"""
        if expect is None:
            assert bf.is_bot({'username': 'someone', 'nickname': None}) is False
        else:
            assert bf.is_bot({'username': name, 'is_npc': False}) is expect

    def test_none_author_is_not_bot(self, bf):
        """作者字段缺失不该被判成机器人（宁可多发一条，也别把真人讨论吞掉）。"""
        assert bf.is_bot(None) is False
        assert bf.is_bot({}) is False

    def test_real_user_passes(self, bf):
        assert bf.is_bot({'username': 'cnb.dMyB1AlBAGA', 'nickname': '阿白', 'is_npc': False}) is False


# ---------------------------------------------------------------------------
# 3. 待回写挑选
# ---------------------------------------------------------------------------


class TestPendingComments:
    def test_new_comment_is_pending(self, bf):
        todo = bf.pending_comments(2, [_comment()], set(), None)
        assert len(todo) == 1

    def test_already_backfilled_is_skipped(self, bf):
        """核心幂等：标记里已有的 (issue, comment) 一律不再回写。"""
        c = _comment(cid=555)
        todo = bf.pending_comments(2, [c], {(2, 555)}, None)
        assert todo == []

    def test_bot_comments_are_pending(self, bf):
        """**机器人评论不再被跳过**（2026-10-18，源 CNB #561）。

        旧行为是「作者是机器人 ⇒ 不回写」，代价是 NPC 写下的结论一个字都到不了
        GitHub。现在闸门交给 `build_comment` 的折叠，`pending_comments` 一律放行。
        """
        npc = _comment(cid=777, author={'username': 'CodeBuddy', 'is_npc': True})
        todo = bf.pending_comments(2, [npc], set(), None)
        assert [c['id'] for c in todo] == ['777']

    def test_bot_comment_still_idempotent(self, bf):
        """放行不等于放弃幂等：已回写过的机器人评论照样不重发。"""
        npc = _comment(cid=777, author={'username': 'CodeBuddy', 'is_npc': True})
        assert bf.pending_comments(2, [npc], {(2, 777)}, None) == []

    def test_since_filters_old(self, bf):
        """--since 只回写该时刻之后的评论；更早的跳过。"""
        old = _comment(cid=1, created_at='2026-09-01T00:00:00Z')
        new = _comment(cid=2, created_at='2026-10-11T00:00:00Z')
        todo = bf.pending_comments(2, [old, new], set(), datetime(2026, 10, 1, tzinfo=UTC))
        assert [c['id'] for c in todo] == ['2']

    def test_comment_without_id_is_skipped(self, bf):
        """没有 id 就没法做幂等 —— 宁可跳过，不可发出一个无法去重的评论。"""
        assert bf.pending_comments(2, [{'body': 'x', 'author': {'is_npc': False}}], set(), None) == []

    def test_sorted_chronologically(self, bf):
        """按时间正序回写，GitHub 上的阅读顺序才跟 CNB 一致。"""
        a = _comment(cid=1, created_at='2026-10-11T03:00:00Z')
        b = _comment(cid=2, created_at='2026-10-11T01:00:00Z')
        c = _comment(cid=3, created_at='2026-10-11T02:00:00Z')
        todo = bf.pending_comments(2, [a, b, c], set(), None)
        assert [x['id'] for x in todo] == ['2', '3', '1']


# ---------------------------------------------------------------------------
# 4. 评论成形
# ---------------------------------------------------------------------------


class TestBuildComment:
    def test_contains_origin_and_marker(self, bf):
        text = bf.build_comment(2, _comment(cid=42))
        assert 'CNB #2' in text
        assert '42' in text
        assert '结论：按方案 A 落地。' in text
        assert '<!-- cnb-backfill: issue=2 comment=42 -->' in text

    def test_long_body_is_collapsed(self, bf):
        """超长正文折叠进 <details>，免得一条回写把整张卡刷掉一屏。"""
        text = bf.build_comment(2, _comment(body='字' * (bf.COLLAPSE_THRESHOLD + 1)))
        assert '<details>' in text and '</details>' in text

    def test_short_body_not_collapsed(self, bf):
        text = bf.build_comment(2, _comment(body='短评'))
        assert '<details>' not in text

    def test_body_is_truncated_to_github_limit(self, bf):
        """GitHub 单条评论上限 65536 字符，超了会 422 —— 必须截断保标记还在。"""
        text = bf.build_comment(2, _comment(cid=8, body='x' * (bf.MAX_BODY + 5000)))
        assert len(text) <= bf.MAX_BODY
        # 截断不能把幂等标记切掉，否则下一轮会重发
        assert bf.collect_markers([{'body': text}]) == {(2, 8)}

    def test_missing_author_does_not_crash(self, bf):
        text = bf.build_comment(2, {'id': '9', 'body': 'x', 'author': None, 'created_at': None})
        assert 'unknown' in text


# ---------------------------------------------------------------------------
# 4b. NPC 折叠口径（2026-10-18，源 CNB #561）
# ---------------------------------------------------------------------------


def _npc_body(with_conclusion: bool) -> str:
    core = '执行日志：跑了 3 条命令、2 个探针。' * 5
    if not with_conclusion:
        return core
    return f'{core}\n\n<!-- conclusion -->\n结论：A 方案的判据不成立。\n<!-- /conclusion -->\n'


class TestNpcCollapse:
    def test_npc_without_conclusion_is_collapsed(self, bf):
        """无结论标记 ⇒ 折叠。执行日志铺满一屏是这一条要防的唯一后果。"""
        text = bf.build_comment(
            561, _comment(cid=1, body=_npc_body(False), author={'username': 'CodeBuddy', 'is_npc': True})
        )
        assert '<details>' in text
        assert 'CNB NPC 回复' in text
        # 正文仍要完整保留 —— 折叠不是删减
        assert '执行日志：跑了 3 条命令' in text

    def test_npc_with_conclusion_is_expanded(self, bf):
        """有结论标记 ⇒ 默认展开，且结论出现在折叠条之外（读者一眼可见）。"""
        text = bf.build_comment(
            561, _comment(cid=2, body=_npc_body(True), author={'username': 'CodeBuddy', 'is_npc': True})
        )
        outside = text.split('<details>')[0]
        assert '结论：A 方案的判据不成立。' in outside
        assert '<details>' not in text

    def test_conclusion_marker_is_invisible(self, bf):
        """标记本身不能漏进 GitHub 正文（HTML 注释虽不可见，但会把结论正文以外的噪声带过去）。"""
        text = bf.build_comment(
            561, _comment(cid=3, body=_npc_body(True), author={'username': 'CodeBuddy', 'is_npc': True})
        )
        assert '<!-- conclusion -->' not in text
        assert '<!-- /conclusion -->' not in text

    def test_inline_conclusion_form(self, bf):
        """`<!-- conclusion: 一句话 -->` 这种单行形态也要认。"""
        body = '很多日志\n<!-- conclusion: 应当保留现状 -->'
        assert bf.extract_conclusion(body) == '应当保留现状'

    def test_human_comment_never_force_collapsed(self, bf):
        """真人短评不受 NPC 口径影响 —— 不能被误折叠，这是最贵的假阳性。"""
        text = bf.build_comment(2, _comment(cid=4, body='短评', author={'username': 'imoyao', 'is_npc': False}))
        assert '<details>' not in text
        assert 'CNB NPC 回复' not in text

    def test_human_long_comment_follows_threshold(self, bf):
        """真人长评仍按 COLLAPSE_THRESHOLD 折叠，且不带 NPC 字样。"""
        body = '字' * (bf.COLLAPSE_THRESHOLD + 1)
        text = bf.build_comment(2, _comment(cid=5, body=body, author={'username': 'imoyao', 'is_npc': False}))
        assert '<details>' in text
        assert 'CNB NPC 回复' not in text

    def test_npc_text_does_not_mention_none_author(self, bf):
        """作者缺失仍按真人处理（既有契约），不要顺手判成机器人去折叠。"""
        text = bf.build_comment(2, {'id': '6', 'body': 'x', 'author': None, 'created_at': None})
        assert '<details>' not in text


class TestStockNotBackfilled:
    """「存量不补」这道下界（2026-10-18 用户拍板）。"""

    def test_default_since_is_frozen(self, bf):
        """不传 --since 时必须有下界，否则第一次跑就把几千条存量 NPC 评论搬过去。"""
        assert bf.default_since(None) == bf.NPC_INCLUDE_SINCE

    def test_explicit_since_cannot_widen(self, bf):
        """--since 只能让范围更窄 —— 传个更早的日期不能把存量放进来。"""
        assert bf.default_since(datetime(2020, 1, 1, tzinfo=UTC)) == bf.NPC_INCLUDE_SINCE

    def test_explicit_since_can_narrow(self, bf):
        later = datetime(2026, 11, 1, tzinfo=UTC)
        assert bf.default_since(later) == later

    def test_run_actually_applies_the_floor(self, bf, monkeypatch, capsys):
        """**接线层**：`run()` 必须真的把下界用上。

        只测 `default_since()` 的返回值不够——把 `run()` 里那行删掉，纯函数测试照样全绿，
        而脚本会把存量全搬过去（这条正是探针 P4 咬出来的）。
        """
        seen: dict = {}

        def fake_pending(n, cs, ex, since):
            seen.setdefault('since', since)
            return []

        def fake_detail(_n):
            # 正文里带 GitHub 溯源块，才走得到 pending_comments 那一步
            return {'body': 'https://github.com/imoyao/fundmate/issues/1'}

        monkeypatch.setattr(bf, 'list_cnb_issues', lambda: [{'number': 1, 'comment_count': 3}])
        monkeypatch.setattr(bf, 'get_cnb_issue', fake_detail)
        monkeypatch.setattr(bf, 'list_cnb_comments', lambda _n: [_comment(cid=1)])
        monkeypatch.setattr(bf, 'list_github_comments', lambda _r, _n: [])
        monkeypatch.setattr(bf, 'load_state', lambda: {'backfilled': {}})
        monkeypatch.setattr(bf, 'save_state', lambda _s: None)
        monkeypatch.setattr(bf, 'pending_comments', fake_pending)
        bf.run(dry_run=True, limit=None, since=None)
        assert seen['since'] == bf.NPC_INCLUDE_SINCE


# ---------------------------------------------------------------------------
# 5. 编号映射
# ---------------------------------------------------------------------------


class TestResolveGithubNumber:
    def test_parses_origin_block(self, bf, monkeypatch):
        """正常情形：镜像卡正文顶部溯源块里的原链接。"""
        monkeypatch.setenv('GITHUB_REPO', 'imoyao/fundmate')
        body = '> - 来源：https://github.com/imoyao/fundmate/issues/783\n\n---\n\n正文'
        assert bf.resolve_github_number({'body': body}) == 783

    def test_returns_none_when_absent(self, bf, monkeypatch):
        """**最关键的一条**：抠不到链接就返回 None（跳过），绝不猜编号。

        猜错 = 把评论贴到别人的卡上，这是本脚本最贵的失效模式。
        """
        monkeypatch.setenv('GITHUB_REPO', 'imoyao/fundmate')
        assert bf.resolve_github_number({'body': '## 背景\n\n本卡开在 CNB。'}) is None
        assert bf.resolve_github_number({'body': None}) is None
        assert bf.resolve_github_number({}) is None

    def test_ignores_other_repos(self, bf, monkeypatch):
        """正文里提到**别的**仓库的 issue 不该被误认成映射。"""
        monkeypatch.setenv('GITHUB_REPO', 'imoyao/fundmate')
        body = '见 https://github.com/other-org/other-repo/issues/999 的讨论'
        assert bf.resolve_github_number({'body': body}) is None

    def test_ignores_pull_urls(self, bf, monkeypatch):
        """`/pull/123` 不是 issue 链接（虽然 GitHub 会把两者编号混在一个命名空间）。"""
        monkeypatch.setenv('GITHUB_REPO', 'imoyao/fundmate')
        body = 'https://github.com/imoyao/fundmate/pull/2051'
        assert bf.resolve_github_number({'body': body}) is None

    def test_first_match_wins(self, bf, monkeypatch):
        """正文里出现多个链接时取第一个（溯源块在顶部，顺序稳定）。"""
        monkeypatch.setenv('GITHUB_REPO', 'imoyao/fundmate')
        body = (
            '> - 来源：https://github.com/imoyao/fundmate/issues/783\n'
            '> - 另见：https://github.com/imoyao/fundmate/issues/999\n'
        )
        assert bf.resolve_github_number({'body': body}) == 783


# ---------------------------------------------------------------------------
# 6. 时间解析
# ---------------------------------------------------------------------------


class TestParseTs:
    def test_parses_z_suffix(self, bf):
        assert bf.parse_ts('2026-10-11T03:00:00Z') == datetime(2026, 10, 11, 3, 0, tzinfo=UTC)

    def test_parses_offset(self, bf):
        got = bf.parse_ts('2026-10-11T11:00:00+08:00')
        assert got is not None and got.utcoffset().total_seconds() == 8 * 3600

    @pytest.mark.parametrize('bad', [None, '', 'not-a-time', '2026-13-45'])
    def test_bad_input_returns_none(self, bf, bad):
        """解不出返回 None —— 调用方据此「不设 since 过滤」，而不是崩掉整轮。"""
        assert bf.parse_ts(bad) is None


# ---------------------------------------------------------------------------
# 6.5 批处理韧性：单点失败不炸整轮
# ---------------------------------------------------------------------------


class TestRunResilience:
    """`_request` 自 df51d21b 起把 HTTPError 包成 RuntimeError（带诊断），
    `run()` 里原有的 `except urllib.error.HTTPError` 随之变成死代码：
    一张被删的 GitHub 卡（404）、一条超限的评论（422）就能让**全天作业**挂掉——
    那正是「定时作业一直报错」的形态。这两条钉子保证坏数据被跳过、好数据照常回写。
    """

    @pytest.fixture()
    def wired(self, bf, monkeypatch):
        """搭一个最小假环境：两张有评论的 CNB 卡，都能映射到 GitHub。"""
        monkeypatch.setenv('GITHUB_REPO', 'imoyao/fundmate')
        monkeypatch.setenv('CNB_REPO', 'duoduobei/fundmate')
        monkeypatch.setattr(bf, 'load_state', lambda: {'last_sync_at': None, 'backfilled': {}})
        monkeypatch.setattr(bf, 'save_state', lambda state: None)
        monkeypatch.setattr(
            bf,
            'list_cnb_issues',
            lambda: [{'number': '2', 'comment_count': 1}, {'number': '3', 'comment_count': 1}],
        )
        monkeypatch.setattr(
            bf,
            'get_cnb_issue',
            lambda n: {'body': f'> - 来源：https://github.com/imoyao/fundmate/issues/{100 + int(n)}'},
        )
        monkeypatch.setattr(
            bf,
            'list_cnb_comments',
            lambda n: [
                {
                    'id': str(1000 + int(n)),
                    'body': '结论：按方案 A 落地。',
                    'author': {'username': 'cnb.user', 'is_npc': False},
                    'created_at': '2026-10-19T00:00:00Z',
                }
            ],
        )
        return bf

    def test_one_issue_read_failure_does_not_abort_run(self, wired, monkeypatch):
        """读某张 GitHub 卡的评论失败（404 被删 / 403 限额）→ 跳过该卡，其余照常。"""

        def fake_list_github_comments(repo, number):
            if number == 102:
                raise RuntimeError('HTTP 404 Not Found（读 GitHub 评论）')
            return []

        monkeypatch.setattr(wired, 'list_github_comments', fake_list_github_comments)
        posted: list[int] = []
        monkeypatch.setattr(wired, 'post_github_comment', lambda repo, number, body: posted.append(number) or {})

        rc = wired.run(dry_run=False, limit=None, since=None)

        assert rc == 0
        assert posted == [103]

    def test_one_comment_post_failure_does_not_abort_run(self, wired, monkeypatch):
        """单条评论回写失败（422 正文超限 / 403）→ 跳过该条，同卡其余评论照常。"""
        monkeypatch.setattr(wired, 'list_cnb_issues', lambda: [{'number': '2', 'comment_count': 2}])
        monkeypatch.setattr(wired, 'list_github_comments', lambda repo, number: [])
        comments = [
            {
                'id': '1',
                'body': '甲',
                'author': {'username': 'u', 'is_npc': False},
                'created_at': '2026-10-19T00:00:00Z',
            },
            {
                'id': '2',
                'body': '乙',
                'author': {'username': 'u', 'is_npc': False},
                'created_at': '2026-10-19T01:00:00Z',
            },
        ]
        monkeypatch.setattr(wired, 'list_cnb_comments', lambda n: comments)
        sent: list[str] = []

        def fake_post(repo, number, body):
            if '乙' in body:
                raise RuntimeError('HTTP 422（正文超限）')
            sent.append('甲')

        monkeypatch.setattr(wired, 'post_github_comment', fake_post)

        rc = wired.run(dry_run=False, limit=None, since=None)

        assert rc == 0
        assert sent == ['甲']


# ---------------------------------------------------------------------------
# 7. 契约冻结：与镜像方向的格式一致性
# ---------------------------------------------------------------------------


class TestContract:
    def test_marker_prefix_is_frozen(self, bf):
        """幂等键的**字面前缀**冻结。

        改这个前缀等于把所有已有回写认成「没写过」，下一轮会把全部 CNB 评论
        重发到 GitHub —— 不可逆。真要改，必须同时提供存量标记的兼容读取。
        """
        assert bf.MARKER_PREFIX == '<!-- cnb-backfill:'

    def test_github_body_limit_matches_api(self, bf):
        """GitHub 评论正文上限 65536；留点余量，别贴着上限写。"""
        assert bf.MAX_BODY < 65536
