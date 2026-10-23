#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守门：入库的前端 env 文件里，Supabase 凭证必须「完整、且示例里不含真实值」（#1028）。

WHY —— 为什么要有这条守卫
----------------------
#1028 的原始故障形态是「开发与生产共用同一个 Supabase 项目」：开发期注册的测试账号
直接写进**生产** Auth 用户表，而当时**没有任何一处会报错**。

这条守卫只管**入库文件**（CI 看得见的那些），分两半：

- **完整性**：`frontend/.env.production` / `.env.staging` 必须同时给出
  `VITE_SUPABASE_URL` 与 `VITE_SUPABASE_ANON_KEY`，且 URL 形态合法。
  缺项时的真实故障形态是 `createBrowserClient(undefined, undefined)` 在浏览器里抛错
  ⇒ **构建期就该红**，而不是等用户点登录才发现。
- **示例文件的卫生**：`frontend/.env.example` 是新人抄配置的入口，
  它里若出现**真实的** URL / anon key，等于把生产凭证抄进下一个仓库。
  故示例里只允许占位形态。

⚠️ 本守卫**不覆盖**「dev 与 prod 是否指向同一项目」——那个判定需要读**不入库**的
`frontend/.env.development`，CI 看不到它，故由 `frontend/build/supabase-env-guard.ts`
在 **dev server 启动**时兜（两条规则不重叠、各有唯一实现）。
「守门之间覆盖范围重叠」会让下一次改动不知道该改哪一处，故此处显式声明边界。

判据
----
1. `frontend/.env.production`：`VITE_SUPABASE_URL` 存在且匹配 `https://<ref>.supabase.co`；
   `VITE_SUPABASE_ANON_KEY` 存在且非空。
2. `frontend/.env.staging`：同上。
3. `frontend/.env.example`：`VITE_SUPABASE_URL` 若存在，必须是占位（含 `<` 或 `>`）；
   `VITE_SUPABASE_ANON_KEY` 若存在，必须是占位（不含两个点、且不以 `sb_publishable_` /
   `sb_secret_` 开头）。

⚠️ **失败态（AGENTS.md「拿不到输入 ≠ 输入为空」）**
读不到任何被检查的文件 ⇒ **必须报红**（退出码 2），不得退化成「没有可检查的项 ⇒ 通过」。
那正是「守门自己失明、却每轮报绿」的形态。

用法
----
    python scripts/guard_supabase_env_separation.py            # 校验（CI）
    python scripts/guard_supabase_env_separation.py --quiet    # 只在失败时输出

退出码：0 = 通过；1 = 命中；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / 'frontend'

# 生产 / 预发两个入库文件：都必须给出完整的凭证
CREDENTIAL_FILES = ('.env.production', '.env.staging')
# 示例文件：只允许占位
EXAMPLE_FILE = '.env.example'

SUPABASE_URL_KEY = 'VITE_SUPABASE_URL'
SUPABASE_ANON_KEY = 'VITE_SUPABASE_ANON_KEY'

# 合法形态：https://<ref>.supabase.co（ref 为小写字母/数字/连字符）
_SUPABASE_URL_RE = re.compile(r'^https://[a-z0-9-]+\.supabase\.co/?$')
# 示例文件里允许的占位形态（含尖括号或 TODO 之类的大写词）
_PLACEHOLDER_MARKERS = ('<', '>', 'xxxx', 'TODO', 'your-', 'your_')


def parse_env(content: str) -> dict[str, str]:
    """解析 dotenv 文本 → {变量名: 值}。忽略空行与 `#` 开头的注释，去掉成对引号。"""
    out: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        else:
            hash_pos = value.find(' #')
            if hash_pos >= 0:
                value = value[:hash_pos].strip()
        if key:
            out[key] = value
    return out


def _looks_like_placeholder(value: str) -> bool:
    """判断示例文件里的取值是否是占位（而不是真实凭证）。"""
    if not value:
        return True
    lowered = value.lower()
    if any(marker.lower() in lowered for marker in _PLACEHOLDER_MARKERS):
        return True
    # 新版 publishable / secret key 一律视为真实值
    if lowered.startswith('sb_publishable_') or lowered.startswith('sb_secret_'):
        return False
    # 旧版 anon key 是三段 JWT（含两个点）；真值几乎必然是这种形态
    if value.count('.') >= 2:
        return False
    return True


def check_credential_file(filename: str, content: str) -> list[str]:
    """校验一个「必须给出完整凭证」的 env 文件，返回问题列表。"""
    problems: list[str] = []
    env = parse_env(content)

    url = env.get(SUPABASE_URL_KEY, '')
    if not url:
        problems.append(
            f'frontend/{filename} 缺少 {SUPABASE_URL_KEY}：'
            f'生产构建将拿不到 Supabase 地址（createBrowserClient 会拿到 undefined）。'
        )
    elif not _SUPABASE_URL_RE.match(url):
        problems.append(
            f'frontend/{filename} 的 {SUPABASE_URL_KEY} 形态非法'
            f'（期望 https://<ref>.supabase.co）——实际值不打印以免泄露。'
        )

    anon_key = env.get(SUPABASE_ANON_KEY, '')
    if not anon_key:
        problems.append(
            f'frontend/{filename} 缺少 {SUPABASE_ANON_KEY}：该环境将无法登录。'
        )
    # 注意：生产/预发文件里的 anon key **就该是真实值**（anon key 按设计公开、受 RLS 保护），
    # 「只放占位」这条只适用于示例文件（见 check_example_file）。

    return problems


def check_example_file(content: str) -> list[str]:
    """校验示例文件：只允许占位形态的 Supabase 取值。"""
    problems: list[str] = []
    env = parse_env(content)

    url = env.get(SUPABASE_URL_KEY, '')
    if url and not _looks_like_placeholder(url):
        problems.append(
            f'frontend/{EXAMPLE_FILE} 的 {SUPABASE_URL_KEY} 是真实项目地址而非占位——'
            f'示例文件是新人抄配置的入口，真实地址会把它抄进下一个仓库。'
        )

    anon_key = env.get(SUPABASE_ANON_KEY, '')
    if anon_key and not _looks_like_placeholder(anon_key):
        problems.append(
            f'frontend/{EXAMPLE_FILE} 的 {SUPABASE_ANON_KEY} 是真实凭证而非占位——'
            f'示例文件里只放占位值（如 xxxx）。'
        )

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(
        description='前端入库 env 文件的 Supabase 凭证完整性守门（#1028）'
    )
    ap.add_argument('--quiet', action='store_true', help='只在失败时输出')
    args = ap.parse_args()

    # Windows 控制台默认 GBK，直接 print 中文/符号会 UnicodeEncodeError 崩掉——
    # 守门在本地跑崩 = 守门失效。统一把输出流切到 UTF-8。
    for _stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(_stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8')
            except (AttributeError, ValueError, OSError):
                pass

    targets = [FRONTEND_DIR / name for name in (*CREDENTIAL_FILES, EXAMPLE_FILE)]
    missing = [p for p in targets if not p.exists()]
    if missing:
        for p in missing:
            print(f'[FAIL] 找不到文件：{p}', file=sys.stderr)
        print('[FAIL] 结论不可信（拿不到输入 ≠ 输入为空）。', file=sys.stderr)
        return 2

    problems: list[str] = []
    for name in CREDENTIAL_FILES:
        problems.extend(
            check_credential_file(name, (FRONTEND_DIR / name).read_text(encoding='utf-8'))
        )
    problems.extend(
        check_example_file((FRONTEND_DIR / EXAMPLE_FILE).read_text(encoding='utf-8'))
    )

    if problems:
        print(
            f'[FAIL] 前端 env 凭证守门失败（{len(problems)} 项）：\n', file=sys.stderr
        )
        for p in problems:
            print(f'  · {p}', file=sys.stderr)
        return 1

    if not args.quiet:
        print(
            '[OK] 前端 env 凭证守门通过：'
            f'{"、".join(CREDENTIAL_FILES)} 均含完整的 Supabase 凭证，'
            f'{EXAMPLE_FILE} 只含占位值'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
