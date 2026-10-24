# -*- coding: utf-8 -*-
"""`scripts/guard_supabase_env_separation.py` 的回归网（#1028）。

守卫治的是「生产构建拿不到 Supabase 凭证 ⇒ 浏览器里才炸」这一类事故。
它自己如果空转，就会变成它要治的那个东西——所以本文件既钉判据，也钉**灵敏度**：

1. 每条规则都有一条能红的用例；
2. **变异探针**（`test_mutation_probe_*`）：把守卫源码做一处最小回退，
   确认对应用例真的转红——「跑一次绿」不算数（AGENTS.md「守门通过 ≠ 守门有效」）。

守卫逻辑按路径加载复用，判定规则只有一份。
"""

import importlib.util
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_supabase_env_separation.py'


def _load_guard():
    spec = importlib.util.spec_from_file_location(
        'guard_supabase_env_separation', _GUARD_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GOOD_PROD = (
    'VITE_APP_ENV=production\n'
    'VITE_SUPABASE_URL=https://abcdefghijklmnopqrst.supabase.co\n'
    'VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.sig\n'
)


class TestParseEnv(unittest.TestCase):
    def test_ignores_comments_and_quotes(self):
        guard = _load_guard()
        env = guard.parse_env(
            '# 注释\n'
            '\n'
            'VITE_APP_ENV=production\n'
            'VITE_PUBLIC_PATH = "/"\n'
            "VITE_ROUTER_HISTORY='hash'\n"
            'VITE_CDN=false # 行尾注释\n'
        )
        self.assertEqual(env['VITE_APP_ENV'], 'production')
        self.assertEqual(env['VITE_PUBLIC_PATH'], '/')
        self.assertEqual(env['VITE_ROUTER_HISTORY'], 'hash')
        self.assertEqual(env['VITE_CDN'], 'false')


class TestCredentialFile(unittest.TestCase):
    def test_complete_file_passes(self):
        guard = _load_guard()
        self.assertEqual(guard.check_credential_file('.env.production', _GOOD_PROD), [])

    def test_missing_url_is_reported(self):
        guard = _load_guard()
        problems = guard.check_credential_file(
            '.env.production', 'VITE_SUPABASE_ANON_KEY=k\n'
        )
        # 断言必须精确到「缺少」这一条：只匹配 'VITE_SUPABASE_URL' 子串会被
        # 「形态非法」那条消息一起命中（变异探针实测踩过：判据太松 → 探针 MISSED）
        self.assertTrue(
            any('缺少' in p and 'VITE_SUPABASE_URL' in p for p in problems),
            f'没报出「缺少 VITE_SUPABASE_URL」：{problems}',
        )

    def test_missing_anon_key_is_reported(self):
        guard = _load_guard()
        problems = guard.check_credential_file(
            '.env.production',
            'VITE_SUPABASE_URL=https://abcdefghijklmnopqrst.supabase.co\n',
        )
        self.assertTrue(any('VITE_SUPABASE_ANON_KEY' in p for p in problems))

    def test_malformed_url_is_reported(self):
        guard = _load_guard()
        problems = guard.check_credential_file(
            '.env.production',
            'VITE_SUPABASE_URL=https://example.com\nVITE_SUPABASE_ANON_KEY=k\n',
        )
        self.assertTrue(any('形态非法' in p for p in problems))

    def test_real_anon_key_in_production_file_is_allowed(self):
        """生产文件里的 anon key 本就该是真实值（公开设计），不得被当成占位违规。"""
        guard = _load_guard()
        self.assertEqual(guard.check_credential_file('.env.production', _GOOD_PROD), [])


class TestExampleFile(unittest.TestCase):
    def test_placeholder_example_passes(self):
        guard = _load_guard()
        content = (
            'VITE_SUPABASE_URL=https://<dev-project>.supabase.co\n'
            'VITE_SUPABASE_ANON_KEY=xxxx\n'
        )
        self.assertEqual(guard.check_example_file(content), [])

    def test_real_url_in_example_is_reported(self):
        guard = _load_guard()
        problems = guard.check_example_file(
            'VITE_SUPABASE_URL=https://abcdefghijklmnopqrst.supabase.co\n'
        )
        self.assertTrue(any('VITE_SUPABASE_URL' in p for p in problems))

    def test_real_jwt_key_in_example_is_reported(self):
        guard = _load_guard()
        problems = guard.check_example_file(
            'VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.sig\n'
        )
        self.assertTrue(any('VITE_SUPABASE_ANON_KEY' in p for p in problems))

    def test_new_style_publishable_key_in_example_is_reported(self):
        guard = _load_guard()
        problems = guard.check_example_file(
            'VITE_SUPABASE_ANON_KEY=sb_publishable_abcdefghijklmnopqrstuvwxyz\n'
        )
        self.assertTrue(any('VITE_SUPABASE_ANON_KEY' in p for p in problems))


class TestRealRepoFiles(unittest.TestCase):
    """拿仓库里的真实文件跑一遍：守卫必须对现状报绿。"""

    def test_repo_env_files_pass(self):
        guard = _load_guard()
        frontend = _REPO_ROOT / 'frontend'
        for name in ('.env.production', '.env.staging'):
            content = (frontend / name).read_text(encoding='utf-8')
            self.assertEqual(
                guard.check_credential_file(name, content), [], f'{name} 未通过守卫'
            )
        example = (frontend / '.env.example').read_text(encoding='utf-8')
        self.assertEqual(guard.check_example_file(example), [])


class TestMutationProbe(unittest.TestCase):
    """变异探针：守卫源码回退一处 → 对应用例必须转红。"""

    def _run_with_mutation(self, old: bytes, new: bytes, test_name: str):
        import subprocess
        import sys

        original = _GUARD_PATH.read_bytes()
        try:
            self.assertIn(old, original, '变异锚点没找到，守卫源码形态变了？')
            _GUARD_PATH.write_bytes(original.replace(old, new, 1))
            result = subprocess.run(
                [sys.executable, '-m', 'unittest', f'scripts.tests.{test_name}'],
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
            )
            return result.returncode != 0
        finally:
            _GUARD_PATH.write_bytes(original)

    def test_mutation_removing_url_check_turns_red(self):
        caught = self._run_with_mutation(
            b"if not url:",
            b"if False:",
            'test_supabase_env_separation.TestCredentialFile.test_missing_url_is_reported',
        )
        self.assertTrue(caught, '变异探针 MISSED：守卫的 URL 缺失检查已失效')

    def test_mutation_removing_example_check_turns_red(self):
        caught = self._run_with_mutation(
            b"if url and not _looks_like_placeholder(url):",
            b"if False:",
            'test_supabase_env_separation.TestExampleFile.test_real_url_in_example_is_reported',
        )
        self.assertTrue(caught, '变异探针 MISSED：示例文件的真实值检查已失效')

    def test_mutation_removing_malformed_url_check_turns_red(self):
        caught = self._run_with_mutation(
            b"elif not _SUPABASE_URL_RE.match(url):",
            b"elif False:",
            'test_supabase_env_separation.TestCredentialFile.test_malformed_url_is_reported',
        )
        self.assertTrue(caught, '变异探针 MISSED：守卫的 URL 形态检查已失效')


if __name__ == '__main__':
    unittest.main()
