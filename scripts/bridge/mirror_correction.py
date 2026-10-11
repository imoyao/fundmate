#!/usr/bin/env python3
"""镜像卡更正台账：往 CNB 镜像卡评论区追加「更正评论」（#120 方案 B）。

为什么需要它
------------
`github_cnb_issues.py` 的取舍是「只增不覆盖」——CNB 侧人工调过的正文不会被覆盖，
但代价是 **GitHub 侧后来的更正永远传不过来**，镜像卡永久停在建卡快照上（活证据：CNB `#106`）。

本仓对原卡已有纪律（AGENTS.md「失实信息修正纪律」）：**用评论追加更正，禁止覆盖原正文**。
这条纪律在 GitHub 上能执行，在镜像卡上缺一条可执行的路径——镜像卡是只读的，下一个人
不知道要去 GitHub 看。本脚本把「在镜像卡评论区写更正」固化成命令，使纪律在 CNB 侧同样可执行。

边界（与 #120 一致）
--------------------
- **单向**：只在 CNB 写评论，**绝不回写 GitHub**（不违反现有取舍）。
- **只增**：不碰镜像卡正文、不改标签、不动状态。
- **幂等**：同一条更正重复执行只发一次，靠正文里的幂等键 `更正键：`（由卡片编号 +
  更正日期 + 摘要哈希拼成）判重，已存在则跳过（`--force` 可强制重发，供返工时用）。
- **纯标准库**：复用 `github_cnb_issues.py` 的 `cnb_api`，无需 pip install。

更正评论的固定格式（写在镜像卡正文里，读者据此知道该写成什么样）
----------------------------------------------------------------
    ## 更正（2026-10-11）

    - ❌ 正文「…」→ ✅ 实际「…」（依据：PR #115）

用法
----
    export CNB_TOKEN=<你的 token>

    # ① 先看台账现状：某张镜像卡已经记过哪些更正
    python scripts/bridge/mirror_correction.py list --cnb 106

    # ② 写更正（默认 dry-run，只打印将发布的正文）
    python scripts/bridge/mirror_correction.py add --cnb 106 --date 2026-10-11 \\
        --correction '正文「WelcomeAssetBoard.vue:119-130」→ 实际该行已随 #980 拆页删除（依据：PR #980）'

    # ③ 确认无误后真正发布
    python scripts/bridge/mirror_correction.py add --cnb 106 --date 2026-10-11 \\
        --correction '…' --apply
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from github_cnb_issues import MIRROR_LABEL, cnb_api  # noqa: E402

# 幂等键：`更正键：<sha1 前 12 位>`。写在评论正文末尾的 HTML 注释里，
# 读者看不见，脚本看得见 —— 也顺带避免了「更正说明本身被当成更正条目」。
IDEMPOTENCY_KEY_RE = re.compile(r'更正键：([0-9a-f]{12})')
IDEMPOTENCY_LINE = '<!-- 更正键：{} -->'

HEADING_RE = re.compile(r'^##\s*更正（(\d{4}-\d{2}-\d{2})）\s*$', re.MULTILINE)


def make_key(cnb_number: int, date: str, bullets: list[str]) -> str:
    """幂等键 = sha1(卡片编号 + 日期 + 逐条摘要)。

    与发布顺序无关（bullets 先排序），故「同一条更正换个顺序重发」仍能被判重。
    """
    digest = hashlib.sha1()
    digest.update(f'{cnb_number}|{date}|'.encode())
    for b in sorted(bullets):
        digest.update(b.strip().encode())
        digest.update(b'\x00')
    return digest.hexdigest()[:12]


def build_comment(date: str, bullets: list[str], key: str) -> str:
    """拼更正评论正文：固定标题 + 逐条 ❌/✅ + 隐藏幂等键。"""
    lines = [f'## 更正（{date}）', '']
    lines.extend(f'- {b.strip()}' for b in bullets)
    lines.extend(['', IDEMPOTENCY_LINE.format(key)])
    return '\n'.join(lines)


def parse_comments(raw: Any) -> list[dict[str, str]]:
    """把 CNB 评论列表归一化成 [{body, id}]。

    CNB 的 `?comment_type=comment`（分页参数）实际会返回顶层评论，
    元素的正文放在 `body` 或 `note` 里（不同接口版本有差异），两者都认。
    """
    if isinstance(raw, dict):
        raw = raw.get('comments') or raw.get('items') or []
    out: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                'id': str(item.get('id') or item.get('note_id') or ''),
                'body': str(item.get('body') or item.get('note') or ''),
            }
        )
    return out


def list_issue_comments(cnb_number: int, *, repo: str | None = None) -> list[dict[str, str]]:
    """拉某张 CNB 卡的评论（分页拉全）。"""
    from github_cnb_issues import _cnb_repo

    out: list[dict[str, str]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({'page': page, 'page_size': 100})
        batch = parse_comments(cnb_api(f'/{repo or _cnb_repo()}/-/issues/{cnb_number}/comments?{qs}'))
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def existing_keys(comments: list[dict[str, str]]) -> set[str]:
    """已发布过的更正幂等键集合。"""
    return {m.group(1) for c in comments for m in IDEMPOTENCY_KEY_RE.finditer(c['body'])}


def is_mirror_card(cnb_number: int, *, repo: str | None = None) -> bool:
    """确认这是一张 GitHub 镜像卡，避免更正写到人工卡上。

    CNB 的 issue 详情用 `labels` 字段（字符串数组），不是 `tags`；旧版返回字符串时也认。
    """
    from github_cnb_issues import _cnb_repo, extract_github_number

    detail = cnb_api(f'/{repo or _cnb_repo()}/-/issues/{cnb_number}') or {}
    labels = [lb.get('name') if isinstance(lb, dict) else str(lb) for lb in (detail.get('labels') or [])]
    return MIRROR_LABEL in labels or extract_github_number(detail.get('body')) is not None


def post_comment(cnb_number: int, body: str, *, repo: str | None = None) -> Any:
    from github_cnb_issues import _cnb_repo

    return cnb_api(
        f'/{repo or _cnb_repo()}/-/issues/{cnb_number}/comments',
        method='POST',
        payload={'body': body},
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_list(cnb_number: int, repo: str | None) -> int:
    comments = list_issue_comments(cnb_number, repo=repo)
    ledger = [c for c in comments if IDEMPOTENCY_KEY_RE.search(c['body'])]
    print(f'CNB #{cnb_number}：评论 {len(comments)} 条，其中更正 {len(ledger)} 条')
    for c in ledger:
        print('─' * 60)
        print(c['body'].split(IDEMPOTENCY_LINE.format('').split('：')[0])[0].rstrip())
    return 0


def run_add(
    cnb_number: int,
    date: str,
    corrections: list[str],
    *,
    repo: str | None,
    apply: bool,
    force: bool,
) -> int:
    if not HEADING_RE.match(f'## 更正（{date}）'):
        print(f'❌ 日期格式不对：{date}（应为 YYYY-MM-DD）')
        return 1
    if not corrections:
        print('❌ 至少给一条 --correction')
        return 1

    if not is_mirror_card(cnb_number, repo=repo):
        print(f'❌ CNB #{cnb_number} 不是 GitHub 镜像卡（无 `{MIRROR_LABEL}` 标签、也读不到 GitHub 编号），拒绝写入')
        return 1

    key = make_key(cnb_number, date, corrections)
    published = existing_keys(list_issue_comments(cnb_number, repo=repo))
    body = build_comment(date, corrections, key)

    if key in published and not force:
        print(f'⏭️  这条更正已发布过（更正键 {key}），跳过。返工要重发请加 --force。')
        return 0

    if not apply:
        print(f'[DRY-RUN] 将在 CNB #{cnb_number} 追加评论（更正键 {key}）：\n')
        print(body)
        return 0

    post_comment(cnb_number, body, repo=repo)
    print(f'✅ 已在 CNB #{cnb_number} 追加更正评论（更正键 {key}）')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='往 CNB 镜像卡追加「更正台账」评论（#120 方案 B）')
    parser.add_argument('--repo', default=None, help='CNB 仓库，默认从 CNB_REPO_SLUG 环境变量识别')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_list = sub.add_parser('list', help='列出某张镜像卡已记的更正')
    p_list.add_argument('--cnb', type=int, required=True, help='CNB 卡编号')

    p_add = sub.add_parser('add', help='追加一条更正')
    p_add.add_argument('--cnb', type=int, required=True, help='CNB 卡编号')
    p_add.add_argument('--date', required=True, help='更正日期 YYYY-MM-DD')
    p_add.add_argument(
        '--correction',
        action='append',
        default=[],
        help='一条更正，格式：❌ 原文「…」→ ✅ 实际「…」（依据：PR/commit）。可重复传。',
    )
    p_add.add_argument('--apply', action='store_true', help='真正发布（默认 dry-run）')
    p_add.add_argument('--force', action='store_true', help='已发布过也重发（返工用）')

    args = parser.parse_args(argv)
    if args.cmd == 'list':
        return run_list(args.cnb, args.repo)
    return run_add(
        args.cnb,
        args.date,
        args.correction,
        repo=args.repo,
        apply=args.apply,
        force=args.force,
    )


if __name__ == '__main__':
    sys.exit(main())
