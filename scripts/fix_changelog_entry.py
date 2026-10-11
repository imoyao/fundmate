#!/usr/bin/env python3
"""一次性修正：更新 FeedLog 已发布 changelog 条目的正文。

## 为什么需要这个脚本（2026-10-09）

v0.1.0 的 Release notes 里，「导入不用手敲」一段写了「盈米」这个导入源，
**该来源并不存在**——是撰写 Release notes 时凭印象编的，发布前未核对实现清单。
发布后经`backend/app/services/importer/parsers/` 逐个核实，真实支持的是：
支付宝（AlipayFundParser）、支付宝 PDF（AlipayPDFParser）、天天基金（TiantianFundParser）、
同花顺股票交割单（THSStockParser）、e 账户（EAccountHoldingParser）、标准模板（StandardTemplateParser）。

这是**对外公开内容的虚假描述**，必须修正（AGENTS.md / D6 的「不虚构能力」原则）。

## 为什么不复用 feedlog_bridge.py

`create_changelog_entry()`（bridge 脚本内）的幂等判据是「同 slug 已存在则更新」，
但它每次用 `uuid4()[:8]` 生成 slug ⇒ **判据在原理上永不命中**。
直接复用会导致**再插一条重复条目**而非更新。

本脚本改用**按 slug 精确定位**（slug 由 FeedLog 生成后即固定），可安全重复执行。

## 用法

```bash
# 预演（只读，不写库）—— 默认行为
export FEEDLOG_DATABASE_URL='postgresql://...'
python scripts/fix_changelog_entry.py --slug '多多贝-0-1-0-家庭投资理财的账本精灵-375e8bda' --body-file docs/working-notes/release-notes-v0.1.0-body.md

# 确认无误后实际写入
python scripts/fix_changelog_entry.py --slug '...' --body-file ... --apply

# 不给 slug 时按标题模糊匹配（列出候选后需人工确认）
python scripts/fix_changelog_entry.py --title-contains '多多贝 0.1.0' --body-file ... --apply
```

**安全设计**：
- 默认 dry-run，不写库
- 只改`published_content`（公开页实际读取的字段），**不动** `content`（editing 版本）
  ⇒ 与 FeedLog 的 Publish 语义一致，也不会把未发布的草稿误推上线
- 只匹配 `status = 'published'` 的条目
- 匹配到多条时**拒绝写入**并列出候选，不猜
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor


def get_conn():
    url = os.environ.get("FEEDLOG_DATABASE_URL")
    if not url:
        sys.exit("缺少环境变量 FEEDLOG_DATABASE_URL（PostgreSQL 直连串，不是 Hyperdrive ID）")
    return psycopg2.connect(url)


def find_entries(conn, slug: str | None, title_contains: str | None) -> list[dict]:
    """按 slug 精确匹配，或按标题模糊匹配。返回 published 条目。"""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if slug:
            cur.execute(
                'SELECT id, slug, title, status FROM "changelog" WHERE slug = %s',
                (slug,),
            )
        else:
            cur.execute(
                'SELECT id, slug, title, status FROM "changelog" WHERE title ILIKE %s',
                (f"%{title_contains}%",),
            )
        return cur.fetchall()


def main() -> None:
    p = argparse.ArgumentParser(description="一次性修正 FeedLog 已发布 changelog 条目正文")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="条目 slug（精确匹配，优先用这个）")
    g.add_argument("--title-contains", help="标题包含（模糊匹配，可能命中多条）")
    p.add_argument("--body-file", required=True, help="新正文文件路径")
    p.add_argument("--apply", action="store_true", help="实际写入（缺省为dry-run）")
    args = p.parse_args()

    with open(args.body_file, encoding="utf-8") as f:
        body = f.read().strip()
    if not body:
        sys.exit("正文文件为空")

    conn = get_conn()
    try:
        rows = find_entries(conn, args.slug, args.title_contains)
        if not rows:
            print("未匹配到任何条目。请检查 slug / 标题。")
            print("提示：可先跑桥接脚本的 release-to-changelog 日志，或查公开 API "
                  "https://feedback.duoduobei.com/api/changelogs 拿 slug。")
            sys.exit(1)

        print(f"匹配到 {len(rows)} 条：")
        for r in rows:
            print(f"  id={r['id']}  slug={r['slug']}")
            print(f"    title={r['title']!r}  status={r['status']}")

        if len(rows) > 1:
            print("\n命中多条，拒绝写入（不猜）。请改用 --slug 精确指定。")
            sys.exit(1)

        row = rows[0]
        if row["status"] != "published":
            print(f"\n条目状态为 {row['status']!r} 而非 published，拒绝写入。")
            print("本脚本只修正已发布条目；草稿请在 FeedLog 后台编辑并 Publish。")
            sys.exit(1)

        if not args.apply:
            print(f"\n[dry-run] 将把 published_content 更新为：\n---\n{body}\n---")
            print("加 --apply 实际写入。")
            return

        with conn.cursor() as cur:
            cur.execute(
                'UPDATE "changelog" SET published_content = %s, updated_at = NOW() WHERE id = %s',
                (body, row["id"]),
            )
        conn.commit()
        print(f"\n✅ 已更新 published_content（id={row['id']}）。")
        print("   editing 版本 content 未动 —— 与 FeedLog Publish 语义一致。")
        print("   验证：curl https://feedback.duoduobei.com/api/changelogs")
    finally:
        conn.close()


if __name__ == "__main__":
    main()