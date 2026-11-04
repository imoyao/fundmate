# -*- coding: utf-8 -*-
"""`scripts/rebuild_dependabot_branch.py` 的回归网（#2434 第二阶段：撞锁）。

## 这一层要钉住什么

守卫（`guard_dependabot_lockfile_regen.py`）只能证明「workflow 会调用重建」，
证明不了「重建真的能解冲突」。而这条通道的价值**全部**在后者：
2026-10-26 的 #2646 / #2648 就是「锁已修好、分支仍冲突」，人肉开了 #2659 收口。

所以本文件用**真 git 仓库**复现那个形态（两个 bump 分支各自重写同一份锁 → dev 先合一个
→ 另一个变冲突），再断言重建之后「分支成为 dev 的后代」——不是断言脚本自己说成功。

## 探针（每条都对应一种「看着正常、实际没修」的形态）

1. 前置条件：重建前那对分支**确实**是冲突的（否则本文件什么都没证明）；
2. 重建后 dev 是分支祖先（冲突在构造上不可能存在）；
3. manifest 的改动被保留、锁被重算（不是「把 PR 改回原样」）；
4. 非 manifest / 锁的改动 ⇒ 退出码 3（不替 PR 决定源码）；
5. 重生成自证失败 ⇒ 退出码 2 且**不提交**（不推半成品）；
6. 第二次运行不产生新提交（否则 rebuild → push → synchronize → rebuild 会自激）。

`node` 不在 PATH 时跳过（CI 由 setup-node 提供，本地一般也有）。
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / 'scripts' / 'rebuild_dependabot_branch.py'

_STUB_REGEN = """
import { readFileSync, writeFileSync } from 'node:fs';
const args = process.argv.slice(2);
const arg = (k) => args[args.indexOf(k) + 1];
const dir = arg('--dir');
const lockPath = dir === '.' ? 'pnpm-lock.yaml' : `${dir}/pnpm-lock.yaml`;
const manifestPath = dir === '.' ? 'package.json' : `${dir}/package.json`;
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const deps = Object.entries(manifest.dependencies || {}).sort()
  .map(([name, spec]) => `  ${name}: ${spec.replace(/^[~^]/, '')}`).join('\\n');
writeFileSync(lockPath, `lockfileVersion: 9\\ndependencies:\\n${deps}\\n`);
console.log(`LOCKFILE_REGEN dir=${dir} changed=1 pinned=1/1 frozen=pass applied=yes`);
"""


def _run(cmd, cwd):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding='utf-8')
    if proc.returncode != 0:
        raise AssertionError(f'{" ".join(cmd)} 失败：{proc.stderr}')
    return proc.stdout


def _lock(deps, rewrite_marker=None):
    """生成一份「像 dependabot 那样整份重写」的锁：倒序 + 指纹行。"""
    order = sorted(deps)
    if rewrite_marker:
        order = list(reversed(order))
    lines = ['lockfileVersion: 9', 'dependencies:']
    lines += [f'  {name}: {spec.lstrip("^~")}' for name, spec in ((n, deps[n]) for n in order)]
    if rewrite_marker:
        lines.append(f'# rewritten-by-dependabot {rewrite_marker}')
    return '\n'.join(lines) + '\n'


class _Fixture:
    """一个「origin + work」的最小仓库：dev 上一份 manifest 与锁。"""

    BASE_DEPS = {'axios': '^1.19.0', 'sass': '^1.105.2', 'vue': '^3.5.43'}

    def __init__(self, root: Path):
        self.root = root
        self.origin = root / 'origin.git'
        self.work = root / 'work'
        self.stub = root / 'stub_regen.mjs'
        self.stub.write_text(_STUB_REGEN, encoding='utf-8')

        _run(['git', 'init', '--bare', '-b', 'dev', str(self.origin)], root)
        self.work.mkdir()
        _run(['git', 'init', '-b', 'dev', '.'], self.work)
        _run(['git', 'config', 'user.name', 'fixture'], self.work)
        _run(['git', 'config', 'user.email', 'fixture@example.com'], self.work)
        _run(['git', 'remote', 'add', 'origin', str(self.origin)], self.work)

        self.write(frontend_manifest=self.BASE_DEPS, lock=_lock(self.BASE_DEPS))
        _run(['git', 'add', '-A'], self.work)
        _run(['git', 'commit', '-m', 'chore: 初始'], self.work)
        _run(['git', 'push', '-u', 'origin', 'dev'], self.work)

    # --- 便捷操作 -------------------------------------------------------
    def write(self, frontend_manifest, lock):
        (self.work / 'frontend').mkdir(exist_ok=True)
        (self.work / 'frontend' / 'package.json').write_text(
            # 多行 JSON：真实 package.json 就是这个形态
            json.dumps({'name': 'fixture', 'dependencies': frontend_manifest}, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        (self.work / 'frontend' / 'pnpm-lock.yaml').write_text(lock, encoding='utf-8')

    def git(self, *args):
        return _run(['git', *args], self.work)

    def bot_branch(self, name, dep, version):
        """模拟 dependabot：把**已有**依赖换一个版本，并**整份重写**锁。

        关键在「整份重写」：真 dependabot 是重新序列化整个 lock，而不是改一行，
        所以同一批两个 PR 的 diff 会大面积重叠 ⇒ 后合的那个必冲突（#2646 / #2648 实测）。
        夹具照抄这个形态（倒序 + 指纹行），否则「前置条件：真的冲突」那条探针会假绿。
        """
        deps = {**self.BASE_DEPS, dep: f'^{version}'}
        self.git('checkout', '-B', name, 'dev')
        self.write(frontend_manifest=deps, lock=_lock(deps, rewrite_marker=name))
        self.git('add', '-A')
        self.git('commit', '-m', f'fix: bump {dep} to {version} in /frontend')
        self.git('push', '-f', 'origin', name)

    def merges_cleanly(self, head, into='dev'):
        """真合并一次再回滚——`merge-tree` 在各版本 git 上行为不一致，不用它。"""
        self.git('checkout', '-B', '__probe', into)
        proc = subprocess.run(
            ['git', 'merge', '--no-commit', '--no-ff', head],
            cwd=str(self.work), capture_output=True, text=True, encoding='utf-8',
        )
        conflict = proc.returncode != 0
        subprocess.run(['git', 'merge', '--abort'], cwd=str(self.work), capture_output=True)
        # 冲突时 index 里留着未合并条目，不清干净会让后续 checkout 报
        # 「you need to resolve your current index first」——那是夹具的脏，不是脚本的病。
        self.git('reset', '--hard', 'dev')
        return not conflict

    def rebuild(self, branch, extra_env=None):
        argv = [
            sys.executable, str(_SCRIPT),
            '--branch', branch, '--base', 'origin/dev',
            '--repo', str(self.work), '--regen-script', str(self.stub), '--apply',
        ]
        result = subprocess.run(
            argv, capture_output=True, text=True, encoding='utf-8', env=extra_env,
        )
        # 脚本只负责重建 + 提交，推送由 workflow 做（force-with-lease）；
        # 夹具在这里补上那一步，否则断言的是「没推上去的分支」。
        if result.returncode == 0 and 'applied=yes' in result.stdout:
            self.git('push', '-f', 'origin', f'HEAD:{branch}')
        return result


@unittest.skipUnless(shutil.which('git') and shutil.which('node'), '需要 git + node')
class TestRebuildResolvesLockConflict(unittest.TestCase):
    """#2646 / #2648 的形态：两个 bot 分支各自重写同一份锁。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = _Fixture(Path(self._tmp.name))
        # 分支 A（先合）与分支 B（后合）：都重写了整份锁
        self.fx.bot_branch('dependabot-a', 'vue', '3.5.44')
        self.fx.bot_branch('dependabot-b', 'sass', '1.106.1')
        self.fx.git('checkout', 'dev')
        self.fx.git('merge', '--no-ff', '--no-edit', 'dependabot-a')
        self.fx.git('push', 'origin', 'dev')

    def tearDown(self):
        self._tmp.cleanup()

    def test_precondition_branch_b_really_conflicts(self):
        """探针 1：重建前必须真的是冲突态，否则本文件什么都没证明。"""
        self.assertFalse(
            self.fx.merges_cleanly('dependabot-b'),
            '构造的样本本身不冲突——测试失去意义（先修夹具）',
        )

    def test_rebuild_makes_branch_a_descendant_of_dev(self):
        """探针 2 + 3：重建后 dev 是分支祖先，且 manifest 意图被保留、锁被重算。"""
        result = self.fx.rebuild('dependabot-b')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('applied=yes', result.stdout)
        self.assertIn('reason=rebuilt', result.stdout)

        self.fx.git('fetch', 'origin', 'dependabot-b')
        ancestor = subprocess.run(
            ['git', 'merge-base', '--is-ancestor', 'origin/dev', 'origin/dependabot-b'],
            cwd=str(self.fx.work),
        )
        self.assertEqual(ancestor.returncode, 0, '重建后分支仍不是 dev 的后代——冲突没被消掉')
        self.assertTrue(self.fx.merges_cleanly('origin/dependabot-b'), '重建后仍判冲突')

        manifest = json.loads(
            self.fx.git('show', 'origin/dependabot-b:frontend/package.json')
        )
        self.assertEqual(manifest['dependencies']['sass'], '^1.106.1', 'PR 的 bump 意图被丢了')
        lock = self.fx.git('show', 'origin/dependabot-b:frontend/pnpm-lock.yaml')
        self.assertIn('sass: 1.106.1', lock, '锁没有按 manifest 重算')
        self.assertIn('vue: 3.5.44', lock, 'dev 上已有的 vue 被重建冲掉')

    def test_second_run_adds_no_commit(self):
        """探针 6：幂等——否则 rebuild → synchronize → rebuild 会自激。"""
        first = self.fx.rebuild('dependabot-b')
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        head_after_first = self.fx.git('rev-parse', 'HEAD').strip()

        second = self.fx.rebuild('dependabot-b')
        self.assertIn(second.returncode, (0, 3), second.stdout + second.stderr)
        self.assertEqual(self.fx.git('rev-parse', 'HEAD').strip(), head_after_first)


@unittest.skipUnless(shutil.which('git') and shutil.which('node'), '需要 git + node')
class TestRebuildGates(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = _Fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_source_change_is_not_applicable(self):
        """探针 4：PR 改了源码 ⇒ 退出码 3，不替 PR 决定非依赖内容。"""
        self.fx.git('checkout', '-B', 'feat-x', 'dev')
        (self.fx.work / 'src.ts').write_text('export const x = 1;\n', encoding='utf-8')
        self.fx.git('add', '-A')
        self.fx.git('commit', '-m', 'feat: 改源码')
        self.fx.git('push', '-f', 'origin', 'feat-x')

        result = self.fx.rebuild('feat-x')
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('reason=non_manifest_change', result.stdout)

    def test_regen_failure_leaves_no_commit(self):
        """探针 5：重生成自证失败 ⇒ 退出码 2，且分支上没有半成品提交。"""
        # 升级一个 **dev 上已存在** 的包（重建是「换 spec」，不是「加依赖」；
        # 加依赖那种形态走旧路径，见 test_added_dependency_falls_back）
        self.fx.bot_branch('dependabot-c', 'axios', '1.19.1')
        # dev 前进一格（改的是无关文件）：分支成为「落后」态，才走重建路径；
        # 否则 dev 本就是分支祖先，脚本会判 already_current 直接交回旧路径。
        self.fx.git('checkout', 'dev')
        (self.fx.work / 'README.md').write_text('# fixture\n', encoding='utf-8')
        self.fx.git('add', '-A')
        self.fx.git('commit', '-m', 'docs: 无关改动')
        self.fx.git('push', 'origin', 'dev')

        argv = [
            sys.executable, str(_SCRIPT),
            '--branch', 'dependabot-c', '--base', 'origin/dev',
            '--repo', str(self.fx.work), '--regen-script', str(self.fx.stub), '--apply',
        ]
        before = self.fx.git('rev-parse', 'HEAD').strip()

        # 把 stub 换成必失败版本：模拟「重生成自证没过」
        self.fx.stub.write_text('console.error("boom"); process.exit(1);\n', encoding='utf-8')
        result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('reason=regen_failed', result.stdout)
        self.assertEqual(self.fx.git('rev-parse', 'HEAD').strip(), before, '失败态留下了提交')


if __name__ == '__main__':
    unittest.main()
