#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FeedLog changelog 的 slug 规则（唯一来源）。

WHY（#1996 反向验证要求 3，结论是「原实现不幂等」）
-------------------------------------------------
#1996 要求实测「同一 Release 重复触发桥接，changelog 会不会插两条」。
答案：**会**。原实现对幂等的注释是「若同 slug 条目已存在则更新而非重复插入」，
但 slug 是 ``f"{slugify(title)}-{uuid4()[:8]}"``——**每次调用都生成新 slug**，
于是那条 ``SELECT id FROM "changelog" WHERE org_id = %s AND slug = %s``
永远查不到，幂等分支成了死代码：它只做到了「不报错」，没做到「不重复」。

修法：发布路径传一个**稳定键**（Release tag）。同一 tag 重复触发 ⇒ 同一 slug
⇒ 命中已有条目走 UPDATE。其它写入路径不传键，保留随机后缀（它们本来就没有
「同一实体重复写入」的语义）。

为什么单独成模块：``feedlog_bridge.py`` 顶层依赖 ``psycopg2`` / ``PyGithub``，
而 CI 的 ``scripts_test`` 只装 ``pyyaml + pytest``；把纯函数放在这里，判据才能
在**没有数据库驱动**的环境里被真实执行（不靠 ``importorskip`` 静默跳过）。
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

#: ``changelog.slug`` 的默认长度上限（与迁移脚本相同时的旧实现一致）。
DEFAULT_MAX_LEN = 80


def slugify(text: str, max_len: int = DEFAULT_MAX_LEN) -> str:
    """生成 FeedLog 所需的 slug（小写、连字符、截断；保留中文）。"""
    slug = re.sub(r'[^\w一-龥]+', '-', (text or '').strip().lower()).strip('-')
    return slug[:max_len] or 'item'


def changelog_slug(
    title: str,
    stable_key: Optional[str] = None,
    max_len: int = DEFAULT_MAX_LEN,
) -> str:
    """生成 changelog 条目的 slug。

    Args:
        title: 条目标题（Release 名或 Issue 标题）。
        stable_key: 稳定键。发布路径传 Release tag（``v0.1.0``），
            同一 tag 重复触发必须得到同一 slug，才能命中已有条目走 UPDATE；
            不传则保留旧的「随机后缀」行为（每次新 slug）。
        max_len: slug 长度上限。

    Returns:
        URL/DB 可用的 slug。稳定键存在时形如 ``v010-...``（``slugify`` 会吃掉点号）。
    """
    base = slugify(title, max_len=max_len)
    if stable_key:
        return slugify(f'{base}-{stable_key}', max_len=max_len)
    return f'{base}-{uuid.uuid4().hex[:8]}'
