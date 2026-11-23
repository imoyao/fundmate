# -*- coding: utf-8 -*-
"""热集口径（持仓 ∪ 自选 ∪ 流水）的取数入口（#3091，从 `cold_set_guard` 抽出）。

## 为什么要单独一个模块

三张来源表**全在 user 域**（Supabase），而调用方都在 market 域会话上做事：冷集巡检要
数 `daily_worth`，写入上限挂在净值 job 里。`_RoutingSession` 的域判定靠**语句里已登记的
模型表**（`core/database.py::_domain_for_statement`），裸 `text()` 一个都认不出来 ⇒ 回落
app（market）域。开发态单库（user 域默认与 market 同文件）完全看不出问题，生产双库上那
三张表根本不在 market 库里：

    SystemExit: 热集来源表缺失: positions    ← 2026-11-12 起每日调度连续红的真因

故热集必须**显式开 user 域会话**读，与 `cross_domain` 的两步法同源：跨域只能「先取键、
再在应用层拼装」，不允许幻想一条语句跨两个引擎。

## 为什么抛 RuntimeError 而不是 SystemExit

原实现用 `SystemExit` 表达「宁可报错也不能少算热集」。但 `SystemExit` 是 `BaseException`，
巡检通道的兜底（`local_checks.run_local_check`）写的是 `except Exception` ⇒ 这一条只读
巡检直接把**已经跑完**的每日调度进程带走：退出码 1、`data/last_run_summary.json` 没写、
告警卡把真因写成「可能崩在建连阶段」（#3091 实测）。

库层表达「不可用」应当用普通异常，收敛方式由各入口自己决定：

- 巡检 → `error` 进摘要，由巡检告警卡承载（进程照常退 0）；
- 写入上限 → fail-open（见 `cold_set_write_scope.load_hot_codes`）；
- CLI → 打印可读提示 + 非零退出码（见 `scripts/check_cold_set_bloat.py`）。
"""

from __future__ import annotations

import re
from typing import List, Optional, Set

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

# 热集口径的来源表：持仓 ∪ 自选 ∪ 流水。与清理脚本同口径（`watchlist` 而非
# `watchlist_items`——后者是 #2145 事故里的错表名）。
HOT_SOURCE_TABLES = ('positions', 'watchlist', 'transactions')

# 「6 位纯数字」= 场外基金代码（`SH600519` / `00700.HK` 这类带前缀或后缀的不算）。
# 刻意放在 Python 侧过滤：原来的 SQL 用了 `GLOB '*[^0-9]*'`，那是 **SQLite 专有**语法，
# 而本模块现在跑在 user 域——生产是 Supabase Postgres，`GLOB` 在那里直接语法错误。
_SIX_DIGITS = re.compile(r'^[0-9]{6}$')


class HotCodesUnavailable(RuntimeError):
    """热集口径不可用（来源表缺失 / 连不上 user 库）。

    调用方**必须**显式决定怎么收敛：少算热集会把这些标的误判成冷集（进而按冷集保留
    窗口清理它们的历史），静默返回空集是这里最贵的失效方式。
    """


def has_table(db: Session, table: str) -> bool:
    """表是否存在——用 SQLAlchemy 反射而非 `sqlite_master`（后者只有 SQLite 有）。"""
    return inspect(db.get_bind()).has_table(table)


def missing_source_tables(db: Session) -> List[str]:
    """热集来源表里当前库缺哪几张（空列表 = 齐了）。"""
    return [table for table in HOT_SOURCE_TABLES if not has_table(db, table)]


def read_hot_codes(session: Optional[Session] = None) -> Set[str]:
    """读热集代码集合（6 位数字代码）。

    Args:
        session: **user 域**会话。不传则自己开一个（生产/CLI/巡检走这条）；
            调用方手里已经有 user 会话时传进来，省一次建连。

    Raises:
        HotCodesUnavailable: 来源表缺失。缺表时**不能**退化成空集——那是「全库皆冷集」。
    """
    if session is not None:
        return _read(session)

    from app.core.db_factory import user_session_factory

    db = user_session_factory()()
    try:
        return _read(db)
    finally:
        db.close()


def _read(db: Session) -> Set[str]:
    missing = missing_source_tables(db)
    if missing:
        raise HotCodesUnavailable(
            '热集来源表缺失: %s\n'
            '热集口径 = 持仓 ∪ 自选 ∪ 流水，少算任一来源都会把「仅自选、未持有」的基金误判为冷集。'
            '这三张表属 user 域，必须经 user 域会话读取（双库下 market 库里没有它们）；'
            '同时请确认配的是正确的库（SUPABASE_DATABASE_URL / DEV_USER_DATABASE_URL）。' % '、'.join(missing)
        )

    parts = ['SELECT DISTINCT symbol FROM %s' % table for table in HOT_SOURCE_TABLES]
    rows = db.execute(text(' UNION '.join(parts))).fetchall()
    return {row[0] for row in rows if isinstance(row[0], str) and _SIX_DIGITS.match(row[0])}
