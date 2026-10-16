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
        self.assertEqual(set(state['mirrored']), {'783', '900'})


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
        self.assertIn('已处置残留', text)
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
        self.assertIn('已处置残留（只剩 1 张 open，其余 closed）：1 个编号', text)
        self.assertIn('已关闭 [6]', text)

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
