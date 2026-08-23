#!/usr/bin/env python3
"""
FeedLog ↔ GitHub Issues 双向桥接脚本

功能：
  一、FeedLog → GitHub（定时同步）
    读取 FeedLog PostgreSQL 中的新帖子 → 在 fundmate 仓库创建 GitHub Issue
  二、GitHub → FeedLog（事件驱动，真正双向）
    - Issue 新建（opened）     → 在 FeedLog 新建帖子并登记映射
    - Issue 标签/关闭/重开     → 回写 FeedLog 帖子状态
    - GitHub Release 发布      → 写入 FeedLog Changelog（系统动态）

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
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from github import Github, UnknownObjectException
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
    "done": "done",
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

# 脚本会自动确保以下 label 存在于目标仓库，避免 create_issue 因未知 label 报 422。
REQUIRED_LABELS = (
    "feedlog",
    "enhancement",
    "bug",
    "feedback",
    "planned",
    "in-progress",
    "done",
)

# FeedLog 系统哨兵作者（用于由 GitHub 事件生成的帖子/动态，无法登录但 user 行存在）
SYSTEM_AUTHOR_ID = "system"
# 单租户默认组织 id（dbb-feedback 迁移 0004 种子值）
DEFAULT_ORG_ID = "default-org"


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
    # PostgreSQL timestamptz 接受 'Z' 后缀，故保持 UTC 'Z' 格式
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str, max_len: int = 80) -> str:
    """生成 FeedLog 所需的 slug（小写、连字符、截断）。"""
    slug = re.sub(r"[^\w一-龥]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:max_len] or "item"


def ensure_label(repo, name: str) -> None:
    """幂等地确保仓库中存在某个 label（不存在则创建）。

    仓库缺失 label 时 PyGithub 的 create_issue 会抛 422，因此每次同步前先保证存在。
    """
    try:
        repo.get_label(name)
    except UnknownObjectException:
        try:
            repo.create_label(name, "0a7ea4")
            print(f"  🏷️ 已创建缺失 label: {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ 创建 label {name} 失败: {exc}")


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
    """查询自 since 以来新创建的帖子（含板名、作者名）。

    关键护栏：排除 system 作者（渠道 2「GitHub→FeedLog」建帖的哨兵作者）。
    这些帖子是 GitHub Issue 的镜像，不应再被渠道 1「FeedLog→GitHub」
    同步回 GitHub，否则会形成 FeedLog ↔ GitHub 死循环。
    这是比 bridge_state.json 更可靠的防循环判据——state 靠 git 提交在
    并发 job 间传递，时序竞争会丢映射，而作者字段在 DB 里不会丢。
    """
    cur = conn.cursor()
    sql = """
        SELECT
            p.id, p.title, p.content, p.status,
            p.created_at, p.updated_at,
            p.vote_count, p.comment_count,
            b.name AS board_name,
            u.name AS author_name, u.email AS author_email
        FROM "post" p
        JOIN "board" b ON p.board_id = b.id
        JOIN "user" u ON p.author_id = u.id
        WHERE p.author_id <> %s
    """
    params: list[Any] = [SYSTEM_AUTHOR_ID]
    if since:
        sql += " AND p.created_at > %s"
        params.append(since)
    sql += " ORDER BY p.created_at ASC"
    cur.execute(sql, params)
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
    # 幂等确保所需 label 都存在（仓库缺失 label 时 create_issue 会报 422）
    for lbl in REQUIRED_LABELS:
        ensure_label(repo, lbl)
    synced = state.setdefault("posts", {})

    for post in posts:
        post_id = post["id"]
        if post_id in synced:
            continue  # 已同步过

        # 决定标签（按 board 名称归一化匹配）
        board_label = BOARD_TO_LABEL.get(
            post.get("board_name", "").strip().lower(), "feedback"
        )
        # 同时反映 FeedLog 帖子当前状态（无状态标签时不追加）
        status_label = LABEL_MAP.get(post.get("status"))
        labels = ["feedlog", board_label]
        if status_label:
            labels.append(status_label)

        title = post["title"] or "（无标题反馈）"
        body = build_issue_body(post)

        if dry_run:
            print(f"  [DRY-RUN] 拟创建 Issue: {title} [labels={labels}]")
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
# GitHub → FeedLog：Issue 新建 / 状态 / Release → FeedLog 回写
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


def update_post_from_issue(conn, post_id: str, title: str, body: str) -> bool:
    """用 GitHub Issue 最新标题/正文覆盖 FeedLog 帖子（内容修复）。

    场景：GitHub 上手动修正了乱码标题/正文（edited 事件），或存量回灌
    （sync-github-issue --update），把修正后的内容写回 FeedLog，避免
    FeedLog 里长期残留乱码镜像。返回是否真正发生了更新。
    """
    cur = conn.cursor()
    new_title = (title or "")[:200]
    new_content = (body or "")[:10000]
    cur.execute(
        """UPDATE "post"
           SET title = %s, content = %s, updated_at = NOW()
           WHERE id = %s AND (title <> %s OR content <> %s)""",
        (new_title, new_content, post_id, new_title, new_content),
    )
    conn.commit()
    return cur.rowcount > 0


def get_org_id(conn) -> str:
    """获取 FeedLog 中第一个组织 ID（作为默认目标）"""
    cur = conn.cursor()
    cur.execute("""SELECT id FROM "organization" ORDER BY created_at ASC LIMIT 1""")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("FeedLog 中未找到任何组织，请先创建")
    return row["id"]


def get_board_id(conn, org_id: str, board_name: str) -> str | None:
    """按名称（忽略大小写）查找 board id；找不到返回 None。"""
    cur = conn.cursor()
    cur.execute(
        """SELECT id FROM "board" WHERE org_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1""",
        (org_id, board_name),
    )
    row = cur.fetchone()
    return row["id"] if row else None


def create_post_from_issue(
    conn, org_id: str, issue_number: int, title: str, body: str, labels: list[str]
) -> str | None:
    """将 GitHub Issue 新建为 FeedLog 帖子（双向补全：人工 issue → FeedLog）。

    幂等（双保险）：
      1. state 中该 issue_number 已映射 → 跳过；
      2. DB 中已存在 gh-issue-{issue_number} slug 的帖子 → 跳过。
    第 2 道是并发安全兜底：state 经 git 提交在并发 job 间传递会丢映射
    （2026-08-23 曾因 5 个 issue 并发触发，4 个映射丢失导致帖子被渠道 1
    重复同步回 GitHub 成 #1069–#1072），DB 层查重不受时序影响。

    护栏：带 feedlog 标签的 issue 是由「FeedLog → GitHub」通道（渠道 1）创建的，
    不应再反向建帖子，否则会形成 FeedLog ↔ GitHub 死循环。
    """
    import uuid as _uuid

    if "feedlog" in labels:
        print(f"  ⚠️ Issue #{issue_number} 带 feedlog 标签，疑似 FeedLog 源头，跳过建帖")
        return None

    state = load_state()
    for pid, info in state.get("posts", {}).items():
        if info.get("issue_number") == issue_number:
            print(f"  ⚠️ Issue #{issue_number} 已映射 FeedLog 帖子 {pid}，跳过")
            return None

    # board 映射：bug → Bug Report，enhancement → Feature Requests，其余 → Other
    board_name = "Other"
    if "bug" in labels:
        board_name = "Bug Report"
    elif "enhancement" in labels:
        board_name = "Feature Requests"
    board_id = get_board_id(conn, org_id, board_name)

    slug = f"gh-issue-{issue_number}"
    cur = conn.cursor()
    cur.execute(
        """SELECT id FROM "post" WHERE org_id = %s AND slug = %s""",
        (org_id, slug),
    )
    existing = cur.fetchone()
    if existing:
        print(
            f"  ⚠️ Issue #{issue_number} 已有帖子 {existing['id']}（slug={slug}），跳过"
        )
        # 并发丢映射兜底：把 DB 已存在的映射补回 state，供后续回写使用
        state.setdefault("posts", {})[existing["id"]] = {
            "issue_number": issue_number,
            "synced_at": now_iso(),
            "origin": "github",
        }
        save_state(state)
        return None

    post_id = str(_uuid.uuid4())
    content = (body or "")[:10000]
    cur.execute(
        """
        INSERT INTO "post"
            (id, org_id, board_id, author_id, slug, status, title, content,
             vote_count, comment_count, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 0, NOW(), NOW())
        RETURNING id
        """,
        (
            post_id,
            org_id,
            board_id,
            SYSTEM_AUTHOR_ID,
            slug,
            "open",
            (title or "")[:200],
            content,
        ),
    )
    cur.fetchone()
    conn.commit()

    # 持久化映射，供后续 closed/labeled 回写使用
    state.setdefault("posts", {})[post_id] = {
        "issue_number": issue_number,
        "synced_at": now_iso(),
        "origin": "github",
    }
    save_state(state)
    return post_id


def create_changelog_entry(
    conn, org_id: str, title: str, content: str, published_at: str | None = None
) -> str:
    """创建 FeedLog Changelog 条目。

    对齐真实 schema：author_id / slug / org_id 均为 NOT NULL，且 slug 按 org 唯一；
    title 列 varchar(70) 需截断；published 时同步 published_* 字段。

    幂等：若同 slug 条目已存在（同一 Release 重复触发），则更新而非重复插入。
    """
    import uuid as _uuid

    # title 列 varchar(70)，强制截断避免超长
    title = (title or "未命名更新")[:70]
    status = "published" if published_at else "draft"
    slug = f"{slugify(title)}-{str(_uuid.uuid4())[:8]}"

    cur = conn.cursor()
    # 幂等：先查是否已存在（同一 Release 重复触发时不报错）
    cur.execute(
        """SELECT id FROM "changelog" WHERE org_id = %s AND slug = %s""",
        (org_id, slug),
    )
    existing = cur.fetchone()
    if existing:
        entry_id = existing["id"]
        cur.execute(
            """
            UPDATE "changelog"
            SET title = %s, content = %s, status = %s,
                published_title = %s, published_content = %s,
                published_categories = %s, published_at = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (
                title,
                content,
                status,
                title if status == "published" else None,
                content if status == "published" else None,
                "[]",
                published_at,
                entry_id,
            ),
        )
        conn.commit()
        return entry_id

    entry_id = str(_uuid.uuid4())
    cur.execute(
        """
        INSERT INTO "changelog"
            (id, org_id, author_id, slug, status, title, content,
             categories, published_title, published_content, published_categories,
             published_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        RETURNING id
        """,
        (
            entry_id,
            org_id,
            SYSTEM_AUTHOR_ID,
            slug,
            status,
            title,
            content,
            "[]",
            title if status == "published" else None,
            content if status == "published" else None,
            "[]",
            published_at,
        ),
    )
    conn.commit()
    return cur.fetchone()["id"]


def sync_issue_to_feedlog(
    conn,
    state: dict[str, Any],
    issue_number: int,
    new_labels: list[str],
    action: str = "",
) -> None:
    """根据 Issue 标签/状态变更回写 FeedLog 帖子状态。

    规则：
      - 含 done        → FeedLog 状态 = done（completed）
      - 含 in-progress → FeedLog 状态 = in_progress
      - 含 planned     → FeedLog 状态 = planned
      - issue 关闭      → FeedLog 状态 = done（completed）
      - issue 重新打开且无状态标签 → FeedLog 状态 = open
    """
    posts = state.get("posts", {})
    # 反向查找：issue_number → post_id
    post_id = None
    for pid, info in posts.items():
        if info.get("issue_number") == issue_number:
            post_id = pid
            break

    if not post_id:
        # state 映射丢失兜底：按 slug gh-issue-{number} 查 DB
        org_id = get_org_id(conn)
        cur = conn.cursor()
        cur.execute(
            """SELECT id FROM "post" WHERE org_id = %s AND slug = %s""",
            (org_id, f"gh-issue-{issue_number}"),
        )
        row = cur.fetchone()
        if row:
            post_id = row["id"]
            posts[post_id] = {
                "issue_number": issue_number,
                "synced_at": now_iso(),
                "origin": "github",
            }
            save_state(state)

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
        # issue 重新打开且无任何状态标签 → 回到 open
        if action == "reopened":
            new_status = "open"
        else:
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

    # github → feedlog（Issue 新建）
    opened_cmd = sub.add_parser(
        "issue-opened-to-feedlog", help="GitHub Issue 新建 → FeedLog 帖子"
    )
    opened_cmd.add_argument("--issue-number", type=int, required=True)
    opened_cmd.add_argument("--title", default="")
    opened_cmd.add_argument("--body", default="")
    opened_cmd.add_argument("--labels", nargs="*", default=[])

    # github → feedlog（Issue 标签 / 关闭 / 重开 → 状态）
    issue_cmd = sub.add_parser(
        "issue-to-feedlog", help="GitHub Issue 标签/状态 → FeedLog 状态"
    )
    issue_cmd.add_argument("--issue-number", type=int, required=True)
    issue_cmd.add_argument("--labels", nargs="*", default=[], help="Issue 当前所有标签")
    issue_cmd.add_argument(
        "--action", default="", help="GitHub 事件 action（如 closed/reopened）"
    )

    # github → feedlog（Issue 编辑 → 覆盖 FeedLog 帖子内容）
    edited_cmd = sub.add_parser(
        "issue-edited-to-feedlog",
        help="GitHub Issue 标题/正文编辑 → 覆盖 FeedLog 帖子内容（修复乱码镜像）",
    )
    edited_cmd.add_argument("--issue-number", type=int, required=True)
    edited_cmd.add_argument("--title", default="")
    edited_cmd.add_argument("--body", default="")

    # github release → feedlog changelog
    rel_cmd = sub.add_parser(
        "release-to-changelog", help="GitHub Release → FeedLog Changelog"
    )
    rel_cmd.add_argument("--tag", required=True)
    rel_cmd.add_argument("--name", default="")
    rel_cmd.add_argument("--body", default="")
    rel_cmd.add_argument("--published-at", default=None)

    # 历史补同步：GitHub Issue → FeedLog（事件驱动只认实时，这里支持回灌）
    backfill_cmd = sub.add_parser(
        "sync-github-issue", help="将 GitHub 历史 Issue 同步到 FeedLog（回灌）"
    )
    backfill_cmd.add_argument(
        "--issue-number",
        type=int,
        default=None,
        help="指定 Issue 编号；省略则同步仓库全部 Issue",
    )
    backfill_cmd.add_argument(
        "--include-releases",
        action="store_true",
        help="同时把 Release 同步为 FeedLog Changelog",
    )
    backfill_cmd.add_argument(
        "--update",
        action="store_true",
        help="对已映射 FeedLog 帖子的 Issue，用 GitHub 最新标题/正文覆盖（修复乱码镜像）",
    )

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

    elif args.command == "issue-opened-to-feedlog":
        conn = get_db()
        try:
            org_id = get_org_id(conn)
            post_id = create_post_from_issue(
                conn, org_id, args.issue_number, args.title, args.body, args.labels
            )
            if post_id:
                print(
                    f"  ✅ FeedLog 帖子已创建: {post_id} (← Issue #{args.issue_number})"
                )
        finally:
            conn.close()

    elif args.command == "issue-to-feedlog":
        conn = get_db()
        try:
            sync_issue_to_feedlog(
                conn, state, args.issue_number, args.labels, args.action
            )
        finally:
            conn.close()

    elif args.command == "issue-edited-to-feedlog":
        conn = get_db()
        try:
            # 从 state 反查该 issue 对应的 FeedLog 帖子
            post_id = None
            for pid, info in state.get("posts", {}).items():
                if info.get("issue_number") == args.issue_number:
                    post_id = pid
                    break
            if not post_id:
                # state 映射丢失兜底：按 slug gh-issue-{number} 查 DB
                org_id = get_org_id(conn)
                cur = conn.cursor()
                cur.execute(
                    """SELECT id FROM "post" WHERE org_id = %s AND slug = %s""",
                    (org_id, f"gh-issue-{args.issue_number}"),
                )
                row = cur.fetchone()
                if row:
                    post_id = row["id"]
            if not post_id:
                print(f"  ⚠️ Issue #{args.issue_number} 无对应 FeedLog 帖子映射，跳过")
                sys.exit(0)
            if update_post_from_issue(conn, post_id, args.title, args.body):
                print(
                    f"  ✅ FeedLog 帖子 {post_id} 内容已更新 (← Issue #{args.issue_number} 编辑)"
                )
            else:
                print(f"  ℹ️ Issue #{args.issue_number} 内容无变化，跳过")
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

    elif args.command == "sync-github-issue":
        conn = get_db()
        try:
            gh = get_gh()
            repo = gh.get_repo(os.environ["GITHUB_REPO"])
            org_id = get_org_id(conn)

            if args.issue_number:
                targets = [repo.get_issue(args.issue_number)]
                print(f"📥 拉取 Issue #{args.issue_number} ...")
            else:
                print("📥 拉取仓库全部 Issue（含历史）…")
                targets = list(repo.get_issues(state="all"))

            created = 0
            updated = 0
            for issue in targets:
                # PyGithub 会同时返回 PR（kind == 'pull_request'），跳过以免重复
                if getattr(issue, "pull_request", None) is not None:
                    continue
                labels = [label.name for label in issue.labels]

                # 先查是否已映射（state 或 DB slug 双保险）
                existing_pid = None
                for pid, info in state.get("posts", {}).items():
                    if info.get("issue_number") == issue.number:
                        existing_pid = pid
                        break
                if not existing_pid:
                    cur = conn.cursor()
                    cur.execute(
                        """SELECT id FROM "post"
                           WHERE org_id = %s AND slug = %s""",
                        (org_id, f"gh-issue-{issue.number}"),
                    )
                    row = cur.fetchone()
                    if row:
                        existing_pid = row["id"]

                if existing_pid and args.update:
                    # 回灌覆盖：用 GitHub 最新内容修复 FeedLog 镜像（如乱码）
                    if update_post_from_issue(
                        conn, existing_pid, issue.title, issue.body or ""
                    ):
                        updated += 1
                        print(
                            f"  ✅ 已回灌更新帖子 {existing_pid} ← Issue #{issue.number}"
                        )
                    else:
                        print(f"  ℹ️ Issue #{issue.number} 内容与帖子一致，无更新")
                    continue

                post_id = create_post_from_issue(
                    conn, org_id, issue.number, issue.title, issue.body or "", labels
                )
                if post_id:
                    created += 1
                    print(f"  ✅ 已创建帖子 {post_id} ← Issue #{issue.number}")
            print(f"🎉 同步完成，新建 {created} 条，回灌更新 {updated} 条 FeedLog 帖子")

            if args.include_releases:
                print("📦 同步 Release → Changelog…")
                for rel in repo.get_releases():
                    sync_release_to_changelog(
                        conn,
                        repo,
                        rel.tag_name,
                        rel.title or rel.tag_name,
                        rel.body or "",
                        rel.published_at.isoformat() if rel.published_at else None,
                    )
        finally:
            conn.close()


if __name__ == "__main__":
    main()
