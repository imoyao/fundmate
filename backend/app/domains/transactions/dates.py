# -*- coding: utf-8 -*-
"""流水「有效日」的唯一口径：排序、筛选、写入补全都从这里取。

## 为什么需要一层

`transactions` 有两列日期，**语义不同、可空性不同**：

- ``trade_date``（DateTime）—— 下单日，用户/文件给的业务事实；
- ``confirm_date``（Date）—— 确认日，份额真正登记的那天（基金 T+1）。

历史导入只填确认日（真实库 1,930 笔里 1,491 笔 ``trade_date`` 为 NULL），于是
「这笔账算哪天」必须有一个**兜底口径**。此前这个口径被实现了 4 遍，且互相不一致：

| 场景 | 旧实现 | 后果 |
|---|---|---|
| 列表排序（#2171 / #2712） | ``COALESCE(trade_date, confirm_date)`` | 正确 |
| 时间范围筛选 | 裸 ``trade_date >= start`` | **把只有确认日的行整批漏掉**（近 30 天实测少 28/61 笔） |
| 持仓份额累加 | 裸 ``ORDER BY trade_date, id`` | NULL 排最前 ⇒ 顺序退化成 id 顺序（当前结果恰好等价，见下） |
| 区间上界 ``<= end`` | 与 Date 类型的列比较 | 当天带时分秒的行（``2026-01-20 00:00:00``）被漏掉 |

同一个语义四处实现、其中三处错，正是「两份实现必然分叉」的教科书案例。本模块把它收成
**一个表达式 + 两个函数**，任何读写路径都不再自己拼 SQL。

## 为什么排序统一到有效日

份额推导（``derive_state_from_txns``）是纯求和，**对顺序不敏感**——所以这不是在修某个
数值错误，而是消除一个**脆弱前提**：现在的正确性依赖「插入顺序恰好等于时间顺序」
（真实库 181 个持仓符合，0 个不符，因为券商导出本身按时间排序）。一旦补录一笔历史流水，
id 顺序与时间顺序立刻脱钩；等哪天推导里出现「先卖后买要截断到 0」这类状态化逻辑，
错误就会静默出现。排序与判定用同一个键，是让这个前提**不再需要**。

## Nullable 到底怎么办

``trade_date`` 列保持可空（存量 1,491 笔不改一个字节——把 ``confirm_date`` 回填成
``trade_date`` 会伪造一个差 1~2 天的交易日，那是**新增错误记录**）。写入侧由
:func:`resolve_trade_date` 保证新行**不再产生**无日期记录；读取侧由本模块的表达式兜住
存量。两头一起改，才不需要动存量数据。
"""

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import String, cast, func
from sqlalchemy.orm import Query

from app.core.time_utils import today_shanghai
from app.domains.transactions.models import Transaction


def effective_day_expr():
    """「这笔账算哪天」的 SQL 表达式：``COALESCE(trade_date, confirm_date)``。

    **为什么转文本再合并**：两列类型不同（``trade_date`` 是 DateTime / ``confirm_date``
    是 Date），SQLite 对 ``CAST('2025-06-20' AS DATETIME)`` 走 NUMERIC 亲和性，把日期当
    「以年份开头的数字」（→ 2025.0），数字恒排于文本之前，「只有确认日」的行会被整批甩到
    最前（开发实测踩到）。转文本后两边都是 ISO 形式（``YYYY-MM-DD[ HH:MM:SS]``），
    字典序即时间序，跨 SQLite / Postgres 一致。

    同一口径也用于筛选（见 :func:`filter_by_effective_range`）——**排序键与筛选键必须
    是同一个值**，否则「列表里看得见、筛出来却看不见」这类自相矛盾永远查不完。
    """
    return func.coalesce(
        cast(Transaction.trade_date, String),
        cast(Transaction.confirm_date, String),
    )


def order_by_effective_day(query: Query, *, descending: bool = True) -> Query:
    """按有效日排序，并列用 ``id`` 兜底（同一天多笔必须有确定顺序，否则翻页会重复/漏行）。

    历史判据（#2171 / #2712 定稿，迁移自 ``transaction_service``）：

    - **WHY 不是 ``created_at``**：那是写入时间。批量导入的历史流水会让整张表退化成
      「导入批次顺序」，真机实测 ``SZ000638`` 的 24 笔排出来是
      ``2023-02-03 → 2023-02-15 → 2023-02-07 → 2023-03-16 → …``（同一批 ``created_at``
      挤在毫秒内、并列区间顺序未定义），用户看到的就是「乱序」。
    - **WHY 不是 ``confirm_date`` 单列**：反过来也有只有交易日的行（基金确认日待定），
      单列排序会把它们整批沉底——屏幕上印的是「交易日优先、确认日兜底」的那个日期，
      排序键必须与展示值一致。
    - **WHY ``id`` 兜底**：同一天多笔的 ``created_at`` 常精确到同一微秒，没有它翻页会在
      并列区间里重复或漏行。

    ``descending=False`` 给「按时间正序累加」的写路径用（持仓重算 / 修复工具），
    唯一目的是让它们与读侧共用同一个键，不再各写一份 ``ORDER BY trade_date``。
    """
    key = effective_day_expr()
    if descending:
        return query.order_by(key.desc(), Transaction.id.desc())
    return query.order_by(key.asc(), Transaction.id.asc())


def _as_day(value) -> Optional[date]:
    """把请求参数里的日期（date / datetime / ``YYYY-MM-DD`` 字符串）归一成 date。"""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def filter_by_effective_range(query: Query, start=None, end=None) -> Query:
    """按有效日筛选 ``[start, end]``（**闭区间**，两端含当天）。

    WHY 半开区间：有效日表达式是文本，而 ``trade_date`` 带时分秒
    （真实库 159 笔形如 ``2026-01-20 00:00:00.000000``）。用 ``expr <= '2026-01-20'``
    做上界会把当天 00:00:00 的行**排除**——用户选了「到 1 月 20 日」，20 号那天的账却
    不显示。改成 ``expr < '2026-01-21'``，两种存量形态（``YYYY-MM-DD`` /
    ``YYYY-MM-DD HH:MM:SS``）都命中。

    起止解析不出来时**忽略该端**（保持旧行为：不因一个坏参数把整张表筛空，也不 500）。
    """
    start_day, end_day = _as_day(start), _as_day(end)
    key = effective_day_expr()
    if start_day is not None:
        query = query.filter(key >= start_day.isoformat())
    if end_day is not None:
        query = query.filter(key < (end_day + timedelta(days=1)).isoformat())
    return query


def resolve_trade_date(trade_date, confirm_date=None):
    """写入侧兜底：``trade_date`` → ``confirm_date`` → 今天（东八区业务日）。

    链上每一级都是**已知事实或其最接近的代理**，不是凭空造数：

    1. 调用方给了 ``trade_date`` ⇒ 原样保留（用户/文件说了算）；
    2. 只给 ``confirm_date`` ⇒ 用它。这与导入器既有口径一致
       （``orchestrator_commit`` 落库时就是 ``trade_date=confirm_date``），代价是场外
       基金差 1~2 天，但比 NULL 强：NULL 在 SQLite 里排在最前，会被当成「最早的一笔」，
       还会被所有 ``trade_date >= ?`` 的筛选漏掉；
    3. 两个都没有 ⇒ 今天（``today_shanghai``，与 ``_parse_row_date`` 的「兜底今天」同源）。

    不返回 None 是**硬约束**：只要新写入的行一定带交易日期，存量那 1,491 笔无日期记录
    就是历史遗留的封闭集合，不会继续增长。
    """
    if trade_date is not None and trade_date != '':
        return trade_date
    if confirm_date is not None and confirm_date != '':
        return confirm_date
    return today_shanghai()


def prepare_write_kwargs(kwargs: dict) -> dict:
    """流水写入前的不变量收敛点（与 :func:`resolve_trade_date` 同属一个汇点）。

    #2916 只收敛了「日期」，#2875 补上第二条：**``ledger_id`` 不许为空**。真实库
    26 笔 ``ledger_id IS NULL`` 的流水全部来自导入器 TAX 分支漏传 / enrich 传 None
    ——它们不进任何账本视图，只能靠全表扫描才能发现。全库检查确认**没有任何合法
    写路径会不带账本**，所以在唯一构造汇点硬拦：

    - ``ledger_id`` 为空（None / 0 / 空串）⇒ ``ValueError``。调用方应当把该行
      计入自己的错误清单（导入器 ``commit_errors``）或让请求失败，而不是落一行
      「不进任何账本」的脏数据——静默写入比报错更难发现。

    与 :func:`resolve_trade_date` 一样：只管**新行**，存量 NULL 由修复脚本
    （``scripts/fix_orphan_ledger_null.py``）按 ``account_name`` 归属回填。
    """
    kwargs['trade_date'] = resolve_trade_date(kwargs.get('trade_date'), kwargs.get('confirm_date'))
    if not kwargs.get('ledger_id'):
        raise ValueError('流水缺少 ledger_id（账本归属）：拒绝写入无账本流水')
    return kwargs


__all__ = [
    'effective_day_expr',
    'filter_by_effective_range',
    'order_by_effective_day',
    'prepare_write_kwargs',
    'resolve_trade_date',
]
