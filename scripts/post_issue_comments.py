#!/usr/bin/env python3
"""批量给 GitHub issue 发依赖排序评论（远程 ClawBot 通道友好）。

用法：
    python scripts/post_issue_comments.py [--dry-run] [--only 990,995]

- 读取 scripts/issue_comments/ 下 {issue号}.md 作为评论正文。
- 通过 `gh issue comment {号} --body-file` 发送，规避 shell 转义问题。
- 每条评论首行已含 [AI 创建] · AI-Created-By: ClawBot 身份标注（AGENTS.md 约定）。
- --dry-run 只打印将要发送的 issue 与字数，不实际发送。
- 发送失败的 issue 会列出，不中断其余 issue。

注意：脚本只发评论（依赖标注），真正的依赖边以 docs/spec/realtime-data-sources.md §3 为权威源。
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMENTS_DIR = REPO_ROOT / "scripts" / "issue_comments"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印，不发送")
    ap.add_argument("--only", help="只发指定 issue 号，逗号分隔，如 990,995")
    args = ap.parse_args()

    only = {s.strip() for s in (args.only or "").split(",") if s.strip()}

    md_files = sorted(COMMENTS_DIR.glob("*.md"))
    if not md_files:
        print(f"未找到评论文件：{COMMENTS_DIR}", file=sys.stderr)
        return 1

    failed = []
    sent = 0
    for f in md_files:
        issue = f.stem
        if only and issue not in only:
            continue
        body = f.read_text(encoding="utf-8").strip()
        if not body:
            print(f"[跳过] #{issue} 正文为空")
            continue
        if args.dry_run:
            print(f"[dry-run] 将向 #{issue} 发送 {len(body)} 字评论")
            continue
        print(f"→ 发送 #{issue} ...", end=" ", flush=True)
        try:
            subprocess.run(
                ["gh", "issue", "comment", issue, "--body-file", str(f)],
                cwd=str(REPO_ROOT),
                check=True,
                capture_output=True,
                text=True,
            )
            print("OK")
            sent += 1
        except subprocess.CalledProcessError as e:
            print("FAIL")
            msg = (e.stderr or e.stdout or str(e)).strip()
            print(f"   错误：{msg[:300]}", file=sys.stderr)
            failed.append(issue)

    if args.dry_run:
        print("dry-run 完成，未实际发送。")
        return 0
    print(f"\n完成：已发送 {sent} 条，失败 {len(failed)} 条。")
    if failed:
        print("失败列表：" + ", ".join(f"#{i}" for i in failed))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
