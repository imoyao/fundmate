#!/usr/bin/env python3
"""dev → main 发版 readiness 机械闸（纯规则，只报告不自动合并）。

背景
----
main 与 dev 已分叉：main 上留有 3 个历史发版 PR（#1524 / #1645 / #1765）用
merge commit 产生的节点，dev 侧从未回合并，分叉点停在 a8fe1be10（2026-09-29）。
本脚本把「dev 是 main 的后代」作为发版前置判据，检不出来就直接拦。

判定边界（重要）
----------------
本脚本**只做机械判定**。它判不出的东西一律标记为 NEEDS_HUMAN 而不是猜测：
  - 「有没有中间态」需要跨文件读代码（新增表有无读路径消费、flag 有无默认值），
    纯规则判不了，交 agent 会话或人工复核，判据见 docs/spec/release-readiness.md；
  - 「这张卡该不该关」不是机械信号。issue_health_scan 的 B 类反例已证：
    「有过合入且无开放 PR」与「验收达成」没有因果关系（#1460 / #1121 / #980）。

因此脚本输出的是**发版前置条件清单**，不是「可以发版」的结论。
开 PR 与合并发版 PR 均由调用方决定，本脚本永不 merge、永不 push。

用法
----
    python scripts/release_readiness.py --repo imoyao/fundmate [--out report.md]
    python scripts/release_readiness.py --repo imoyao/fundmate --json

退出码
------
    0  全部机械闸通过
    1  存在 BLOCK 级问题（不可发版）
    2  执行错误（gh 未认证 / 网络 / 仓库不存在）

依赖：gh CLI 已认证。本地可 `gh auth token`，CI 注入 GITHUB_TOKEN 后 gh 同样可用。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_REPO = 'imoyao/fundmate'
MAIN_BRANCH = 'main'
DEV_BRANCH = 'dev'
GATE_CONTEXT = '质量门禁汇总'
#: 拉取 PR 的页大小。
#:
#: **性能实测（2026-10-08，本机到 GitHub 链路）**：
#:   pulls?state=closed&base=dev&per_page=100  → 单次 94s
#:   compare/main...dev                → 单次 45s
#: 全流程串起来一度稳定 SIGTERM（预算被 120s 默认上限截断）。降低往返次数是
#: 唯一有效手段：
#:   1) page=30 而非 100 —— 单次响应体小得多（body 字段是大头），够覆盖一周批次；
#:   2) gate 判定复用同一份已合列表，不再二次拉取；
#:   3) 双向 compare 合并为一次 `compare/main...dev`，behind 由
#:      「dev 是否为 main 的祖先」这一等价判据推出，省掉 45s。
PR_PAGE = 30
#: gate 判定最多回溯多少个已合 PR（每个 PR 一次 check-runs API 调用）
GATE_SCAN_MAX = 4

# 发版节奏护栏：距上次发版的提交数与天数超过软阈值时提示人工复核，
# 不是拦截——高产出期发版是合理的，只是需要人确认「这段时间真的都验证过」。
COMMITS_SOFT_MAX = 120
DAYS_SOFT_MAX = 10
# 单个 PR 的规模软上限：超大 PR 的 diff 难以在正文里穷举，review 覆盖度必然下降。
PR_FILES_SOFT_MAX = 40
PR_ADDITIONS_SOFT_MAX = 1500

#: 中间态信号词。出现在功能 PR 的**标题**里 → BLOCK（明确自我声明为中间态）。
#: 出现在**发版 PR 正文**里 → 单独提示（发版 PR 正文常引用这类卡做说明，属正常）。
#:
#: 反向验证过的排除项（2026-10-08 实证）：
#:  - 「占位」**不是**中间态信号。#1855「按方案 A 处置死代码——删重复实现，两页降为占位」
#:    与 #1854「占位页去假数据」都是**完成态**：刻意把废弃功能收敛为占位页是交付结果，
#:    不是「做了一半」。误伤会让机械闸可信度归零（同issue-health-scan B 类的教训）。
#:  - 「临时方案」「过渡」保留，但需人工确认——它们同样可能是「刻意保留的过渡态」。
INTERMEDIATE_TITLE_PATTERNS = (
    r'\bwip\b',
    r'中间态',
    r'分步',
    r'未完成',
    r'半成品',
)

#: closing keyword 解析。与 `scripts/close_linked_issues.js`（D37）口径**必须一致**：
#: 那边支持的写法这边也得认，否则「体检说该关、发版报告说没写 Closes」⇒ 口径分裂。
#:
#: 关键字形态照抄真源：`close[sd]?` / `fix(?:e[sd])?` / `resolve[sd]?` 九个变体。
#: **不要**写成 `clos(?:e[sd])?`——那展开是 `clos|close|closeds|closes`，匹配不到 `closed`
#: （2026-10-08 实测：`close #5; closed #6` 只抓到 #6/#7，#5 被吞）。
CLOSER_RE = re.compile(
    r'(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*'
    r'(?:[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*)?'
    r'#\d+(?:\s*[,，、]\s*#?\d+)*'
)
NUM_RE = re.compile(r'#(\d+)')
# 剥离围栏代码块与行内代码，避免文档示例被当成真关键字。
FENCE_RE = re.compile(r'(?ms)^```.*?^```\s*$')
INLINE_CODE_RE = re.compile(r'`[^`\n]*`')


def strip_code(body: str | None) -> str:
    """去掉围栏代码块与行内代码，只留正文散文。"""
    if not body:
        return ''
    return INLINE_CODE_RE.sub(' ', FENCE_RE.sub(' ', body))


# ---------------------------------------------------------------- 纯函数层


@dataclass
class Check:
    """单条机械检查结果。"""

    name: str
    level: str  # 'block' | 'warn' | 'ok'
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


def is_intermediate_title(title: str | None) -> bool:
    """标题是否自我声明为中间态。纯正则，无副作用。"""
    if not title:
        return False
    low = title.lower()
    return any(re.search(pat, low) for pat in INTERMEDIATE_TITLE_PATTERNS)


def closers_in(body: str | None) -> set[int]:
    """从 PR 正文提取 closing keyword 指向的 issue 编号（已剥离代码块）。

    先按 CLOSER_RE 定位「keyword + 编号列表」整段，再在段内逐个取 `#N`——
    这样 `Closes #1, #2` / `Closes #1、#2` / `Closes #1,#2` 都能全抓到。
    跨仓 `owner/repo#N` 也返回（由`cross_repo_closers` 单独标出），
    因为 `close_linked_issues.js` 对跨仓「只登记不操作」，报告要能区分。
    """
    text = strip_code(body)
    out: set[int] = set()
    for seg in CLOSER_RE.finditer(text):
        out.update(int(n) for n in NUM_RE.findall(seg.group(0)))
    return out


def cross_repo_closers(body: str | None) -> set[int]:
    """跨仓 closing keyword 指向的编号（GitHub 不会对本仓生效）。

    与 `close_linked_issues.js` 的「跨仓只登记不操作」口径一致。
    """
    text = strip_code(body)
    return {
        int(m.group(1))
        for m in re.finditer(
            r'(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*'
            r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*#(\d+)',
            text,
        )
    }


def classify_fork(ahead: int, behind: int) -> str:
    """main/dev 分叉性质。

    ahead  = origin/dev 有而 main 没有的提交数（dev 领先）
    behind = origin/main 有而 dev 没有的提交数（main 领先）
    """
    if behind > 0:
        return 'block'
    if ahead == 0:
        return 'ok'
    return 'ok'


def diff_size_warn(commits: int, days: float) -> Check:
    """发版批次规模护栏。超软阈值 → warn，不拦。"""
    reasons = []
    if commits > COMMITS_SOFT_MAX:
        reasons.append(f'提交数 {commits} > {COMMITS_SOFT_MAX}')
    if days > DAYS_SOFT_MAX:
        reasons.append(f'距上次发版 {days:.1f} 天 > {DAYS_SOFT_MAX}')
    if not reasons:
        return Check('批次规模', 'ok', f'{commits} 提交 / {days:.1f} 天，在常规区间')
    return Check(
        '批次规模',
        'warn',
        '；'.join(reasons) + ' —— diff 难以在发版 PR 正文里穷举，review 覆盖度会下降',
        {'commits': commits, 'days': round(days, 1)},
    )


def pr_size_warn(pr: dict) -> Check | None:
    """单个功能 PR 规模过大 → warn。"""
    files = pr.get('changed_files') or 0
    adds = pr.get('additions') or 0
    reasons = []
    if files > PR_FILES_SOFT_MAX:
        reasons.append(f'{files} 文件 > {PR_FILES_SOFT_MAX}')
    if adds > PR_ADDITIONS_SOFT_MAX:
        reasons.append(f'+{adds} 行 > +{PR_ADDITIONS_SOFT_MAX}')
    if not reasons:
        return None
    return Check(
        f'PR #{pr["number"]} 规模',
        'warn',
        '；'.join(reasons),
        {'number': pr['number'], 'files': files, 'additions': adds},
    )


def merged_since_release(
    pool: list[dict], release_merged_at: str | None, page_size: int = PR_PAGE
) -> tuple[list[dict], bool]:
    """从**一页**已合 PR 里挑出「上次发版之后合入」的，并判断这一页是否取全。

    WHY（2026-11-02 修复）：首版直接 `len(merged_since)` 当待发 PR 数。但 `PR_PAGE=30`
    是刻意的性能取舍（见 PR_PAGE 注释），一页只装 30 条——v0.3.0 发版实测真实 220 个
    待发 PR，报告却写「27 个待发 PR」并据此断言「标题无中间态信号词」。
    **数字看着像全量、实际只覆盖 12%**，比不查更危险：读者会据此认为中间态已扫完。

    ⇒ 返回 `(items, complete)`。`complete` 为假的三种来源，一并视为「未取全」：
      1. 本页装满（`len == page_size`）且末条仍新于上次发版 —— 后面还有；
      2. 上游没给出「上次发版」的时间边界 —— 边界未知，无从判断；
      3. 本页为空但时间边界缺失（同 2 的退化情形）。

    注意：调用方**必须**把 `complete=False` 渲染成「≥N」，不得写成精确值。
    """
    if not release_merged_at:
        return [], False
    items = [p for p in pool if p.get('merged_at') and p['merged_at'] > release_merged_at]
    merged_times = [p.get('merged_at') or '' for p in pool]
    oldest = min((t for t in merged_times if t), default='')
    if len(pool) < page_size:
        return items, True
    # 本页装满：末条已经旧于（或等于）上次发版 ⇒ 边界已被跨过，本页即全量
    return items, bool(oldest and oldest <= release_merged_at)


#: DDL 判据的路径形态。
#: 2026-11-02 修正（v0.3.0 发版实测）：首版只认 `alembic` / `migrations/` / `schema.sql` /
#: `init_db` / `*.sql`，而**本仓没有 alembic**——迁移函数写在
#: `backend/app/core/migrations.py`，`init_db()` 在 `backend/app/core/database.py` 里，
#: 而 `init_db` 是**函数名**，路径里根本不会出现。于是这条闸在本仓**结构上不可能亮红**：
#: 那次发版实际有 1320 行迁移改动、5 张新表，脚本却判「未命中迁移或建表脚本」（假绿灯）。
#:
#: ⇒ 判据按**真实布局**认三类：迁移实现 / 表结构定义 / SQL 脚本。
DDL_PATH_PATTERNS = (
    r'alembic/',
    r'migrations?/',  # 目录式迁移（含 supabase/migrations/）
    r'\.sql$',  # 含 schema.sql / 各类 DDL 脚本
    # 本仓实际形态：迁移函数与 init_db 都在 core 下
    r'backend/app/core/migrations\.py$',
    r'backend/app/core/database\.py$',
    # 表/列定义集中在各域 models.py、app/models/*.py（一文件一张表）与独立 schema 脚本
    r'(?:^|/)models\.py$',
    r'(?:^|/)models/[^/]+\.py$',
    r'init_db',  # init_db 本身是函数名；保留关键字形态，以兼容独立脚本化的迁移
    # Supabase 侧 DDL（触发器 / RLS / REVOKE）
    r'supabase/',
)
DDL_PATH_RE = re.compile('|'.join(f'(?:{p})' for p in DDL_PATH_PATTERNS), re.I)
DDL_SCOPE_NOTE = '用本地 `git diff --name-only origin/main...origin/dev` 复核'


def migration_risk_warn(changed: list[str], truncated: bool = False) -> Check:
    """改动命中迁移/建表文件时提示：DDL 不可逆，发版前必须确认可回滚。

    `truncated`（compare API 只回前 300 个文件）时**不得判 ok**——拿不到完整文件列表
    就等于「不知道有没有 DDL」，把它报成「通过」是本仓反复踩过的假绿灯形态
    （同 `check_view_thickness` 的「拿不到输入一律按红」）。
    """
    risky = [f for f in changed if DDL_PATH_RE.search(f)]
    if risky:
        detail = f'改动含 {len(risky)} 个迁移 / 建表相关文件；DDL 不可逆，发版前确认回滚路径'
        if truncated:
            detail += f'（文件列表被截断，实际可能更多；{DDL_SCOPE_NOTE}）'
        return Check(
            'DDL / 迁移',
            'warn',
            detail,
            {'files': risky[:20], 'truncated': truncated},
        )
    if truncated:
        return Check(
            'DDL / 迁移',
            'warn',
            f'文件列表被截断（仅见 {len(changed)} 个），无法确认是否含迁移改动；{DDL_SCOPE_NOTE}',
            {'files': [], 'truncated': True},
        )
    return Check('DDL / 迁移', 'ok', '未命中迁移或建表脚本', {'files': [], 'truncated': False})


# ---------------------------------------------------------------- gh 适配层


# ---------------------------------------------------------------- 进程内缓存
#
# 2026-10-08 实测：GitHub REST 的 pulls 列表每条都带完整 body，单页 100 条 ≈ 数 MB，
# 而同一进程内 `list_prs(repo, 'dev')` 会被 latest_gate_status / merged_since /
# open_release_pr 反复调用（各自带不同 limit ⇒ 缓存键必须含 limit）。
# 不加缓存时脚本稳定 SIGTERM。加了之后整轮 API 调用从 ~15 次降到 ~5 次。

_CACHE: dict[tuple[str, ...], Any] = {}


def gh_json(args: list[str], retries: int = 3, cache: bool = True) -> Any:
    """调用 gh api 并解析 JSON，带重试与进程内缓存。"""
    key = tuple(args)
    if cache and key in _CACHE:
        return _CACHE[key]
    last: Exception | None = None
    for _ in range(retries):
        try:
            proc = subprocess.run(
                ['gh', 'api', *args], capture_output=True, text=True, timeout=90, encoding='utf-8'
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout).strip()[:400])
            data = json.loads(proc.stdout or 'null')
            if cache:
                _CACHE[key] = data
            return data
        except Exception as exc:  # noqa: BLE001 —— 统一重试
            last = exc
    raise RuntimeError(f'gh 调用失败（重试 {retries} 次）: {last}')


def branch_sha(repo: str, branch: str) -> str | None:
    data = gh_json([f'repos/{repo}/branches/{branch}'])
    return (data or {}).get('commit', {}).get('sha')


def compare(repo: str, base: str, head: str) -> dict:
    return gh_json([f'repos/{repo}/compare/{base}...{head}']) or {}


def is_ancestor(repo: str, maybe_ancestor: str, descendant: str) -> bool:
    """`maybe_ancestor` 是否为 `descendant` 的祖先。

    用于替代「反向 compare」省一次 45s 往返（见 PR_PAGE 处的性能实测）：
    `behind == 0` 等价于「origin/main 是 dev 的祖先」。
    """
    data = gh_json([f'repos/{repo}/compare/{maybe_ancestor}...{descendant}'])
    return (data or {}).get('status') in ('ahead', 'identical')


def list_prs(repo: str, base: str, state: str = 'closed', limit: int = 100) -> list[dict]:
    data = gh_json(
        [f'repos/{repo}/pulls?state={state}&base={base}&per_page={limit}&sort=updated&direction=desc']
    )
    return data if isinstance(data, list) else []


def latest_release_pr(repo: str) -> dict | None:
    """最近一次已合并的 dev → main 发版 PR。"""
    for pr in list_prs(repo, MAIN_BRANCH, 'closed', 30):
        if pr.get('merged_at') and pr.get('head', {}).get('ref') == DEV_BRANCH:
            return pr
    return None


def latest_checks(repo: str, ref: str) -> list[dict]:
    data = gh_json([f'repos/{repo}/commits/{ref}/check-runs?per_page=100'])
    return (data or {}).get('check_runs', []) or []


def latest_gate_status(repo: str, merged: list[dict] | None = None) -> tuple[str | None, dict]:
    """取 dev 上最近一个已合并 PR 的 `质量门禁汇总` 结果。

    为什么查 PR 而非 dev HEAD（2026-10-08 实证）：`ci.yml` 的 gate job 由
    `pull_request` 触发，`push` 到 dev 只跑 `乱码守卫` 与 `Analyze`。
    所以查 dev HEAD 的 check-runs **永远查不到 gate**，会误报「CI 未跑」。

    `max_pr` 上界很重要：每个 PR 要单独调一次 check-runs API（≈1s），
    无上界时逐个扫就是逐个等，脚本必然超时（2026-10-08 实测）。

    `merged` 由调用方传入已拉好的列表，避免重复请求（缓存键含 limit，故必须复用同一份）。
    """
    pool = merged if merged is not None else list_prs(repo, DEV_BRANCH, 'closed', PR_PAGE)
    for pr in pool[:GATE_SCAN_MAX]:
        if not pr.get('merged_at'):
            continue
        sha = (pr.get('merge_commit_sha') or '').strip()
        if not sha:
            continue
        runs = latest_checks(repo, sha)
        gate = [c for c in runs if c.get('name') == GATE_CONTEXT]
        if gate:
            g = gate[0]
            return (g.get('conclusion') or g.get('status') or 'unknown').upper(), {
                'pr': pr['number'],
                'sha': sha,
                'url': g.get('html_url'),
            }
        # 该 PR 的 merge commit 上没有 gate —— 若还有非终态 check，说明 CI 在跑，
        # 报 pending 而不是继续往前找（往前找会读到更旧的绿灯，掩盖当下红灯）。
        if any((c.get('status') or '') in ('queued', 'in_progress') for c in runs):
            return 'PENDING', {'pr': pr['number'], 'sha': sha}
    return None, {}


def open_release_pr(repo: str) -> dict | None:
    """是否已存在未合并的 dev → main 发版 PR（幂等：避免每周重复开）。"""
    for pr in list_prs(repo, MAIN_BRANCH, 'open', 20):
        if pr.get('head', {}).get('ref') == DEV_BRANCH:
            return pr
    return None


def days_between(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400


# ---------------------------------------------------------------- 编排层


def scan(repo: str) -> dict:
    checks: list[Check] = []

    main_sha = branch_sha(repo, MAIN_BRANCH)
    dev_sha = branch_sha(repo, DEV_BRANCH)
    if not main_sha or not dev_sha:
        raise RuntimeError(f'取不到 {MAIN_BRANCH} / {DEV_BRANCH} 的 sha（仓库 {repo} 存在？）')

    # 闸一 1：分叉。只需一次 compare（main...dev），behind 用祖先关系反推（省 45s 往返）
    cmp_dev = compare(repo, MAIN_BRANCH, DEV_BRANCH)
    ahead = cmp_dev.get('total_commits', 0)
    dev_is_descendant = cmp_dev.get('status') in ('ahead', 'identical')
    behind = 0 if dev_is_descendant else compare(repo, DEV_BRANCH, MAIN_BRANCH).get(
        'total_commits', 0
    )
    lvl = classify_fork(ahead, behind)
    checks.append(
        Check(
            'main/dev 分叉',
            lvl,
            (
                f'{MAIN_BRANCH} 独有 {behind} 个提交 —— dev 不是 main 的后代，'
                '发版 PR 会出现反向差异'
                if lvl == 'block'
                else f'dev 领先 {ahead} 个提交，main 无独有提交（分叉已消除）'
            ),
            {'ahead': ahead, 'behind': behind, 'main_sha': main_sha, 'dev_sha': dev_sha},
        )
    )

    # 一次拉齐，已合 PR 列表供 gate 判定与 merged_since 共用（见 gh_json 缓存说明）
    dev_closed = list_prs(repo, DEV_BRANCH, 'closed', PR_PAGE)
    rel = latest_release_pr(repo)

    # 闸一 2：dev 最新合入的 gate 状态（main 的 required check 就是它）
    concl, ev = latest_gate_status(repo, merged=dev_closed)
    if concl is None:
        checks.append(
            Check(
                'dev 门禁状态',
                'warn',
                f'最近 20 个已合 PR 上都没读到 {GATE_CONTEXT}，可能 CI 未跑或已过保留期',
            )
        )
    else:
        checks.append(
            Check(
                'dev 门禁状态',
                'ok' if concl == 'SUCCESS' else 'warn',
                f'{GATE_CONTEXT} = {concl}（PR #{ev.get("pr")} 的 merge commit）',
                {**ev, 'conclusion': concl},
            )
        )

    # 闸一 3：批次规模 + DDL
    if rel:
        days = days_between(rel.get('merged_at'))
        checks.append(
            diff_size_warn(ahead, days if days is not None else 0.0)
            if days is not None
            else diff_size_warn(ahead, 0.0)
        )
        checks.append(
            Check(
                '上次发版',
                'ok',
                f"#{rel['number']} @ {rel.get('merged_at')} —— {rel.get('title', '')[:60]}",
                {'number': rel['number']},
            )
        )
    else:
        checks.append(Check('上次发版', 'warn', '找不到历史 dev → main 发版 PR'))
        checks.append(diff_size_warn(ahead, 0.0))

    files = sorted({f.get('filename', '') for f in (cmp_dev.get('files') or [])})
    # compare API 只返回前 300 个文件且被截断时，明确说明覆盖范围而不是假装扫全了。
    truncated = bool(cmp_dev.get('files_truncated') or len(cmp_dev.get('files') or []) >= 300)
    # 截断必须传给 DDL 判定：拿不到完整文件列表时不得输出「通过」（见 migration_risk_warn）
    checks.append(migration_risk_warn(files, truncated=truncated))
    if truncated:
        checks.append(
            Check(
                'DDL 覆盖范围',
                'warn',
                f'GitHub compare API 返回的文件数被截断（≥300 / 上限），'
                f'已按返回的 {len(files)} 个判定；完整范围{DDL_SCOPE_NOTE}',
                {'returned': len(files)},
            )
        )

    # 闸一 4：已存在未合并的发版 PR → 幂等提示
    pending = open_release_pr(repo)
    checks.append(
        Check(
            '待合并发版 PR',
            'warn' if pending else 'ok',
            (
                f"#{pending['number']} 已存在未合并的 dev → main PR —— "
                '本周不重复开，先处理它'
                if pending
                else '无待合并发版 PR'
            ),
            {'number': pending['number']} if pending else {},
        )
    )

    # 闸二输入：待发 PR 清单 + 中间态信号（判据本身在 docs/spec/release-readiness.md）
    rel_merged_at = (rel or {}).get('merged_at') or ''
    merged_since, prs_complete = merged_since_release(dev_closed, rel_merged_at or None)
    count_label = f'{len(merged_since)}' if prs_complete else f'≥{len(merged_since)}'
    scope = f'{count_label} 个待发 PR' + ('（已取全）' if prs_complete else f'（仅取最近 {len(dev_closed)} 条）')
    intermediate = [
        {'number': p['number'], 'title': p['title'], 'url': p.get('html_url')}
        for p in merged_since
        if is_intermediate_title(p.get('title'))
    ]
    checks.append(
        Check(
            '中间态信号',
            'warn' if intermediate else ('ok' if prs_complete else 'warn'),
            (
                f'{len(intermediate)} 个已合 PR 标题含中间态信号词，需人工确认是否真完整（{scope}）'
                if intermediate
                else f'{scope}，标题无中间态信号词'
                + ('' if prs_complete else ' —— 但只扫了这一页，更早的待发 PR 未覆盖')
            ),
            {
                'intermediate': intermediate,
                'merged_since': len(merged_since),
                'merged_since_complete': prs_complete,
            },
        )
    )
    if not prs_complete:
        checks.append(
            Check(
                '待发 PR 覆盖范围',
                'warn',
                f'待发 PR 数只能给下限 {count_label}：`PR_PAGE={PR_PAGE}` 只取最近一页，'
                f'更早的待发 PR 既未计数也未扫标题。需要精确值请人工分页（`gh api` 逐页）复核',
                {'counted': len(merged_since), 'page_size': PR_PAGE},
            )
        )

    for pr in merged_since:
        w = pr_size_warn(pr)
        if w:
            checks.append(w)

    # release note 判据：base=main 时 GitHub 原生解析 closing keyword ⇒ 写错就真关卡
    rel_body = (rel or {}).get('body')
    release_note_closers = sorted(closers_in(rel_body))
    cross = sorted(cross_repo_closers(rel_body))
    checks.append(
        Check(
            '上次发版 Closes',
            'ok',
            (
                f"#{rel['number']} 正文带 Closes {release_note_closers}"
                + (f"（另有跨仓引用 {cross}，GitHub 不会对本仓生效）" if cross else '')
                + ' —— base=main 时原生生效，已核对'
                if rel and release_note_closers
                else '上次发版正文无 closing keyword'
            ),
            {'closers': release_note_closers, 'cross_repo': cross},
        )
    )

    # 语义闸无法机械判定 —— 显式交接，不让「全绿」被误读成「可发版」
    checks.append(
        Check(
            '语义闸（不可机械化）',
            'warn',
            '中间态识别 / 卡片该不该关，必须回 origin/dev grep 实证，见 '
            'docs/spec/release-readiness.md；本脚本绿灯不代表可发版',
            {'handoff': 'docs/spec/release-readiness.md'},
        )
    )

    return {
        'repo': repo,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'ahead': ahead,
        'behind': behind,
        'main_sha': main_sha,
        'dev_sha': dev_sha,
        'last_release_pr': rel['number'] if rel else None,
        'pending_release_pr': pending['number'] if pending else None,
        'merged_since': len(merged_since),
        'merged_since_complete': prs_complete,
        'checks': [asdict(c) for c in checks],
        'verdict': 'BLOCK' if any(c.level == 'block' for c in checks) else 'PASS_WITH_WARN',
    }


def render(rep: dict) -> str:
    lines = [
        f"# 发版 readiness 机械闸报告（{rep['repo']}）",
        '',
        f"- 生成时间：{rep['generated_at']}",
        f"- dev 领先 main：**{rep['ahead']}** 提交 / main 独有：**{rep['behind']}**",
        f"- dev HEAD：`{rep['dev_sha'][:9]}`",
        f"- 上次发版：#{rep['last_release_pr'] or '-'}",
        f"- 待合并发版 PR：#{rep['pending_release_pr'] or '无'}",
        f"- 待发 PR 数：{rep['merged_since']}{'' if rep.get('merged_since_complete') else '（**下限**：只统计了最近一页）'}",
        f"- 机械闸结论：**{rep['verdict']}**",
        '',
        '> 本报告只做机械判定。绿灯 ≠ 可发版——中间态识别与关卡决策需回 `origin/dev` 实证。',
        '',
        '## 检查项',
        '',
        '| 项 | 级别 | 说明 |',
        '|----|------|------|',
    ]
    icon = {'block': '阻断', 'warn': '提示', 'ok': '通过'}
    for c in rep['checks']:
        lines.append(f"| {c['name']} | {icon[c['level']]} | {c['detail']} |")

    blocks = [c for c in rep['checks'] if c['level'] == 'block']
    if blocks:
        lines += ['', '## 阻断项', '']
        for c in blocks:
            lines.append(f"- **{c['name']}**：{c['detail']}")

    inter = next((c for c in rep['checks'] if c['name'] == '中间态信号'), None)
    if inter and inter['evidence'].get('intermediate'):
        lines += ['', '## 标题含中间态信号词的 PR（需人工确认）', '']
        for p in inter['evidence']['intermediate']:
            lines.append(f"- #{p['number']} {p['title']} — {p['url']}")

    lines += [
        '',
        '## 下一步',
        '',
        '1. 修完所有「阻断」项',
        '2. 按 `docs/spec/release-readiness.md` 的判据清单做语义复核（回 `origin/dev` grep）',
        '3. 决定哪些卡写`Closes`（base=main 时原生生效），哪些留 open 并标注「本次不发」',
        '4. 开 dev → main 发版 PR，**合并由人工确认**',
        '',
    ]
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description='dev → main 发版 readiness 机械闸')
    ap.add_argument('--repo', default=DEFAULT_REPO)
    ap.add_argument('--out', default='release_readiness.md')
    ap.add_argument('--json', action='store_true', help='输出 JSON 而非markdown')
    args = ap.parse_args()

    try:
        rep = scan(args.repo)
    except Exception as exc:  # noqa: BLE001
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        md = render(rep)
        if args.out and args.out != '-':
            from pathlib import Path

            Path(args.out).write_text(md, encoding='utf-8')
            print(f'→ {args.out}')
        else:
            print(md)

    return 1 if rep['verdict'] == 'BLOCK' else 0


if __name__ == '__main__':
    sys.exit(main())
