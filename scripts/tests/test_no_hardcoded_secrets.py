# -*- coding: utf-8 -*-
"""`scripts/guard_no_hardcoded_secrets.py` 的回归网（密钥字面量守卫，源 #2486）。

守卫治的是「Token 进了仓库」——它自己空转就会变成它要治的东西，所以本文件既钉判据、
也钉**灵敏度**：

1. **每种形态各一条正例**：前缀形态、赋值形态、env 行形态；
2. **灵敏度探针**：在临时 git 仓库里 `git add` 一份带假 Token 的文件，`scan_repo()`
   必须真的找得到——这条同时证明「扫描循环没被短路成空列表」（同 CNB #450 的教训：
   判据错的时候，日志只会更响亮地重复错结论）；
3. **失败态**：拿不到输入（不是 git 仓库 / 文件读不了）必须退 2，不得当成通过；
4. **误报反例**：占位值、`Bearer {token}` 拼接、`os.getenv()`、真实仓库全量扫描。

**Token 一律在运行时拼接**（如 `'ak_' + 'A1b2…'`）：写成字面量的话，本文件自己会被
守卫咬住——而「把测试数据改成占位形态」等于把假绿固化下来（探针是在改生产代码，
不是在改测试数据）。
"""

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_no_hardcoded_secrets.py'


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_no_hardcoded_secrets', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    # 必须先登记进 `sys.modules`：3.14 的 `@dataclass` 会回查 `cls.__module__` 的模块字典，
    # 不登记就 `AttributeError: 'NoneType' object has no attribute '__dict__'`
    # （本文件首跑 16 条全红即此因）。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_secret(kind: str) -> str:
    """运行时拼出假凭据（不落任何 token 形态字面量）。"""
    body = 'a1B2c3D4e5F6g7H8i9J0k1L2m3N4'
    return {
        'wind': 'ak_' + body,
        'openai': 'sk-' + 'proj-' + body,
        'github': 'ghp_' + body + 'o5P6q7R8',
        'aws': 'AKIA' + 'IOSFODNN7EXAMPLE',
        'slack': 'xox' + 'b-' + '1234567890-abcdefghij',
        'bearer': 'Bearer ' + body,
        'assign': body,
        'env': body,
    }[kind]


def _jwt(role: str) -> str:
    import base64
    import json

    def enc(obj) -> str:
        raw = json.dumps(obj).encode('utf-8')
        return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

    return f'{enc({"alg": "HS256"})}.{enc({"role": role, "iss": "supabase"})}.{enc({"sig": "x" * 8})}'


class TestStrongForms(unittest.TestCase):
    """前缀形态：自带特征，几乎不可能误报。"""

    def test_each_prefix_is_caught(self):
        guard = _load_guard()
        for kind in ('wind', 'openai', 'github', 'aws', 'slack', 'bearer'):
            with self.subTest(kind=kind):
                text = f'X = 1  # {_fake_secret(kind)}'
                findings = guard.scan_text('sample.py', text)
                self.assertTrue(findings, f'{kind} 形态未被抓住')

    def test_line_number_is_reported(self):
        guard = _load_guard()
        text = 'line1\nline2\nX = 1  # ' + _fake_secret('wind') + '\n'
        findings = guard.scan_text('sample.py', text)
        self.assertEqual([f.line_no for f in findings], [3])


class TestAssignmentAndEnvLine(unittest.TestCase):
    """凭据名 + 长字面量：最常见的两种写法。"""

    def test_quoted_assignment_is_caught(self):
        guard = _load_guard()
        text = f"api_key = '{_fake_secret('assign')}'"
        self.assertTrue(guard.scan_text('sample.py', text))

    def test_unquoted_env_line_is_caught(self):
        guard = _load_guard()
        text = f'QIEMAN_API_KEY={_fake_secret("env")}'
        self.assertTrue(guard.scan_text('.env', text))

    def test_short_or_sentence_value_is_not_caught(self):
        guard = _load_guard()
        text = "api_key = 'short'\npassword = '这是一句中文说明，不是凭据'"
        self.assertEqual(guard.scan_text('sample.py', text), [])

    def test_code_line_is_not_mistaken_for_env_line(self):
        """真实仓库首跑踩过：`user_token = auth_header[7:].strip()` 曾被当成 env 行。"""
        guard = _load_guard()
        text = '\n'.join(
            [
                'user_token = auth_header[7:].strip()',
                'private_key = ec.generate_private_key(ec.SECP256R1())',
            ]
        )
        self.assertEqual(guard.scan_text('sample.py', text), [])


class TestAllowlist(unittest.TestCase):
    """白名单只认语义，不认路径。"""

    def test_placeholder_values_pass(self):
        guard = _load_guard()
        text = '\n'.join(
            [
                "SECRET_KEY = 'not-so-secret-in-tests'",
                'VITE_SUPABASE_ANON_KEY=xxxx',
                "access_token: 'e2e-injected-access-token'",
                "api_key = 'your-key-here'",
            ]
        )
        self.assertEqual(guard.scan_text('.env', text), [])

    def test_bearer_fstring_has_no_literal(self):
        guard = _load_guard()
        text = "\n".join(
            [
                "headers = {'Authorization': f'Bearer {token}'}",
                "headers = {'Authorization': 'Bearer ' + token}",
            ]
        )
        self.assertEqual(guard.scan_text('sample.py', text), [])

    def test_os_getenv_is_not_a_literal(self):
        guard = _load_guard()
        self.assertEqual(guard.scan_text('a.py', "key = os.getenv('QIEMAN_API_KEY')"), [])

    def test_supabase_anon_jwt_passes(self):
        guard = _load_guard()
        text = f'VITE_SUPABASE_ANON_KEY={_jwt("anon")}'
        self.assertEqual(guard.scan_text('.env.production', text), [])

    def test_service_role_jwt_is_caught(self):
        """同形 JWT 但 role=service_role ⇒ 真密钥，必须报（这是按 payload 判的理由）。"""
        guard = _load_guard()
        text = f'SUPABASE_SERVICE_ROLE_KEY={_jwt("service_role")}'
        self.assertTrue(guard.scan_text('.env', text))


class TestMasking(unittest.TestCase):
    def test_error_text_does_not_echo_token(self):
        guard = _load_guard()
        secret = _fake_secret('wind')
        masked = guard._mask(secret)
        self.assertNotIn(secret, masked)
        self.assertIn(f'{len(secret)} 位', masked)


class TestScanRepo(unittest.TestCase):
    """扫描循环本身：探针仓库里 `git add` 一份假 Token，必须真的找得到。"""

    def test_finds_secret_in_temp_repo(self):
        guard = _load_guard()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True, capture_output=True)
            (root / 'config.py').write_text(
                "TOKEN = '" + _fake_secret('assign') + "'\n", encoding='utf-8'
            )
            subprocess.run(['git', 'add', 'config.py'], cwd=root, check=True, capture_output=True)

            findings, stats = guard.scan_repo(root)

            self.assertEqual(stats['unreadable'], 0)
            self.assertTrue(findings, '探针仓库里的假 Token 没被扫到 ⇒ 扫描循环空转')
            self.assertEqual(findings[0].path, 'config.py')

    def test_real_repo_is_clean(self):
        """真实仓库全量扫描：0 命中。谁把 Token 写进仓库，这条会先红。"""
        guard = _load_guard()
        findings, stats = guard.scan_repo(_REPO_ROOT)
        self.assertEqual(stats['unreadable'], 0)
        self.assertEqual([f.render() for f in findings], [])


class TestUnavailable(unittest.TestCase):
    """失败态：拿不到输入 ≠ 干净。"""

    def _main_quiet(self, guard) -> int:
        """跑 `main()` 但吞掉它写到 stderr 的告警——那两行是**预期输出**，
        不吞的话 CI 日志里会多出一段看着像报错的红字（真红会被 `assertEqual` 抓住）。"""
        with contextlib.redirect_stderr(io.StringIO()):
            return guard.main([])

    def test_not_a_git_repo_exits_2(self):
        guard = _load_guard()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(guard, 'REPO_ROOT', Path(tmp)):
                self.assertEqual(self._main_quiet(guard), 2)

    def test_unreadable_tracked_file_exits_2(self):
        guard = _load_guard()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(guard, 'REPO_ROOT', Path(tmp)), mock.patch.object(
                guard, '_tracked_files', return_value=['definitely-missing.txt']
            ):
                self.assertEqual(self._main_quiet(guard), 2)


if __name__ == '__main__':
    unittest.main()
