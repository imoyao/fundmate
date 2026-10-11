#!/usr/bin/env python3
"""CNB Issues → GitHub Issues 回写（评论镜像 + 状态对账）。

为什么需要它
------------
`github_cnb_issues.py` 只做 GitHub → CNB 的单向建卡，CNB 侧积累的讨论回流不到
GitHub——在 CNB 上把一张卡分析完、结论写在 CNB 评论里，GitHub 上的人完全看不到，
两边各说各话。本脚本补上反向那条腿。

为什么由 GitHub Actions 来跑（而不是 CNB 侧推）
----------------------------------------------
CNB 构建内的环境**没有**任何 GitHub 凭证（`env` 里只有 `CNB_*`，`api.github.com`
匿名 POST 返回 401），所以「CNB 去写 GitHub」在当前环境里做不到。反方向的凭据是
现成的：GitHub Actions 里 `GITHUB_TOKEN` 自动注入且带 `issues: write`。故采用
**GitHub 定时拉取 CNB** 的拓扑——不需要在 CNB 存 GitHub PAT，也不需要 CNB 有写权限。

三条设计取舍（与镜像方向互为镜像）
--------------------------------
- **单向**：只 CNB → GitHub，绝不在 CNB 建/改任何东西。CNB 侧是只读消费。
- **只增不覆盖**：已回写过的评论永不重发、永不编辑（幂等标记见下）。CNB 侧改过的
  评论不会把 GitHub 上的旧副本改掉——历史被改写比留个过时副本更糟。
- **状态只会计数，不会自动关**：GitHub 只接受「有评论提到它」的中转，不替人做
  「这卡到底做完了没」的判断（#1177 用 PR 状态代验收的教训）。

幂等键
------
每条回写评论末尾带一行隐藏标记：

    <!-- cnb-backfill: issue=2 comment=2109119676427591680 -->

回写前先把目标 issue 的**全部**评论扫一遍收集标记（GitHub 单 issue 评论数 ≤ 100，
一次分页调用就够），已存在的 CNB 评论 id 直接跳过。所以同一天跑十遍只会发一遍。

网络与依赖
----------
纯标准库（urllib），零 pip 依赖。
- CNB：匿名 `api.cnb.cool` 对**公开仓库**无需 token；给了 `CNB_TOKEN` 也用不上（那是
  CNB 侧的凭证，GitHub runner 上没有）。私有仓库要自己配一个只读 token 传进来。
- GitHub：`GITHUB_TOKEN`（Actions 自动注入，`issues: write` 足够）。

用法
----
    python scripts/bridge/cnb_github_backfill.py --dry-run       # 只看要回写什么
    python scripts/bridge/cnb_github_backfill.py --apply         # 真正回写
    python scripts/bridge/cnb_github_backfill.py --apply --since 2026-10-01
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / 'cnb_github_backfill_state.json'

# 与本仓库 AGENTS.md / issue #2 的历史口径保持一致：CNB 侧是 duoduobei/fundmate，
# GitHub 侧是 imoyao/fundmate。
CNB_REPO_DEFAULT = 'duoduobei/fundmate'
GITHUB_REPO_DEFAULT = 'imoyao/fundmate'

# 回写评论的隐藏标记。**不可改**——它是幂等键，改了等于把所有已有回写认成「没写过」，
# 下一轮会把全部评论重发一遍。
MARKER_PREFIX = '<!-- cnb-backfill:'
MARKER_RE = re.compile(r'<!--\s*cnb-backfill:\s*issue=(\d+)\s+comment=(\d+)\s*-->')

# GitHub 评论正文上限 65536 字符。CNB 单条评论没有这么长的，但截断总比 422 好。
MAX_BODY = 60000

# 超过这个长度的正文会在回写评论里折叠（GitHub 原生 <details>），避免长评论刷屏。
COLLAPSE_THRESHOLD = 2000

# 机器人账号不回流：两侧各有自己的机器人（CNB 的 OCI / CodeBuddy，GitHub 的
# github-actions[bot] 等），把它们的输出互相搬运只会造成回声。
_BOT_SUFFIXES = ('[bot]',)
_BOT_NAMES = {'OCI', 'CodeBuddy'}


# ---------------------------------------------------------------------------
# 纯函数（被 backend/tests/test_cnb_github_backfill.py 覆盖）
# ---------------------------------------------------------------------------


def now_utc() -> str:
    return datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def is_bot(author: dict[str, Any] | None) -> bool:
    """判断评论作者是不是机器人（不该回流）。

    CNB 的 NPC 用 `is_npc: true` 明示；用户名后缀 `[bot]` 与几个已知名字是兜底
    ——历史数据里 NPC 的 `is_npc` 不一定都填了。
    """
    if not author:
        return False
    username = (author.get('username') or '').strip()
    nickname = (author.get('nickname') or '').strip()
    if author.get('is_npc') is True:
        return True
    if any(username.lower().endswith(s) for s in _BOT_SUFFIXES):
        return True
    return username in _BOT_NAMES or nickname in _BOT_NAMES


def backfill_marker(cnb_issue: int, cnb_comment: Any) -> str:
    """回写评论的幂等标记（HTML 注释，渲染时不可见）。

    同时登记 issue 号与评论 id：前者让「这张卡一共回写了多少」可数，后者是真正的
    去重键（CNB 的评论 id 是全局唯一雪花号）。
    """
    return f'{MARKER_PREFIX} issue={cnb_issue} comment={cnb_comment} -->'


def collect_markers(comments: list[dict[str, Any]]) -> set[tuple[int, int]]:
    """从目标 issue 的已有评论里收集 (cnb_issue, cnb_comment) 幂等键。"""
    found: set[tuple[int, int]] = set()
    for c in comments:
        for m in MARKER_RE.finditer(c.get('body') or ''):
            found.add((int(m.group(1)), int(m.group(2))))
    return found


def build_comment(cnb_issue: int, comment: dict[str, Any]) -> str:
    """拼一条回写到 GitHub 的评论。

    形态：来源说明 + 原文（长文折叠）+ 隐藏幂等标记。
    来源说明里带 CNB 原评论的 id，方便反查；`@{user}` 用原样 grep 得到，
    不做 @ 提及（避免无意 ping 真人）。
    """
    author = comment.get('author') or {}
    who = author.get('nickname') or author.get('username') or 'unknown'
    when = str(comment.get('created_at') or '')[:19].replace('T', ' ')
    body = comment.get('body') or ''

    header = (
        f'> 💬 **本评论由 CNB 回写**（来源：CNB #{cnb_issue}，评论 id `{comment.get("id")}`）\n'
        f'>\n'
        f'> - 作者：{who}　时间：{when} UTC\n'
        f'>\n'
        f'> ⚠️ 正文为 CNB 侧原文的副本，仅追加不回改；后续讨论请在**本卡**继续。\n'
    )

    if len(body) > COLLAPSE_THRESHOLD:
        quoted = f'<details>\n<summary>展开 CNB 侧原文（{len(body)} 字）</summary>\n\n{body}\n\n</details>'
    else:
        quoted = body

    marker = backfill_marker(cnb_issue, comment.get('id'))
    text = f'{header}\n{quoted}\n\n{marker}\n'

    if len(text) > MAX_BODY:
        # **截断必须保住标记**：标记是幂等键，切掉了下一轮就会把这条评论重发一遍
        # （而且 GitHub 上发出去的评论不能被脚本静默撤回）。所以先把带标记的尾巴
        # 留出来，再按剩余额度裁正文。
        keep = MAX_BODY - len(marker) - 1
        return f'{text[:keep]}\n{marker}'
    return text


def parse_ts(value: str | None) -> datetime | None:
    """解析 ISO 时间戳（容忍末尾 Z 与空值）。解不出返回 None。"""
    if not value:
        return None
    try:
        # Python 3.11+ 的 fromisoformat 直接认末尾 Z，不必手工换成 +00:00
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HTTP（标准库）
# ---------------------------------------------------------------------------


def _request(
    url: str,
    *,
    method: str = 'GET',
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> bytes:
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('User-Agent', 'fundmate-cnb-github-backfill')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cnb_api(path: str) -> Any:
    """调 CNB 只读 OpenAPI（匿名可读公开仓库）。

    `Authorization` 是 Bearer 且 `Accept` 必须是 `application/vnd.cnb.api+json`，
    否则拿到的是网页 HTML —— 细节同 github_cnb_issues.py。
    """
    base = (os.environ.get('CNB_API_ENDPOINT') or 'https://api.cnb.cool').rstrip('/')
    headers = {'Accept': 'application/vnd.cnb.api+json'}
    token = os.environ.get('CNB_READ_TOKEN') or os.environ.get('CNB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    raw = _request(f'{base}{path}', headers=headers)
    return json.loads(raw) if raw else None


def github_api(path: str, *, method: str = 'GET', payload: dict | None = None) -> Any:
    """调 GitHub REST API。

    **读**（GET）允许匿名 —— 这样才能真正本地 `--dry-run` 一遍而不用先配 PAT；
    匿名限额 60 次/时/IP，dry-run 的调用量远低于此。
    **写**（POST）必须带 token：没 token 直接抛，别等到 GitHub 回 401 才让人猜。
    """
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_PAT')
    if method != 'GET' and not token:
        raise RuntimeError('缺少 GITHUB_TOKEN（Actions 内自动注入；本地跑请显式 export）')
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'

    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    if data is not None:
        headers['Content-Type'] = 'application/json'
    raw = _request(f'https://api.github.com{path}', method=method, data=data, headers=headers)
    return json.loads(raw) if raw else None


def list_cnb_issues() -> list[dict[str, Any]]:
    """列 CNB 仓库全部 issue（open + closed）。

    关闭的卡也要拉：卡片常是「讨论完 → 关掉」，而不回写等于把讨论整段丢掉。
    """
    repo = os.environ.get('CNB_REPO') or CNB_REPO_DEFAULT
    out: list[dict[str, Any]] = []
    for state in ('open', 'closed'):
        page = 1
        while True:
            qs = urllib.parse.urlencode({'page': page, 'page_size': 100, 'state': state})
            batch = cnb_api(f'/{repo}/-/issues?{qs}') or []
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return out


def get_cnb_issue(number: int) -> dict[str, Any]:
    """取单张 CNB 卡的详情。

    **必须走这里才能拿到 `body`**：CNB 的列表接口不返回正文（实测 `page_size=100`
    的返回里没有 `body` 键，加 `detail` 参数也没用），而「这张卡对应哪个 GitHub
    issue」只能从正文里的溯源块读。故映射阶段是列表 + 逐张详情两步。
    """
    repo = os.environ.get('CNB_REPO') or CNB_REPO_DEFAULT
    return cnb_api(f'/{repo}/-/issues/{number}') or {}


def list_cnb_comments(number: int) -> list[dict[str, Any]]:
    """列单张 CNB 卡的全部评论（分页拉全）。"""
    repo = os.environ.get('CNB_REPO') or CNB_REPO_DEFAULT
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({'page': page, 'page_size': 100})
        batch = cnb_api(f'/{repo}/-/issues/{number}/comments?{qs}') or []
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def list_github_comments(github_repo: str, number: int) -> list[dict[str, Any]]:
    """列 GitHub issue 的全部评论（分页拉全），用于收集幂等标记。"""
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode({'per_page': 100, 'page': page})
        batch = github_api(f'/repos/{github_repo}/issues/{number}/comments?{qs}')
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def post_github_comment(github_repo: str, number: int, body: str) -> dict[str, Any]:
    return github_api(
        f'/repos/{github_repo}/issues/{number}/comments',
        method='POST',
        payload={'body': body},
    )


# ---------------------------------------------------------------------------
# 映射与状态
# ---------------------------------------------------------------------------


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {'last_sync_at': None, 'backfilled': {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def resolve_github_number(cnb_issue: dict[str, Any]) -> int | None:
    """一张 CNB 卡对应哪个 GitHub issue？只从正文里的 GitHub 链接认，不猜。

    镜像卡正文顶部有 `https://github.com/<repo>/issues/<N>`（由 GitHub→CNB 脚本写入），
    这里把它抠出来。抠不到就跳过——**宁可漏，不可错**：猜错编号等于把评论贴到别人卡上。
    """
    body = cnb_issue.get('body') or ''
    repo = re.escape(os.environ.get('GITHUB_REPO') or GITHUB_REPO_DEFAULT)
    m = re.search(rf'https://github\.com/{repo}/issues/(\d+)', body)
    return int(m.group(1)) if m else None


def pending_comments(
    cnb_issue_number: int,
    cnb_comments: list[dict[str, Any]],
    existing: set[tuple[int, int]],
    since: datetime | None,
) -> list[dict[str, Any]]:
    """挑出还没回写过的评论（按时间正序）。"""
    out: list[dict[str, Any]] = []
    for c in cnb_comments:
        cid = c.get('id')
        if cid is None or is_bot(c.get('author')):
            continue
        if (cnb_issue_number, int(cid)) in existing:
            continue
        created = parse_ts(c.get('created_at'))
        if since and created and created < since:
            continue
        out.append(c)
    out.sort(key=lambda c: str(c.get('created_at') or ''))
    return out


def run(*, dry_run: bool, limit: int | None, since: datetime | None) -> int:
    github_repo = os.environ.get('GITHUB_REPO') or GITHUB_REPO_DEFAULT
    state = load_state()
    backfilled: dict[str, Any] = state.setdefault('backfilled', {})

    cnb_issues = list_cnb_issues()
    print(f'📥 CNB issue {len(cnb_issues)} 张（open + closed）')

    mapped = 0
    created = 0
    skipped_no_map = 0

    for issue in cnb_issues:
        cnb_number = int(issue['number'])
        # 没评论的卡直接跳过：省掉一次详情调用（列表接口已带 comment_count）
        if not issue.get('comment_count'):
            continue

        detail = get_cnb_issue(cnb_number)
        gh_number = resolve_github_number(detail)
        if gh_number is None:
            skipped_no_map += 1
            continue
        mapped += 1

        cnb_comments = list_cnb_comments(cnb_number)
        if not cnb_comments:
            continue

        try:
            existing = collect_markers(list_github_comments(github_repo, gh_number))
        except urllib.error.HTTPError as exc:
            # 404 = 镜像卡指向的 GitHub 卡不存在（被删/编号写错）；403 = 限额。
            # 都不该让整轮跑挂掉。
            print(f'  ⚠️ 读取 GitHub #{gh_number} 评论失败（CNB #{cnb_number}）：{exc}')
            continue

        todo = pending_comments(cnb_number, cnb_comments, existing, since)
        if not todo:
            continue

        print(f'  → CNB #{cnb_number} → GitHub #{gh_number}：待回写 {len(todo)} 条')
        for c in todo:
            if dry_run:
                print(f'      [DRY-RUN] comment id {c.get("id")} by {(c.get("author") or {}).get("nickname")}')
                continue
            try:
                post_github_comment(github_repo, gh_number, build_comment(cnb_number, c))
            except urllib.error.HTTPError as exc:
                print(f'      ❌ 回写失败（id {c.get("id")}）：{exc}')
                continue
            backfilled.setdefault(str(cnb_number), {})[str(c.get('id'))] = {
                'github': gh_number,
                'at': now_utc(),
            }
            created += 1
            print(f'      ✅ 已回写 comment id {c.get("id")}')
            if limit and created >= limit:
                print(f'      （达到 --limit {limit}，停止）')
                break
        if limit and created >= limit:
            break

    if not dry_run and created:
        state['last_sync_at'] = now_utc()
        save_state(state)

    print(
        f'🎉 完成：可映射 {mapped} 张，回写 {created} 条评论'
        f'{("（dry-run，未写入）" if dry_run else "")}；'
        f'无 GitHub 映射跳过 {skipped_no_map} 张'
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='CNB → GitHub issue 评论回写')
    parser.add_argument('--apply', action='store_true', help='真正回写（默认 dry-run）')
    parser.add_argument('--dry-run', action='store_true', help='只报告不写入（默认行为）')
    parser.add_argument('--limit', type=int, default=None, help='本次最多回写几条（调试用）')
    parser.add_argument('--since', type=str, default=None, help='只回写该时间之后的 CNB 评论（ISO8601）')
    args = parser.parse_args(argv)

    since = parse_ts(args.since) if args.since else None
    return run(dry_run=not args.apply, limit=args.limit, since=since)


if __name__ == '__main__':
    sys.exit(main())
