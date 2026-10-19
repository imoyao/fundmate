"""重复镜像建卡的回归网（源 CNB #450）。

## WHY 有这份文件

#450 的故障是两个**独立**的失败叠在一起，缺一个都不会造成 224 张重复卡：

1. **根因**：`harvest_existing()` 拿状态文件缓存当前置短路 —— 缓存里非空就直接返回，
   于是状态文件没记的镜像卡（CNB 侧真实存在）在判定时"不存在"，每轮重建一遍。
   它读起来像合理的缓存优化，**靠人 review 拦不住**（它就是漏过 review 的那一版）。
2. **无声**：全程零信号。建卡成功、日志全绿，而没有一条作业在问
   "这张卡是不是已经建过了"。三天攒出 224 张。

故这里有**两组**用例，对应两件事：

- `HarvestMustScanTest`：钉住"扫描 CNB 侧是必经之路"，并把**修复前的原始代码**
  喂给守卫，确认它真的转红（变异探针）——守卫自己崩过两次的教训见 AGENTS.md
  "判据必须在真实代码上跑，且要有一次回退验证"；
- `DuplicateReportTest`：钉住重复检测的**分类语义**，尤其是
  "读不到 ≠ 不重复"（#171 的失败态纪律：拿不到输入不得退化成看起来正常的结论）。

## 怎么跑

    python -m unittest discover -s scripts/tests -p "test_*.py"

零新依赖（只用标准库）；网络层全部打桩，纯离线。
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'bridge'))

import check_duplicate_mirrors as dup  # noqa: E402
import github_cnb_issues  # noqa: E402,F401  （HarvestUnionTest 用 sys.modules 拿它打桩）
import harvest_scan_guard as guard  # noqa: E402

REPO_FILE = ROOT / 'scripts' / 'bridge' / 'github_cnb_issues.py'

# 修复「缓存短路」那个提交的**父提交**（不可变 SHA）：探针必须拿它当「修复前」的样本。
# 不能用 `origin/dev` —— 修复合入后它就变成修复后的代码，探针会随分支推进自行失效。
PREFIX_FIX_COMMIT = 'dbac7233'


def _card(number: int, gh: int | None, mirror: bool = True) -> dict:
    body = f'# 正文\n\n> - GitHub 编号：`#{gh}`　状态：`open`\n' if gh is not None else '# 无键正文\n'
    labels = [{'name': 'GitHub 同步'}] if mirror else []
    return {'number': str(number), 'body': body, 'labels': labels, 'title': f'card {number}'}


class HarvestMustScanTest(unittest.TestCase):
    """`harvest_existing()` 必须真扫 CNB 侧，不得用缓存短路。"""

    def test_当前代码通过守卫(self):
        problems = guard.check(REPO_FILE.read_text(encoding='utf-8'))
        self.assertEqual(problems, [], '\n'.join(problems))

    def test_变异探针_修复前的短路形态必须被抓到(self):
        """把**修复前**的真实版本喂给守卫 —— 它必须报红。

        这是本组最重要的一条：不加它，"守卫绿"只能证明"代码里没有它不认识的东西"，
        证明不了"它能认出那个 bug"。判据自己崩过的例子，AGENTS.md 里已记过两次。

        ⚠️ **必须钉在不可变的 commit SHA 上，不能读 `origin/dev`**（2026-10-14 实测踩到）：
        该守卫的修复 PR #451 一旦合入 `dev`，`origin/dev` 里就是**修复后**的代码，
        这条探针便永远取不到「修复前」的版本而**恒红/恒绿**——把探针钉在可变的 ref 上，
        等于让它随分支推进自己失效。故改用修复提交的父提交 `dbac7233`（不可变）。
        """
        completed = subprocess.run(
            ['git', 'show', f'{PREFIX_FIX_COMMIT}:scripts/bridge/github_cnb_issues.py'],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding='utf-8',
        )
        before = completed.stdout
        # 浅克隆（CI 默认 checkout depth=1）取不到历史 commit ⇒ 拿不到"修复前"样本。
        # 这里优雅跳过而非硬断言失败：守卫的修复前探针只在「有完整历史」时才有意义，
        # 缺样本时若硬红会变成"环境依赖型失败"（AGENTS.md 的判据反例）。
        # 本地全历史克隆下仍会真实跑这条探针，守卫价值不丢。
        if not before.strip():
            self.skipTest(
                f'取不到 {PREFIX_FIX_COMMIT} 版本（浅克隆/无完整历史），跳过修复前探针'
            )
        problems = guard.check(before)
        self.assertTrue(problems, '修复前的短路形态未被守卫抓到 —— 守卫是假的')
        self.assertTrue(any('list_cnb_issues' in p and 'return' in p for p in problems), problems)

    def test_变异探针_合成短路写法同样被抓到(self):
        """不拟合具体写法：`if len(known) > 10: return known` 这种也要拦。"""
        src = (
            'def harvest_existing(state):\n'
            '    mirrored = state.setdefault("mirrored", {})\n'
            '    known = {int(k) for k in mirrored if str(k).isdigit()}\n'
            '    if len(known) > 10:\n'
            '        return known\n'
            '    for c in list_cnb_issues("open"):\n'
            '        pass\n'
            '    return known\n'
        )
        problems = guard.check(src)
        self.assertTrue(problems, '>= 阈值短路未被抓到')
        self.assertTrue(any('return' in p for p in problems), problems)

    def test_变异探针_完全不扫描也要被抓到(self):
        src = 'def harvest_existing(state):\n    return {int(k) for k in state["mirrored"] if str(k).isdigit()}\n'
        problems = guard.check(src)
        self.assertTrue(problems, '完全不扫描未被抓到')
        self.assertTrue(any('没有调用' in p for p in problems), problems)

    def test_真扫形态放行(self):
        src = (
            'def harvest_existing(state):\n'
            '    known = {int(k) for k in state["mirrored"] if str(k).isdigit()}\n'
            '    seen = set()\n'
            '    for c in list_cnb_issues("open"):\n'
            '        seen.add(1)\n'
            '    return known | seen\n'
        )
        self.assertEqual(guard.check(src), [])

    def test_函数改名不静默放过(self):
        """函数找不到时必须报红 —— 否则"改名即免检"。"""
        problems = guard.check('def something_else(state):\n    return {}\n')
        self.assertTrue(problems)
        self.assertTrue(any('找不到函数' in p for p in problems), problems)


class HarvestUnionTest(unittest.TestCase):
    """修好之后的**行为**契约：缓存与 CNB 实况取并集。"""

    def _run(self, cached: dict, cards: list[dict], details: dict[int, dict]):
        state = {'last_sync_at': None, 'mirrored': cached}
        mod = sys.modules['github_cnb_issues']
        with (
            mock.patch.object(mod, 'list_cnb_issues', side_effect=[cards, []]),
            mock.patch.object(mod, 'get_cnb_issue', side_effect=lambda n: details[n]),
        ):
            return mod.harvest_existing(state)

    def test_缓存不全时仍能看见_CNB_侧已有的卡(self):
        """这正是 #450：缓存只有 1 条，CNB 侧却有 3 张卡 ⇒ 三张都必须算已镜像。"""
        cards = [_card(5, 783), _card(6, 900), _card(7, 901)]
        details = {5: _card(5, 783), 6: _card(6, 900), 7: _card(7, 901)}
        got = self._run({'783': {'cnb': 5, 'title': 'x'}}, cards, details)
        self.assertEqual(got, {783, 900, 901})

    def test_CNB_侧读不到时保留缓存里的条目(self):
        """读不到的卡不能被判成"没镜像过"——否则下一轮就是重复建卡。

        口径：**宁可漏建，不可重复建**（漏建下一轮补得上，重复建不可逆）。
        """
        cards = [_card(5, 783)]
        details = {5: _card(5, 783)}
        with (
            mock.patch.object(sys.modules['github_cnb_issues'], 'list_cnb_issues', side_effect=[[], []]),
        ):
            state = {'last_sync_at': None, 'mirrored': {'783': {'cnb': 5, 'title': 'x'}}}
            got = sys.modules['github_cnb_issues'].harvest_existing(state)
        self.assertEqual(got, {783})

    def test_扫描结果回写缓存(self):
        """扫描发现的映射要落进 state，否则状态文件永远停在首轮那 107 条。"""
        cards = [_card(5, 783), _card(6, 900)]
        details = {5: _card(5, 783), 6: _card(6, 900)}
        with (
            mock.patch.object(sys.modules['github_cnb_issues'], 'list_cnb_issues', side_effect=[cards, []]),
            mock.patch.object(sys.modules['github_cnb_issues'], 'get_cnb_issue', side_effect=lambda n: details[n]),
        ):
            state = {'last_sync_at': None, 'mirrored': {}}
            sys.modules['github_cnb_issues'].harvest_existing(state)
        # 缓存里现在还有一维 `_recently_closed`（源 CNB #6）：它是「最近被关过的幂等键」，
        # 与「已镜像」是两件事，故只断言编号那部分。
        self.assertEqual({k for k in state['mirrored'] if k.isdigit()}, {'783', '900'})


class EveryStateCountsTest(unittest.TestCase):
    """「建过」与「开着」是两件事（源 CNB #6，2026-10-19）。

    只拿 `open` 判重时，**关一张卡 = 下一轮再建一张**：清理动作把幂等键匿名掉，
    建卡作业原地重建一张空卡，分诊再给它贴评论，再被清理……用户在同一个 bug 上
    看到 37 条一模一样的评论。故这里钉住两条：

    1. `closed` 的镜像卡同样证明「建过」；
    2. 但**最近被关过**的键不重建（否则人手动关掉的卡永远建不回来，
       而敞开重建又会让清理变成重建开关 —— 中间那条线是时间窗）。
    """

    def _detail(self, number: int, gh: int, state: str, closed_at: str = '') -> dict:
        card = _card(number, gh)
        card['state'] = state
        card['closed_at'] = closed_at
        return card

    def test_closed_的镜像卡也算建过(self):
        mod = sys.modules['github_cnb_issues']
        details = {
            5: self._detail(5, 783, 'closed', '2026-10-19T06:44:36Z'),
            6: self._detail(6, 900, 'open'),
        }
        state = {'mirrored': {}}
        with (
            mock.patch.object(mod, 'list_cnb_issues', side_effect=[[details[6]], [details[5]]]),
            mock.patch.object(mod, 'get_cnb_issue', side_effect=lambda n: details[n]),
        ):
            got = mod.harvest_existing(state)
        self.assertEqual(got, {783, 900}, '已关闭的镜像卡同样是「建过」——否则关一张就重建一张')

    def test_变异探针_只认open会漏掉已关闭的卡(self):
        """**回退验证**：把 `closed` 从判重里摘掉，结论必须不同。"""
        mod = sys.modules['github_cnb_issues']
        details = {5: self._detail(5, 783, 'closed', '2026-10-19T06:44:36Z')}
        state = {'mirrored': {}}
        with (
            mock.patch.object(mod, 'list_cnb_issues', side_effect=[[], [details[5]]]),
            mock.patch.object(mod, 'get_cnb_issue', side_effect=lambda n: details[n]),
        ):
            got = mod.harvest_existing(state)
        open_only = {
            int(k)
            for k, v in state['mirrored'].items()
            if k.isdigit() and (v or {}).get('cnb') is not None and str(v.get('cnb')) in {'6'}
        }
        self.assertEqual(got, {783})
        self.assertEqual(open_only, set(), '旧判据（只问 open）会把这个键当成「没建过」')

    def test_最近被关的键进_重新关窗口_且过期后自动放出(self):
        mod = sys.modules['github_cnb_issues']
        from datetime import UTC, datetime

        now = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
        mirrored: dict = {}
        fresh = mod._remember_recently_closed(
            mirrored,
            {783: [self._detail(5, 783, 'closed', '2026-10-19T06:44:36Z')]},
            now=now,
        )
        self.assertEqual(fresh, {783: '2026-10-19T06:44:36Z'})
        self.assertEqual(mod.recently_closed({'mirrored': mirrored}, now=now), {783: '2026-10-19T06:44:36Z'})

        # 窗口外：**自动放出**，不需要谁去改配置（否则就是永久死锁）
        later = now.replace(year=2027)
        self.assertEqual(mod.recently_closed({'mirrored': mirrored}, now=later), {})

    def test_关闭时间解析不了就不记_不猜时间(self):
        mod = sys.modules['github_cnb_issues']
        mirrored: dict = {}
        fresh = mod._remember_recently_closed(mirrored, {783: [self._detail(5, 783, 'closed', '')]})
        self.assertEqual(fresh, {}, '拿不到关闭时间就不该编一个出来（#171：拿不到 ≠ 没有）')

    def test_run_跳过已建过的卡_不再重建(self):
        """端到端：`run()` 不得再对「已建过（含已关闭）」的 GitHub 卡建第二张。"""
        import io
        from contextlib import redirect_stdout

        import github_cnb_issues as mirror

        out = io.StringIO()
        state = {'mirrored': {'783': {'cnb': 5, 'title': 'x'}}}
        gh = [{'number': 783, 'title': 't', 'labels': [], 'body': 'b'}]
        with (
            mock.patch.object(mirror, 'load_state', return_value=state),
            mock.patch.object(mirror, 'harvest_existing', return_value={783}),
            mock.patch.object(mirror, 'fetch_github_open_issues', return_value=(gh, True)),
            mock.patch.object(mirror, 'create_cnb_issue') as create,
            mock.patch.object(mirror, 'save_state'),
            redirect_stdout(out),
        ):
            rc = mirror.run(dry_run=False, limit=None)
        create.assert_not_called()
        self.assertEqual(rc, 0)
        self.assertIn('已建过', out.getvalue(), '跳过要有信号，否则读日志的人以为「都没事」')


class DuplicateReportTest(unittest.TestCase):
    """重复检测的分类语义与退出码。"""

    def test_同一编号多张卡_判为重复(self):
        cards = [_card(5, 783), _card(6, 783)]
        grouped, unkeyed = dup.group_by_github_number(cards)
        self.assertEqual(grouped[783], [5, 6])
        self.assertEqual(unkeyed, [])

    def test_每张卡只出现一次_不报重复(self):
        cards = [_card(5, 783), _card(6, 900)]
        grouped, unkeyed = dup.group_by_github_number(cards)
        _text, code = dup.render(grouped, None, unkeyed, [])
        self.assertEqual(code, dup.EXIT_OK)

    def test_有重复时退出码为1(self):
        cards = [_card(5, 783), _card(6, 783)]
        grouped, unkeyed = dup.group_by_github_number(cards)
        text, code = dup.render(grouped, None, unkeyed, [])
        self.assertEqual(code, dup.EXIT_DUPES)
        # 「多出来的」是 1 张，不是 2 张 —— 口径要说清，否则清理时会多关一张
        self.assertIn('多出来的 open 卡：1 张', text)

    def test_抠不到键的卡单独记账_不混进重复判定(self):
        """无键卡既不能算重复、也不能算不重复 —— 必须能被看见（#450 里有一张）。"""
        cards = [_card(5, 783), _card(6, None)]
        grouped, unkeyed = dup.group_by_github_number(cards)
        self.assertEqual(len(grouped[783]), 1)
        self.assertEqual(unkeyed, [6])
        text, _code = dup.render(grouped, None, unkeyed, [])
        self.assertIn('抠不到幂等键的镜像卡：1 张', text)

    def test_读取失败时退出码为2且明确声明结论不可信(self):
        """「拿不到输入」不得退化成「无重复」（#171 的失败态纪律）。"""
        grouped = {783: [5], 900: [6]}
        text, code = dup.render(grouped, None, [], failed=[7, 8])
        self.assertEqual(code, dup.EXIT_UNKNOWN, '读不到卡时不得以「无重复」结案')
        self.assertIn('结论不可信', text)
        self.assertIn('下限', text)

    def test_非镜像卡不参与(self):
        cards = [_card(5, 783, mirror=False), _card(6, 783, mirror=False)]
        mirror_cards = [c for c in cards if dup._is_mirror(c)]
        self.assertEqual(mirror_cards, [])

    def test_有重复且有读取失败_优先报不可信(self):
        """两个坏消息同时存在时，报"结论不可信"（更保守的那个）。"""
        grouped = {783: [5, 6]}
        _text, code = dup.render(grouped, None, [], failed=[9])
        self.assertEqual(code, dup.EXIT_UNKNOWN)


class OpenVsClosedSemanticsTest(unittest.TestCase):
    """「活跃重复」只看 open；已处置残留不报红（清理 224 张后补的口径）。

    用「总数 >1」当判据，会把**已清理干净的卡**永远报成重复 ——
    清理当天它就从「224 张」变成「还是 224 张」，红灯从此失去意义（假红也是病）。
    """

    @staticmethod
    def _stateful(number: int, gh: int | None, state: str) -> dict:
        card = _card(number, gh)
        card['state'] = state
        return card

    def test_open_多于一张才算活跃重复(self):
        cards = [self._stateful(5, 783, 'open'), self._stateful(6, 783, 'open')]
        opened, closed, unkeyed = dup.split_by_state(cards)
        self.assertEqual(opened[783], [5, 6])
        self.assertEqual(closed, {})
        _text, code = dup.render(opened, closed, unkeyed, [])
        self.assertEqual(code, dup.EXIT_DUPES)

    def test_只剩一张open_其余closed_不报红(self):
        """这正是清理完成后的形态：同一编号只剩一张活的，其余是历史留痕。"""
        cards = [self._stateful(5, 783, 'open'), self._stateful(6, 783, 'closed')]
        opened, closed, unkeyed = dup.split_by_state(cards)
        self.assertEqual(opened[783], [5])
        self.assertEqual(closed[783], [6])
        text, code = dup.render(opened, closed, unkeyed, [])
        self.assertEqual(code, dup.EXIT_OK, '已清理干净的卡不得继续报红')
        # 措辞在 2026-10-19 改过（源 CNB #6）：这个桶里现在**分两种**（留痕 / 掉头），
        # 故不再断言旧标题「已处置残留（只剩 1 张 open，其余 closed）」—— 断言的意图
        # （「不报红、但要能看见」）不变。
        self.assertIn('只剩 1 张 open 的组', text)
        self.assertIn('不报红', text)

    def test_全closed_同编号_不报红(self):
        """整组都关掉（含正本）也不该报「活跃重复」——没有活的重复。"""
        cards = [self._stateful(5, 783, 'closed'), self._stateful(6, 783, 'closed')]
        opened, closed, unkeyed = dup.split_by_state(cards)
        _text, code = dup.render(opened, closed, unkeyed, [])
        self.assertEqual(code, dup.EXIT_OK)

    def test_残留仍列在报告里_不被静默吞掉(self):
        """不报红 ≠ 不报事实：残留要能看见，否则「清理过多少」无从核对。"""
        cards = [self._stateful(5, 783, 'open'), self._stateful(6, 783, 'closed')]
        opened, closed, unkeyed = dup.split_by_state(cards)
        text, _code = dup.render(opened, closed, unkeyed, [])
        self.assertIn('只剩 1 张 open、其余 closed 的编号：1 个', text)
        self.assertIn('已关闭 1 张', text)

    def test_open_的是编号最大的那张_判据被掉头_报红(self):
        """源 CNB #6：**「只剩一张 open」不等于「已处置干净」**。

        清理动作先写判据、再关卡，那句判据落在被关卡的评论区；第二轮按
        「有人类评论优先」选保留卡时，被关的那张成了「唯一有讨论的正本」
        ⇒ 正本被关、重复卡留在看板上。首版把这种组一律写「历史留痕，无需处理」，
        于是它在指标上一声不响——用户先看到的是「怎么一直在重复刷」。
        """
        cards = [self._stateful(5, 783, 'closed'), self._stateful(6, 783, 'open')]
        opened, closed, unkeyed = dup.split_by_state(cards)
        text, code = dup.render(opened, closed, unkeyed, [])
        self.assertEqual(code, dup.EXIT_DUPES, '最早创建的被关了、后来建的留着 ⇒ 必须报红')
        self.assertIn('判据被掉头', text)

    def test_留痕组的open卡是编号最小的_仍不报红(self):
        """掉头判据不能把**正常清理结果**也拖红（假红也是病）。"""
        cards = [
            self._stateful(5, 783, 'open'),
            self._stateful(6, 783, 'closed'),
            self._stateful(7, 783, 'closed'),
        ]
        opened, closed, unkeyed = dup.split_by_state(cards)
        _text, code = dup.render(opened, closed, unkeyed, [])
        self.assertEqual(code, dup.EXIT_OK)

    def test_跨度过大时不下结论_不猜也不假装绿(self):
        """`#164` 那批是整轮重划前的重建产物：编号小 ≠ 建卡早。

        组形态：open 的是 #281，而 #164 更小且已关。按「编号最小」硬判就是「掉头」，
        可那批卡本来就不按编号先后建 —— 硬下结论会让人去关掉真正最早的那张。
        故跨度 >100 时报成待人工判断：不报红，也不打 ✅。
        """
        cards = [
            self._stateful(164, 2096, 'closed'),
            self._stateful(183, 2096, 'closed'),
            self._stateful(281, 2096, 'open'),
        ]
        opened, closed, unkeyed = dup.split_by_state(cards)
        text, code = dup.render(opened, closed, unkeyed, [])
        self.assertEqual(code, dup.EXIT_OK, '前提不成立时不得硬判成掉头（假红）')
        self.assertIn('❔', text)
        self.assertNotIn('已掉头', text)
        self.assertNotIn('✅ GitHub #2096', text, '判据不可信时不得打勾')

    def test_open的是全组最小_即使跨度大也是确定留痕(self):
        """实测形态（GitHub #2096 对应的 CNB 组）：open 的 CNB `#164` 确实是同组**最早创建**的那张。

        「跨度大 ⇒ 不下结论」不能把这种**本来确定**的事实一起降级 —— 那会让真正
        最早的那张看起来可疑。判据是「open 的编号是否严格大于某张 closed 卡」，不是跨度本身。
        """
        cards = [
            self._stateful(164, 2096, 'open'),
            self._stateful(183, 2096, 'closed'),
        ]
        opened, closed, unkeyed = dup.split_by_state(cards)
        text, code = dup.render(opened, closed, unkeyed, [])
        self.assertEqual(code, dup.EXIT_OK)
        self.assertIn('✅ GitHub #2096', text)
        self.assertNotIn('❔', text)

    def test_变异探针_拿掉掉头判据会漏报(self):
        """**回退验证**：把 flipped 从退出码里去掉，这条用例必须红。"""
        cards = [self._stateful(5, 783, 'closed'), self._stateful(6, 783, 'open')]
        opened, closed, unkeyed = dup.split_by_state(cards)
        with mock.patch.object(dup, 'EXIT_DUPES', dup.EXIT_OK):
            # 模拟「旧版只问 open 张数」：结论退化成「已处置残留」
            _text, old_code = dup.render(opened, closed, unkeyed, [])
        _text2, new_code = dup.render(opened, closed, unkeyed, [])
        self.assertNotEqual(
            (old_code == dup.EXIT_OK), (new_code == dup.EXIT_OK), '探针咬不住：两种判据结论相同'
        )

    def test_变异探针_按总数判会假红(self):
        """**回退验证**：若判据退回「总数 >1」，已清理的卡会被永久报红。

        这条确认上面的口径是真的在起作用——不是「碰巧绿」。
        """
        cards = [self._stateful(5, 783, 'open'), self._stateful(6, 783, 'closed')]
        opened, closed, unkeyed = dup.split_by_state(cards)

        # 正确判据（只看 open）：绿
        _text, code = dup.render(opened, closed, unkeyed, [])
        self.assertEqual(code, dup.EXIT_OK)

        # 错误判据：把 open/closed 混在一起数总数 —— 会假红
        merged, _ = dup.group_by_github_number(cards)
        _t2, naive_code = dup.render(merged, None, unkeyed, [])
        self.assertEqual(naive_code, dup.EXIT_DUPES, '探针失效：混数总数竟没报红？')
        self.assertNotEqual(code, naive_code, '两种判据必须给出不同结论，否则口径没生效')


if __name__ == '__main__':
    unittest.main()
