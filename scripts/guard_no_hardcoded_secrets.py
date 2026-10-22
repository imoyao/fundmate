#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：仓库里不得出现**密钥字面量**（Token / API Key / 私钥 / 口令）。

WHY（源 #2486；上位约束 `docs/dev/mcp-integration.md` §1 红线一）
------------------------------------------------------------------
接 MCP（Wind、且慢）之后，Token 会以三种最平常的方式进仓库：写进适配器常量、
写进测试夹具、写进文档示例。而现有守卫**没有一条看密钥字面量**：

- `scripts/guard_secret_imports.py` 管的是 `.cnb.yml` 的插件 imports 结构（凭据**引用**方式），
  不看值；
- `scripts/guard_mojibake.py` 管编码；
- `scripts/guard_scheduler_env_example.py` 管「调度开关有没有写进 `.env.example`」。

所以这条规则此前只有一道防线：**记得别写**。而它失败时的代价不可逆——Token 一旦进了
提交历史，删文件不够（要改写历史或轮换 Token）。同仓已有同型教训：只靠自觉的规则
不会被执行（`scripts/guard_rule_registry.py` 的预算就是为这件事设的）。

判据（只看字面量，不联网、不读运行时）
--------------------------------------
1. **强形态**：命中已知密钥前缀即报——`ak_`（Wind）、`sk-` / `sk-proj-`（OpenAI 系）、
   `ghp_` / `gh[pousr]_` / `github_pat_`、`AKIA`（AWS）、`xox[baprs]-`（Slack）、
   `Bearer <长串>`、`eyJ….….…`（JWT）。
2. **赋值形态**：`api_key` / `access_token` / `secret_key` / `password` 等**凭据名**后面
   直接跟一个 ≥20 字符的字面量，且该值字母数字混排（纯中文句子、纯路径不报）。
3. **env 行形态**：`*_KEY=` / `*_TOKEN=` / `*_SECRET=` / `*_PASSWORD=` 等变量名后面
   直接跟无引号长值（`.env*` 被跟踪时最容易漏的形态）。

白名单只认**语义**，不认路径（按路径开口子等于给「这个文件以后随便写」发通行证）
--------------------------------------------------------------------------------
- **占位值**：含 `xxxx` / `test` / `fake` / `dummy` / `example` / `placeholder` /
  `changeme` / `injected` / `not-so-secret` / `redacted` / `sample` / `your-` / `<` / `***`
  ——示例文件与测试夹具本来就该长这样。
- **Supabase `anon` key**：JWT 的 payload 里 `role=anon` 即放行。anon key 会被打进前端
  bundle，**公开是设计如此**（权限由 RLS 兜底）。而同一形态的 `service_role` key
  是**真密钥**，必须报——判据按 payload 而不是按文件名，就是为了拦住这一点。
- **无字面量的拼接**：`Bearer {token}` / `f'Bearer {token}'` / `os.getenv('…')` 不含
  可读密钥，强形态正则要求 `Bearer` 后有 ≥24 位的实际字符，天然不命中。

已知不覆盖（写在这里，避免下一个人以为它在管）
----------------------------------------------
- **提交信息 / PR 正文 / issue**：它们不在工作区里，本脚本读不到（同 `guard_mojibake`
  的边界）。真要覆盖提交信息，得另挂 `commit-msg` 钩子。
- **未跟踪文件**：扫的是 `git ls-files`，本地 `.env` 不在内——但它本来也不该入库。
- **二进制 / >512KB / 锁文件**：跳过（性能）。若把 Token 塞进 PNG 或锁文件，这里看不见。
- **拆分拼接的密钥**（`'ak_' + 'A'*24`）：静态文本看不出来。这是刻意留的口子——
  测试夹具正是靠它构造假 Token，否则守卫会咬自己的用例。
- **历史提交**：只扫当前工作区的跟踪文件，**已推上去的历史不追**（要清历史得人工）。

用法
----
    python scripts/guard_no_hardcoded_secrets.py            # 校验（CI）
    python scripts/guard_no_hardcoded_secrets.py --report   # 打印各类命中数与扫描面

退出码：0 = 干净；1 = 命中密钥字面量；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 单文件上限：超过就不读（大文件是压缩产物 / 数据，不是源码）。
MAX_BYTES = 512 * 1024
# 二进制探针窗口：这 8KB 里出现 NUL 就当二进制跳过。
BINARY_PROBE = 8192

# 跳过：图片 / 字体 / 数据库 / 压缩包。
SKIP_SUFFIXES = (
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.bmp', '.svgz',
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.db', '.db-wal', '.db-shm', '.sqlite', '.sqlite3',
    '.pdf', '.zip', '.gz', '.7z', '.mp4', '.mp3',
)
# 跳过：锁文件与 vendored 依赖（内容是哈希与包名，且体积大）。
SKIP_NAMES = ('pnpm-lock.yaml', 'package-lock.json', 'pdm.lock', 'yarn.lock', 'uv.lock')

# 占位值关键词：命中即视为「示例 / 夹具」，不报。**小写比较**。
PLACEHOLDER_HINTS = (
    'xxxx', 'test', 'fake', 'dummy', 'example', 'placeholder', 'changeme',
    'injected', 'not-so-secret', 'redacted', 'sample', 'your-', '<', '***', '…',
)

# 强形态：自带前缀，几乎不可能误报。
_STRONG_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ('wind_token', re.compile(r'ak_[A-Za-z0-9]{16,}'), 'Wind MCP Token（ak_ 前缀）'),
    ('openai_key', re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9]{20,}'), 'OpenAI 系密钥（sk- 前缀）'),
    (
        'github_token',
        re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})'),
        'GitHub Token（ghp_ / github_pat_ 等前缀）',
    ),
    ('aws_access_key', re.compile(r'\bAKIA[0-9A-Z]{16}\b'), 'AWS Access Key（AKIA 前缀）'),
    ('slack_token', re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}'), 'Slack Token（xox?- 前缀）'),
    (
        'bearer_literal',
        re.compile(r'Bearer\s+[A-Za-z0-9\-_.=]{24,}'),
        'Authorization 头里写死的 Bearer 口令',
    ),
    (
        'jwt',
        re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
        'JWT（anon 以外的都是真密钥）',
    ),
)

# 赋值形态：凭据名 + 引号里的长字面量（同**行内**，不跨行——跨行会把 docstring 里
# 引号未闭合的片段整段吞进来，2026-10-21 侦察时实测踩到）。
#
# `token` 是裸名也收（`TOKEN = '…'` 是最常见的泄漏写法之一）；`user_token = auth_header[7:].strip()`
# 这类**代码行**不会命中——它的值不在引号里（无引号形态由下面的 env 行规则管，且字符集收窄）。
_ASSIGN_RE = re.compile(
    r'(?i)\b(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|secret[_-]?key'
    r'|client[_-]?secret|password|passwd)\s*[:=]\s*[\'"]([^\'"\n]{20,})[\'"]'
)

# env 行形态：`SOMETHING_KEY=长值`（无引号，`.env*` 被跟踪时最容易漏）。
#
# 值的字符集**收窄到 base64/hex 一族**（`A-Za-z0-9_-./+=`）：不收窄的话
# `user_token = auth_header[7:].strip()`、`private_key = ec.generate_private_key(...)`
# 这类**代码行**会被当成 env 行（变量名含 token/key、值含数字且够长）——
# 2026-10-21 在真实仓库上首跑即命中这两条假阳性。凭据值不含括号与方括号，
# 用字符集把代码挡在外面，比事后按路径开白名单可靠。
_ENV_LINE_RE = re.compile(
    r'(?im)^[ \t]*(?:export[ \t]+)?([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)'
    r'[ \t]*=[ \t]*([A-Za-z0-9_\-./+=]{20,})[ \t]*$'
)

# 字母 + 数字混排：把「一句中文」「一个路径」排除掉，只留真像凭据的值。
_MIXED_RE = re.compile(r'(?=.*[A-Za-z])(?=.*\d)')


@dataclass(frozen=True)
class Finding:
    """一条命中：路径 + 行号 + 类型 + 脱敏后的片段。"""

    path: str
    line_no: int
    kind: str
    sample: str

    def render(self) -> str:
        return f'{self.path}:{self.line_no} [{self.kind}] {self.sample}'


class Unavailable(RuntimeError):
    """拿不到输入（git 失败 / 文件读不了）——结论不可信，必须退 2。"""


def _mask(value: str) -> str:
    """脱敏：只留前缀 6 位 + 长度。**报错信息本身不得回显 Token**（同 §1 红线一）。"""
    head = value[:6]
    return f'{head}***（{len(value)} 位）'


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(hint in low for hint in PLACEHOLDER_HINTS)


def _is_anon_jwt(token: str) -> bool:
    """JWT payload 里 `role=anon` ⇒ Supabase 匿名 key，公开可见是设计如此。

    刻意按 payload 判而不是按文件名：`role=service_role` 的同形字符串是**真密钥**，
    按路径放行会把 service_role 一起放过（那才是能被拿来绕过 RLS 的那把）。
    """
    parts = token.split('.')
    if len(parts) != 3:
        return False
    payload = parts[1]
    payload += '=' * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode('ascii')))
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and data.get('role') == 'anon'


def _looks_like_secret(value: str) -> bool:
    if _is_allowlisted_literal(value):
        return False
    return bool(_MIXED_RE.search(value))


def _is_allowlisted_literal(value: str) -> bool:
    """占位值 / Supabase anon key ⇒ 放行（赋值与 env 行两条路共用一份判断）。"""
    if _is_placeholder(value):
        return True
    return value.startswith('eyJ') and value.count('.') == 2 and _is_anon_jwt(value)


def scan_text(rel_path: str, text: str) -> list[Finding]:
    """扫一段文本，返回命中（纯函数，单测直接喂字符串）。"""
    findings: list[Finding] = []
    seen: set[tuple[int, str]] = set()

    def add(line_no: int, kind: str, raw: str) -> None:
        key = (line_no, kind)
        if key in seen:
            return
        seen.add(key)
        findings.append(Finding(rel_path, line_no, kind, _mask(raw)))

    lines = text.splitlines()
    for line_no, line in enumerate(lines, 1):
        for kind, rx, _note in _STRONG_PATTERNS:
            for match in rx.finditer(line):
                raw = match.group(0)
                if kind == 'jwt' and _is_anon_jwt(raw):
                    continue
                if kind == 'bearer_literal' and _is_placeholder(raw):
                    continue
                add(line_no, kind, raw)
        for match in _ASSIGN_RE.finditer(line):
            value = match.group(1)
            if _looks_like_secret(value):
                add(line_no, 'credential_assignment', value)
        match = _ENV_LINE_RE.match(line)
        if match:
            value = match.group(2)
            if _looks_like_secret(value):
                add(line_no, 'env_line', value)
    return findings


def _tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ['git', 'ls-files', '-z'], cwd=root, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise Unavailable(
            'git ls-files 失败，无法确定扫描面（结论不可信）：'
            + result.stderr.decode('utf-8', 'replace').strip()
        )
    return [p for p in result.stdout.decode('utf-8', 'replace').split('\0') if p]


def _should_skip(rel_path: str) -> bool:
    name = rel_path.rsplit('/', 1)[-1]
    if name in SKIP_NAMES:
        return True
    return rel_path.lower().endswith(SKIP_SUFFIXES)


def scan_repo(root: Path | None = None) -> tuple[list[Finding], dict[str, int]]:
    """扫整个仓库的跟踪文件。

    返回 ``(findings, stats)``；``stats`` 里 ``unreadable`` > 0 同样要退 2 ——
    读不到的文件不能假装它干净。
    """
    base = Path(root or REPO_ROOT)
    findings: list[Finding] = []
    stats = {'tracked': 0, 'scanned': 0, 'skipped_binary': 0, 'skipped_large': 0,
             'skipped_name': 0, 'unreadable': 0}
    for rel in _tracked_files(base):
        stats['tracked'] += 1
        if _should_skip(rel):
            stats['skipped_name'] += 1
            continue
        path = base / rel
        try:
            blob = path.read_bytes()
        except OSError:
            stats['unreadable'] += 1
            continue
        if len(blob) > MAX_BYTES:
            stats['skipped_large'] += 1
            continue
        if b'\x00' in blob[:BINARY_PROBE]:
            stats['skipped_binary'] += 1
            continue
        stats['scanned'] += 1
        findings.extend(scan_text(rel, blob.decode('utf-8', 'replace')))
    return findings, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='仓库内不得出现密钥字面量（#2486）')
    parser.add_argument('--report', action='store_true', help='打印扫描面与命中分类')
    args = parser.parse_args(argv)

    try:
        findings, stats = scan_repo()
    except Unavailable as exc:
        print(f'⛔ {exc}', file=sys.stderr)
        return 2

    if args.report:
        print(
            '扫描面：跟踪 {tracked} / 实际扫 {scanned} / 跳过（名称 {skipped_name}、'
            '过大 {skipped_large}、二进制 {skipped_binary}）/ 读不了 {unreadable}'.format(**stats)
        )

    if stats['unreadable']:
        print(
            f'⛔ 有 {stats["unreadable"]} 个跟踪文件读不出来，本次结论不可信（不是通过）',
            file=sys.stderr,
        )
        return 2

    if not findings:
        if args.report:
            print('✅ 未发现密钥字面量')
        return 0

    print(f'❌ 发现 {len(findings)} 处密钥字面量（红线：Token 一律走环境变量）：', file=sys.stderr)
    for finding in findings:
        print(f'  - {finding.render()}', file=sys.stderr)
    print(
        '\n处置：删掉字面量改读环境变量（`os.getenv` / `os.environ`）；'
        '示例一律写 `xxxx`。若确属示例/夹具，把值写成占位形态（含 `test` / `fake` / `xxxx` 等）。',
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
