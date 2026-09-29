#!/usr/bin/env python3
"""Issue 体检周报扫描器（纯规则，只报告不自动关）。

背景（2026-09-26 全库排查教训）：
  - GitHub 只在 PR 目标为默认分支时解释 closing keyword，本仓默认分支是 main，
    功能 PR 一律 base=dev ⇒ 关卡长期靠人肉（close-linked-issues.yml 只管 9-24 之后的增量）。
  - 存量里存在「交付 PR 全部合入、卡还开着」（如 #1101 拖 24 天）与「closer 关键字误标」
    （PR #1349 标题带 #1133 实为对账功能）两类问题，需要每周机械扫出来给人工复核。

判定全部为机械信号（不需要 AI），产出四类清单：
  A. 建议关闭（强）    —— 存在正文带 closing keyword 且已合入的关联 PR，且无开放关联 PR
  B. 可关候选（弱）    —— 关联 PR ≥1 且全部 MERGED，无开放关联 PR（需实证复核，见 #1133 反例）
  C. 验收全勾          —— 正文 checkbox 均已勾选（可能范围已被收窄，需复核）
  D. 停滞高优          —— Q1-RED 超过 STALE_HIGH_DAYS 天无更新（推进 P0 或降级的信号）
  E. 僵尸卡            —— 超过 STALE_DAYS 天无更新且无任何关联 PR

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
CHECKBOX_DONE = re.compile(r'^\s*[-*]\s+\[[xX]\]', re.MULTILINE)
CHECKBOX_ANY = re.compile(r'^\s*[-*]\s+\[( |x|X)\]', re.MULTILINE)


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

    strong: list[tuple[dict, list[int]]] = []  # A: closer PR 已合入
    weak: list[tuple[dict, list[int]]] = []  # B: 关联 PR 全合入
    checked_all: list[dict] = []  # C: checkbox 全勾
    stale_high: list[dict] = []  # D: Q1-RED 停滞
    zombie: list[dict] = []  # E: 僵尸卡

    for it in issues:
        num = it['number']
        prs = cross_ref_prs(repo, num)
        merged, open_prs, closers = [], [], []
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
                refs = {int(x[1]) for x in CLOSER_KW.findall(d.get('body') or '')}
                if num in refs:
                    closers.append(p)
            elif d.get('state') == 'open':
                open_prs.append(p)
            # else: closed 未合入（废弃 PR）——不算阻塞也不算交付

        body = it.get('body') or ''
        any_cb = CHECKBOX_ANY.findall(body)
        done_cb = CHECKBOX_DONE.findall(body)
        has_q1 = any(l['name'] == 'Q1-RED' for l in it.get('labels', []))
        stale = days_since(it.get('updated_at'))

        if closers and not open_prs:
            strong.append((it, closers))
        elif merged and not open_prs:
            weak.append((it, merged))
        if any_cb and len(done_cb) == len(any_cb):
            checked_all.append(it)
        if has_q1 and stale > STALE_HIGH_DAYS:
            stale_high.append(it)
        if stale > STALE_DAYS and not prs:
            zombie.append(it)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    lines = [
        f'## Issue 体检周报 · {today}',
        '',
        f'扫描开放卡 **{len(issues)}** 张（机械规则，只报告不自动关；候选需人工/agent 回 origin/dev 实证复核后再关——'
        f'反例：PR #1349 标题误标 #1133 实为对账功能）。本轮规则命中：',
        '',
        f'### A. 建议关闭（强信号：closing keyword 的 PR 已合入，{len(strong)} 张）',
        '',
    ]
    lines += [fmt_issue(it, f' | closer PR {prs}') for it, prs in strong] or ['（无）']
    lines += ['', f'### B. 可关候选（关联 PR 已全部合入，{len(weak)} 张）', '']
    lines += [fmt_issue(it, f' | 已合入 PR {prs}') for it, prs in weak] or ['（无）']
    lines += ['', f'### C. 验收 checkbox 全勾（{len(checked_all)} 张）', '']
    lines += [fmt_issue(it) for it in checked_all] or ['（无）']
    lines += ['', f'### D. 停滞高优（Q1-RED 超 {STALE_HIGH_DAYS} 天无更新 → 提 P0 推进或降级，{len(stale_high)} 张）', '']
    lines += [fmt_issue(it) for it in stale_high] or ['（无）']
    lines += ['', f'### E. 僵尸卡（超 {STALE_DAYS} 天无更新且无关联 PR，{len(zombie)} 张）', '']
    lines += [fmt_issue(it) for it in zombie] or ['（无）']
    lines += [
        '',
        '---',
        '',
        '> 本评论由 CI 规则扫描生成（`scripts/issue_health_scan.py`，每周一 08:30 北京时间）。',
        '> 处置约定：A/B/C 类候选请回 origin/dev 实证后决定关档或收窄转写；D 类请拍板提 P0 或降级；E 类建议直接关闭（reason: not planned）。',
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
