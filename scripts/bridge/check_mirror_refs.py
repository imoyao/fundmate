#!/usr/bin/env python3
"""扫描 CNB 镜像卡，把**正文里已失效的 `path:line` 引用**报出来。

为什么需要它（源 CNB issue #118）
--------------------------------
镜像卡的三条取舍里有一条是「**只增不覆盖**」：已建好的卡永不改动。这保住了 CNB 侧
的人工调整，代价是 **GitHub 侧后来的更正永远传不过来**——包括「正文引用的那行代码
已经删了」这件事本身。

实测（2026-10-11）：#106（GitHub #2034）正文引用 `WelcomeAssetBoard.vue:119-130`，
该行随 #980 拆页删除、#1955 又改了口径，卡面描述的是两个版本之前的代码。而按现行
机制我们**没有任何办法发现它**——只能靠下一个人读到时运气好去 `git show` 验一遍。

本脚本把「运气」换成「作业」：批量扫全部镜像卡，报出失效引用。

判据
----
对每张镜像卡的正文：
1. 抽取 `path:line` / `path@ref:line` 引用（复用 `check_issue_refs.py`，同一套正则）；
2. 按 `--ref`（默认 `origin/dev`）逐条核对；
3. 卡面**自带 `@ref`** 的按其指定的版本核对——这是本卡倡导的写法，得尊重。

边界（有意为之）
----------------
- **只报告，不改卡**：改镜像卡正文需要产品拍板（见 CNB #120），本脚本不越界；
- **不回写 GitHub**：与本仓「镜像单向」的取舍一致；
- CNB 侧只读（匿名可读公开仓库；给了 `CNB_TOKEN` 就用）。

用法
----
    # 看当前有哪些镜像卡的引用已失效（只读，走 CNB + 本地 git）
    python scripts/bridge/check_mirror_refs.py --report

    # 输出到文件（供 CI 归档）
    python scripts/bridge/check_mirror_refs.py --report --out refs-report.md

    # 只查某几张卡
    python scripts/bridge/check_mirror_refs.py --report --issue 106 --issue 104
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
CNB_REPO_DEFAULT = 'duoduobei/fundmate'
MIRROR_LABEL = 'GitHub 同步'
# 与 github_cnb_issues.py 的幂等键一致：镜像卡正文里必有这一行
GITHUB_NUMBER_RE = __import__('re').compile(r'GitHub 编号：`#(\d+)`')


def _load_checker() -> Any:
    """复用 `check_issue_refs.py` 的抽取 / 核对逻辑 —— 不抄第二份正则。

    抄一份的代价不是「多几行」，而是**两份判据会漂移**：今天加个后缀、明天改个
    边界，漂移之后哪份绿都说明不了问题（本仓 `AGENTS.md` 对同类问题的原话是
    「复刻等于把被测逻辑抄一份，抄错的那份才是绿的」）。
    """
    spec = importlib.util.spec_from_file_location('check_issue_refs', SCRIPT_DIR / 'check_issue_refs.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['check_issue_refs'] = module
    spec.loader.exec_module(module)
    return module


def cnb_get(path: str) -> Any:
    """只读调 CNB OpenAPI。公开仓库匿名即可；有 token 就带上。"""
    base = (os.environ.get('CNB_API_ENDPOINT') or 'https://api.cnb.cool').rstrip('/')
    req = urllib.request.Request(f'{base}{path}')
    req.add_header('User-Agent', 'fundmate-mirror-ref-check')
    req.add_header('Accept', 'application/vnd.cnb.api+json')
    token = os.environ.get('CNB_TOKEN')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def list_mirror_cards(repo: str) -> list[dict[str, Any]]:
    """列出所有带镜像标签的卡（含已关闭——过期的卡同样误导人）。"""
    out: list[dict[str, Any]] = []
    for state in ('open', 'closed'):
        page = 1
        while True:
            qs = urllib.parse.urlencode({'page': page, 'page_size': 100, 'state': state})
            batch = cnb_get(f'/{repo}/-/issues?{qs}') or []
            if not batch:
                break
            for it in batch:
                names = [(lb.get('name') if isinstance(lb, dict) else lb) for lb in (it.get('labels') or [])]
                if MIRROR_LABEL in names:
                    out.append(it)
            if len(batch) < 100:
                break
            page += 1
    return out


def build_report(rows: list[dict[str, Any]], default_ref: str) -> str:
    stale = [r for r in rows if r['stale']]
    lines = [
        '## 镜像卡引用时效自检',
        '',
        f'- 扫描镜像卡：{len(rows)} 张（默认核对版本 `{default_ref}`）',
        f'- **引用已失效**：{len(stale)} 张',
        '',
    ]
    if not stale:
        lines.append('✅ 全部镜像卡正文里的 `path:line` 引用在当前版本上仍然有效。')
        return '\n'.join(lines)

    lines += ['| CNB | GitHub | 失效引用 | 原因 |', '|---|---|---|---|']
    for r in stale:
        for ref, why in r['stale']:
            lines.append(
                f'| #{r["cnb"]} | [#{r["github"]}](https://github.com/{r["gh_repo"]}/issues/{r["github"]}) | `{ref}` | {why} |'
            )
    lines += [
        '',
        '> 镜像卡「只增不覆盖」，正文不会自动更正。处置方式见 `AGENTS.md`「失实信息修正纪律」：',
        '> 在原卡追加更正评论，**不要**改正文。',
    ]
    return '\n'.join(lines)


def run(args: argparse.Namespace) -> int:
    checker = _load_checker()
    repo = args.repo
    cards = list_mirror_cards(repo)
    if args.issue:
        wanted = {int(n) for n in args.issue}
        cards = [c for c in cards if int(c['number']) in wanted]
    print(f'🔍 镜像卡 {len(cards)} 张，逐张读取正文…')

    rows: list[dict[str, Any]] = []
    for card in cards:
        number = int(card['number'])
        try:
            detail = cnb_get(f'/{repo}/-/issues/{number}')
        except Exception as exc:  # noqa: BLE001
            print(f'  ⚠️ 读取 CNB #{number} 失败，跳过：{exc}')
            continue
        body = detail.get('body') or ''
        m = GITHUB_NUMBER_RE.search(body)
        refs = checker.extract_refs(body)
        stale = []
        for ref in refs:
            why = checker.check_ref(ref, args.ref, cwd=args.cwd)
            if why:
                stale.append((ref['raw'], why))
        rows.append(
            {
                'cnb': number,
                'github': int(m.group(1)) if m else None,
                'gh_repo': os.environ.get('GITHUB_REPO') or 'imoyao/fundmate',
                'title': (card.get('title') or '')[:60],
                'refs': len(refs),
                'stale': stale,
            }
        )

    report = build_report(rows, args.ref)
    print()
    print(report)
    if args.out:
        Path(args.out).write_text(report + '\n', encoding='utf-8')
        print(f'\n📄 报告已写入 {args.out}')
    # 只报告不失败：调用方（.cnb.yml）用 `|| true` 明确表达「这是信号不是门禁」，
    # 这里也返回 0，避免「一不小心就红了建卡作业」。
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='扫描 CNB 镜像卡里已失效的 path:line 引用')
    p.add_argument('--report', action='store_true', help='输出 markdown 报告（默认行为）')
    p.add_argument('--repo', default=CNB_REPO_DEFAULT, help=f'CNB 仓库（默认 {CNB_REPO_DEFAULT}）')
    p.add_argument('--ref', default='origin/dev', help='核对版本（默认 origin/dev）')
    p.add_argument('--cwd', default=None, help='git 仓库路径（默认当前目录）')
    p.add_argument('--issue', action='append', help='只查指定 CNB 卡号（可重复）')
    p.add_argument('--out', default=None, help='报告写入文件')
    return run(p.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
