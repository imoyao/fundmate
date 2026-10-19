#!/usr/bin/env python3
"""GitHub Issues → CNB Issues 单向增量镜像。

为什么需要它
------------
CNB 侧没有 GitHub 的 issue 视图，讨论散在两处。2026-10-11 做过一次全量手工同步
（107 张卡，CNB `#5`~`#112`），但那是**一次性**的：GitHub 之后新开的卡不会再出现，
两侧很快又各说各话。本脚本把那次同步固化成可重复执行的增量作业，配套
`.cnb.yml` 的每日 cron 跑。

设计取舍（与 #2 的那轮同步一致，避免同一批卡出现两种格式）
--------------------------------------------------------
- **单向**：只 GitHub → CNB，绝不回写 GitHub。双向会在两侧状态不一致时互相打架。
- **只增不覆盖**：已存在的镜像卡永不改动。存量卡里的正文/标签若被 CNB 侧人工调过，
  覆盖等于抹掉那些调整；镜像卡正文顶部已写明「只读镜像，讨论回 GitHub」。
- **关闭态不同步**：GitHub 关了 → CNB 也关，会造成「CNB 侧看不到活跃讨论」的误判，
  且关闭动作由人决定更稳。本脚本只建新卡（结论：只增）。
  （2026-10-11，CNB #117 硬要求 ②：改为**标记不关**——`mirror_state_sync.py` 在镜像卡
  评论区回流一条状态评论 + 挂 `GitHub 已关闭` 标签，**不替人做关闭决定**。见 CNB #117。  cross-repo-ref-allow
- **幂等键 = GitHub 编号**，写在镜像卡正文的 `GitHub 编号：#N` 里；辅以状态文件
  缓存映射，避免每次都逐张拉正文（CNB 列表接口不返回 body）。

依赖
----
纯标准库（urllib），无需 pip install —— 便于在任意 CI 镜像里直接跑。

环境变量
--------
- `GITHUB_REPO`（可选）GitHub 仓库，默认 `imoyao/fundmate`
- `GITHUB_TOKEN`（可选）GitHub PAT；不设则走匿名 API（60 次/时/IP，够用）
- `CNB_REPO`（可选）CNB 仓库，默认从 `CNB_REPO_SLUG` 读，再退到 `duoduobei/fundmate`
- `CNB_TOKEN`（构建内自动注入）CNB 写凭证

用法
----
    python scripts/bridge/github_cnb_issues.py --dry-run      # 只看要建哪些卡
    python scripts/bridge/github_cnb_issues.py --apply        # 真正创建
    python scripts/bridge/github_cnb_issues.py --apply --limit 5
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
STATE_FILE = SCRIPT_DIR / 'github_cnb_state.json'

GITHUB_REPO_DEFAULT = 'imoyao/fundmate'
CNB_REPO_DEFAULT = 'duoduobei/fundmate'

MIRROR_LABEL = 'GitHub 同步'
MILESTONE_LABEL_PREFIX = '里程碑:'

# CNB 标签名的硬限制：只允许中英文/数字/`._:-/\` 与内部空格，长度 ≤50。
# 含 `&`、`（）`、`#` 等会被 400 拒绝，故做等价替换（见 #2 那轮同步的踩坑记录）。
_LABEL_CHAR_MAP = str.maketrans(
    {
        '&': '和',
        '（': ' ',
        '）': ' ',
        '(': ' ',
        ')': ' ',
        '#': 'No.',
        '，': ' ',
        '、': ' ',
    }
)

# 象阵 → CNB 原生 priority（拍板口径，见 #2 评论）
XIANGZHEN_TO_PRIORITY = {
    'Q1-RED': 'P0',
    'Q2-YELLOW': 'P1',
    'Q3-GREEN': 'P2',
    'Q4-GRAY': 'P3',
}

# GitHub 标签里已经转成 priority / 里程碑的，不再重复挂成标签
_LABELS_DROPPED = set(XIANGZHEN_TO_PRIORITY) | {'象阵'}

# CNB 单卡标签上限
MAX_LABELS = 10


# ---------------------------------------------------------------------------
# 纯函数（被 scripts/tests/github_cnb_issues.test.js 之外的单测覆盖）
# ---------------------------------------------------------------------------


def sanitize_label(name: str) -> str:
    """把 GitHub 标签名改写成 CNB 能接受的标签名。

    CNB 只允许中英文/数字/`._:-/\\` 与内部空格，且长度 ≤50。
    非法字符做等价替换（保留语义可读），超长直接截断到 50。
    """
    s = (name or '').strip().translate(_LABEL_CHAR_MAP)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:50]


def priority_from_labels(labels: list[str]) -> str | None:
    """从 GitHub 标签里挑出象阵，转成 CNB priority。无则返回 None（用默认）。"""
    for name in labels:
        p = XIANGZHEN_TO_PRIORITY.get(name.strip())
        if p:
            return p
    return None


def build_labels(issue: dict[str, Any]) -> list[str]:
    """组装 CNB 标签列表：镜像标记 + 里程碑标签 + 原标签（去掉已转 priority 的）。

    上限 MAX_LABELS，超出按「先原标签、后里程碑」顺序截断 —— 里程碑信息在正文里
    还有一份，丢标签不会丢信息；原标签则没有别处承载。
    """
    labels: list[str] = [MIRROR_LABEL]

    milestone = (issue.get('milestone') or {}).get('title')
    milestone_label = sanitize_label(f'{MILESTONE_LABEL_PREFIX}{milestone}') if milestone else None

    originals: list[str] = []
    for raw in issue.get('labels') or []:
        name = raw['name'] if isinstance(raw, dict) else str(raw)
        if name.strip() in _LABELS_DROPPED:
            continue
        cleaned = sanitize_label(name)
        if cleaned and cleaned not in originals:
            originals.append(cleaned)

    room = MAX_LABELS - len(labels) - (1 if milestone_label else 0)
    labels.extend(originals[: max(room, 0)])
    if milestone_label and len(labels) < MAX_LABELS:
        labels.append(milestone_label)
    return labels


def build_body(issue: dict[str, Any]) -> str:
    """拼镜像卡正文：顶部溯源块 + `---` + GitHub 原文（原样保留）。

    溯源块的字段顺序与措辞跟 2026-10-11 那轮全量同步保持一致，免得同一批卡
    出现两种长相；标识行 `GitHub 编号：#N` 是幂等键，**不可改**。
    """
    number = issue['number']
    state = issue.get('state', 'open')
    # 建卡快照时刻：显式打印出来，避免正文里只有 GitHub 的创建时间、读者误以为本卡很新。见 `#120` 方案 A。
    mirrored_at = datetime.now(UTC)
    milestone = (issue.get('milestone') or {}).get('title') or '—'
    author = (issue.get('user') or {}).get('login') or 'unknown'
    created = (issue.get('created_at') or '')[:10]
    comments = issue.get('comments', 0)

    origin_labels = [(raw['name'] if isinstance(raw, dict) else str(raw)) for raw in (issue.get('labels') or [])]
    labels_text = ' '.join(f'`{n}`' for n in origin_labels) if origin_labels else '—'

    header = '\n'.join(
        [
            '> 🔁 **本卡由 GitHub Issue 同步而来（CNB 镜像）**',
            '>',
            f'> - 来源：https://github.com/{_github_repo()}/issues/{number}',
            f'> - GitHub 编号：`#{number}`　状态：`{state}`',
            f'> - 里程碑：`{milestone}`',
            f'> - 原标签：{labels_text}',
            f'> - 作者：@{author}　创建：{created}　评论数：{comments}',
            f'> - 镜像生成时间：{mirrored_at:%Y-%m-%d %H:%M UTC}',
            '>',
            f'> ⚠️ 本卡是**建卡时快照**（截至 {mirrored_at:%Y-%m-%d}），**不覆盖后续变更**；',
            '> 正文引用的文件 / 行号 / 字段 / 结论均为快照时刻的位置，可能与当前代码不一致——',
            '> 按它动手之前，先用 `git show <ref>:<file>` 确认该行仍在当前分支上。',
            '> ⚠️ 正式讨论、更正与状态变更请回到 GitHub 原卡，CNB 侧改动不会自动回流；',
            '> 本卡正文若与 GitHub 原卡不符，**一律以 GitHub 为准**。',
            '>',
            '> 📝 **更正**：在本卡评论区追加一条更正评论（不改正文）——',
            '> 标题写 `## 更正（{日期}）`，正文逐条写「❌ 原文 → ✅ 实际（依据：PR/commit）」。',
            '> 依据 AGENTS.md「失实信息修正纪律」；命令见 `scripts/bridge/mirror_correction.py`。',
        ]
    )
    return f'{header}\n\n---\n\n{issue.get("body") or ""}'


GITHUB_NUMBER_RE = re.compile(r'GitHub 编号：`#(\d+)`')


def extract_github_number(body: str | None) -> int | None:
    """从镜像卡正文里抠出 GitHub 编号（幂等键）。抽不到返回 None。"""
    m = GITHUB_NUMBER_RE.search(body or '')
    return int(m.group(1)) if m else None


# 本地卡标记：CNB 侧自造、**永不镜像到 GitHub** 的卡。
# 为什么需要它见文件头「CNB 本地卡」一节；这里只放判据。
LOCAL_LABEL = 'CNB 本地'
# 正文里的显式声明（人工写的本地卡也能自己声明，不强制会挂标签）。
# 锚在**行首的引用块**上：正文里提到「**CNB 本地卡**」这个概念不该被当成本地卡。
LOCAL_MARKER_RE = re.compile(r'^\s*>\s*(?:📍\s*)?\*\*CNB 本地卡\*\*', re.MULTILINE)
# 镜像卡正文里的来源链接，反向对照用（不是本地卡判据）
GITHUB_URL_RE = re.compile(r'https://github\.com/[\w.-]+/[\w.-]+/issues/(\d+)')
# **裸引用**（`imoyao/fundmate#2034`），不带完整 URL。
# 这条存在的原因：CNB #117 正文写的就是裸引用，而回写作业
# （`cnb_github_backfill.py` 的 `resolve_github_number`）只认完整 URL ⇒ 认不出、静默跳过。
# 本处**只用于在报告里把这张卡标出来**，不把它当映射（裸引用歧义大，自动当编号等于猜）。
_NAKED_REF_RE = re.compile(r'([\w.-]+/[\w.-]+)#(\d+)')


def local_card_kind(card: dict[str, Any]) -> str:
    """本地卡的判定**来源**：`label` / `body` / `fallback` / `''`（不是本地卡）。

    把「来源」和「是不是」分开，是本判据最容易做错的地方。合在一起时，
    「无标签、无幂等键」的兜底会把一张**只是格式写歪**的镜像卡也说成「本地卡」，
    而报告里看不出这一条是**声明**还是**猜**。分开之后：

    - `label` / `body` 是**声明**，直接信；
    - `fallback` 是**猜**（无 `GitHub 同步` 标签、也抠不到 `GitHub 编号：#N`），
      报告里单独计数，供人复核。
    """
    labels = [lb.get('name') if isinstance(lb, dict) else str(lb) for lb in (card.get('labels') or [])]
    body = card.get('body') or ''
    if LOCAL_LABEL in labels:
        return 'label'
    if LOCAL_MARKER_RE.search(body):
        return 'body'
    if MIRROR_LABEL not in labels and not GITHUB_NUMBER_RE.search(body):
        return 'fallback'
    return ''


def is_local_card(card: dict[str, Any]) -> bool:
    """这张 CNB 卡是不是「CNB 本地卡」（自造、不镜像到 GitHub）。"""
    return local_card_kind(card) != ''


def is_mirror_card(card: dict[str, Any]) -> bool:
    """镜像卡的判据：挂 `GitHub 同步` 标签，或正文有幂等键 `GitHub 编号：#N`。

    与本地卡判据互补；两者都真（既挂镜像标签又挂本地标签）属数据错误，
    由 `report_local_cards()` 报出来，不在这里静默选一边。
    """
    labels = [lb.get('name') if isinstance(lb, dict) else str(lb) for lb in (card.get('labels') or [])]
    body = card.get('body') or ''
    return MIRROR_LABEL in labels or GITHUB_NUMBER_RE.search(body) is not None


def _github_refs(body: str) -> list[str]:
    """正文里出现的 **GitHub 侧**卡引用（去重，保持出现顺序）。

    只收 GitHub 仓库（`_github_repo()`，默认 `imoyao/fundmate`）的引用，两种形态：

    - 完整 URL：`https://github.com/o/r/issues/N`；
    - 裸引用：`o/r#N`。

    **只收 GitHub 侧**是刻意的：一张 CNB 本地卡正文里常有大量 `duoduobei/fundmate#106`
    这类**指向 CNB 自己**的引用，把它们也算成「提到了 GitHub」会让提示变成噪音。

    裸引用**只是提示**——报告里显示出来让人判断，不参与任何自动映射。
    这是刻意与 `cnb_github_backfill.py` 的 `resolve_github_number` 保持不同：
    那边是**写路径**，认错了会把评论贴到别人卡上，所以只认完整 URL、宁可漏；
    这边是**只读报告**，漏掉才是问题，所以两种都收。
    """
    repo = _github_repo()
    out: list[str] = []
    for m in GITHUB_URL_RE.finditer(body or ''):
        if not m.group(0).startswith(f'https://github.com/{repo}/'):
            continue
        ref = f'https://github.com/{repo}/issues/{m.group(1)}'
        if ref not in out:
            out.append(ref)
    for m in _NAKED_REF_RE.finditer(body or ''):
        if m.group(1) != repo:
            continue
        ref = f'{m.group(1)}#{m.group(2)}'
        if ref not in out:
            out.append(ref)
    return out


def local_card_report(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """扫全部 CNB 卡，算出「本地卡 vs 镜像卡」的账，供 `--report-local` 打印。

    这是本卡最该落地的一件事：**没有任何作业知道 CNB 侧有多少卡是本地卡**。
    回写作业（`cnb_github_backfill.py`）对认不出 GitHub 编号的卡是**静默跳过**的
    （「抠不到就跳过——宁可漏，不可错」），于是「本地卡有多少、有没有一条讨论
    真的被落下」全靠人肉发现。本函数把它变成可执行的一条命令。

    返回 `{summary, cards}`：`summary` 是计数，`cards` 是逐卡归类（按编号升序）。

    三个需要人看的量：

    - `conflict`：既像本地卡又像镜像卡 —— 数据错误，判据不替人选边；
    - `fallback`：靠「无标签 + 无幂等键」**猜**出来的本地卡，可能是格式写歪的镜像卡；
    - `comments_on_local`：本地卡上的评论总数 —— 这些讨论**永远不会到 GitHub**，
      是「静默无出口」的实际规模。
    """
    rows: list[dict[str, Any]] = []
    for card in cards:
        kind = local_card_kind(card)
        mirror = is_mirror_card(card)
        body = card.get('body') or ''
        rows.append(
            {
                'number': int(card['number']),
                'state': card.get('state') or '',
                'title': (card.get('title') or '')[:60],
                'comments': int(card.get('comment_count') or 0),
                'kind': kind,  # label / body / fallback / ''（非本地卡）
                'local': kind != '',
                'mirror': mirror,
                'conflict': kind != '' and mirror,
                # 本地卡正文里出现了 GitHub issue 链接（完整 URL 或裸引用）——
                # 可能本就该是镜像卡，也可能只是「引用了别处的卡」。
                # 两种情况都需要人看一眼，故一并标出，并区分形态。
                'mentions_github': bool(kind and (GITHUB_URL_RE.search(body) or _NAKED_REF_RE.search(body))),
                'github_refs': _github_refs(body) if kind else [],
            }
        )
    rows.sort(key=lambda r: r['number'])
    summary = {
        'total': len(rows),
        'local': sum(1 for r in rows if r['local']),
        'mirror': sum(1 for r in rows if r['mirror'] and not r['conflict']),
        'conflict': sum(1 for r in rows if r['conflict']),
        'by_kind': {k: sum(1 for r in rows if r['kind'] == k) for k in ('label', 'body', 'fallback')},
        'comments_on_local': sum(r['comments'] for r in rows if r['local']),
        # 本地卡里引用了 GitHub 侧卡的数量 —— 这些是「讨论真被截断」的候选，
        # 因为它们**指向 GitHub**，却因为不是镜像卡而不参与回写（#117 实测出的缺口）。
        'local_mentions_github': sum(1 for r in rows if r['local'] and r['mentions_github']),
    }
    return {'summary': summary, 'cards': rows}


def render_local_report(report: dict[str, Any]) -> str:
    """把 `local_card_report` 的结果渲染成 markdown（打印 / 归档两用）。"""
    s = report['summary']
    lines = [
        '## CNB 本地卡对照报告',
        '',
        f'- CNB 卡总数：**{s["total"]}**',
        f'- 镜像卡：**{s["mirror"]}**',
        (
            f'- 本地卡：**{s["local"]}**'
            f'（标签声明 {s["by_kind"]["label"]} / 正文声明 {s["by_kind"]["body"]} /'
            f' **兜底猜测 {s["by_kind"]["fallback"]}**）'
        ),
        f'- 判据冲突（既像本地又像镜像）：**{s["conflict"]}**',
        f'- 本地卡上的评论总数：**{s["comments_on_local"]}** —— 这些讨论不会出现在 GitHub',
        f'- 其中**引用了 GitHub 侧卡**的本地卡：**{s["local_mentions_github"]}**'
        f' —— 回写作业只认完整 URL，裸引用（`o/r#N`）会被静默跳过',
        '',
    ]
    if s['conflict'] or s['by_kind']['fallback']:
        lines += [
            '> ⚠️ 有需要人工复核的项：`conflict` 说明卡面上两种标记打架；',
            '> `fallback` 是靠「无标签 + 无幂等键」猜出来的本地卡，可能是格式写歪的镜像卡。',
            '',
        ]
    locals_ = [r for r in report['cards'] if r['local']]
    if locals_:
        lines += ['| CNB | 状态 | 判定 | 评论 | 标题 |', '|---|---|---|---|---|']
        for r in locals_:
            marks = ''
            if r['conflict']:
                marks += ' ⚠️判据冲突'
            if r['github_refs']:
                marks += ' 🔗' + ' / '.join(r['github_refs'])
            lines.append(f'| #{r["number"]} | {r["state"]} | {r["kind"]}{marks} | {r["comments"]} | {r["title"]} |')
    else:
        lines.append('（无本地卡）')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# HTTP（标准库，无三方依赖）
# ---------------------------------------------------------------------------


def _github_repo() -> str:
    return os.environ.get('GITHUB_REPO') or GITHUB_REPO_DEFAULT


def _cnb_repo() -> str:
    return os.environ.get('CNB_REPO') or os.environ.get('CNB_REPO_SLUG') or CNB_REPO_DEFAULT


def _request_with_headers(
    url: str,
    *,
    method: str = 'GET',
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[bytes, dict[str, str]]:
    """同 `_request`，但**连响应头一起返回**。

    WHY 需要头（源 CNB #586，2026-10-19 实测）：GitHub 对**大结果集**关掉了 `page` 分页，  # cross-repo-ref-allow
    第 11 页起直接 422：

        Pagination with the page parameter is not supported for large datasets,
        please use cursor based pagination (after/before)

    而游标就在响应的 `Link` 头里（`rel="next"` 那段 URL 带 `after=…`）。只读 body 就
    拿不到游标，只能继续拼 `page=` ⇒ 永远撞同一面墙。故翻页必须读头。
    """
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('User-Agent', 'fundmate-github-cnb-mirror')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), dict(resp.headers.items())


def _request(
    url: str,
    *,
    method: str = 'GET',
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> bytes:
    """只关心 body 的调用方走这里（保留旧签名，不必为了头把每个调用点都改一遍）。"""
    return _request_with_headers(
        url, method=method, data=data, headers=headers, timeout=timeout
    )[0]


# 单次拉取的最大页数（防无限翻页 / 打爆限额）。100/页 ⇒ 上限 3000 张卡。
# 达到它说明仓库规模已超出「匿名限额够用」的前提，**必须显式报警**、不得当成拉全了。
MAX_ISSUE_PAGES = 30


def _link_next(headers: dict[str, str]) -> str | None:
    """从响应的 `Link` 头里取 `rel="next"` 的 URL（没有就 None）。

    GitHub 对大结果集（本仓已超 1000 张卡）**关掉了 `page` 分页**：
    第 11 页起直接返回 422 `Pagination with the page parameter is not supported
    for large datasets, please use cursor based pagination (after/before)`。
    而游标就藏在这个头里，形如：

        Link: <https://api.github.com/repositories/296191288/issues?state=all&per_page=100
               &page=11&sort=updated&after=Y3Vyc29yOnYyOpLPAAABoJW4oGDPAAAAAUPO_yc%3D>; rel="next"

    ⇒ **翻页只能跟着它走**。只读 body 的实现（本函数上线前的两个 fetch）在 page 11
    必然 422，而错误被当成「数据不完整」⇒ 状态回流实际只处理了 1/42 张（源 CNB #586）。
    """
    raw = headers.get('Link') or headers.get('link') or ''
    for part in raw.split(','):
        if 'rel="next"' not in part:
            continue
        url = part.split(';')[0].strip()
        return url.strip('<>').strip() or None
    return None


def fetch_github_issues(
    state: str,
    *,
    sort: str = 'created',
    direction: str | None = 'asc',
    max_pages: int = MAX_ISSUE_PAGES,
) -> tuple[list[dict[str, Any]], bool, str]:
    """拉 GitHub 仓库的 issue 列表（跨页，**PR 也一并返回**，由调用方剔除）。

    返回 `(items, complete, note)`：
      - `items`：已拿到的卡（含 PR，调用方按 `pull_request` 字段过滤）；
      - `complete`：这次拉取是否可信；
      - `note`：失败原因（空串 = 没出问题）。**`complete=False` 时调用方必须把它喊出来**
        ——「拉不到」不等于「没有」，这是本仓 #171 / #179 反复踩的假绿。

    翻页跟 `Link` 头走（`_link_next`）；拿不到头时才退回 `page=` 递增，这样
    「GitHub 没给 Link」这种退化不会变成「只拉了一页却报完整」。
    """
    headers: dict[str, str] = {'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'

    def page_url(n: int) -> str:
        params = {'state': state, 'per_page': 100, 'page': n, 'sort': sort}
        if direction:
            params['direction'] = direction
        qs = urllib.parse.urlencode(params)
        return f'https://api.github.com/repos/{_github_repo()}/issues?{qs}'

    out: list[dict[str, Any]] = []
    complete = True
    note = ''
    page = 1
    url = page_url(1)
    last_full = False
    while True:
        if page > max_pages:
            # 触顶 = 数据不完整，**显式**记下来（由调用方报警），不静默当成拉全了。
            complete = False
            note = f'翻页触顶（>{max_pages} 页）'
            break
        try:
            raw, resp_headers = _request_with_headers(url, headers=headers)
        except urllib.error.HTTPError as exc:
            complete = False
            if exc.code == 403:
                note = 'GitHub 限额用尽（403）'
            elif exc.code == 422:
                # 大结果集不支持 page 分页。走到这里说明 **Link 头也没给** ——
                # 那就真的拿不全了，必须如实说，不得退化成「就这么多」。
                note = (
                    'GitHub 拒绝 page 分页（422，大结果集只支持游标分页），'
                    '且本次响应未给 Link 头 —— 拿不到后续页'
                )
            else:
                note = f'GitHub 返回 {exc.code}'
            note = f'{note}（中断在 page {page}）'
            break
        batch = json.loads(raw)
        if not batch:
            # 空页：若此前已满页，说明分页中途断了（正常翻到尾时上一页不满页），
            # 这种情况数据不完整，必须记下来。
            if page > 1 and last_full:
                complete = False
                note = f'分页中断：page {page} 返回空，但上一页是满页'
            break
        out.extend(batch)
        last_full = len(batch) >= 100
        if not last_full:
            break
        nxt = _link_next(resp_headers)
        if nxt:
            url = nxt
        else:
            page += 1
            url = page_url(page)
            continue
        page += 1
    return out, complete, note


def fetch_github_open_issues() -> tuple[list[dict[str, Any]], bool]:
    """拉取 GitHub 仓库全部 open issue（跨页，剔除 PR）。

    GitHub 的 `/issues` 会把 PR 也混进来，靠 `pull_request` 字段剔除。
    匿名限额 60/时/IP；分页 100/页，一般 1~2 次调用即可，余量充足。

    返回 `(issues, complete)`：**`complete` 是这次拉取是否可信**（源 CNB #179）。
    调用方**不得**在 `complete=False` 时报「无新增，两侧已对齐」——
    「拉不到」不是「没有」。两种形态会让数据不完整：翻页触顶、分页中断。

    翻页实现收敛到 `fetch_github_issues()`（源 CNB #586）：这里原先自己拼 `page=`，
    而 GitHub 对**大结果集**已关闭 `page` 分页（第 11 页起 422），必须跟 `Link` 头走。
    同一份翻页逻辑原来抄了两遍（本函数 + `mirror_state_sync`），于是同一个 bug 修了两次
    —— 现在只有一处。
    """
    items, complete, _note = fetch_github_issues('open', sort='created', direction='asc')
    return [i for i in items if 'pull_request' not in i], complete


def cnb_api(path: str, *, method: str = 'GET', payload: dict | None = None) -> Any:
    """调 CNB OpenAPI。path 以 `/` 开头，形如 `/{repo}/-/issues`。

    鉴权头是 `Authorization: Bearer <CNB_TOKEN>`，**不是** `X-CNB-Token`
    —— 后者对 `api.cnb.cool` 会 401。`Accept` 必须是
    `application/vnd.cnb.api+json`，否则拿到的是网页而不是 JSON。
    这些细节抄自 cnb-cli 的实现（dist/index.js 的 resolveApiDomain / req 包装）。
    """
    base = (os.environ.get('CNB_API_ENDPOINT') or 'https://api.cnb.cool').rstrip('/')
    token = os.environ.get('CNB_TOKEN')
    if not token:
        raise RuntimeError('缺少 CNB_TOKEN（构建内自动注入；本地跑请显式 export）')

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.cnb.api+json',
    }
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    if data is not None:
        headers['Content-Type'] = 'application/json'

    raw = _request(f'{base}{path}', method=method, data=data, headers=headers)
    return json.loads(raw) if raw else None


def list_cnb_issues(state: str) -> list[dict[str, Any]]:
    """列 CNB issue（分页拉全）。列表接口不返回 body，故幂等映射另走状态文件。"""
    repo = _cnb_repo()
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        # 查询参数是下划线的 page_size（OpenAPI 定义如此，用连字符会被忽略成默认 10）
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
    """取单张卡详情（列表接口不返回 body，故抠幂等键必须走这里）。"""
    repo = _cnb_repo()
    return cnb_api(f'/{repo}/-/issues/{number}') or {}


def create_cnb_issue(issue: dict[str, Any]) -> int | None:
    """在 CNB 建一张镜像卡，返回新卡编号。

    分两段：先 create（`labels` 在这一步会被静默忽略，见 #2 踩坑记录），
    再单独调 `put-issue-labels` 挂标签。
    """
    repo = _cnb_repo()
    payload = {
        'title': issue['title'][:200],
        'body': build_body(issue),
        'priority': priority_from_labels(
            [raw['name'] if isinstance(raw, dict) else str(raw) for raw in (issue.get('labels') or [])]
        ),
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    created = cnb_api(f'/{repo}/-/issues', method='POST', payload=payload)
    number = int((created or {}).get('number'))

    labels = build_labels(issue)
    if labels:
        try:
            cnb_api(
                f'/{repo}/-/issues/{number}/labels',
                method='PUT',
                payload={'labels': labels},
            )
        except urllib.error.HTTPError as exc:  # 挂标签失败不该丢卡
            print(f'  ⚠️ #{number} 挂标签失败（卡已建好）：{exc}')
    return number


# ---------------------------------------------------------------------------
# 状态文件
# ---------------------------------------------------------------------------


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {'last_sync_at': None, 'mirrored': {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def harvest_existing(state: dict[str, Any]) -> set[int]:
    """收集 CNB 侧已存在的镜像卡对应的 GitHub 编号。

    ⚠️ **必须每次真扫 CNB 侧，不得拿状态文件当前置短路**（CNB #450，2026-10-14）。

    旧版在 `known` 非空时**直接 return**，把状态文件当成了「已镜像集合」的全集。
    但它是**一份缓存、而且是不全的缓存**：

      - 它只在**建卡成功的那条路径**里被写入（`run()` 里建一张写一条），
        历史上任何一次「卡建出来了、state 没落盘」（构建被中断 / `save_state` 抛错 /
        Web 端手工建卡）都不会补记；
      - CNB 侧的卡还会被**人工**创建或调整，它们同样不在缓存里；
      - 于是「缓存里有 1 条 ⇒ 判定整个 CNB 侧已镜像完毕」这个推论是**错的**。

    实测后果（2026-10-14）：缓存里 107 条（首轮全量同步那批，CNB #5~#112）冻结了三天，
    而 CNB 侧已有 365 张镜像卡 ⇒ 之后每一轮 cron / push 都把 ~140 张 GitHub 卡**再建一遍**，
    累计产生 **224 张重复卡**（CNB #164~#447，同一 GitHub 编号最多 11 张）。  # cross-repo-ref-allow
    建卡是**幂等键判重**的，判重依据却停在一份不全会话的缓存上 —— 幂等就失效了。

    现在的口径：**缓存只是索引，CNB 实况才是判据**。两者取并集，
    且扫描结果回写缓存（只用于加速与审计，不再是信任边界）。

    扫描成本：CNB 列表接口 100/页，逐张拉详情抠幂等键。实测 365 张镜像卡
    约 370 次请求，可接受 —— 相比「重复建 140 张卡」的代价，这个成本必须付。

    ## 第二层（源 CNB #6，2026-10-19）：**跳过的代价是「明天再建一张」**

    上面那条只治了「扫描被缓存短路」。第二层更贵，而且**当前就在发生**：

    ```text
    @CodeBuddy 怎么一直在重复刷？肯定是出 bug 了            ← 用户在同一个 bug 上喊了 37 遍
    分诊作业每轮会给每张卡贴一条评论
      → 08:57 贴到重复卡 #6 上 ⇒ #6 有了「有人类评论」的假象（分诊评论是 NPC 的，
        但清理脚本 08:57 之前的判据数的是**总评论数**）
      → 清理脚本按「有评论优先」保留 #6、关掉正本 #5
      → 建卡作业只问 `open`，**没有「已关闭的算不算建过」这一问** ⇒ 下一轮把
        GitHub #783 再建一张（#164 / #468 这些都是这么长出来的）
      → 新卡的评论区空空如也 ⇒ 分诊再贴一条 ⇒ 再关、再建……
    ```

    两个洞，都必须补：

    - **判重必须问全部 state**：`closed` 的镜像卡同样证明「这张 GitHub 卡建过」。
      只问 `open` 时，清理动作（关卡）直接把幂等键**匿名掉**，于是「关卡」变成
      「下一轮重建」的开关 —— 清理与重建互相喂饭。
      ⚠️ 只补这一条还不够：人**确实想**看一张仍然 open 的 GitHub 卡的镜像卡时，
      手动关掉后会被永久钉死（再也建不出来）。所以还缺下面一条闸。
    - **最近被关的卡不重建**（`RECENTLY_CLOSED_HOURS`）：同一幂等键在窗口内被关过
      ⇒ 本轮**跳过建卡**并打印一行人话。判据刻意用「时间窗」而不是「关闭原因」：
      CNB 侧关闭动作至少有四条来源（重复卡清理 / 状态回流 / 人手动 / NPC 误关），
      逐条识别等于拟合历史；时间窗一视同仁，且 60 天后自动放飞，不会永久死锁。

    一句话：**「建过」与「开着」是两件事。** 把前者按后者判，就等于让「关一张卡」
    成了「下一轮再建一张」的许可证。
    """
    mirrored: dict[str, Any] = state.setdefault('mirrored', {})
    # 状态文件的键就是 GitHub 编号（str），值只存 CNB 编号与标题快照。
    cached = {int(k) for k in mirrored if str(k).isdigit()}

    existing = list_cnb_issues('open') + list_cnb_issues('closed')
    mirror_cards = [
        it
        for it in existing
        if any((lb.get('name') if isinstance(lb, dict) else lb) == MIRROR_LABEL for lb in (it.get('labels') or []))
    ]
    print(
        f'🔍 CNB 侧 {len(existing)} 张卡中有镜像卡 {len(mirror_cards)} 张，逐张读取 GitHub 编号…'
        f'（状态文件缓存 {len(cached)} 条，**只作索引、不作为已镜像全集**）'
    )

    seen: set[int] = set()
    closed_groups: dict[int, list[dict[str, Any]]] = {}
    for card in mirror_cards:
        try:
            detail = get_cnb_issue(int(card['number']))
        except Exception as exc:  # noqa: BLE001
            print(f'  ⚠️ 读取 CNB #{card["number"]} 失败，跳过：{exc}')
            continue
        gh = extract_github_number(detail.get('body'))
        if not gh:
            continue
        # **全部 state 都算「建过」**（源 CNB #6）：只认 open 时，清理动作（关卡）
        # 等于把幂等键匿名掉 ⇒ 下一轮原地重建一张空卡，再被分诊贴评论、再被关……
        # 「建过」与「开着」是两件事，判重只能问前者。
        seen.add(gh)
        if (detail.get('state') or 'open') != 'open':
            closed_groups.setdefault(gh, []).append(detail)
            continue
        mirrored[str(gh)] = {'cnb': int(card['number']), 'title': card['title'][:80]}

    _remember_recently_closed(mirrored, closed_groups)

    # 并集：缓存里有、CNB 侧已找不到的也保留（可能只是本轮读取失败），
    # **宁可漏建也不重复建** —— 漏建能被下一轮扫描补上，重复建会污染看板且不可逆。
    return cached | seen


# 同一幂等键在这么久之内被关过 ⇒ 本轮**不重建**。60 天足够覆盖任何人工清理节奏，
# 又不至于把「用户想重开」永久钉死（到期后自动放飞，不需要谁去改配置）。
RECENTLY_CLOSED_HOURS = 24 * 60


def _parse_cnb_time(value: Any) -> datetime | None:
    """解析 CNB 的时间串（`2026-10-19T09:17:28Z` 这类）。解析不了返回 None，不猜。"""
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone(UTC)
    except ValueError:
        return None


def _remember_recently_closed(
    mirrored: dict[str, Any],
    closed_groups: dict[int, list[dict[str, Any]]],
    *,
    now: datetime | None = None,
    window_hours: int = RECENTLY_CLOSED_HOURS,
) -> dict[int, str]:
    """把「最近被关过」的幂等键记进缓存，返回 `{GitHub 编号: 关闭时刻}`。

    纯函数（`now` 可注入），供单测直接用。三个刻意的选择：

    - **只记时间点，不记原因**：关闭来源至少有重复卡清理 / 状态回流 / 人手动 / NPC 误关
      四种，逐条识别等于拟合历史；时间窗一视同仁。
    - **同一键有多张 closed 卡时取最新那张**：重建出来的卡一定是后来那张。
    - **解析不了时间就不记**：宁可多建一张，也不用一个猜出来的时间当判据
      （#171：「拿不到」不等于「没有」—— 但它在这里的正确处置是**不动手**，不是编一个值）。
    """
    now = now or datetime.now(UTC)
    fresh: dict[int, str] = {}
    for gh, cards in closed_groups.items():
        latest: datetime | None = None
        for card in cards:
            ts = _parse_cnb_time(card.get('closed_at')) or _parse_cnb_time(card.get('updated_at'))
            if ts and (latest is None or ts > latest):
                latest = ts
        if latest is None:
            continue
        if (now - latest).total_seconds() <= window_hours * 3600:
            fresh[gh] = latest.strftime('%Y-%m-%dT%H:%M:%SZ')
    mirrored['_recently_closed'] = {str(k): v for k, v in sorted(fresh.items())}
    return fresh


def recently_closed(state: dict[str, Any], *, now: datetime | None = None) -> dict[int, str]:
    """从缓存里取「最近被关过」的键 → 关闭时刻（供 `run()` 判「要不要跳过建卡」）。"""
    now = now or datetime.now(UTC)
    raw = (state.get('mirrored') or {}).get('_recently_closed') or {}
    out: dict[int, str] = {}
    for key, value in raw.items():
        if not str(key).isdigit():
            continue
        ts = _parse_cnb_time(value)
        if ts is None:
            continue
        if (now - ts).total_seconds() <= RECENTLY_CLOSED_HOURS * 3600:
            out[int(key)] = str(value)
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_local_report(*, out: str | None = None) -> int:
    """`--report-local`：只报告，不建卡、不写状态文件。

    为什么要有它（而不是让人自己数）：回写作业对「认不出 GitHub 编号」的卡是
    **静默跳过**的，于是「CNB 侧到底有多少卡是本地卡、它们上面有多少讨论」在
    今天**没有任何观测手段**——只能人肉翻。这与 #117 全卡的主题同源：不是缺功能，
    是缺「能问出这件事」的作业。

    **只读**：不建卡、不改卡、不落状态文件。与 `check_mirror_refs.py` 同一条边界。
    """
    cards: list[dict[str, Any]] = []
    for st in ('open', 'closed'):
        cards.extend(list_cnb_issues(st))
    # 列表接口不返回 body，而判据要看正文 ⇒ 逐张取详情。
    #
    # **不做「已知镜像卡就跳过」的优化**：状态文件里的映射是一份缓存、且历史上只覆盖
    # 首轮全量同步那批（107 张）。用它跳过等于让报告只统计「状态文件不知道的卡」——
    # 数字会小得离谱且**看不出来**（实测：跳过 107 张后报告说「本地卡 12 张」，
    # 而真实总数是 123 张卡）。一份少算了 87% 却依然自洽的报告，比没有报告更坏。
    detailed: list[dict[str, Any]] = []
    print(f'📥 CNB 卡 {len(cards)} 张，逐张读取正文…', file=sys.stderr)
    for card in cards:
        try:
            detail = get_cnb_issue(int(card['number']))
        except Exception as exc:  # noqa: BLE001  # 取不到不能当成「它是本地卡」
            print(f'  ⚠️ 读取 CNB #{card["number"]} 失败，跳过（不计入任何一类）：{exc}', file=sys.stderr)
            continue
        # 详情接口不保证带 comment_count，缺了就用列表里的值
        if not detail.get('comment_count'):
            detail['comment_count'] = card.get('comment_count')
        detailed.append(detail)

    report = local_card_report(detailed)
    text = render_local_report(report)
    print(text)
    if out:
        Path(out).write_text(text + '\n', encoding='utf-8')
        print(f'\n已写入 {out}')
    return 0


def run(dry_run: bool, limit: int | None) -> int:
    state = load_state()
    already = harvest_existing(state)

    gh_issues, complete = fetch_github_open_issues()
    print(f'📥 GitHub open issue {len(gh_issues)} 张；CNB 已镜像 {len(already)} 张')

    # ⚠️ 这里**不再**按 `already` 过滤：`recently_closed()` 是同一份判据的**子集**，
    # 下面只过滤一次，免得「先滤掉、再滤一次」写成两处真相（第二次漏了就没人发现）。
    pending = sorted(gh_issues, key=lambda i: i['number'])

    # 闸门 ①：已经建过的（**含已关闭的**）不再重建。
    # 「开着」与「建过」是两件事（源 CNB #6）：只认 open 时，关一张卡 =
    # 下一轮再建一张，清理动作反而成了重建开关。
    skipped_mirrored = [i for i in pending if i['number'] in already]
    pending = [i for i in pending if i['number'] not in already]
    if skipped_mirrored:
        print(f'⏭️ {len(skipped_mirrored)} 张已建过（含已关闭的镜像卡），跳过')

    # 闸门 ②：**最近被关过的镜像卡不重建**（源 CNB #6，2026-10-19）。
    #
    # 为什么需要它（上面那层只管住了「缓存短路」）：判重改问全部 state 之后，
    # 一张被人**手动关掉**、而 GitHub 侧仍 open 的卡就再也建不出来了。把它恢复成
    # 「能建」又会让清理动作重新变成「明天再建一张」的开关。二者之间的那条线是时间：
    # 窗口内（`RECENTLY_CLOSED_HOURS`）当「刚处置过、别碰」，到期后自动放飞。
    fresh_closed = recently_closed(state)
    if fresh_closed:
        held = [i for i in pending if i['number'] in fresh_closed]
        if held:
            pending = [i for i in pending if i['number'] not in fresh_closed]
            print(
                f'⏸️ {len(held)} 张 GitHub 卡在 CNB 侧的镜像卡**最近被关过**'
                f'（{RECENTLY_CLOSED_HOURS // 24} 天内），本轮不重建：'
                f'{[i["number"] for i in held][:10]}'
                f'{"…" if len(held) > 10 else ""}'
            )
            print('   判据见 harvest_existing 的 docstring（「建过」≠「开着」）；要立刻重建请直接跑 --limit 或手工建卡。')

    if limit:
        pending = pending[:limit]

    if not pending:
        # 「拉不到」不等于「没有新增」（源 CNB #179 / #171 同族）：
        # 数据不完整时报「已对齐」是本机制最坏的失败形态 —— 漏建 + 无人发现。
        if not complete:
            print('❌ 数据不完整，本次结论不可信：拉取被截断（翻页触顶或分页中断）。')
            print('   注意：这里本该打印「无新增」——但因数据不完整，该结论不成立。')
            return 1
        print('✅ 无新增，两侧已对齐')
        save_state(state)
        return 0

    if not complete:
        # 有得建就照建（部分数据仍安全），但**不背书**「这是全部」。
        print(f'⚠️ 数据不完整（拉取被截断）：已发现的 {len(pending)} 张照常处理，但可能仍有遗漏。')

    print(f'🆕 待建 {len(pending)} 张')
    created = 0
    for issue in pending:
        title = issue['title']
        if dry_run:
            print(f'  [DRY-RUN] #{issue["number"]} {title[:60]}')
            continue
        try:
            number = create_cnb_issue(issue)
        except Exception as exc:  # noqa: BLE001
            print(f'  ❌ #{issue["number"]} {title[:60]} 失败：{exc}')
            continue
        state['mirrored'][str(issue['number'])] = {
            'cnb': number,
            'title': title[:80],
        }
        created += 1
        print(f'  ✅ CNB #{number} ← GitHub #{issue["number"]} {title[:50]}')

    if not dry_run:
        state['last_sync_at'] = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
        save_state(state)

    print(f'🎉 完成：新建 {created} 张，跳过已存在 {len(gh_issues) - len(pending)} 张')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='GitHub → CNB issue 增量镜像')
    parser.add_argument('--apply', action='store_true', help='真正创建（默认 dry-run）')
    parser.add_argument('--dry-run', action='store_true', help='只报告不创建（默认行为）')
    parser.add_argument('--limit', type=int, default=None, help='本次最多建几张（调试用）')
    parser.add_argument(
        '--report-local',
        action='store_true',
        help='只报告：CNB 侧本地卡 vs 镜像卡的对照（不建卡、不写状态文件）',
    )
    parser.add_argument('--out', default=None, help='配合 --report-local 把 markdown 报告写到文件')
    args = parser.parse_args(argv)

    if args.report_local:
        return run_local_report(out=args.out)

    return run(dry_run=not args.apply, limit=args.limit)


if __name__ == '__main__':
    sys.exit(main())
