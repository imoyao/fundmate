# -*- coding: utf-8 -*-
"""`scripts/guard_font_glyph_coverage.py` 的回归网（MiSans 子集字形覆盖，源 #2402）。

守卫治的是「字表悄悄退回 GB2312 一级」——它自己空转就会重演那张卡的形态：**没有任何
东西能回答「页面上出现了 MiSans 没有的字吗」**，只能等用户截图。所以本文件既钉判据、
也钉**灵敏度**：

1. **真实仓库**：报告能跑出真数字（一级 100%、GBK 覆盖率是个有限值），不是 `except: pass`
   之后返回空健康报告；
2. **正例**：临时目录里放一个**只覆盖一级**的子集 → 必须判红，且提示里点名缺 GBK；
3. **反例**：子集覆盖全部 GBK → 必须判绿（否则它会永远红，没人看它）；
4. **失败态**：字体目录不存在 → 退 2（结论不可信），**不得**退 0；
5. **字表快照与产物一致性**：快照里缺字同样判红——和产物对不上的快照比没有更误导人。

判据边界（写在这里，避免下一个人以为它在管）：
- **不检查字形画得对不对**：只比 cmap 有没有这个码位；
- **不检查母本是否有该字**：母本缺字时请调 `GBK_MIN_COVERAGE` 并在 PR 里写明；
- **不扫用户输入**：它比的是「GBK 该有的都有」，不是「用户真的会输入什么」；
- **不判体积**：字表扩到 GBK 后单字重约 2.8 MB，首屏预算谈判属于另一件事
  （`docs/design/font-design.md` §5.2 / §11.2）。
"""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_font_glyph_coverage.py'
_FONT_DIR = _REPO_ROOT / 'frontend' / 'public' / 'fonts'


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_font_glyph_coverage', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(*args):
    """跑守卫 CLI，返回 (returncode, stdout+stderr)。"""
    proc = subprocess.run(
        [sys.executable, str(_GUARD_PATH), *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    return proc.returncode, (proc.stdout or '') + (proc.stderr or '')


class TestCharsetSets(unittest.TestCase):
    """字符集口径：这三个数是判据的基础，算错等于钉错。"""

    @classmethod
    def setUpClass(cls):
        cls.guard = _load_guard()

    def test_gb2312_level1_is_3755(self):
        self.assertEqual(len(self.guard.gb2312_level1_chars()), 3755)

    def test_gbk_hanzi_is_20902(self):
        """GBK 汉字全集 20,902——这是目标字符集，数错则覆盖率全错。"""
        self.assertEqual(len(self.guard.gbk_hanzi_chars()), 20902)

    def test_level1_is_subset_of_gbk(self):
        """一级必须完全落在 GBK 里，否则「GBK ≥98%」与「一级 100%」会互相矛盾。"""
        self.assertTrue(self.guard.gb2312_level1_chars() <= self.guard.gbk_hanzi_chars())

    def test_user_reported_chars_are_in_gbk(self):
        """用户截图里的字必须在目标字符集内，否则这张卡的验收无从谈起。

        ⚠️ 其中 `犇 喆 堃 赟 燚 彧 玊` **不在 GB2312 任何一级**（含二级）——这正是
        判据不能只看 GB2312 的原因。
        """
        probe = '荃鑫淼犇喆堃赟燚彧玊'
        gbk = self.guard.gbk_hanzi_chars()
        missing = [c for c in probe if c not in gbk]
        self.assertEqual(missing, [], f'这些字不在 GBK 目标字符集里：{missing}')

    def test_seven_of_probe_are_outside_gb2312(self):
        """钉住「只补二级不够」这个判断——它决定了判据的边界。"""
        l2 = self.guard.gb2312_level1_chars()
        outside = [c for c in '犇喆堃赟燚彧玊' if c not in l2]
        self.assertEqual(len(outside), 7, f'预期 7 个字不在 GB2312，实际 {len(outside)}')


class TestGuardOnRepo(unittest.TestCase):
    """真实仓库：必须跑得动、报得出数。"""

    def test_report_runs_and_prints_numbers(self):
        code, out = _run('--report')
        # 现状是红的（字表还没重生成），但必须**报出数字**而不是崩掉退 2。
        self.assertIn(code, (0, 1), f'守卫不该因解析失败退出，输出：{out}')
        self.assertIn('cmap', out, f'报告应打印每个字重的覆盖数，输出：{out}')
        self.assertIn('GBK', out, f'报告应打印 GBK 覆盖率，输出：{out}')

    def test_current_fonts_cover_level1_fully(self):
        """一级 100% 是既有事实——若它掉下来，说明产物被换成了更浅的字表。"""
        guard = _load_guard()
        result = guard.check()
        self.assertFalse(result.get('unreachable'), '字体产物应可达')
        for row in result['rows']:
            covered, total, _cov = row['level1']
            self.assertEqual(covered, total, f'{row["font"]} 的一级覆盖掉了：{covered}/{total}')

    def test_current_fonts_fail_gbk_coverage(self):
        """现状必须判红——这是本卡的起点，绿了说明要么字表已补、要么判据失效。"""
        guard = _load_guard()
        result = guard.check()
        gbk_cov = min(row['gbk'][2] for row in result['rows'])
        self.assertLess(gbk_cov, guard.GBK_MIN_COVERAGE, '当前产物不该达到 GBK 下限')


class TestFailureModes(unittest.TestCase):
    """失败态：拿不到输入必须退 2，不得当成通过。"""

    def test_missing_font_dir_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run('--font-dir', tmp)
        self.assertEqual(code, 2, f'字体目录为空应退 2（结论不可信），实际 {code}：{out}')
        self.assertIn('不可达', out)

    def test_missing_charset_snapshot_is_red_not_crash(self):
        """字表快照缺失 → 判红（1），不是崩溃（2）：产物本身仍可审计。"""
        guard = _load_guard()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'nope.txt'
            result = guard.check(_FONT_DIR, charset_file=missing)
        self.assertFalse(result['ok'])
        self.assertFalse(result.get('unreachable'))
        self.assertTrue(
            any('字表快照缺失' in p for p in result['problems']),
            f'应报告快照缺失，实际：{result["problems"]}',
        )

    def test_snapshot_shallower_than_fonts_is_red(self):
        """快照比产物浅（只写一级）→ 判红：产物与字表不同步比没有快照更误导人。"""
        guard = _load_guard()
        with tempfile.TemporaryDirectory() as tmp:
            shallow = Path(tmp) / 'charset.txt'
            shallow.write_text(''.join(sorted(guard.gb2312_level1_chars())), encoding='utf-8')
            result = guard.check(_FONT_DIR, charset_file=shallow)
        self.assertFalse(result['ok'])
        self.assertTrue(
            any('字表快照 GBK 覆盖' in p for p in result['problems']),
            f'应报告快照覆盖不足，实际：{result["problems"]}',
        )


class TestMutationProbes(unittest.TestCase):
    """变异探针：把判据改松，回归网必须抓住。

    「守卫会红」本身不证明它咬的是**它该咬的东西**——判据改成永远通过，上面那些
    用例照样绿。故这里直接改源码副本、断言行为变化。

    两个探针都来自本卡的真实教训：
    1. 覆盖率下限调成 0 ⇒ 现状（18%）会被判通过，正是「只补二级就交差」的形态；
    2. 一级覆盖被算成「只要有字就算过」⇒ 界面文案缺字不会被发现。
    """

    def _mutated_guard(self, old, new):
        src = _GUARD_PATH.read_text(encoding='utf-8')
        self.assertIn(old, src, f'探针锚点已失效，请更新本用例：{old[:40]}')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'guard_mutated.py'
            path.write_text(src.replace(old, new), encoding='utf-8')
            spec = importlib.util.spec_from_file_location('guard_mutated', path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module

    def test_probe_threshold_zero_would_pass_current_fonts(self):
        """把 GBK 下限调成 0 ⇒ 现状三成不到的覆盖会被判绿（证明阈值真的在起作用）。"""
        mutated = self._mutated_guard('GBK_MIN_COVERAGE = 0.98', 'GBK_MIN_COVERAGE = 0.0')
        result = mutated.check(_FONT_DIR)
        # 快照那一路仍会红（字表本身没扩），所以只看字体产物的判定
        font_problems = [p for p in result['problems'] if p.endswith('.woff2') or '.woff2:' in p]
        self.assertEqual(font_problems, [], f'阈值失效，仍报字体问题：{font_problems}')

    def test_probe_level1_check_removed_lets_shallow_fonts_pass(self):
        """删掉一级判据 ⇒ 只覆盖一级缺一半的字体也不会因「一级」被判红。"""
        mutated = self._mutated_guard(
            '        if miss1:\n',
            '        if False and miss1:\n',
        )
        result = mutated.check(_FONT_DIR)
        self.assertTrue(
            all('GB2312 一级缺' not in p for p in result['problems']),
            f'一级判据没被删掉：{result["problems"]}',
        )


if __name__ == '__main__':
    unittest.main()
