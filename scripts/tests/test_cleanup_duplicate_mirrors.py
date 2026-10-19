"""重复镜像卡清理的回归网（源 CNB #450）。

## WHY 有这份文件

`cleanup_duplicate_mirrors.py` 是 `check_duplicate_mirrors.py` 的配套：前者只读发现，
后者**真的会关卡**（`--apply`）。关心它是因为两条判据错了后果都不可逆：

1. **保留判据**——有评论的优先，其余留编号最小。这不是审美，是「评论不可再生」；
   判反了就会**关掉唯一带着讨论的正本**。CNB #167（38 条评论、原卡）正是这个坑的
   真实样本：它是 `closed`，而 9 张重复卡全是空的 `open`——**按状态判会保留错的**。
2. **失败态**——读不到输入时**拒绝执行**，不得因为「读不到」就退化成一个看起来
   正常的结论（#171 的纪律）。`--apply` 尤其：宁可不动手，不可关错。
3. **零丢评论是硬约束**——清单里「被关闭卡上的评论总数」必须为 0，否则停下核实。
4. **动作只能是关闭**——CNB OpenAPI 不支持删除 issue（`DELETE` 对真实卡返 404），
   故「清除重复」的等价动作是 `PATCH state=closed`。

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

import cleanup_duplicate_mirrors as cleanup  # noqa: E402


def _detail(number: int, comments: int = 0, state: str = 'open', human_comments: int | None = None) -> dict:
    """`comments` 是**总**评论数（含机器人），`human_comments` 只在显式给定时才记。"""
    d = {'number': str(number), 'comment_count': comments, 'state': state}
    if human_comments is not None:
        d['human_comment_count'] = human_comments
    return d


def _comment(author: str = 'imoyao', is_npc: bool = False) -> dict:
    return {'author': {'username': author, 'is_npc': is_npc}, 'body': 'x'}


class PickKeeperTest(unittest.TestCase):
    """保留判据：有评论优先，其余编号最小。"""

    def test_全无评论_留编号最小(self):
        keeper, removed = cleanup.pick_keeper([_detail(183), _detail(164), _detail(211)])
        self.assertEqual(keeper, 164)
        self.assertEqual(removed, [183, 211])

    def test_有评论的优先_即使编号更大(self):
        """评论是不可再生的信息 —— 留带评论的那张，哪怕它编号更大。"""
        keeper, removed = cleanup.pick_keeper([_detail(186), _detail(214, human_comments=38), _detail(243)])
        self.assertEqual(keeper, 214, '有评论的卡必须被保留（关了就没讨论可读了）')
        self.assertEqual(removed, [186, 243])

    def test_多张都有评论_取评论多的(self):
        keeper, _removed = cleanup.pick_keeper([_detail(1, human_comments=2), _detail(2, human_comments=9)])
        self.assertEqual(keeper, 2)

    def test_变异探针_拿掉评论维度后会保留错卡(self):
        """**回退验证**：把 pick_keeper 换成「只按编号最小」，必须保留错卡。

        这条不是「再跑一遍绿」，而是确认这条判据**真的会红**——
        若把评论维度摘掉后结论不变，说明这条用例根本没在测「评论优先」。

        注意本探针特意让**有评论的卡编号更大**（214 带 38 条评论 vs 186 空），
        否则「编号最小」与「有评论」会指向同一张卡，探针咬不住。
        """
        cards = [_detail(186), _detail(214, human_comments=38), _detail(243)]

        # 正确判据：留带评论的 214
        keeper, _ = cleanup.pick_keeper(cards)
        self.assertEqual(keeper, 214)

        # 回退到「只按编号最小」——它必须给出**不同**的结论（186）
        naive = min(cards, key=lambda d: int(d['number']))
        self.assertEqual(int(naive['number']), 186)
        self.assertNotEqual(keeper, int(naive['number']), '探针失效：摘掉评论维度后结论没变')

    def test_变异探针_按状态open优先会保留错卡(self):
        """按 `state=open` 优先是**错的**判据（#167 是 closed 却是正本）。"""
        cards = [_detail(186, state='open'), _detail(167, human_comments=38, state='closed')]
        keeper, _ = cleanup.pick_keeper(cards)
        self.assertEqual(keeper, 167, '不得因原卡是 closed 就改留空的 open 重复卡')


class HumanCommentCountTest(unittest.TestCase):
    """「机器人评论不算讨论」—— 2026-10-19 分诊评论把判据 1 抹平，误关了 CNB #196 / #552。

    真实形态：同一 GitHub 编号下十几张重复卡，**每张**都被分诊作业贴了同一条
    「分诊结论」评论 ⇒ 总评论数一律为 1 ⇒ 判据 1「有评论优先」对整组同时成立 ⇒
    退化成「编号最小」，而留哪张取决于分诊贴到谁头上（实测 #196 被关、#551 被留）。
    """

    def test_机器人评论不计入(self):
        comments = [_comment('CodeBuddy', is_npc=True), _comment('github-actions'), _comment('release-bot')]
        self.assertEqual(cleanup.human_comment_count(comments), 0)

    def test_人类评论计入(self):
        self.assertEqual(cleanup.human_comment_count([_comment('imoyao'), _comment('CodeBuddy', True)]), 1)

    def test_空列表为0(self):
        self.assertEqual(cleanup.human_comment_count([]), 0)

    def test_分诊评论不改变保留判据(self):
        """整组都被贴了分诊评论时，仍然按「编号最小」选 —— 而不是按谁被贴过。"""
        cards = [
            _detail(164, comments=1, human_comments=0),
            _detail(464, comments=1, human_comments=0),
            _detail(542, comments=1, human_comments=0),
        ]
        keeper, removed = cleanup.pick_keeper(cards)
        self.assertEqual(keeper, 164)
        self.assertEqual(removed, [464, 542])

    def test_人类评论仍然压过编号(self):
        """收紧后不得把「有真讨论」这条判据一起丢掉。"""
        cards = [_detail(186, comments=1, human_comments=0), _detail(214, comments=1, human_comments=1)]
        keeper, _ = cleanup.pick_keeper(cards)
        self.assertEqual(keeper, 214)

    def test_变异探针_用总评论数会选错卡(self):
        """回退到「按总评论数」必须给出不同结论 —— 否则这条判据根本没在测。

        真实样本取自 CNB #196 那组：196 是编号最小、但只有分诊评论；
        551 编号更大、也只有分诊评论。用总评论数时两者打平（都 1），
        谁被分诊先贴谁就被留下 —— 结论与「留最早创建」相反。
        """
        cards = [
            _detail(196, comments=1, human_comments=0),
            _detail(551, comments=2, human_comments=0),  # 551 多了 1 条分诊重跑评论
        ]
        self.assertEqual(cleanup.pick_keeper(cards)[0], 196, '正确判据：两个都没人讨论 ⇒ 留编号最小')

        naive = sorted(cards, key=lambda d: (-int(d['comment_count']), int(d['number'])))[0]
        self.assertEqual(int(naive['number']), 551)
        self.assertNotEqual(cleanup.pick_keeper(cards)[0], int(naive['number']), '探针失效：用总数结论没变')

    def test_评论读不到时记失败_不猜成没有讨论(self):
        """#171 的纪律：读不到 ⇒ 结论不可信，不得退化成「无人讨论」然后照样关卡。"""
        cards = [
            {'number': '196', 'body': '> GitHub 编号：`#2139`', 'labels': [{'name': 'GitHub 同步'}], 'title': 'a'},
            {'number': '551', 'body': '> GitHub 编号：`#2139`', 'labels': [{'name': 'GitHub 同步'}], 'title': 'b'},
        ]
        with (
            mock.patch.object(cleanup, 'collect', return_value=(cards, [])),
            mock.patch.object(cleanup, 'get_cnb_issue', side_effect=lambda n: _detail(n, comments=1)),
            mock.patch.object(cleanup, 'fetch_human_comment_count', side_effect=RuntimeError('403')),
            mock.patch.object(cleanup, 'close_issue') as fake_close,
        ):
            code = cleanup.main(['--apply'])

        self.assertEqual(code, cleanup.EXIT_UNKNOWN)
        fake_close.assert_not_called()


class PlanTest(unittest.TestCase):
    """`plan()` 只对重复编号产出条目，且账要算清。"""

    def test_只处理重复编号(self):
        grouped = {783: [5, 6], 900: [7]}
        details = {5: _detail(5), 6: _detail(6), 7: _detail(7)}
        plans = cleanup.plan(grouped, details)
        self.assertEqual(set(plans), {783})
        self.assertEqual(plans[783]['keep'], 5)
        self.assertEqual(plans[783]['remove'], [6])

    def test_统计被关闭卡上的评论数(self):
        grouped = {783: [5, 6]}
        details = {5: _detail(5, human_comments=3), 6: _detail(6, human_comments=4)}
        plans = cleanup.plan(grouped, details)
        # 有评论优先 ⇒ 留评论多的 6，关闭 5（带 3 条评论）—— 账必须体现出来
        self.assertEqual(plans[783]['keep'], 6)
        self.assertEqual(plans[783]['removed_comments'], 3)


class RenderTest(unittest.TestCase):
    """报告语义与退出码。"""

    def _plans(self):
        return {783: {'keep': 5, 'remove': [6], 'keep_comments': 0, 'removed_comments': 0}}

    def test_dry_run_有可清理项时退出码为1(self):
        text, code = cleanup.render(self._plans(), [], applied=False)
        self.assertEqual(code, cleanup.EXIT_ACTIONED)
        self.assertIn('dry-run', text)

    def test_读取失败时退出码为2且声明结论不可信(self):
        text, code = cleanup.render(self._plans(), failed=[9, 10], applied=False)
        self.assertEqual(code, cleanup.EXIT_UNKNOWN)
        self.assertIn('结论不可信', text)
        self.assertIn('不得', text)

    def test_无重复时退出码为0(self):
        text, code = cleanup.render({}, [], applied=False)
        self.assertEqual(code, cleanup.EXIT_OK)
        self.assertIn('无重复卡', text)

    def test_零丢评论是显式的(self):
        text, _ = cleanup.render(self._plans(), [], applied=False)
        self.assertIn('被关闭卡上的人类评论总数：0 条', text)

    def test_动作在报告里写明是关闭(self):
        text, _ = cleanup.render(self._plans(), [], applied=False)
        self.assertIn('关闭', text)
        self.assertNotIn('删除（DELETE）', text)


class KeeperStateTest(unittest.TestCase):
    """保留卡状态必须跟 GitHub 对齐 —— 否则这组会一张 open 都不剩。

    真实场景（2026-10-14 实测）：#167 带 38 条评论但是 `closed`（人工拆卡转移），
    GitHub `2118` 却还 `open`。判据 1 选它当保留卡 → 再把 9 张 open 的关掉 →
    这组**一张 open 都没有**，镜像从看板上消失。故须补一条：GitHub 仍 open ⇒ 重开保留卡。
    """

    def _plans(self):
        return {2118: {'keep': 167, 'remove': [186], 'keep_comments': 38, 'removed_comments': 0}}

    def test_保留卡是closed且GitHub仍open_要重开(self):
        details = {167: _detail(167, human_comments=38, state='closed')}
        fixes = cleanup.keeper_state_fixes(self._plans(), details, github_open={2118})
        self.assertEqual(fixes, {2118: 167})

    def test_保留卡已open_不动(self):
        details = {167: _detail(167, comments=38, state='open')}
        fixes = cleanup.keeper_state_fixes(self._plans(), details, github_open={2118})
        self.assertEqual(fixes, {})

    def test_GitHub已关_不动(self):
        """GitHub 关了的话，保留卡是 closed 反而是对的（那是状态回流的正常形态）。"""
        details = {167: _detail(167, human_comments=38, state='closed')}
        fixes = cleanup.keeper_state_fixes(self._plans(), details, github_open=set())
        self.assertEqual(fixes, {})

    def test_变异探针_不检查GitHub状态会漏修(self):
        """把「GitHub 是否 open」这个维度摘掉（恒当真），必须给出不同结论。

        这里用「GitHub 已关」那组来证伪：正确判据不动手，摘掉维度会误动手。
        """
        details = {167: _detail(167, human_comments=38, state='closed')}
        # 正确：GitHub 关了 ⇒ 不重开
        self.assertEqual(cleanup.keeper_state_fixes(self._plans(), details, github_open=set()), {})
        # 错误（摘掉维度，恒当真）：会去重开一张 GitHub 已关的卡
        naive = cleanup.keeper_state_fixes(self._plans(), details, github_open={2118})
        self.assertEqual(naive, {2118: 167})
        self.assertNotEqual(naive, {}, '探针失效：摘掉 GitHub 状态后结论没变')

    def test_reopen_issue_走_PATCH_open(self):
        with mock.patch.object(cleanup, 'cnb_api') as fake:
            cleanup.reopen_issue(167)
        _args, kwargs = fake.call_args
        self.assertEqual(kwargs['method'], 'PATCH')
        self.assertEqual(kwargs['payload']['state'], 'open')


class ActionTest(unittest.TestCase):
    """动作面：只有关闭，没有删除。"""

    def test_模块里不存在删除动作(self):
        """CNB OpenAPI 不支持删除 issue —— 脚本不得有删除路径。

        判据不是「文档里写了」，而是**模块里没有能删卡的函数**。
        """
        public = [n for n in dir(cleanup) if not n.startswith('_')]
        self.assertFalse([n for n in public if 'delete' in n.lower()], '脚本不得有删除动作')

    def test_close_issue_走_PATCH_closed(self):
        with mock.patch.object(cleanup, 'cnb_api') as fake:
            cleanup.close_issue(42)
        _args, kwargs = fake.call_args
        self.assertEqual(kwargs['method'], 'PATCH')
        self.assertEqual(kwargs['payload']['state'], 'closed')


class ApplyTest(unittest.TestCase):
    """`--apply` 的两种行为：拒绝动手 / 逐张关闭。"""

    def test_有读取失败时_apply_拒绝动手(self):
        with (
            mock.patch.object(cleanup, 'collect', return_value=([], [999])),
            mock.patch.object(cleanup, 'get_cnb_issue', side_effect=RuntimeError('boom')),
            mock.patch.object(cleanup, 'close_issue') as fake_close,
        ):
            code = cleanup.main(['--apply'])

        self.assertEqual(code, cleanup.EXIT_UNKNOWN)
        fake_close.assert_not_called()

    def test_apply_逐张关闭_且只关多余卡(self):
        cards = [
            {'number': '5', 'body': '> GitHub 编号：`#783`', 'labels': [{'name': 'GitHub 同步'}], 'title': 'a'},
            {'number': '6', 'body': '> GitHub 编号：`#783`', 'labels': [{'name': 'GitHub 同步'}], 'title': 'b'},
        ]
        with (
            mock.patch.object(cleanup, 'collect', return_value=(cards, [])),
            mock.patch.object(cleanup, 'get_cnb_issue', side_effect=lambda n: _detail(n)),
            mock.patch.object(cleanup, 'close_issue') as fake_close,
        ):
            code = cleanup.main(['--apply'])

        self.assertEqual(code, cleanup.EXIT_OK)
        fake_close.assert_called_once_with(6)


if __name__ == '__main__':
    unittest.main()
