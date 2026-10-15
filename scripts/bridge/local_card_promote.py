#!/usr/bin/env python3
"""CNB 本地卡 → GitHub 卡的推广通道（CNB `#172` 第一个动作）。

为什么需要它
------------
「CNB 本地卡」（D49 / CNB `#117`）的存在意义依赖 CNB 这个环境——讲 `.cnb.yml` 的
cron 语义、`CNB_TOKEN` 构建内注入、CNB 镜像链路取舍这类事，镜像到 GitHub 读起来
确实莫名其妙。但本地卡是**只增不回**的：上面的结论、更正、决策**永远到不了 GitHub**。

`--report-local` 能把这些卡**数出来**（当前 CNB 共 123 张卡 / 镜像 111 / 本地 12，
本地卡上 72 条评论），但「数出来」不等于「有出口」——数完仍然只能人肉把结论抄过去。
CNB `#172` 把这条缺口定性为**真缺口**，并选定「本地卡按需推广」作为处置方式：
默认仍是本地卡，**但结论需要让 GitHub 侧看见时，要有可执行的命令行**。

本脚本就是那条命令。它不做自动判定（脚本猜「这张卡该不该推广」是危险的：猜错会往
GitHub 建一堆讲 CNB cron 的卡），只把「人工决定推广」这件事变成三步固定动作。

三步（缺一不可）
----------------
1. **在 GitHub 建卡**（CHANNEL 1）：用推广正文（去 CNB 味的标题 + 背景说明）；
2. **在 CNB 原卡留链**（CHANNEL 2）：追加一条「## 已推广到 GitHub」评论，
   给出 GitHub 新卡链接——这是本卡**唯一**不会被后续机制覆盖的位置（正文是只读的）；
3. **刷新映射**：把 GitHub 新卡 + 原卡评论镜像到 CNB，并挂上 `GitHub 同步` 标签。

第 2、3 步常被漏掉，而漏掉它们的后果是隐形的：卡建出来了、评论也回写了，但**点击链
不会自己出现**，下一个人仍然找不到。故三者写进同一段代码，且幂等。

边界
----
- **纯标准库**（`urllib`），与 `scripts/bridge/` 其它脚本一致——每日作业不该被三方包带崩；
- **先 GitHub 后 CNB**：GitHub 建卡失败 ⇒ CNB 侧一个字都不改，不会留下「半个推广」；
- **幂等**：推广键 = `推广键：<sha1(CNB 编号|GitHub 编号) 的前 12 位>`，写在 CNB 原卡
  那条评论的**隐藏标记**里。跑第二遍只会复用已有映射，不会重复建卡、不会重复发评论；
- **只推广声明过的本地卡**：非本地卡（镜像卡 / 判据读不出来）一律拒绝——镜像卡本来
  就在 GitHub 有原卡，推广它只会造出第二张卡。

用法
----
    # ① 先看有哪些本地卡可以推广（只读，与前缀 `--report-local` 同一口径）
    python scripts/bridge/local_card_promote.py --list

    # ② 演练：算出要建什么卡、要发什么评论，但不写任何东西（默认）
    python scripts/bridge/local_card_promote.py --cnb 172 \\
        --title '本地卡结论需要回流时的推广通道' \\
        --body-file /tmp/promote-body.md

    # ③ 真正执行（GitHub 建卡 + CNB 留链 + 刷新镜像）
    python scripts/bridge/local_card_promote.py --cnb 172 \\
        --title '…' --body-file /tmp/promote-body.md --apply

环境变量
--------
- `GITHUB_TOKEN`（**必需**）推广要**写** GitHub，匿名没有写权限——缺失时直接失败，
  不静默空跑（这是 `mirror_state_sync.py` #171 的教训：拿不到数据还报「已对齐」）。
- `GITHUB_REPO`（可选）默认 `imoyao/fundmate`
- `GITHUB_LABELS`（可选）给新卡挂的 GitHub 标签，逗号分隔；默认 `CNB 本地`
- `CNB_TOKEN`（构建内自动注入；本地跑请显式 export）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from github_cnb_issues import (  # noqa: E402
    _github_repo,
    _request,
    cnb_api,
    get_cnb_issue,
    list_cnb_issues,
    local_card_kind,
)
from mirror_correction import parse_comments, post_comment  # noqa: E402

# 推广链的幂等键：写在「已推广到 GitHub」评论末尾的隐藏标记里。
PROMOTE_KEY_RE = re.compile(r'推广键：([0-9a-f]{12})')
PROMOTE_KEY_LINE = '<!-- 推广键：{} -->'

# GitHub 新建卡默认标签：`CNB 本地` 让「这批卡原本只在 CNB 存在」可被一眼筛出。
DEFAULT_GH_LABELS = 'CNB 本地'


def make_key(cnb_number: int, gh_number: int | None = None) -> str:
    """推广键 = sha1(CNB 编号 | GitHub 编号)。

    推广**之前** GitHub 编号还不存在，故先算「只有 CNB 编号」的占位键（用于在
    GitHub 卡创建**之前**就写进本地状态文件，避免建卡成功、留链失败时重复建卡）。
    建卡成功后重算带编号的键，写进评论正文。
    """
    raw = f'{cnb_number}|{gh_number if gh_number is not None else ""}'
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def build_promote_comment(
    gh_number: int,
    gh_repo: str,
    key: str,
    *,
    today: str,
    gh_title: str = '',
) -> str:
    """CNB 原卡上的「已推广到 GitHub」评论。

    读者是**下一轮看这张卡的人**：他要能从这里一步跳到 GitHub 新卡，所以链接必须
    是**完整 URL**（`cnb_github_backfill.py` 的 `resolve_github_number` 只认完整 URL，
    裸引用会被静默跳过——CNB `#117` 实测踩过这个坑）。
    """
    lines = [
        f'## 已推广到 GitHub（{today}）',
        '',
        f'- 新卡：https://github.com/{gh_repo}/issues/{gh_number}' + (f'　（{gh_title}）' if gh_title else ''),
        '- 性质：本卡是 **CNB 本地卡**，它的结论需要 GitHub 侧可见，故**另开**一张 GitHub 卡；',
        '  **不是把本卡镜像过去**（本卡讲的是 CNB 环境语义，镜像过去读者会看不懂）。',
        '- 后续讨论请在 GitHub 新卡继续；CNB 侧的评论会由回写作业同步过去。',
        '',
        PROMOTE_KEY_LINE.format(key),
    ]
    return '\n'.join(lines)


def existing_promote_keys(cnb_number: int) -> set[str]:
    """CNB 原卡评论区里已记的推广键。"""
    out: set[str] = set()
    for c in parse_comments(cnb_api(f'/{_cnb_repo()}/-/issues/{cnb_number}/comments?page=1&page_size=100')):
        out |= {m.group(1) for m in PROMOTE_KEY_RE.finditer(c['body'])}
    return out


def _cnb_repo() -> str:
    from github_cnb_issues import _cnb_repo as impl

    return impl()


# ---------------------------------------------------------------------------
# GitHub 写接口（本脚本自带，不复用 github_cnb_issues 的读路径）
# ---------------------------------------------------------------------------


def _github_headers() -> dict[str, str]:
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        # 缺 token 直接失败：匿名调 GitHub 写接口只会拿到 401 然后静默啥也没建。
        raise RuntimeError(
            '缺少 GITHUB_TOKEN。推广要**写** GitHub（建卡 + 挂标签），匿名没有写权限。\n'
            'GitHub Actions 里由 `secrets.GH_PAT || secrets.GITHUB_TOKEN` 注入；本地跑请 export。'
        )
    return {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
    }


def github_api(path: str, *, method: str = 'GET', payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    headers = _github_headers()
    if data is not None:
        headers['Content-Type'] = 'application/json'
    raw = _request(f'https://api.github.com{path}', method=method, data=data, headers=headers)
    return json.loads(raw) if raw else None


def find_existing_github_card(title: str) -> int | None:
    """按标题精确匹配找一张已存在的 GitHub 卡（重跑时的兜底，避免重复建卡）。

    只认**完全相同**的标题：模糊匹配会撞上「标题相似但其实是另一件事」的卡，
    那比重复建一张更贵。
    """
    repo = _github_repo()
    page = 1
    while page <= 10:
        batch = github_api(f'/repos/{repo}/issues?state=all&per_page=100&page={page}')
        if not batch:
            break
        for item in batch:
            if 'pull_request' in item:
                continue
            if (item.get('title') or '').strip() == title.strip():
                return int(item['number'])
        if len(batch) < 100:
            break
        page += 1
    return None


def create_github_card(title: str, body: str, labels: list[str]) -> int:
    repo = _github_repo()
    created = github_api(
        f'/repos/{repo}/issues',
        method='POST',
        payload={'title': title, 'body': body, 'labels': labels},
    )
    number = int((created or {}).get('number') or 0)
    if not number:
        raise RuntimeError(f'GitHub 建卡返回里没有编号：{created!r}')
    return number


# ---------------------------------------------------------------------------
# 本地卡账（复用 `--report-local` 的判据，避免两处口径漂移）
# ---------------------------------------------------------------------------


def list_local_cards() -> list[dict[str, Any]]:
    """扫全部 CNB 卡，返回**本地卡**清单（`local_card_kind` 非空的那些）。

    判据直接调 `github_cnb_issues.local_card_kind`，不在这里复写一遍——
    口径分两处实现，迟早会长出两种结论。
    """
    out: list[dict[str, Any]] = []
    for st in ('open', 'closed'):
        for card in list_cnb_issues(st):
            number = int(card['number'])
            detail = get_cnb_issue(number)
            kind = local_card_kind(detail)
            if not kind:
                continue
            out.append(
                {
                    'number': number,
                    'state': detail.get('state') or card.get('state') or '',
                    'title': (detail.get('title') or '')[:80],
                    'kind': kind,
                    'comments': int(detail.get('comment_count') or card.get('comment_count') or 0),
                }
            )
    out.sort(key=lambda r: r['number'])
    return out


def run_list() -> int:
    cards = list_local_cards()
    by_kind: dict[str, int] = {}
    for r in cards:
        by_kind[r['kind']] = by_kind.get(r['kind'], 0) + 1
    print(f'CNB 本地卡 {len(cards)} 张（判定来源：{by_kind or "无"}）')
    print()
    print('| CNB | 状态 | 判定 | 评论 | 标题 |')
    print('|---|---|---|---|---|')
    for r in cards:
        print(f'| #{r["number"]} | {r["state"]} | {r["kind"]} | {r["comments"]} | {r["title"]} |')
    print()
    print('推广某一张（默认 dry-run，加 --apply 执行）：')
    print('  python scripts/bridge/local_card_promote.py --cnb <编号> \\')
    print('      --title "<GitHub 卡标题>" --body-file <utf8 正文文件> --apply')
    return 0


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_promote(
    cnb_number: int,
    title: str,
    body_file: str,
    *,
    apply: bool,
    labels: list[str],
    refresh: bool,
) -> int:
    today = _today()
    detail = get_cnb_issue(cnb_number)
    if not detail:
        print(f'❌ CNB #{cnb_number} 读不到')
        return 1
    kind = local_card_kind(detail)
    if not kind:
        print(
            f'❌ CNB #{cnb_number} 不是本地卡（判据读不出来）。\n'
            '   镜像卡在 GitHub 已有原卡，推广它会多出一张重复卡；\n'
            '   若这确实是一张本地卡，请先在正文顶部写 `> 📍 **CNB 本地卡**` 或挂 `CNB 本地` 标签。'
        )
        return 1

    body_path = Path(body_file)
    if not body_path.is_file():
        print(f'❌ 正文文件不存在：{body_file}')
        return 1
    gh_body = body_path.read_text(encoding='utf-8')
    if not gh_body.strip():
        print(f'❌ 正文文件是空的：{body_file}')
        return 1

    gh_labels = labels or ([s.strip() for s in DEFAULT_GH_LABELS.split(',') if s.strip()])

    print(f'📋 CNB #{cnb_number}「{(detail.get("title") or "")[:50]}」（判定来源：{kind}）')
    print(f'   GitHub 卡标题：{title}')
    print(f'   GitHub 标签：{gh_labels}')
    print(f'   正文：{len(gh_body)} 字符（来自 {body_file}）')

    if not apply:
        print()
        print('[DRY-RUN] 将执行：')
        print(f'  1. GitHub 建卡：{title}')
        print(f'  2. CNB #{cnb_number} 追加「已推广到 GitHub」评论（含完整 URL 与幂等键）')
        if refresh:
            print('  3. 刷新镜像（把 GitHub 新卡的评论拉回 CNB）')
        print('  加 --apply 真正执行。')
        return 0

    # 幂等：先看 CNB 原卡是否已经记过推广键（只有 CNB 编号的占位键 + 带编号的正式键）。
    published = existing_promote_keys(cnb_number)
    placeholder = make_key(cnb_number)
    if placeholder in published:
        print(f'⏭️  CNB #{cnb_number} 已记录过推广（占位键 {placeholder}），跳过。返工请按提示手工处理。')
        return 0

    # CHANNEL 1：GitHub 建卡。先查同标题是否已存在，避免重跑造重复卡。
    existing = find_existing_github_card(title)
    if existing:
        print(f'ℹ️ GitHub 已有同名卡 #{existing}，复用它（不重复建卡）。')
        gh_number = existing
    else:
        gh_number = create_github_card(title, gh_body, gh_labels)
        print(f'✅ GitHub 建卡成功：https://github.com/{_github_repo()}/issues/{gh_number}')

    # CHANNEL 2：CNB 原卡留链。这是**唯一**不会被后续覆盖的位置。
    key = make_key(cnb_number, gh_number)
    if key in published:
        print(f'⏭️  推广评论已存在（推广键 {key}），跳过评论。')
    else:
        post_comment(
            cnb_number,
            build_promote_comment(gh_number, _github_repo(), key, today=today, gh_title=title),
        )
        print(f'✅ CNB #{cnb_number} 已追加推广评论（推广键 {key}）')

    # CHANNEL 3：刷新映射，让新卡的评论回流到 CNB（挂 `GitHub 同步` 标签走工建卡作业）。
    if refresh:
        rc = _refresh_mirror()
        if rc != 0:
            print(f'⚠️ 镜像刷新返回 {rc}——卡片已建、链已留，这一步失败不影响推广本身，但评论回流会推迟。')
    else:
        print('ℹ️ 已跳过镜像刷新（--no-refresh）；每日 cron 的建卡作业会补上。')

    print()
    print(f'🎉 推广完成：CNB #{cnb_number} → GitHub #{gh_number}')
    print(f'   GitHub：https://github.com/{_github_repo()}/issues/{gh_number}')
    return 0


def _refresh_mirror() -> int:
    """调既有建卡作业刷新映射（复用，不重写一份建卡逻辑）。"""
    script = SCRIPT_DIR / 'github_cnb_issues.py'
    proc = subprocess.run(
        [sys.executable, str(script), '--apply'],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    sys.stdout.write(proc.stdout or '')
    sys.stderr.write(proc.stderr or '')
    return proc.returncode


def _today() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime('%Y-%m-%d')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='CNB 本地卡 → GitHub 卡的推广通道（CNB `#172`）：默认 dry-run',
    )
    parser.add_argument('--list', action='store_true', help='只列出本地卡（只读）')
    parser.add_argument('--cnb', type=int, default=None, help='要推广的 CNB 本地卡编号')
    parser.add_argument('--title', default=None, help='GitHub 新卡的标题')
    parser.add_argument('--body-file', default=None, help='GitHub 新卡正文（UTF-8 文件，禁止内联中文）')
    parser.add_argument('--labels', default=None, help=f'GitHub 标签，逗号分隔（默认 {DEFAULT_GH_LABELS}）')
    parser.add_argument('--no-refresh', dest='refresh', action='store_false', help='跳过镜像刷新')
    parser.add_argument('--apply', action='store_true', help='真正执行（默认 dry-run）')
    args = parser.parse_args(argv)

    if args.list:
        return run_list()
    if not (args.cnb and args.title and args.body_file):
        parser.print_help()
        print('\n❌ 推广需要同时给 --cnb / --title / --body-file（或用 --list 先看看有哪些卡）')
        return 1
    try:
        return run_promote(
            args.cnb,
            args.title,
            args.body_file,
            apply=args.apply,
            labels=[s.strip() for s in (args.labels or '').split(',') if s.strip()],
            refresh=args.refresh,
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:400] if hasattr(exc, 'read') else ''
        print(f'❌ HTTP {exc.code}：{body}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
