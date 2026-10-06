#!/usr/bin/env python3
"""Issue 体检周报扫描器（纯规则，只报告不自动关）。

背景（2026-09-26 全库排查教训）：
  - GitHub 只在 PR 目标为默认分支时解释 closing keyword，本仓默认分支是 main，
    功能 PR 一律 base=dev ⇒ 关卡长期靠人肉（close-linked-issues.yml 只管 9-24 之后的增量）。
  - 存量里存在「交付 PR 全部合入、卡还开着」（如 #1101 拖 24 天）这类问题，
    需要每周机械扫出来给人工复核。

判定全部为机械信号（不需要 AI），产出四类清单：
  A. 建议关闭（强）    —— 存在正文带 closing keyword 且已合入的关联 PR，且无开放关联 PR
  B. 已合 PR 待复核    —— 关联 PR ≥1 且全部 MERGED，无开放关联 PR（有过合入 ≠ 验收达成，见下方反例）
  C. 验收全勾          —— 正文 checkbox 均已勾选（可能范围已被收窄，需复核）
  D. 停滞高优          —— Q1-RED 超过 STALE_HIGH_DAYS 天无更新（推进 P0 或降级的信号）
  E. 僵尸卡            —— 超过 STALE_DAYS 天无更新且无关联 PR

口径修正（#1908，2026-10-06 逐张实证复核后）：
  - **closing keyword 带括号限定词 → 从 A 降级到 B**：`Closes #1286（数据底座部分）`、
    `Closes #1285（仅备注编辑部分）` 这类 keyword 只覆盖卡的一部分，计为 A 会「关早了」。
    本轮 A 类实证 5 张里3 张属此类。
  - **两类卡不进 A/B**：【自动告警】卡（如 #1490 daily-snapshot，workflow 成功时自动关）
    与「固定跟踪卡」（如 #1709 周报自身，每周追加评论、永不关档）——它们该不该关由生命周期决定，
    由交付信号推断会给出错误处方。
  - **B 与 D 重叠只出一处**：同轮同时命中 B（待复核）与 D（提 P0 或降级）时保留 D，
    因为「提 P0 或降级」是更具体的处方；B 段末尾附注数量，避免同一张卡收到相反处方。
  - **B 的措辞不是「可关」**：「有过合入且无开放」与「验收达成」没有因果关系，
    反例见 #1460（P2 待拍板 / P3 未动 / 定时链 15 连红）、#1121 与 #980（大 tracker 远未完成）。

用法：
    python scripts/issue_health_scan.py [--dry-run] [--repo imoyao/fundmate] [--out report.md]

- 依赖 gh CLI 认证（本地取 gh auth token；CI 注入 GITHUB_TOKEN 后 gh 同样可用）。
- --dry-run 只打印报告不发送；默认行为也只是把报告写到 --out 文件，发送由调用方决定。
- 永不自动关闭 issue / 永不修改其他卡 —— 本脚本只读 + 写一个报告文件。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REPO = 'imoyao/fundmate'
STALE_HIGH_DAYS = 21  # Q1-RED 无更新天数阈值（推进 P0 或降级的信号）
STALE_DAYS = 90  # 僵尸卡阈值
TIMELINE_MAX_ISSUES = 400  # 防御性上限，避免 API 调用失控

CLOSER_KW = re.compile(r'(?i)\b(fix(?:e[sd])?|clos(?:e[sd])?|resolv(?:e[sd])?)\s*#(\d+)')
# #1908 项1：keyword 后紧跟的括号里带「部分/仅/除…」限定词时，closing 只覆盖卡的一部分，
# 计为 A 强信号会关早卡，降级为 B 待复核。只认紧随其后的第一个括号——括号之后另起的
# 句子不算限定词。
CLOSER_LIMITED = re.compile(
    r'(?i)^[（(][^）)]*(?:部分|仅|仅限|除|不含|其余|其他|else|only|part\b)[^）)]*[）)]'
)
# #1908 项2：该不该关由生命周期决定的卡，不该由交付信号推断。
TRACK_ONLY_TITLE_PATTERNS = ('【自动告警】', '固定跟踪卡')
CHECKBOX_DONE = re.compile(r'^\s*[-*]\s+\[[xX]\]', re.MULTILINE)
CHECKBOX_ANY = re.compile(r'^\s*[-*]\s+\[( |x|X)\]', re.MULTILINE)


def closer_refs(body: str | None) -> tuple[set[int], set[int]]:
    """解析PR 正文里的 closing keyword，返回 (强信号编号集, 限定降级编号集)。

    同一编号可能同时落进两个集合（某个 PR 写 `Closes #1286`、另一个写
    `Closes #1286（部分）`）——判定以强信号为准，故调用方先查 strong。
    """
    text = body or ''
    strong: set[int] = set()
    limited: set[int] = set()
    for m in CLOSER_KW.finditer(text):
        num = int(m.group(2))
        # 只认紧随其后的括号：中间出现换行就是另起一句，不算对本次 keyword 的限定
        tail = text[m.end():m.end() + 60].lstrip(' \t')
        bucket = limited if CLOSER_LIMITED.match(tail) else strong
        bucket.add(num)
    return strong, limited


def split_closers(num: int, merged_prs: list[int], refs: tuple[set[int], set[int]]) -> tuple[list[int], list[int]]:
    """把已合入的关联 PR 分成 (closer PR 列表, 限定降级 PR 列表)。

    同一张卡若既有强信号 PR 又有降级 PR，以强信号为准（不重复计入降级），
    否则 #1286 这类「一部分交付」的卡会在 A/B 两段各出现一次。
    """
    strong, limited = refs
    closers = [p for p in merged_prs if num in strong]
    limited_only = [p for p in merged_prs if num in limited and num not in strong]
    return closers, limited_only


def is_track_only(issue: dict) -> bool:
    """自动告警卡 / 固定跟踪卡：关档由生命周期决定，不该进 A/B 候选（#1908 项2）。"""
    title = issue.get('title') or ''
    return any(p in title for p in TRACK_ONLY_TITLE_PATTERNS)


def classify(
    issue: dict, closers: list[int], limited: list[int], merged: list[int], open_prs: list[int]
) -> str | None:
    """把一张卡归入 A / B / TRACK_ONLY / None（不进候选）；抽成纯函数以便离线测试。

    - A：存在**无限定词**的 closer keyword 且已合入、无开放关联 PR；
    - B：有关联 PR 全部合入、无开放 PR（有过合入 ≠ 验收达成）；
    - TRACK_ONLY：【自动告警】/ 固定跟踪卡，关档由生命周期决定，不进候选。
    """
    if is_track_only(issue):
        return 'TRACK_ONLY'
    if closers and not open_prs:
        return 'A'
    if merged and not open_prs:
        return 'B'
    return None


def dedupe_bd(weak: list[tuple], stale_high: list[dict]) -> tuple[list[tuple], list[int]]:
    """B∩D 去重：同轮同时命中时只保留 D，B 侧返回被剔除的编号（#1908 项4）。

    「提 P0 或降级」比「待复核」是更具体的处方，故保留 D；否则同一张卡会在报告里
    同时收到两个相反处方（本轮实证 #1028 / #1014 / #894 / #808）。
    """
    d_nums = {it['number'] for it in stale_high}
    if not d_nums:
        return list(weak), []
    kept: list[tuple] = []
    overlap: list[int] = []
    for it, prs, note in weak:
        if it['number'] in d_nums:
            overlap.append(it['number'])
        else:
            kept.append((it, prs, note))
    return kept, overlap


def gh_json(args: list[str], retries: int = 3) -> object:
    """调用 gh api 并解析（--paginate 会输出逐页拼接的 JSON 数组，需逐段 raw_decode）。

    网络抖动（TLS handshake timeout 等）重试至多 3 次，指数退避。
    """
    import time

    last_err = ''
    for attempt in range(retries):
        out = subprocess.run(
            ['gh', 'api'] + args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=120,
        )
        if out.returncode == 0:
            text = out.stdout.strip()
            decoder = json.JSONDecoder()
            items: list = []
            idx = 0
            while idx < len(text):
                while idx < len(text) and text[idx] in ' \n\r\t':
                    idx += 1
                if idx >= len(text):
                    break
                obj, end = decoder.raw_decode(text, idx)
                items.extend(obj if isinstance(obj, list) else [obj])
                idx = end
            return items
        last_err = out.stderr.strip()[:200]
        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'gh api {" ".join(args[:3])}... 重试 {retries} 次仍失败: {last_err}')


def list_open_issues(repo: str) -> list[dict]:
    issues: list = []
    page = 1
    while True:
        batch = gh_json([f'repos/{repo}/issues?state=open&per_page=100&page={page}'])
        if not batch:
            break
        issues.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        if page > 10:
            break
    # 排除 PR（issues API 会混入 PR）
    return [i for i in issues if 'pull_request' not in i]


def cross_ref_prs(repo: str, num: int) -> set[int]:
    evs = gh_json([f'repos/{repo}/issues/{num}/timeline?per_page=100', '--paginate'])
    prs = set()
    for e in evs:
        if isinstance(e, dict) and e.get('event') == 'cross-referenced':
            src = (e.get('source') or {}).get('issue') or {}
            if src.get('pull_request'):
                prs.add(src['number'])
    return prs


def get_pr(repo: str, num: int) -> dict:
    out = subprocess.run(
        ['gh', 'api', f'repos/{repo}/pulls/{num}'],
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=60,
    )
    if out.returncode != 0:
        return {}
    return json.loads(out.stdout)


def days_since(iso: str | None) -> float:
    if not iso:
        return -1.0
    dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def fmt_issue(it: dict, extra: str = '') -> str:
    title = (it.get('title') or '').replace('|', '\\|')[:60]
    lbl = ','.join(l['name'] for l in it.get('labels', []) if l.get('name')) or '-'
    ms = (it.get('milestone') or {}).get('title') or '-'
    stale = max(0.0, days_since(it.get('updated_at')))
    return f'- #{it["number"]} {title}（标签:{lbl} | 里程碑:{ms} | {stale:.0f} 天未更新{extra}）'


def scan(repo: str) -> str:
    issues = list_open_issues(repo)[:TIMELINE_MAX_ISSUES]
    pr_cache: dict[int, dict] = {}

    strong: list[tuple[dict, list[int]]] = []  # A: closer PR 已合入（无括号限定词）
    weak: list[tuple[dict, list[int], str]] = []  # B: 关联 PR 全合入（待复核）
    checked_all: list[dict] = []  # C: checkbox 全勾
    stale_high: list[dict] = []  # D: Q1-RED 停滞
    zombie: list[dict] = []  # E: 僵尸卡
    track_only: list[dict] = []  # 【自动告警】/ 固定跟踪卡：关档由生命周期决定
    bd_overlap: list[int] = []  # 同轮命中 B 与 D，只在 D 出现

    for it in issues:
        num = it['number']
        prs = cross_ref_prs(repo, num)
        merged, open_prs = [], []
        merged_bodies: list[tuple[int, str]] = []  # (PR 号, 正文) —— 供 split_closers 判定 closer
        for p in sorted(prs):
            if p not in pr_cache:
                pr_cache[p] = get_pr(repo, p)
            d = pr_cache[p]
            if not d:
                continue
            # 注意：REST API 的 pulls.state 只有 open/closed，merged 是独立布尔字段
            # （GraphQL 封装 gh pr view 的 state 才是 MERGED，不能混用）
            if d.get('merged') is True:
                merged.append(p)
                merged_bodies.append((p, d.get('body') or ''))
            elif d.get('state') == 'open':
                open_prs.append(p)
            # else: closed 未合入（废弃 PR）——不算阻塞也不算交付
        # closing keyword 的强弱拆分集中在 split_closers（纯函数，可离线测试）
        strong_refs: set[int] = set()
        limited_refs: set[int] = set()
        for _p, _body in merged_bodies:
            _s, _l = closer_refs(_body)
            strong_refs |= _s
            limited_refs |= _l
        closers, limited_closers = split_closers(num, merged, (strong_refs, limited_refs))

        body = it.get('body') or ''
        any_cb = CHECKBOX_ANY.findall(body)
        done_cb = CHECKBOX_DONE.findall(body)
        has_q1 = any(l['name'] == 'Q1-RED' for l in it.get('labels', []))
        stale = days_since(it.get('updated_at'))

        bucket = classify(it, closers, limited_closers, merged, open_prs)
        if bucket == 'TRACK_ONLY':
            # 这类卡的关档由生命周期决定，交付信号对它们没有意义
            track_only.append(it)
        elif bucket == 'A':
            strong.append((it, closers))
        elif bucket == 'B':
            note = ' | closing keyword 带括号限定词，已从 A 降级待复核' if limited_closers else ''
            weak.append((it, merged, note))
        if any_cb and len(done_cb) == len(any_cb):
            checked_all.append(it)
        if has_q1 and stale > STALE_HIGH_DAYS:
            stale_high.append(it)
        if stale > STALE_DAYS and not prs:
            zombie.append(it)

    # B∩D 去重（#1908 项4）：只保留 D，B 段末尾附注被剔除的编号
    weak, bd_overlap = dedupe_bd(weak, stale_high)
    return render(len(issues), strong, weak, checked_all, stale_high, zombie, track_only, bd_overlap)


def render(
    total: int,
    strong: list[tuple],
    weak: list[tuple],
    checked_all: list[dict],
    stale_high: list[dict],
    zombie: list[dict],
    track_only: list[dict],
    bd_overlap: list[int],
) -> str:
    """把分类结果渲染成周报文本；抽成纯函数，使输出口径可离线断言（#1908）。"""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    lines = [
        f'## Issue 体检周报 · {today}',
        '',
        f'扫描开放卡 **{total}** 张（机械规则，只报告不自动关；候选需人工/agent 回 origin/dev 实证复核后再关）。本轮规则命中：',
        '',
        f'### A. 建议关闭（强信号：closing keyword 的 PR 已合入，{len(strong)} 张）',
        '',
    ]
    lines += [fmt_issue(it, f' | closer PR {prs}') for it, prs in strong] or ['（无）']
    lines += [
        '',
        '> A 类只认无限定词的 closing keyword；`Closes #N（部分/仅…）` 一律降级到 B。',
        '',
        f'### B. 已合 PR 待复核（关联 PR 已全部合入、无开放 PR，{len(weak)} 张）',
        '',
    ]
    lines += [fmt_issue(it, f' | 已合入 PR {prs}{note}') for it, prs, note in weak] or ['（无）']
    if bd_overlap:
        overlap_list = ', '.join(f'#{n}' for n in bd_overlap)
        lines += [
            '',
            (
                f'>另有 {len(bd_overlap)} 张同时命中 D（停滞高优）：{overlap_list}'
                '——已列于 D，此处不重复。'
            ),
        ]
    lines += ['', f'### C. 验收 checkbox 全勾（{len(checked_all)} 张）', '']
    lines += [fmt_issue(it) for it in checked_all] or ['（无）']
    lines += ['', f'### D. 停滞高优（Q1-RED 超 {STALE_HIGH_DAYS} 天无更新 → 提 P0 推进或降级，{len(stale_high)} 张）', '']
    lines += [fmt_issue(it) for it in stale_high] or ['（无）']
    lines += ['', f'### E. 僵尸卡（超 {STALE_DAYS} 天无更新且无关联 PR，{len(zombie)} 张）', '']
    lines += [fmt_issue(it) for it in zombie] or ['（无）']
    if track_only:
        lines += [
            '',
            f'> 另有 {len(track_only)} 张【自动告警】/ 固定跟踪卡按生命周期排除，不参与关档候选：'
            + ', '.join(f"#{it['number']}" for it in track_only),
        ]
    lines += [
        '',
        '---',
        '',
        '> 本评论由 CI 规则扫描生成（`scripts/issue_health_scan.py`，每周一 08:30 北京时间）。',
        (
            '> 处置约定：A 类候选请回 origin/dev 实证后决定关档或收窄转写；B 类仅表示「有过合入且无开放」，'
            '**不等于验收达成**（反例：#1460 P2 待拍板 / P3 未动 / 定时链 15 连红，#1121 与 #980 大 tracker 远未完成），'
            '须复核范围后决定；C 类请确认范围未被收窄；D 类请拍板提 P0 或降级；E 类建议直接关闭（reason: not planned）。'
        ),
        '',
    ]
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=DEFAULT_REPO)
    ap.add_argument('--dry-run', action='store_true', help='只打印报告，不写文件')
    ap.add_argument('--out', default='.workbuddy/tmp/issue_health_report.md')
    args = ap.parse_args()

    report = scan(args.repo)
    if args.dry_run:
        print(report)
        return 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding='utf-8')
    print(f'报告已写入 {out}（{len(report)} 字符）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
