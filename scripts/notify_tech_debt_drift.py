# -*- coding: utf-8 -*-
"""技术债台账漂移的「大声失败」出口（源 TD-021 / TD-025 状态回流事故，2026-11-21）。

## WHY：为什么光有 `--online` 判据还不够

`guard_tech_debt_register.py --online` 能判定「台账写着 open、issue 早已 CLOSED」这类漂移，
但它有两个结构性缺口：

1. **不进 CI**：`--online` 要 gh 凭据 + 网络，`ci.yml` 里跑的只有离线模式（无参数），
   于是「issue 关了、台账没改」只能靠人偶然撞见 —— 2026-11-19 关 #1502、11-20 关 #2803，
   台账两次都没跟上，两次都是人工核对才发现的；
2. **结论只进日志**：定时任务红了没人盯。这与镜像断链（`scripts/bridge/notify_mirror_divergence.py`）
   是同一种形态 —— 从外部看，「停摆」和「正常」长得一模一样。

本脚本只补这两点：把结论搬到一张**固定跟踪卡**上，并在恢复时把卡关掉。

## 边界（刻意不做的事）

- **不裁决、不改台账**：漂移怎么处置（重开 issue / 改 wontfix / 补代码）属 owner 口径，
  脚本只把事实摆到卡上，不替人做判断；
- **不修 issue 业务状态**：只建卡 / 评论 / 关自己建的卡；
- **幂等**：评论末尾写「报告内容 sha1」标记，同一份报告只发一次 —— 重复告警比不告警
  更消耗注意力（每周刷一条一样的红，第三周就没人看了）；
- **失败不静默**：gh 调用失败一律非零退出，让 workflow 变红；「提醒挂了」不能盖掉
  「台账漂了」这个真问题，但也不能假装成功。

## 用法

    # 本地演练（只打印将要执行的动作，不碰 GitHub）
    python scripts/notify_tech_debt_drift.py --report drift.txt --status drift --dry-run

    # 由 .github/workflows/tech-debt-drift.yml 每周调用（GH_TOKEN 由 workflow 注入）
    python scripts/notify_tech_debt_drift.py --report drift.txt --status drift --repo imoyao/fundmate

`--status ok` 时，若跟踪卡还开着就评论一句并关闭 —— 否则「红的卡永远红」，
下一个人会以为问题还在。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from typing import Callable

#: 跟踪卡标题即幂等键。含「固定跟踪卡」四个字是**故意的**：
#: `scripts/issue_health_scan.py` 的 `TRACK_ONLY_TITLE_PATTERNS` 认这个标记，
#: 生命周期由本脚本管，不由「PR 全合入」这类交付信号推断。
TITLE = '[技术债台账] 与事实漂移（固定跟踪卡）'
MARKER_RE = '<!-- tech-debt-drift: {} -->'
SKIP_REASON = '同一份报告已发过（内容未变）'


def marker(report: str) -> str:
    """报告内容的短摘要 —— 幂等键随**内容**走，不随运行次数走。"""
    digest = hashlib.sha1(report.strip().encode('utf-8')).hexdigest()
    return digest[:12]


def build_body(report: str, status: str) -> str:
    """卡面/评论正文。drift 给现场 + 处置入口；ok 给恢复说明。"""
    key = MARKER_RE.format(marker(report))
    if status == 'ok':
        return (
            '## 已恢复\n\n'
            '本周 `guard_tech_debt_register.py --online` 与事实一致：'
            '台账里状态为 `open` 的条目，对应 issue 都还开着。\n\n'
            f'```\n{report.strip()}\n```\n\n'
            f'{key}\n'
        )
    return (
        '## 台账与事实对不上\n\n'
        '`guard_tech_debt_register.py --online` 判定：台账里的状态和 issue 的真实状态不一致。\n'
        '这类漂移**不会**让 CI 变红（CI 只跑离线判据），所以只能由这张卡兜住。\n\n'
        '### 现场\n\n'
        f'```\n{report.strip()}\n```\n\n'
        '### 处置（owner 裁决，脚本不替你选）\n\n'
        '1. 若**代码/数据确实没做完**：台账保持 `open`，把 issue 重开（关单属提前关单）；\n'
        '2. 若**确实已做完**：台账改 `done` 并补 `evidence`（判据要能自动判定，不能只写一句结论）；\n'
        '3. 若**决定不做**：台账改 `wontfix` 并写 `decision`（决策编号或文档位置）。\n\n'
        '改完重跑 `python scripts/guard_tech_debt_register.py --online`，'
        '绿了下次巡检会自动关掉这张卡。\n\n'
        f'{key}\n'
    )


def find_tracker(list_json: str) -> int | None:
    """从 `gh issue list --json number,title` 的返回里挑出标题完全一致的卡。"""
    try:
        rows = json.loads(list_json or '[]')
    except json.JSONDecodeError as exc:
        raise SystemExit(f'gh 返回的 issue 列表不是合法 JSON：{exc}') from exc
    for row in rows:
        if isinstance(row, dict) and row.get('title') == TITLE:
            number = row.get('number')
            if isinstance(number, int):
                return number
    return None


def last_comment_body(comments_json: str) -> str:
    """取最后一条评论正文；没有评论返回空串。"""
    try:
        rows = json.loads(comments_json or '[]')
    except json.JSONDecodeError as exc:
        raise SystemExit(f'gh 返回的评论列表不是合法 JSON：{exc}') from exc
    if not isinstance(rows, list) or not rows:
        return ''
    tail = rows[-1]
    return tail.get('body', '') if isinstance(tail, dict) else ''


def _gh(args: list[str]) -> str:
    proc = subprocess.run(['gh', *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f'gh {" ".join(args)} 失败（rc={proc.returncode}）：{proc.stderr.strip()}')
    return proc.stdout


def execute(
    status: str,
    report: str,
    repo: str,
    dry_run: bool = False,
    run: Callable[[list[str]], str] = _gh,
    echo: Callable[[str], None] = print,
) -> int:
    """按 status 建卡 / 评论 / 关单。返回退出码（0=正常，2=输入不可信）。"""
    if status not in ('drift', 'ok'):
        echo(f'未知 status={status!r}（只接受 drift / ok）')
        return 2
    if not report.strip():
        echo('报告为空 —— 判据没跑出结论时不得当作「已恢复」')
        return 2

    listed = run(['issue', 'list', '--repo', repo, '--state', 'open', '--limit', '20', '--json', 'number,title'])
    number = find_tracker(listed)
    body = build_body(report, status)

    if status == 'ok':
        if number is None:
            echo('台账一致，且没有未关闭的跟踪卡 —— 无需动作')
            return 0
        if dry_run:
            echo(f'[dry-run] 将评论并关闭 #{number}')
            return 0
        run(['issue', 'comment', str(number), '--repo', repo, '--body', body])
        run(['issue', 'close', str(number), '--repo', repo, '--reason', 'completed'])
        echo(f'台账已恢复一致，跟踪卡 #{number} 已关闭')
        return 0

    if number is not None:
        last = last_comment_body(run(['api', f'repos/{repo}/issues/{number}/comments']))
        if MARKER_RE.format(marker(report)) in last:
            echo(f'{SKIP_REASON}（#{number}）')
            return 0
        if dry_run:
            echo(f'[dry-run] 将在 #{number} 追加一条漂移评论')
            return 0
        run(['issue', 'comment', str(number), '--repo', repo, '--body', body])
        echo(f'已在跟踪卡 #{number} 追加漂移报告')
        return 0

    if dry_run:
        echo('[dry-run] 将新建跟踪卡')
        return 0
    run(['issue', 'create', '--repo', repo, '--title', TITLE, '--body', body])
    echo('已新建技术债漂移跟踪卡')
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # 中文输出在 Windows GBK 控制台会炸（#2453 同族坑）
    ap = argparse.ArgumentParser(description='技术债台账漂移 → 固定跟踪卡（幂等）')
    ap.add_argument('--report', required=True, help='guard --online 的输出文件')
    ap.add_argument('--status', required=True, choices=('drift', 'ok'))
    ap.add_argument('--repo', default='imoyao/fundmate')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)
    try:
        report = open(args.report, encoding='utf-8').read()
    except OSError as exc:
        print(f'读不到报告文件 {args.report}：{exc}')
        return 2
    return execute(args.status, report, args.repo, args.dry_run)


if __name__ == '__main__':
    raise SystemExit(main())
