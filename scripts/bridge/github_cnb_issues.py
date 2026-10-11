#!/usr/bin/env python3
"""GitHub Issues → CNB Issues 单向增量镜像。

为什么需要它
------------
CNB 侧没有 GitHub 的 issue 视图，讨论散在两处。2026-10-11 做过一次全量手工同步
（107 张卡，CNB #5~#112），但那是**一次性**的：GitHub 之后新开的卡不会再出现，
两侧很快又各说各话。本脚本把那次同步固化成可重复执行的增量作业，配套
`.cnb.yml` 的每日 cron 跑。

设计取舍（与 #2 的那轮同步一致，避免同一批卡出现两种格式）
--------------------------------------------------------
- **单向**：只 GitHub → CNB，绝不回写 GitHub。双向会在两侧状态不一致时互相打架。
- **只增不覆盖**：已存在的镜像卡永不改动。存量卡里的正文/标签若被 CNB 侧人工调过，
  覆盖等于抹掉那些调整；镜像卡正文顶部已写明「只读镜像，讨论回 GitHub」。
- **关闭态不同步**：GitHub 关了 → CNB 也关，会造成「CNB 侧看不到活跃讨论」的误判，
  且关闭动作由人决定更稳。本脚本只建新卡（结论：只增）。
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
    # 建卡快照时刻：显式打印出来，避免正文里只有 GitHub 的创建时间、读者误以为本卡很新。见 #120 方案 A。
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
            f'> ⚠️ 本卡是**建卡时快照**（截至 {mirrored_at:%Y-%m-%d}），**不覆盖后续变更**；'
            '> 正文引用的文件 / 行号 / 字段 / 结论均为快照时刻的位置，可能与当前代码不一致——'
            '> 按它动手之前，先用 `git show <ref>:<file>` 确认该行仍在当前分支上。',
            '> ⚠️ 正式讨论、更正与状态变更请回到 GitHub 原卡，CNB 侧改动不会自动回流；'
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


# ---------------------------------------------------------------------------
# HTTP（标准库，无三方依赖）
# ---------------------------------------------------------------------------


def _github_repo() -> str:
    return os.environ.get('GITHUB_REPO') or GITHUB_REPO_DEFAULT


def _cnb_repo() -> str:
    return os.environ.get('CNB_REPO') or os.environ.get('CNB_REPO_SLUG') or CNB_REPO_DEFAULT


def _request(
    url: str,
    *,
    method: str = 'GET',
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> bytes:
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('User-Agent', 'fundmate-github-cnb-mirror')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_github_open_issues() -> list[dict[str, Any]]:
    """拉取 GitHub 仓库全部 open issue（跨页，剔除 PR）。

    GitHub 的 `/issues` 会把 PR 也混进来，靠 `pull_request` 字段剔除。
    匿名限额 60/时/IP；分页 100/页，一般 1~2 次调用即可，余量充足。
    """
    repo = _github_repo()
    headers: dict[str, str] = {'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'

    out: list[dict[str, Any]] = []
    page = 1
    while True:
        qs = urllib.parse.urlencode(
            {'state': 'open', 'per_page': 100, 'page': page, 'sort': 'created', 'direction': 'asc'}
        )
        raw = _request(f'https://api.github.com/repos/{repo}/issues?{qs}', headers=headers)
        batch = json.loads(raw)
        if not batch:
            break
        out.extend(i for i in batch if 'pull_request' not in i)
        if len(batch) < 100:
            break
        page += 1
    return out


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

    状态文件里有映射的直接信它；没有的（首次运行、或别人手工建的镜像卡）
    逐张拉正文抠 `GitHub 编号：#N`，并把结果写回状态文件，下次就不必再拉。
    """
    mirrored: dict[str, Any] = state.setdefault('mirrored', {})
    # 状态文件的键就是 GitHub 编号（str），值只存 CNB 编号与标题快照。
    known = {int(k) for k in mirrored if str(k).isdigit()}
    if known:
        return known

    existing = list_cnb_issues('open') + list_cnb_issues('closed')
    mirror_cards = [
        it
        for it in existing
        if any((lb.get('name') if isinstance(lb, dict) else lb) == MIRROR_LABEL for lb in (it.get('labels') or []))
    ]
    print(f'🔍 CNB 侧已有镜像卡 {len(mirror_cards)} 张，逐张读取 GitHub 编号…')

    for card in mirror_cards:
        try:
            detail = get_cnb_issue(int(card['number']))
        except Exception as exc:  # noqa: BLE001
            print(f'  ⚠️ 读取 CNB #{card["number"]} 失败，跳过：{exc}')
            continue
        gh = extract_github_number(detail.get('body'))
        if gh:
            mirrored[str(gh)] = {'cnb': int(card['number']), 'title': card['title'][:80]}
    return {int(k) for k in mirrored if str(k).isdigit()}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run(dry_run: bool, limit: int | None) -> int:
    state = load_state()
    already = harvest_existing(state)

    gh_issues = fetch_github_open_issues()
    print(f'📥 GitHub open issue {len(gh_issues)} 张；CNB 已镜像 {len(already)} 张')

    pending = [i for i in gh_issues if i['number'] not in already]
    pending.sort(key=lambda i: i['number'])
    if limit:
        pending = pending[:limit]

    if not pending:
        print('✅ 无新增，两侧已对齐')
        save_state(state)
        return 0

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
    args = parser.parse_args(argv)

    return run(dry_run=not args.apply, limit=args.limit)


if __name__ == '__main__':
    sys.exit(main())
