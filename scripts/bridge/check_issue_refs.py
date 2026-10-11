#!/usr/bin/env python3
"""核对 issue 正文里的 `path:line` 引用是否还指向**真实存在的那一行**。

为什么需要它（源 CNB issue #118）
--------------------------------
镜像卡正文顶上写着「状态：`open`」这类字段，读者会当成权威事实；而正文里
`views/welcome/components/WelcomeAssetBoard.vue:119-130` 这种引用，**没有任何标记**
说明它取自哪个版本。实测（2026-10-11）那张卡引用的行号在 `dev` / `main` 上早已删除
（随 #980 拆页消失），下一个人照着不存在的代码动手——这不是作者写错，是流程里
缺一道「引用 vs 代码」的一致性检查。

本脚本把「核对成本」压到一条命令：抽取 → 逐条 `git show` → 报出失效项。
它也顺带钉住一条纪律：**引用具体行号时必须写 `@<ref>`**（见 `--strict-ref`），
否则核对者不知道拿哪个版本去比。

用法
----
    # 从 issue / PR 正文核对（走 gh CLI，只读）
    python scripts/bridge/check_issue_refs.py --issue 2034

    # 从文件 / stdin 核对（便于手工粘贴卡面）
    python scripts/bridge/check_issue_refs.py --file card.md --ref origin/dev

    # 要求所有引用都带 @ref，缺了就红灯（写卡时就该带）
    python scripts/bridge/check_issue_refs.py --file card.md --strict-ref

判据
----
- `path:line`：该文件在 `--ref` 下存在，且行数 ≥ line（越界即失效）；
- `path:line-end`：同上，取 end；
- `path@ref:line`：按 `@ref` 指定的版本核对（优先于 `--ref`）。

只读：本脚本永不改文件、永不改 issue、永不写仓库状态。退出码 0=全部有效，
1=有失效引用，2=用法错误。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# 匹配形如 `src/foo/Bar.vue:119-130` 或 `src/foo/Bar.vue@origin/dev:119`。
# 路径至少含一个 `/` 或一个扩展名——避免把 `#118`、`12:30` 这类误当成引用。
REF_RE = re.compile(
    r'(?<![\w/.-])'  # 左侧不能是路径字符（防匹配到 URL / 更长的路径尾巴）
    r'(?P<path>[A-Za-z0-9_][\w./-]*\.(?:vue|ts|mts|js|mjs|py|md|yml|yaml|json|css|scss|html))'
    r'(?:@(?P<ref>[\w./-]+))?'
    r':(?P<start>\d+)(?:-(?P<end>\d+))?'
    r'(?![\w-])'
)


def extract_refs(text: str) -> list[dict[str, object]]:
    """抽取正文里所有 `path[:@ref]:line[-end]` 引用（按出现顺序去重）。

    去掉围栏代码块 / 行内代码里的内容吗？**不去**——本仓的卡面大量把引用写在行内代码
    里（`` `Foo.vue:12` ``），去掉等于把要核对的对象删了。这正是与
    `close_linked_issues.js`（那里必须 `stripCode`）相反的一处，别照抄。
    """
    out: list[dict[str, object]] = []
    seen: set[tuple[str, str | None, int, int | None]] = set()
    for m in REF_RE.finditer(text or ''):
        key = (m.group('path'), m.group('ref'), int(m.group('start')), m.group('end'))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                'path': m.group('path'),
                'ref': m.group('ref'),
                'start': int(m.group('start')),
                'end': int(m.group('end')) if m.group('end') else None,
                'raw': m.group(0),
            }
        )
    return out


def _git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True)
    return r.returncode, (r.stdout or r.stderr or '').strip()


# 卡面里的路径常常是「从某个源码根写起」的（`views/welcome/...`、
# `services/summary_service.py`），而 git 要的是仓库根相对路径
# （`frontend/src/views/welcome/...`、`backend/app/services/summary_service.py`）。
# 按顺序试这些前缀，命中即用。
#
# **顺序有意义**：本仓 `frontend/` 与 `backend/` 下有大量同名目录（`services/`、
# `core/`、`domains/`、`models/`），前缀选错会把引用核对成**另一个文件**，
# 比报「不存在」更坏（给的是假安心）。故：
#   ① 空前缀（已经是仓库根相对路径）排第一；
#   ② `backend/app/` 在 `backend/` 之前——卡面写 `services/xxx.py` 时指的是
#      `backend/app/services/xxx.py`，而不是 `backend/services/xxx.py`；
#   ③ `scripts/` **不放进来**：它是本脚本自己的目录，放进来会让一句
#      `foo.py:1` 去试 `scripts/foo.py`，把「不存在」报成存在。
PATH_PREFIXES = (
    '',
    'frontend/src/',
    'frontend/',
    'backend/app/',
    'backend/',
    'docs/spec/',
    'docs/',
)

_PATH_CACHE: dict[tuple[str, str, str | None], tuple[str | None, str]] = {}


def _resolve_path(path: str, version: str, cwd: str | None) -> tuple[str | None, str]:
    """把卡面里的短路径补成仓库根相对路径。返回 (真实路径, 人类可读的说明)。

    两条路径：

    ① **前缀拼接**（快，覆盖绝大多数）：按 `PATH_PREFIXES` 逐个试 `git show`；
    ② **后缀唯一命中**（兜住裸文件名）：卡面常只写 `summary_service.py:392`，
       没有任何目录信息。此时列一次全仓文件，若**恰好一个**文件以该路径结尾，
       就认它；**零个或多个都判「无法核对」**。

    为什么第 ② 条必须要求唯一：按错误的文件核对会给出**假绿灯**，比报「不存在」
    更坏——本仓 `frontend/` 与 `backend/` 下同名文件很多，多命中时挑一个等于猜。
    """
    key = (path, version, cwd)
    if key in _PATH_CACHE:
        real, note = _PATH_CACHE[key]
        return real, note

    for prefix in PATH_PREFIXES:
        candidate = f'{prefix}{path}'
        code, _ = _git(['show', f'{version}:{candidate}'], cwd=cwd)
        if code == 0:
            _PATH_CACHE[key] = (candidate, '')
            return candidate, ''

    # ② 后缀唯一命中
    code, listing = _git(['ls-tree', '-r', '--name-only', version], cwd=cwd)
    if code == 0:
        suffix = f'/{path}'
        hits = [f for f in listing.splitlines() if f.endswith(suffix)]
        if len(hits) == 1:
            _PATH_CACHE[key] = (hits[0], f'（由裸文件名唯一命中：{hits[0]}）')
            return hits[0], f'唯一命中 {hits[0]}'
        if len(hits) > 1:
            note = f'{path} 在 `{version}` 上有 {len(hits)} 个同名文件，无法唯一确定引用对象'
            _PATH_CACHE[key] = (None, note)
            return None, note

    note = f'{path} 在 `{version}` 上不存在'
    _PATH_CACHE[key] = (None, note)
    return None, note


def check_ref(ref: dict[str, object], default_ref: str, cwd: str | None = None) -> str | None:
    """核对一条引用。返回 None 表示有效，否则返回人类可读的失效原因。"""
    path = str(ref['path'])
    version = str(ref['ref'] or default_ref)
    start = int(ref['start'])
    end = ref['end']
    highest = max(start, int(end)) if end else start

    real, note = _resolve_path(path, version, cwd)
    if real is None:
        return note

    _, content = _git(['show', f'{version}:{real}'], cwd=cwd)
    total = content.count('\n') + (0 if content.endswith('\n') else 1)
    if highest > total:
        return f'{real} 在 `{version}` 上只有 {total} 行，引用到 {highest} 行（越界）'
    return None


def load_body(args: argparse.Namespace) -> str:
    if args.issue:
        code, out = _git([])  # 占位：真正取正文走 gh
        cmd = ['gh', 'issue', 'view', str(args.issue), '--json', 'body', '-q', '.body']
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f'❌ 读取 issue #{args.issue} 失败：{r.stderr.strip()}', file=sys.stderr)
            raise SystemExit(2)
        return r.stdout
    if args.file:
        with open(args.file, encoding='utf-8') as fh:
            return fh.read()
    return sys.stdin.read()


def run(args: argparse.Namespace) -> int:
    body = load_body(args)
    refs = extract_refs(body)
    if not refs:
        print('✅ 正文里没有 `path:line` 形式的引用，无需核对')
        return 0

    missing_ref = [r for r in refs if not r['ref']]
    # 按 raw 文本做键：同一处引用重复出现时只报一次（extract_refs 已去重，
    # 但 raw 可能撞车，故用「索引 + raw」做稳定键）。
    checked: list[tuple[dict[str, object], str | None]] = [(r, check_ref(r, args.ref, cwd=args.cwd)) for r in refs]
    failed = [(r, why) for r, why in checked if why]

    print(f'🔍 共 {len(refs)} 条引用（默认版本 {args.ref}）')
    for r, why in checked:
        mark = '❌' if why else '✅'
        print(f'  {mark} {r["raw"]}')
        if why:
            print(f'       → {why}')

    code = 0
    if failed:
        print(f'\n❌ {len(failed)} 条引用已失效：卡面读过时了，改卡或改引用。')
        code = 1
    if args.strict_ref and missing_ref:
        print(f'\n❌ {len(missing_ref)} 条引用没写 `@<ref>`：核对者不知道拿哪个版本比。')
        print('   写法：`path/to/File.vue@origin/dev:119-130`')
        code = 1
    if code == 0:
        print('\n✅ 全部引用在当前版本上仍然有效')
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='核对 issue 正文的 path:line 引用是否有效')
    src = p.add_mutually_exclusive_group()
    src.add_argument('--issue', type=int, help='从 GitHub issue 正文核对（走 gh CLI）')
    src.add_argument('--file', help='从文件核对（不给则读 stdin）')
    p.add_argument('--ref', default='origin/dev', help='默认核对的版本（默认 origin/dev）')
    p.add_argument('--cwd', default=None, help='git 仓库路径（默认当前目录）')
    p.add_argument('--strict-ref', action='store_true', help='要求每条引用都写 @ref')
    p.add_argument('--json', action='store_true', help='以 JSON 输出，便于机器消费')
    args = p.parse_args(argv)

    if args.json:
        body = load_body(args)
        refs = extract_refs(body)
        out = []
        for r in refs:
            out.append({**r, 'valid': check_ref(r, args.ref, cwd=args.cwd) is None})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    return run(args)


if __name__ == '__main__':
    sys.exit(main())
