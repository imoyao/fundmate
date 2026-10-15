# -*- coding: utf-8 -*-
"""`scripts/bridge/claim_detect.py` 的回归用例（源 CNB #179）。

## WHY 有这份文件

本脚本做的是**有外部副作用**的事：往 GitHub issue **挂标签 + 发评论**。
判错了不是「少标一张」，而是：

  - **把一张不相关的 GitHub 卡标成「CNB 处理中」**（引用认错编号）——
    下一个人会因此不去动那张卡，而其实根本没人管它；
  - **重复刷认领评论**（幂等键写歪）→ 同一张卡评论区被刷一屏；
  - **给本地卡找 GitHub 卡**（D52 明确本地卡不进 GitHub）——等于生产幻觉；
  - **把已关的卡标成「正在处理」**——「正在」这个词在关掉的卡上是自相矛盾。

故这里钉死六类边界：

1. **认领只由事实定义**：「CNB 侧有 open PR 引用这张卡」。不看 assignee、不看谁说了什么；
2. **闸门三步**：必须是 open 卡 + 镜像卡（非本地卡）+ 能定位 GitHub 编号，缺一即跳过；
3. **引用认错的代价**：`unknown_refs` 必须被交出去（引用了不存在的卡），不得静默丢弃；
4. **幂等**：认领评论只发一次；重复跑不重发；
5. **「拿不到数据」≠「没有认领」**：`complete=False` 时不得宣称「无认领」且退出码非 0；
6. **缺 token 必须提前失败**：否则写的时候才 401，会被 `|| true` 收尾吞成假绿（#171）。

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

import claim_detect as cd  # noqa: E402


def mirror_card(number: int, github: int, *, state: str = 'open') -> dict:
    """造一张最简镜像卡（只留判据要读的字段）。"""
    return {
        'number': number,
        'state': state,
        'labels': [{'name': cd.MIRROR_LABEL}],
        'body': f'> - 来源：https://github.com/imoyao/fundmate/issues/{github}\n'
        f'> - GitHub 编号：`#{github}`\u3000状态：`open`\n',
    }


def local_card(number: int) -> dict:
    return {
        'number': number,
        'state': 'open',
        'labels': [{'name': cd.LOCAL_LABEL}],
        'body': '> 📍 **CNB 本地卡**\n\n# 只对 CNB 有效\n',
    }


def pull(number: int, title: str, body: str = '', state: str = 'open') -> dict:
    return {'number': number, 'title': title, 'body': body, 'state': state}


# ---------------------------------------------------------------------------
# 一、从卡面抠编号
# ---------------------------------------------------------------------------


class TestExtractNumber(unittest.TestCase):
    def test_编号行优先(self):
        self.assertEqual(cd.extract_github_number(mirror_card(106, 2034)['body']), 2034)

    def test_链接行兜底(self):
        body = '> - 来源：https://github.com/imoyao/fundmate/issues/2034\n'
        self.assertEqual(cd.extract_github_url_number(body), 2034)

    def test_两条路都认(self):
        card = {'body': '> - 来源：https://github.com/imoyao/fundmate/issues/2034\n'}
        self.assertEqual(cd.github_number_of(card), 2034)

    def test_没有编号返回None(self):
        self.assertIsNone(cd.github_number_of({'body': '随便一段话'}))
        self.assertIsNone(cd.github_number_of({}))

    def test_别的仓库的链接不认(self):
        """认成别的仓库的卡 = 把标签挂到不相干的 issue 上。"""
        body = '> - 来源：https://github.com/someone/else/issues/2034\n'
        self.assertIsNone(cd.extract_github_url_number(body))


# ---------------------------------------------------------------------------
# 二、闸门：本地卡 / 关闭卡 / 非镜像卡
# ---------------------------------------------------------------------------


class TestGates(unittest.TestCase):
    def test_本地卡被拦(self):
        """**这是 `is_local_card` 闸门唯一真正咬得住、也最该咬住的形态。**

        本地卡正文里**引用了** GitHub 卡是常见且被鼓励的写法（AGENTS.md 要求跨仓引用
        写完整 URL）。于是它同时满足：
          - `is_mirror_card` 为真（正文能抠到 GitHub 链接）；
          - `github_number_of` 有值（2118）。
        若只看这两条，一张**永远不该进 GitHub 的本地卡**会被判成「认领 GitHub #2118」，
        于是一张讲 CNB cron 语义的卡，把标签挂到一条完全不相干的 GitHub 需求上。

        （先前这条例用「本地卡不引用任何 GitHub 卡」的 fixture 写，
        `is_local_card` 摘掉后仍然绿 —— 探针 MISSED 抓出了这个假用例。）
        """
        card = {
            'number': 179,
            'state': 'open',
            'labels': [{'name': cd.LOCAL_LABEL}],
            'body': '> 📍 **CNB 本地卡**\n\n它讲的是 https://github.com/imoyao/fundmate/issues/2118 那条线\n',
        }
        # 先断言前提成立：这条 fixture 确实能通过另外两道闸门（否则这条用例又在测空气）
        self.assertTrue(cd.is_mirror_card(card))
        self.assertEqual(cd.github_number_of(card), 2118)
        claims, unknown = cd.plan_claims([card], [pull(180, 'fix: 同步模型（#179）')])
        self.assertEqual(claims, [])
        self.assertEqual(unknown, [])

    def test_正文声明本地卡也算本地卡(self):
        card = {'number': 1, 'state': 'open', 'labels': [], 'body': '> 📍 **CNB 本地卡**\n'}
        self.assertTrue(cd.is_local_card(card))

    def test_提到概念不算本地卡声明(self):
        """锚在行首引用块上：正文里「提到 CNB 本地卡这个概念」不该被当成声明（D52 同款证伪）。"""
        card = {'number': 1, 'state': 'open', 'labels': [], 'body': '本节回答「CNB 本地卡 怎么处理」\n'}
        self.assertFalse(cd.is_local_card(card))

    def test_已关闭的卡不算正在处理(self):
        """`CNB 处理中` 挂在一张关掉的卡上是自相矛盾——「正在」不能用在已结束的事上。"""
        claims, _ = cd.plan_claims([mirror_card(106, 2034, state='closed')], [pull(180, 'fix（#106）')])
        self.assertEqual(claims, [])

    def test_关闭的PR不算正在处理(self):
        pulls = [pull(180, 'fix（#106）', state='closed')]
        claims, _ = cd.plan_claims([mirror_card(106, 2034)], pulls)
        self.assertEqual(claims, [])

    def test_既非镜像也非本地则跳过(self):
        card = {'number': 9, 'state': 'open', 'labels': [], 'body': '一张说不清的卡\n'}
        claims, _ = cd.plan_claims([card], [pull(1, 'x（CNB #9）')])
        self.assertEqual(claims, [])

    def test_镜像卡但抠不到编号则跳过(self):
        card = {'number': 9, 'state': 'open', 'labels': [{'name': cd.MIRROR_LABEL}], 'body': 'no number\n'}
        claims, _ = cd.plan_claims([card], [pull(1, 'x（CNB #9）')])
        self.assertEqual(claims, [])


# ---------------------------------------------------------------------------
# 三、认领判定
# ---------------------------------------------------------------------------


class TestPlanClaims(unittest.TestCase):
    def test_open_pr_引用镜像卡算认领(self):
        claims, unknown = cd.plan_claims(
            [mirror_card(106, 2034)],
            [pull(180, 'fix(bridge): 分叉判据（CNB #106）')],
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].cnb_number, 106)
        self.assertEqual(claims[0].github_number, 2034)
        self.assertEqual(claims[0].prs, [180])
        self.assertEqual(unknown, [])

    def test_引用未纳入本轮的卡也算unknown(self):
        """`unknown_refs` 是「CNB 侧找不到这张卡」，不是「没引用」——
        故 `only_cnb` 那种只喂一张卡的场景，其它合法引用也计入 unknown，
        由调用方按「本轮没判」而非「引用写错」阅读。这条把语义钉住，免得下一个人
        把它当成 bug 去「修」成静默忽略。"""
        claims, unknown = cd.plan_claims([mirror_card(106, 2034)], [pull(180, '（CNB #106、CNB #179）')])
        self.assertEqual(len(claims), 1)
        self.assertEqual(unknown, [179])

    def test_多个PR合并到一条认领(self):
        claims, _ = cd.plan_claims(
            [mirror_card(179, 2120)],
            [pull(180, '（CNB #179）'), pull(181, '（CNB #179）')],
        )
        self.assertEqual(claims[0].prs, [180, 181])

    def test_全文URL形态也认(self):
        claims, _ = cd.plan_claims(
            [mirror_card(106, 2034)],
            [pull(9, 'fix', '见 https://cnb.cool/duoduobei/fundmate/-/issues/106')],
        )
        self.assertEqual(claims[0].github_number, 2034)

    def test_引用了不存在的卡必须报出来(self):
        """不是「没有认领」，是「引用了不存在的卡」——这是真实错误，不得静默丢弃（#171/#179）。"""
        claims, unknown = cd.plan_claims([mirror_card(106, 2034)], [pull(7, 'fix（CNB #99999）')])
        self.assertEqual(claims, [])
        self.assertEqual(unknown, [99999])

    def test_同一PR引用两张卡各成一条(self):
        claims, _ = cd.plan_claims(
            [mirror_card(106, 2034), mirror_card(107, 2037)],
            [pull(5, 'chore（CNB #106、CNB #107）')],
        )
        self.assertEqual([c.github_number for c in claims], [2034, 2037])

    def test_refs_抽号不重复(self):
        self.assertEqual(cd.refs_in_title('#1 #1 #2'), {1, 2})

    def test_完整URL最可靠(self):
        self.assertEqual(
            cd.refs_in_text('见 https://cnb.cool/duoduobei/fundmate/-/issues/106'),
            {106},
        )

    def test_限定写法也认(self):
        for text in ('CNB #179', 'CNB 的 #179', 'CNB 侧 #179', 'CNB 卡 #179'):
            self.assertEqual(cd.refs_in_text(text), {179}, text)

    def test_正文裸号一律不收(self):
        """**这是判据里最要紧的一条**（2026-10-14 实测推翻的初版判据）。

        真实 CNB 正文里，裸 `#N` 抽出来的 7 个有 4 个是别的东西：
        `PR #210`（PR 编号）、`#1403` / `#2034`（**GitHub** 侧卡号）。
        而 CNB 编号连续、镜像卡从 #5 起 ⇒ 这些号在 CNB 侧**确实存在同号卡**
        ⇒ 照收就会把标签挂到一张完全不相干的卡上。
        """
        for text in (
            '本 PR 修了 #106 的分叉判定。',
            '上一张 PR #210 已合入 `dev`。',
            '绝不退化为全库 3 万只（#1403 的形态）。',
            '**#2034 的预存在问题**，与本次无关。',
            '撞 #1403 同族限流。',
        ):
            self.assertEqual(cd.refs_in_text(text), set(), text)

    def test_标题裸号收(self):
        """标题就是「这件事是什么」，`（#167）` 必然是本次在做的卡。"""
        self.assertEqual(cd.refs_in_title('feat(risk): 本轮回撤 + 风险指标每日快照与展示（#167）'), {167})

    def test_refs_of_pull_标题与正文取并集(self):
        pull_ = {
            'title': 'fix(bridge): 分叉判据（CNB #179）',
            'body': 'Closes https://cnb.cool/duoduobei/fundmate/-/issues/106',
        }
        self.assertEqual(cd.refs_of_pull(pull_), {179, 106})

    def test_refs_of_pull_正文里的GitHub侧编号不被收(self):
        """**端到端**：把一个真实 PR 的标题+正文喂进去，确认只抽出该认的那张卡。

        数据取自 CNB PR #238 的真实正文（标题 `（#167）`，正文提到 `#1403` / `PR #210`）。
        """
        pull_ = {
            'title': 'feat(risk): 本轮回撤 + 风险指标每日快照与展示（#167）',
            'body': (
                'CNB #167（基金风险收益指标调研）。上一张 PR #210 已合入 `dev`（纯计算骨架），\n'
                '本 PR 落地用户在 #167 提的三件事。\n'
                '  绝不退化为全库 3 万只**（#1403 的形态）。全库回填走显式 `--targets __full__`。\n'
            ),
        }
        self.assertEqual(cd.refs_of_pull(pull_), {167})

    def test_纯数字不被误当引用(self):
        self.assertEqual(cd.refs_in_title('CNB 卡总数 189 张'), set())

    def test_无引用不产生认领(self):
        claims, unknown = cd.plan_claims([mirror_card(106, 2034)], [pull(1, '无引用')])
        self.assertEqual((claims, unknown), ([], []))


# ---------------------------------------------------------------------------
# 四、幂等键与评论正文
# ---------------------------------------------------------------------------


class TestMarkerAndComment(unittest.TestCase):
    def test_标记能被解析回来(self):
        claim = cd.Claim(cnb_number=106, github_number=2034, prs=[180, 181])
        text = f'blah\n{claim.marker()}\n'
        self.assertEqual(cd.collect_markers([{'body': text}]), {2034})

    def test_收集多个标记(self):
        comments = [
            {'body': '<!-- cnb-claim: github=2034 prs=180 -->'},
            {'body': '与本次无关的评论'},
            {'body': '<!-- cnb-claim: github=2037 prs=181,182 -->'},
        ]
        self.assertEqual(cd.collect_markers(comments), {2034, 2037})

    def test_别的注释不算标记(self):
        self.assertEqual(cd.collect_markers([{'body': '<!-- cnb-backfill: issue=2 comment=3 -->'}]), set())

    def test_标记前缀是冻结契约(self):
        """改了前缀等于把所有已发的认领评论认成「没发过」，下一轮全部重发。"""
        self.assertEqual(cd.MARKER_PREFIX, '<!-- cnb-claim:')

    def test_评论正文带解释与标记(self):
        claim = cd.Claim(cnb_number=106, github_number=2034, prs=[180])
        body = cd.build_claim_comment(claim)
        self.assertIn('CNB 侧已认领', body)
        self.assertIn('去重信号', body)  # 说清标签的含义，免得下一个人去猜
        self.assertIn('只发一次', body)
        self.assertTrue(body.rstrip().endswith('-->'))
        self.assertEqual(cd.collect_markers([{'body': body}]), {2034})

    def test_没有PR编号也不炸(self):
        body = cd.build_claim_comment(cd.Claim(cnb_number=1, github_number=2, prs=[]))
        self.assertIn('未识别到 PR 编号', body)


# ---------------------------------------------------------------------------
# 五、run()：闸门、幂等、不完整数据、缺 token
# ---------------------------------------------------------------------------


class TestRunGates(unittest.TestCase):
    def _run(self, issues, pulls, *, issues_ok=True, pulls_ok=True, dry_run=True, **kw):
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=(issues, issues_ok)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=(pulls, pulls_ok)),
            mock.patch.object(cd, 'get_cnb_issue', side_effect=lambda n: issues[0] if issues else {}),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=dry_run, only_cnb=kw.get('only_cnb'))
        return rc, out.getvalue()

    def test_无认领且数据完整才报已对齐(self):
        rc, out = self._run([mirror_card(106, 2034)], [])
        self.assertEqual(rc, 0)
        self.assertIn('✅ 无 CNB 侧认领（两侧已对齐）', out)

    def test_数据不完整不得报已对齐(self):
        """本仓 #171 / #179 的老病：拿不到输入被当成「没有」。这里必须红。"""
        rc, out = self._run([], [], pulls_ok=False)
        self.assertNotEqual(rc, 0)
        self.assertNotIn('✅ 无 CNB 侧认领', out)
        self.assertIn('数据不完整，本次结论不可信', out)

    def test_dry_run不写任何东西(self):
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=([mirror_card(106, 2034)], True)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=([pull(180, '（CNB #106）')], True)),
            mock.patch.object(cd, 'get_cnb_issue', return_value=mirror_card(106, 2034)),
            mock.patch.object(cd, 'add_github_label') as add,
            mock.patch.object(cd, 'post_github_comment') as post,
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=True, only_cnb=None)
        self.assertEqual(rc, 0)
        add.assert_not_called()
        post.assert_not_called()
        self.assertIn('[dry-run]', out.getvalue())

    def test_apply缺token提前失败(self):
        """没 token 却继续跑 ⇒ 每条都 401 ⇒ 被 `|| true` 收尾吞掉 ⇒ 一直绿、一直没干活。"""
        with mock.patch.dict('os.environ', {'GITHUB_TOKEN': '', 'GH_PAT': ''}, clear=False):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=False, only_cnb=None)
        self.assertEqual(rc, 1)
        self.assertIn('缺少 GITHUB_TOKEN', out.getvalue())

    def test_apply时标签已存在且评论已在时什么都不做(self):
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=([mirror_card(106, 2034)], True)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=([pull(180, '（CNB #106）')], True)),
            mock.patch.object(cd, 'get_cnb_issue', return_value=mirror_card(106, 2034)),
            mock.patch.object(cd, 'github_issue_labels', return_value={cd.CLAIM_LABEL}),
            mock.patch.object(
                cd,
                'list_github_issue_comments',
                return_value=[{'body': '<!-- cnb-claim: github=2034 prs=180 -->'}],
            ),
            mock.patch.object(cd, 'list_github_issues_with_label', return_value=([], True)),
            mock.patch.object(cd, 'add_github_label') as add,
            mock.patch.object(cd, 'post_github_comment') as post,
            mock.patch.dict('os.environ', {'GITHUB_TOKEN': 'x'}, clear=False),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=False, only_cnb=None)
        self.assertEqual(rc, 0)
        add.assert_not_called()
        post.assert_not_called()
        self.assertIn('标签已存在，跳过', out.getvalue())

    def test_标签已存在但缺认领评论时会补上(self):
        """标签与评论是**两条独立的记帐**：标签挂着、评论没发（例如上一轮写评论时挂了），
        那么这一轮该把评论补上——否则卡上有标签、没有任何解释它从哪来。"""
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=([mirror_card(106, 2034)], True)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=([pull(180, '（CNB #106）')], True)),
            mock.patch.object(cd, 'get_cnb_issue', return_value=mirror_card(106, 2034)),
            mock.patch.object(cd, 'github_issue_labels', return_value=set()),
            mock.patch.object(cd, 'ensure_github_label_exists'),
            mock.patch.object(cd, 'add_github_label') as add,
            mock.patch.object(
                cd,
                'list_github_issue_comments',
                return_value=[{'body': '<!-- cnb-claim: github=2034 prs=180 -->'}],
            ),
            mock.patch.object(cd, 'list_github_issues_with_label', return_value=([], True)),
            mock.patch.object(cd, 'post_github_comment') as post,
            mock.patch.dict('os.environ', {'GITHUB_TOKEN': 'x'}, clear=False),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=False, only_cnb=None)
        self.assertEqual(rc, 0)
        add.assert_called_once_with(2034, cd.CLAIM_LABEL)
        post.assert_not_called()

    def test_取详情失败不得静默当没有(self):
        """拿不到卡面 ⇒ 本轮不判该卡，且**不得**报「已对齐」（#171 老病）。"""
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=([mirror_card(106, 2034)], True)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=([pull(180, '（CNB #106）')], True)),
            mock.patch.object(
                cd,
                'get_cnb_issue',
                side_effect=__import__('urllib.error', fromlist=['HTTPError']).HTTPError('u', 500, 'boom', {}, None),
            ),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=True, only_cnb=None)
        self.assertEqual(rc, 1)
        self.assertIn('数据不完整', out.getvalue())


# ---------------------------------------------------------------------------
# 五之二、解除与刷新（标签不能只挂不摘）
# ---------------------------------------------------------------------------


class TestUnclaim(unittest.TestCase):
    def _apply(self, *, claims_issues, pulls, labeled, handler_comments=None):
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=(claims_issues, True)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=(pulls, True)),
            mock.patch.object(
                cd, 'get_cnb_issue', side_effect=lambda n: next(i for i in claims_issues if int(i['number']) == n)
            ),
            mock.patch.object(cd, 'github_issue_labels', return_value={cd.CLAIM_LABEL}),
            mock.patch.object(cd, 'list_github_issue_comments', return_value=handler_comments or []),
            mock.patch.object(cd, 'list_github_issues_with_label', return_value=(labeled, True)),
            mock.patch.object(cd, 'remove_github_label') as rm,
            mock.patch.object(cd, 'post_github_comment') as post,
            mock.patch.dict('os.environ', {'GITHUB_TOKEN': 'x'}, clear=False),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=False, only_cnb=None)
        return rc, out.getvalue(), rm, post

    def test_CNB侧没有PR时摘掉标签(self):
        """挂牌不摘 = 标签变成噪音，下一个人学到的教训是「别信它」——比不挂更坏。"""
        rc, out, rm, _ = self._apply(claims_issues=[mirror_card(106, 2034)], pulls=[], labeled=[2034])
        self.assertEqual(rc, 0)
        rm.assert_called_once_with(2034, cd.CLAIM_LABEL)
        self.assertIn('已摘除', out)

    def test_仍在认领的卡不摘标签(self):
        rc, out, rm, _ = self._apply(
            claims_issues=[mirror_card(106, 2034)],
            pulls=[pull(180, '（CNB #106）')],
            labeled=[2034],
        )
        self.assertEqual(rc, 0)
        rm.assert_not_called()

    def test_数据不完整时不摘任何标签(self):
        """摘错了比留错了贵：宁可多留一个过期标签，也不误摘一张其实有人动的卡。"""
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=([], False)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=([], True)),
            mock.patch.object(cd, 'remove_github_label') as rm,
            mock.patch.dict('os.environ', {'GITHUB_TOKEN': 'x'}, clear=False),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=False, only_cnb=None)
        rm.assert_not_called()
        self.assertEqual(rc, 1)
        self.assertIn('不摘除', out.getvalue())

    def test_有认领但数据不完整时也不摘标签(self):
        """`complete` 这个闸门在「有认领」与「无认领」两条路上都得成立。

        前一条用例（无认领 + 不完整）走的是 `not claims` 那条路，压根到不了摘除代码；
        若只在那一处断言，把 `if complete or dry_run` 换成 `if True` 仍然绿
        —— 探针 S10 抓出的正是这个盲区。故补这条**有认领**的用例。
        """
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=([mirror_card(106, 2034)], True)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=([], False)),  # PR 拉取失败
            mock.patch.object(cd, 'github_issue_labels', return_value={cd.CLAIM_LABEL}),
            mock.patch.object(cd, 'list_github_issue_comments', return_value=[]),
            mock.patch.object(cd, 'list_github_issues_with_label', return_value=([2034], True)),
            mock.patch.object(cd, 'remove_github_label') as rm,
            mock.patch.object(cd, 'post_github_comment'),
            mock.patch.dict('os.environ', {'GITHUB_TOKEN': 'x'}, clear=False),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=False, only_cnb=None)
        rm.assert_not_called()
        self.assertEqual(rc, 1)
        self.assertIn('不摘除', out.getvalue())

    def test_拿不到带标签清单则不动手(self):
        with (
            mock.patch.object(cd, 'list_cnb_issues', return_value=([mirror_card(106, 2034)], True)),
            mock.patch.object(cd, 'list_cnb_pulls', return_value=([], True)),
            mock.patch.object(cd, 'list_github_issues_with_label', return_value=([], False)),
            mock.patch.object(cd, 'remove_github_label') as rm,
            mock.patch.dict('os.environ', {'GITHUB_TOKEN': 'x'}, clear=False),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = cd.run(dry_run=False, only_cnb=None)
        rm.assert_not_called()
        self.assertEqual(rc, 1)
        self.assertIn('拿不到就不动手', out.getvalue())

    def test_新增PR时补一条说明评论(self):
        """标签只能说「有人在动」，说不出「哪些 PR 在动」——而第 2 条线加入时正是最该被看见的时刻。"""
        rc, out, _, post = self._apply(
            claims_issues=[mirror_card(106, 2034)],
            pulls=[pull(180, '（CNB #106）'), pull(181, '（CNB #106）')],
            labeled=[2034],
            handler_comments=[{'body': '<!-- cnb-claim: github=2034 prs=180 -->'}],
        )
        self.assertEqual(rc, 0)
        post.assert_called_once()
        self.assertIn('补一条说明评论', out)

    def test_PR集合没变化则不补评论(self):
        rc, out, _, post = self._apply(
            claims_issues=[mirror_card(106, 2034)],
            pulls=[pull(180, '（CNB #106）')],
            labeled=[2034],
            handler_comments=[{'body': '<!-- cnb-claim: github=2034 prs=180 -->'}],
        )
        post.assert_not_called()

    def test_collect_marked_prs(self):
        comments = [
            {'body': '<!-- cnb-claim: github=2034 prs=180,181 -->'},
            {'body': '<!-- cnb-claim: github=2037 prs=182 -->'},
        ]
        self.assertEqual(cd.collect_marked_prs(comments), {180, 181, 182})

    def test_collect_marked_prs_空(self):
        self.assertEqual(cd.collect_marked_prs([{'body': '无关'}]), set())


# ---------------------------------------------------------------------------
# 六、只读纪律
# ---------------------------------------------------------------------------


class TestScriptContract(unittest.TestCase):
    def test_CNB侧只读(self):
        """CNB 侧只允许 GET：把 `cnb_api` 打成必抓，跑一轮 `--report`，确认没有任何写调用。

        用**行为**而不是**字符串匹配**来判——字符串版先前就在这里假失败过一次
        （`cnb_api(` 出现在自己的 docstring / 定义里）。判据要问「有没有真的发起写请求」。
        """
        calls: list[str] = []

        def spy(path: str) -> object:
            calls.append(path)
            return []

        with mock.patch.object(cd, 'cnb_api', side_effect=spy):
            out = io.StringIO()
            with redirect_stdout(out):
                cd.run(dry_run=True, only_cnb=None)
        # 只读路径只会走「列表」两个端点；出现 `/comments`、`/label` 一类即越界。
        self.assertTrue(calls)
        for path in calls:
            self.assertRegex(path, r'-/(issues|pulls)')

    def test_不导入HTTP客户端以外的重依赖(self):
        """纯标准库：每日作业不该被某个三方包的破坏性升级带崩（与其它 bridge 脚本同口径）。"""
        src = (ROOT / 'scripts' / 'bridge' / 'claim_detect.py').read_text(encoding='utf-8')
        for forbidden in ('import requests', 'import github', 'import httpx'):
            self.assertNotIn(forbidden, src)


if __name__ == '__main__':
    unittest.main()
