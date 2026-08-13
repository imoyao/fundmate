#!/usr/bin/env python3
"""
FeedLog ↔ GitHub Issues 双向桥接脚本

功能：
  一、FeedLog → GitHub（定时同步）
    读取 FeedLog PostgreSQL 中的新帖子 → 在 fundmate 仓库创建 GitHub Issue
  二、GitHub → FeedLog（事件驱动）
    Issue 状态变更 / Release 发布 → 回写 FeedLog PostgreSQL

依赖：
  pip install psycopg2-binary PyGithub

环境变量（必需）：
  FEEDLOG_DATABASE_URL  — PostgreSQL 直连串（不是 Hyperdrive ID）
  GITHUB_TOKEN           — GitHub Personal Access Token（含 repo scope）
  GITHUB_REPO            — 目标仓库，如 imoyao/fundmate

状态文件：
  bridge_state.json — 记录已同步帖子映射、最后同步时间
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from github import Github
from psycopg2.extras import RealDictCursor

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "bridge_state.json"

# 帖子状态 → GitHub Issue Label 映射
LABEL_MAP = {
    "open": "feedback",
    "planned": "planned",
    "in_progress": "in-progress",
    "completed": "done",
}

# Issue 标签反向映射
LABEL_REVERSE_MAP = {v: k for k, v in LABEL_MAP.items()}

# FeedLog Board → Issue label（按 board 名称映射；board 表无 slug 列，标识只有 name）
# 名称大小写/空格敏感，故查找时统一小写归一化。
BOARD_TO_LABEL = {
    "feature requests": "enhancement",
    "bug report": "bug",
    "improvements": "enhancement",
    "other": "feedback",
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def load_state() -> dict[str, Any]:
    """加载同步状态文件"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_sync_at": None, "posts": {}}


def save_state(state: dict[str, Any]) -> None:
    """保存同步状态"""
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_db() -> psycopg2.extensions.connection:
    """连接 FeedLog PostgreSQL"""
    url = os.environ["FEEDLOG_DATABASE_URL"]
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def get_gh() -> Github:
    return Github(os.environ["GITHUB_TOKEN"])


# ---------------------------------------------------------------------------
# FeedLog → GitHub：帖子 → Issue
# ---------------------------------------------------------------------------


def fetch_new_posts(conn, since: str | None) -> list[dict]:
    """查询自 since 以来新创建的帖子（含板名、作者名）"""
    cur = conn.cursor()
    if since:
        cur.execute(
            """
            SELECT
                p.id, p.title, p.content, p.status,
                p.created_at, p.updated_at,
                p.vote_count, p.comment_count,
                b.name AS board_name,
                u.name AS author_name, u.email AS author_email
            FROM "post" p
            JOIN "board" b ON p.board_id = b.id
            JOIN "user" u ON p.author_id = u.id
            WHERE p.created_at > %s
            ORDER BY p.created_at ASC
            """,
            (since,),
        )
    else:
        cur.execute(
            """
            SELECT
                p.id, p.title, p.content, p.status,
                p.created_at, p.updated_at,
                p.vote_count, p.comment_count,
                b.name AS board_name,
                u.name AS author_name, u.email AS author_email
            FROM "post" p
            JOIN "board" b ON p.board_id = b.id
            JOIN "user" u ON p.author_id = u.id
            ORDER BY p.created_at ASC
            """
        )
    return [dict(row) for row in cur.fetchall()]


def build_issue_body(post: dict) -> str:
    """用 FeedLog 帖子内容拼 GitHub Issue body（Markdown）"""
    parts = [
        "**来自 FeedLog 反馈中心**",
        "",
        "---",
        "",
        f"### {post['title']}",
        "",
        post.get("content") or "_（无正文）_",
        "",
        "---",
        "",
        "| 属性 | 值 |",
        "|------|-----|",
        f"| 看板 | {post.get('board_name', '?')} |",
        f"| 作者 | {post.get('author_name') or post.get('author_email', '匿名')} |",
        f"| 赞同 | {post.get('vote_count', 0)} |",
        f"| 评论 | {post.get('comment_count', 0)} |",
        f"| FeedLog ID | `{post['id']}` |",
    ]
    return "\n".join(parts)


def sync_posts_to_github(
    conn, gh_repo, state: dict[str, Any], dry_run: bool = False
) -> dict[str, Any]:
    """将新帖子同步为 GitHub Issues"""
    last_sync = state.get("last_sync_at")
    posts = fetch_new_posts(conn, last_sync)

    if not posts:
        print(f"📭 无新帖子（上次同步: {last_sync or '初次'}）")
        return state

    print(f"📥 发现 {len(posts)} 条新帖子")

    gh = get_gh()
    repo = gh.get_repo(os.environ["GITHUB_REPO"])
    synced = state.setdefault("posts", {})

    for post in posts:
        post_id = post["id"]
        if post_id in synced:
            continue  # 已同步过

        # 决定标签（按 board 名称归一化匹配）
        board_label = BOARD_TO_LABEL.get(
            post.get("board_name", "").strip().lower(), "feedback"
        )
        labels = ["feedlog", board_label]

        title = post["title"] or "（无标题反馈）"
        body = build_issue_body(post)

        if dry_run:
            print(f"  [DRY-RUN] 拟创建 Issue: {title} [label={board_label}]")
            synced[post_id] = {
                "issue_number": 0,
                "synced_at": now_iso(),
                "dry_run": True,
            }
        else:
            issue = repo.create_issue(title=title, body=body, labels=labels)
            synced[post_id] = {
                "issue_number": issue.number,
                "synced_at": now_iso(),
            }
            print(f"  ✅ #{issue.number} {title}")

    # 更新最后同步时间
    if posts:
        latest_ts = max(p["created_at"] for p in posts)
        state["last_sync_at"] = (
            latest_ts.isoformat() if hasattr(latest_ts, "isoformat") else str(latest_ts)
        )

    save_state(state)
    return state


# ---------------------------------------------------------------------------
# GitHub → FeedLog：Issue 状态 / Release → FeedLog 回写
# ---------------------------------------------------------------------------


def update_post_status(conn, post_id: str, new_status: str) -> bool:
    """更新 FeedLog 帖子状态"""
    cur = conn.cursor()
    cur.execute(
        """UPDATE "post" SET status = %s, updated_at = NOW() WHERE id = %s""",
        (new_status, post_id),
    )
    conn.commit()
    return cur.rowcount > 0


def create_changelog_entry(
    conn, org_id: str, title: str, content: str, published_at: str | None = None
) -> str:
    """创建 FeedLog Changelog 条目"""
    import uuid as _uuid

    entry_id = str(_uuid.uuid4())
    status = "published" if published_at else "draft"
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO "changelog" (id, org_id, title, content, status, published_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
        RETURNING id
        """,
        (entry_id, org_id, title, content, status, published_at),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_org_id(conn) -> str:
    """获取 FeedLog 中第一个组织 ID（作为默认目标）"""
    cur = conn.cursor()
    cur.execute("""SELECT id FROM "organization" ORDER BY created_at ASC LIMIT 1""")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("FeedLog 中未找到任何组织，请先创建")
    return row["id"]


def sync_issue_to_feedlog(
    conn, state: dict[str, Any], issue_number: int, new_labels: list[str]
) -> None:
    """根据 Issue 标签变更回写 FeedLog 帖子状态

    规则：
      - 含 done → FeedLog 状态 = completed
      - 含 in-progress → FeedLog 状态 = in_progress
      - 含 planned → FeedLog 状态 = planned
      - issue 关闭 → FeedLog 状态 = completed
    """
    posts = state.get("posts", {})
    # 反向查找：issue_number → post_id
    post_id = None
    for pid, info in posts.items():
        if info.get("issue_number") == issue_number:
            post_id = pid
            break

    if not post_id:
        print(f"  ⚠️ Issue #{issue_number} 无对应 FeedLog 帖子，跳过")
        return

    # 按优先级匹配状态
    new_status = None
    for label in ("done", "in-progress", "planned"):
        if label in new_labels:
            new_status = LABEL_REVERSE_MAP.get(label)
            break

    if not new_status:
        return  # 没有匹配的标签，不更新

    if update_post_status(conn, post_id, new_status):
        print(f"  ✅ FeedLog 帖子 {post_id} 状态 → {new_status}")
    else:
        print(f"  ❌ 更新 FeedLog 帖子 {post_id} 失败")


def sync_release_to_changelog(
    conn,
    repo,
    release_tag: str,
    release_name: str,
    release_body: str,
    published_at: str,
) -> None:
    """将 GitHub Release 创建为 FeedLog Changelog 条目"""
    org_id = get_org_id(conn)
    title = release_name or release_tag
    entry_id = create_changelog_entry(conn, org_id, title, release_body, published_at)
    print(f"  ✅ FeedLog Changelog 已创建: {entry_id} → {title}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(description="FeedLog ↔ GitHub 双向桥接")
    sub = parser.add_subparsers(dest="command")

    # feedlog → github
    sync_cmd = sub.add_parser("feedlog-to-github", help="FeedLog 帖子 → GitHub Issues")
    sync_cmd.add_argument("--dry-run", action="store_true", help="仅预览，不创建 Issue")

    # github → feedlog（Issue label 变更）
    issue_cmd = sub.add_parser(
        "issue-to-feedlog", help="GitHub Issue 标签 → FeedLog 状态"
    )
    issue_cmd.add_argument("--issue-number", type=int, required=True)
    issue_cmd.add_argument("--labels", nargs="*", default=[], help="Issue 当前所有标签")

    # github release → feedlog changelog
    rel_cmd = sub.add_parser(
        "release-to-changelog", help="GitHub Release → FeedLog Changelog"
    )
    rel_cmd.add_argument("--tag", required=True)
    rel_cmd.add_argument("--name", default="")
    rel_cmd.add_argument("--body", default="")
    rel_cmd.add_argument("--published-at", default=None)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 检查必需的环境变量
    required_env = ["FEEDLOG_DATABASE_URL", "GITHUB_TOKEN", "GITHUB_REPO"]
    missing = [e for e in required_env if not os.environ.get(e)]
    if missing:
        print(f"❌ 缺少环境变量: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    state = load_state()

    if args.command == "feedlog-to-github":
        conn = get_db()
        try:
            sync_posts_to_github(conn, None, state, dry_run=args.dry_run)
        finally:
            conn.close()

    elif args.command == "issue-to-feedlog":
        conn = get_db()
        try:
            sync_issue_to_feedlog(conn, state, args.issue_number, args.labels)
        finally:
            conn.close()

    elif args.command == "release-to-changelog":
        conn = get_db()
        try:
            sync_release_to_changelog(
                conn, None, args.tag, args.name, args.body, args.published_at
            )
        finally:
            conn.close()


if __name__ == "__main__":
    main()
