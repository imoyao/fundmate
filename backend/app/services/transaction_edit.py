# -*- coding: utf-8 -*-
"""交易编辑的**留痕**：改了什么、改成什么（`PATCH /ledgers/<id>/transactions/<tid>/`）。

## 为什么要有它

2026-11-15 排查「补录日志记的是 115 份 @30 元，落库行却是 30 份 @115 元」时，最后只能靠
`transactions.updated_at` 比 `created_at` 晚 3 分钟来猜「这一行建完之后被手工改过」——
改的人、改前改后都查不到。补录、回补、重建、删除这些动作都写 `adjustment_logs`，
唯独最常走的「编辑交易」不写：审计链在这里断了一环，出事时只能倒推。

## 为什么落在 `adjustment_logs`

它是全仓唯一的写操作留痕表（`reconciliation` 域的 `AdjustmentLog`），已经承载
补录 / 忽略差异 / 悬空补救 / 撤销等动作。审计要能按时间线一次看全，就不该再造第二张表。
本模块只**写一行**审计，不读、不 join，不参与 reconciliation 域的任何计算。

## 只记变化字段

一次编辑往往只改一列（用户改个备注），把整行前后都塞进日志会让「改了什么」被噪声淹没。
故 before/after 只保留**值确实变了**的字段，`changed` 里列出字段名。没有任何变化时不写日志
（清空后再提交、前端重复提交同一份表单都不该留下痕迹）。
"""

import json
from datetime import date, datetime

from app.domains.reconciliation.models import AdjustmentLog

#: 编辑允许改动的字段（与 `update_ledger_transaction` 的入参契约一致）。
#: `import_hash` 不在此列：它被清空是编辑的**后果**，不是用户输入，记录它会误导排查。
_TRACKED = (
    'quantity',
    'price',
    'amount',
    'fee',
    'fee_commission',
    'fee_stamp_duty',
    'fee_transfer_fee',
    'fee_other',
    'trade_date',
    'confirm_date',
    'notes',
    'entry_status',
)


def _plain(value):
    """把 date/datetime 折成 ISO 字符串：JSON 直出会带 `Date` 前缀且不可回读。"""
    if isinstance(value, datetime):
        return value.isoformat(sep=' ')
    if isinstance(value, date):
        return value.isoformat()
    return value


def snapshot(txn) -> dict:
    """编辑前的行快照（只取被跟踪字段）。"""
    return {field: _plain(getattr(txn, field, None)) for field in _TRACKED}


def record(db, txn, before: dict, data: dict | None = None) -> bool:
    """比对 `before` 与当前行，写一条 `transaction_edit` 审计；无变化返回 False。

    `data` 只用来透传 operator / reason（前端可选传），不参与比对。
    """
    after = snapshot(txn)
    changed = [field for field in _TRACKED if before.get(field) != after.get(field)]
    if not changed:
        return False
    data = data or {}
    db.add(
        AdjustmentLog(
            family_id=txn.family_id,
            action='transaction_edit',
            before_json=json.dumps(
                {'transaction_id': txn.id, 'fields': {f: before.get(f) for f in changed}},
                ensure_ascii=False,
            ),
            after_json=json.dumps(
                {'transaction_id': txn.id, 'changed': changed, 'fields': {f: after[f] for f in changed}},
                ensure_ascii=False,
            ),
            reason=data.get('reason') or '编辑交易',
            operator=data.get('operator'),
        )
    )
    return True
