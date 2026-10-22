#!/usr/bin/env python3
"""把每日调度的运行摘要渲染成告警卡正文片段（#2457）。

## WHY：告警卡要指名道姓，不能只说「运行失败」

每日调度跑 20 个 job（`stock_list` / `fund_nav` / `asset_snapshot` …），
`app/tools/scheduler.py` 现在会把逐 job 结果写进 `backend/data/last_run_summary.json`，
并在**有 job 失败时以退出码 2 结束**（让 workflow 的失败告警真的触发）。

但一张只写「每日调度失败」的卡，排查的人还是得自己去翻 20 个 job 的日志。
本脚本把摘要渲染成**可直接贴进卡片正文**的片段：哪几个 job 坏了、各自什么状态。

## 失败语义（#171 的「空 ≠ 没拿到」）

摘要文件**不存在** ≠ 「没有失败 job」：
- 文件在、没有失败 job → 「✅ 本次调度无失败 job」
- 文件不在 → 「⚠️ 未找到运行摘要 …… **无法确认 job 级结果**」

两者必须能被区分，否则「拿不到输入」会被读成「一切正常」。

## 用法

    python scripts/daily_run_alert.py                          # 打印片段到 stdout
    python scripts/daily_run_alert.py --github-output "$GITHUB_OUTPUT"   # 写成 key=value 输出

退出码：0（无论有没有失败，**都要出片段**——卡正文要如实说明「能不能确认」）；
`--strict` 时，摘要缺失退 2（给 CI 严格场景用）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: 默认摘要位置：仓库根/backend/data/last_run_summary.json（scripts/ 的上一级是仓库根）。
DEFAULT_SUMMARY_PATH = Path(__file__).resolve().parent.parent / 'backend' / 'data' / 'last_run_summary.json'


def load_summary(path: Path) -> dict[str, Any] | None:
    """读摘要；**读不到就返回 None**（不返回空 dict——那是「一切正常」的谎言）。"""
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def render_detail(summary: dict[str, Any] | None, summary_path: Path | None = None) -> str:
    """把摘要渲染成告警卡正文片段。"""
    if summary is None:
        where = f'（{summary_path}）' if summary_path else ''
        return (
            f'⚠️ **未找到每日调度运行摘要**{where}——**无法确认 job 级结果**。'
            '调度可能崩在建连或初始化阶段（早于写摘要那一步），请直接看本次 run 日志。'
        )

    failed = list(summary.get('failed') or [])
    jobs = summary.get('jobs') or {}
    total = summary.get('total') or len(jobs)

    if not failed:
        return f'✅ 本次调度**无失败 job**（共 {total} 个 job 参与）。'

    lines = [f'❌ **失败 job：{len(failed)}/{total}** —— ' + '、'.join(f'`{name}`' for name in failed)]
    detail_rows: list[str] = []
    for name in failed:
        status = (jobs.get(name) or 'unknown')
        detail_rows.append(f'- `{name}`：{status}')
    if detail_rows:
        lines.append('')
        lines.append('逐项状态：')
        lines.extend(detail_rows)
    elapsed = summary.get('elapsed_seconds')
    if elapsed is not None:
        lines.append('')
        lines.append(f'耗时 {elapsed}s；起始 {summary.get("started_at", "未知")}。')
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description='渲染每日调度 job 级失败明细（#2457）')
    parser.add_argument('--summary', default=str(DEFAULT_SUMMARY_PATH), help='运行摘要 JSON 路径')
    parser.add_argument('--github-output', default=None, help='把片段写入该文件的 key=value 输出')
    parser.add_argument('--strict', action='store_true', help='摘要缺失时退出码 2（默认只提示）')
    args = parser.parse_args(argv)

    path = Path(args.summary)
    summary = load_summary(path)
    detail = render_detail(summary, path)

    if args.github_output:
        # GitHub 输出文件：多行值要用 heredoc 语法，不能直接写 key=value
        with open(args.github_output, 'a', encoding='utf-8') as fh:
            fh.write('job_failure_detail<<EOF\n')
            fh.write(detail)
            fh.write('\nEOF\n')
    print(detail)

    if args.strict and summary is None:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
