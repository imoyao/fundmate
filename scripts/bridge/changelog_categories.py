#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FeedLog changelog 分类徽章的推导规则（纯函数，唯一来源）。

WHY（#1996 验收：categories 徽章 New/Improved/Fixed）
--------------------------------------------------
`changelog.categories` / `published_categories` 两列一直是硬编码的 `'[]'`，
于是更新日志页每条都**没有分类徽章**。要补它，得先回答三个问题：

1. **列存什么**：`jsonb`，`DEFAULT '[]'::jsonb NOT NULL`，**没有 enum / CHECK 约束**
   （FeedLog 仓 `server/db/migrations/0002_yellow_spectrum.sql`）⇒ 写任意字符串数组都不会
   让 INSERT 失败（这点很重要：桥接写的是生产库，写坏值会直接打断发版链路）。
2. **前端认哪些值**：`new` / `improved` / `fixed` 三个
   （FeedLog 仓 `app/components/changelog/ChangelogTimelineItem.vue` 的
   `CATEGORY_LABEL` / `CATEGORY_CLASS`；未知值会原样显示，不会崩）。
3. **从哪推导**：Conventional Commits 的 type（发版范围 = 两个 Release tag 之间的 commit）。
   只映射**用户可感知**的 type；`docs` / `test` / `chore` / `build` / `ci` 不进徽章——
   它们对用户没有可见影响，算进去就是噪音。

为什么单独成模块：``feedlog_bridge.py`` 顶层依赖 ``psycopg2`` / ``PyGithub``，
而 CI 的 ``scripts_test`` 只装 ``pyyaml + pytest``；把纯函数放这里，判据才能在
没有数据库驱动与网络的环境里被真实执行。

边界
----
- 只产出**取值集合**与**顺序**（new → improved → fixed），不写库、不联网；
- 推导不出就返回空列表（没有徽章），**不猜**。
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

CATEGORY_NEW = 'new'
CATEGORY_IMPROVED = 'improved'
CATEGORY_FIXED = 'fixed'

#: 允许写入 ``categories`` 的全部取值（与 FeedLog 前端的 CATEGORY_LABEL 一一对应）。
CATEGORY_VALUES: tuple[str, ...] = (CATEGORY_NEW, CATEGORY_IMPROVED, CATEGORY_FIXED)

#: Conventional Commits type → 分类。
#: 只收用户可感知的：feat=新功能、fix=修问题、perf/refactor/style=体验/实现改进。
TYPE_TO_CATEGORY: dict[str, str] = {
    'feat': CATEGORY_NEW,
    'fix': CATEGORY_FIXED,
    'perf': CATEGORY_IMPROVED,
    'refactor': CATEGORY_IMPROVED,
    'style': CATEGORY_IMPROVED,
}

#: Conventional Commits 标题：``type(scope)!: subject``。
_COMMIT_HEAD = re.compile(r'^([A-Za-z]+)(\([^)]*\))?(!)?:\s')


def parse_commit_type(message: str) -> Optional[str]:
    """取 commit 首行的 Conventional Commits type；取不到返回 None。

    - ``feat(pro): 权益校验`` → ``feat``
    - ``fix: 修复`` → ``fix``
    - ``Merge pull request #1 from x`` → None（合并提交不参与分类）
    - ``随手改一行`` → None（非规范格式不猜）
    """
    if not message:
        return None
    head = message.strip().splitlines()[0].strip() if message.strip() else ''
    if not head or head.startswith('Merge '):
        return None
    matched = _COMMIT_HEAD.match(head)
    if not matched:
        return None
    return matched.group(1).lower()


def categories_from_messages(messages: Iterable[str]) -> list[str]:
    """由 commit 标题列表推导分类徽章（去重，固定顺序 new → improved → fixed）。"""
    found: set[str] = set()
    for message in messages or []:
        commit_type = parse_commit_type(message)
        if not commit_type:
            continue
        category = TYPE_TO_CATEGORY.get(commit_type)
        if category:
            found.add(category)
    # 只输出白名单内的取值：即使映射表被改坏，也不会往库里写前端不认的值
    return [value for value in CATEGORY_VALUES if value in found]
