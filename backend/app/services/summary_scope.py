# -*- coding: utf-8 -*-
"""汇总口径的**作用域计算**（#3246 第三段 / D127）.

为什么单独一个文件：`summary_service.py` 已 1420 行、贴着 `guard_service_size` 的冻结
基线，而「成员切片 ∩ 可见性」这套判断要被 `get_summary_data` / `get_account_groups` /
`get_distributions` / `_per_ledger_buckets` 四处共用。放进主文件既顶破基线，又会让
同一个判断散在四个调用点各写一遍——那正是 #2154「四处各累加、只有两处改对」的形态。

本模块**只做纯计算**（不 import `summary_service`，避免循环）；聚合仍由主文件委托
`family_totals`（唯一出口）。三个函数各回答一个问题：

- ``effective_scope``  —— 这次请求到底该看哪些账户，以及「无主明细」算不算；
- ``ledger_visible``   —— 单个账户在不在范围内（明细聚合用，O(1)）；
- ``apply_scope``      —— 把范围挂到 query 上（持仓 / 资产两张表共用）。
"""

from typing import List, Optional

from sqlalchemy import false, or_

from app.core.database import Session
from app.services.family_member_service import ledger_ids_for_member


def effective_scope(
    db: Session, family_id: int, member_id: int | None, visible_ids: set | None
) -> tuple[Optional[List[int]], bool]:
    """成员切片 ∩ 可见性 → ``(生效账户集合, 是否放行无主明细)``（D127 双口径的唯一入口）.

    两个来源语义完全不同，这里只做交集，**不用任何一个推导另一个**（D125 三轴不互推）：
    成员归属是报表维度（这笔钱是谁的），可见性是授权（谁允许看见）。

    **「放行无主」为什么随来源变**（本函数唯一不显然的地方，两个方向都有既有判据）：

    - **成员切片**（``member_id`` 有值）：``ledger_id IS NULL`` 的持仓不属于任何成员，
      放进成员视图就是「A 的账里出现一笔没主的钱」——既有口径明确不放行。
    - **只看可见性**（``member_id`` 为空）：无主明细按「家庭共有」放行，与
      ``domains/ledgers/visibility.restrict_visible`` 的 NULL 判据**必须同一份**。这里若用
      `IN` 把它排掉，就会出现「持仓列表有 93 行未归档、总资产里一分钱没有」——明细与汇总
      各算一套，用户拿着列表核总额永远对不上。

    任一维度为 ``None`` 表示不限制；都为 ``None`` ⇒ 家庭全量（``(None, False)``，
    与改造前逐字一致）。
    """
    member_ids = None if member_id is None else ledger_ids_for_member(db, family_id, member_id)
    if member_ids is not None:
        if visible_ids is None:
            return member_ids, False
        return sorted(set(member_ids) & set(visible_ids)), False
    if visible_ids is None:
        return None, False
    return sorted(visible_ids), True


def ledger_visible(ledger_id, ledger_ids) -> bool:
    """单个账户是否在生效集合内（明细聚合用）.

    ``ledger_ids is None`` = 不限制；**无主（``None`` / 哨兵 0）一律视为家庭共有**——
    与 ``restrict_visible`` 的 NULL 判据是同一份。两处若分叉，会出现
    「账户明细里有这 93 行未归档、汇总里一分钱没有」的死账。
    """
    if ledger_ids is None or not ledger_id:
        return True
    return ledger_id in ledger_ids


def apply_scope(query, column, ledger_ids: Optional[List[int]], include_unowned: bool):
    """把生效集合挂到 query 上（持仓 / 资产两张表共用同一份规则）.

    ``ledger_ids is None`` 且不放行无主 ⇒ 原样返回（家庭全量，零额外 WHERE）。
    空集不能写成 ``IN ()``——各方言行为不一致，PG 直接语法错。
    """
    if ledger_ids is None and not include_unowned:
        return query
    if ledger_ids:
        clause = column.in_(ledger_ids)
        return query.filter(or_(clause, column.is_(None)) if include_unowned else clause)
    if include_unowned:
        return query.filter(column.is_(None))
    return query.filter(false())


def family_scope_payload(visible_ids: set | None, all_ids: set, family_totals: dict, own_totals: dict):
    """要不要下发「家庭」对照块 + 组装（纯函数，不碰 DB）.

    判据是**金额真的不同**，不是「存在不可见账户」：给父母开的空账户、或那个账户已清空时
    两个数相等，下发只会让首页出现两张一模一样的卡。只给三个总数——市场分布 / 账户分组 /
    类别占比按家庭口径给，等于把「别人的钱在哪个市场、哪个账户」拆开告诉他，那是明细泄露。
    ``hidden_account_count`` 只报个数：用户要知道「少了几个账户」，但账户名与金额永不下发。
    """
    if visible_ids is None or all_ids <= set(visible_ids):
        return None
    if (
        family_totals['total_assets'] == own_totals['total_assets']
        and family_totals['total_liabilities'] == own_totals['total_liabilities']
    ):
        return None
    return {
        'total_assets_cny': family_totals['total_assets'],
        'total_liabilities_cny': family_totals['total_liabilities'],
        'net_assets_cny': family_totals['net_worth'],
        'hidden_account_count': len(all_ids) - len(set(visible_ids) & all_ids),
        'own_total_assets_cny': own_totals['total_assets'],
    }
