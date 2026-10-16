# -*- coding: utf-8 -*-
"""跨账本重复交易（「幽灵重复」）忽略记录服务（#2151 域 D）。

WHY 单独一个 service 而不是塞进 `reconciliation_service`：本服务的输入来自
**summary 域的实时扫描**（`services.summary_service.scan_cross_ledger_duplicates`），
而落库表（`ghost_duplicate_ignores`）挂在对账域。若把它写进 `reconciliation_service`，
后者就要 import 前者 —— 而 `summary_service` 是**领域服务**，方向没问题
（`reconciliation_service` 同为领域服务），但会让「对账服务」多背一个跨域的数据源依赖。
本模块只做四件事：**读扫描结果 → 减掉已忽略 → 写忽略 / 撤销忽略**，
是「域 D 视图」与「两个既有数据源」之间的薄编排层。
"""

import json
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.core.time_utils import now_shanghai
from app.domains.reconciliation.models import GhostDuplicateIgnore
from app.services.summary_service import scan_cross_ledger_duplicates

#: 单家庭忽略记录上限（写侧封顶）。
#: 为什么需要：忽略表只增不改，而扫描器对「金额/账本集合变化」会产生新指纹——
#: 用户反复操作理论上可无限累积。真实量级是「几十条」，设 200 是给异常留余量；
#: 超过时**拒绝新的忽略**（而不是静默丢弃），并把已忽略清单交给用户自行撤销。
MAX_IGNORES_PER_FAMILY = 200


def ignored_fingerprints(db: Session, family_id: int) -> set[str]:
    """已忽略指纹集合。"""
    rows = db.query(GhostDuplicateIgnore.fingerprint).filter(GhostDuplicateIgnore.family_id == family_id).all()
    return {r[0] for r in rows}


def scan_visible_groups(db: Session, family_id: int) -> list[dict]:
    """扫描结果减去已忽略的组（域 D 的列表数据源）。"""
    groups = scan_cross_ledger_duplicates(db, family_id)
    ignored = ignored_fingerprints(db, family_id)
    return [g for g in groups if g['fingerprint'] not in ignored]


def list_ignores(db: Session, family_id: int) -> list[dict]:
    """已忽略清单（可撤销；展示当初忽略的组快照）。"""
    rows = (
        db.query(GhostDuplicateIgnore)
        .filter(GhostDuplicateIgnore.family_id == family_id)
        .order_by(GhostDuplicateIgnore.created_at.desc())
        .all()
    )
    result: list[dict] = []
    for row in rows:
        snapshot: dict[str, Any] = {}
        if row.snapshot_json:
            try:
                snapshot = json.loads(row.snapshot_json)
            except (TypeError, ValueError):
                # 快照坏了不影响撤销（撤销只认 fingerprint），降级为不展示摘要
                logger.warning('幽灵重复忽略记录快照解析失败 id={}', row.id)
        result.append(
            {
                'id': row.id,
                'fingerprint': row.fingerprint,
                'symbol': snapshot.get('symbol'),
                'confirm_date': snapshot.get('confirm_date'),
                'txn_type': snapshot.get('txn_type'),
                'amount_yuan': snapshot.get('amount_yuan'),
                'ledger_names': snapshot.get('ledger_names') or [],
                'reason': row.ignored_reason,
                'ignored_at': row.ignored_at.isoformat() if row.ignored_at else None,
            }
        )
    return result


def ignore_group(
    db: Session, family_id: int, fingerprint: str, reason: str | None = None, operator: int | None = None
) -> dict:
    """忽略一组跨账本重复（幂等）。

    幂等条件：该家庭 + 该指纹已存在 → 直接返回既有记录，不报错也不重复写。
    为什么幂等重要：前端「忽略」与「刷新」可能并发/重放，报错会让用户看到无意义的红字。

    返回 {'id', 'fingerprint', 'created'}；`created=False` 表示原本已忽略。
    """
    existing = (
        db.query(GhostDuplicateIgnore)
        .filter(GhostDuplicateIgnore.family_id == family_id, GhostDuplicateIgnore.fingerprint == fingerprint)
        .first()
    )
    if existing:
        return {'id': existing.id, 'fingerprint': existing.fingerprint, 'created': False}

    total = db.query(GhostDuplicateIgnore).filter(GhostDuplicateIgnore.family_id == family_id).count()
    if total >= MAX_IGNORES_PER_FAMILY:
        raise ValueError(f'已忽略记录已达上限 {MAX_IGNORES_PER_FAMILY} 条，请先在已忽略清单中撤销部分记录')

    # 快照只写「当时扫描到的组」（用于清单里解释「当初忽略的是什么」）。
    # 查不到不算错误：请求可能来自已过期的列表（组已因用户删除流水而消失），
    # 此时忽略仍然成立（用户确实表达了「这组不要再提示」）。
    current = next((g for g in scan_cross_ledger_duplicates(db, family_id) if g['fingerprint'] == fingerprint), None)
    snapshot = None
    if current:
        snapshot = json.dumps(
            {
                'symbol': current['symbol'],
                'confirm_date': current['confirm_date'],
                'txn_type': current['txn_type'],
                'amount_yuan': current['amount_yuan'],
                'ledger_names': current['ledger_names'],
            },
            ensure_ascii=False,
        )

    row = GhostDuplicateIgnore(
        family_id=family_id,
        fingerprint=fingerprint,
        ignored_reason=reason,
        ignored_at=now_shanghai().replace(tzinfo=None),
        ignored_by=operator,
        snapshot_json=snapshot,
    )
    db.add(row)
    db.flush()
    return {'id': row.id, 'fingerprint': row.fingerprint, 'created': True}


def undo_ignore(db: Session, family_id: int, fingerprint: str) -> bool:
    """撤销忽略（删除记录）。返回是否真的删到了——已不存在时返回 False（幂等）。"""
    deleted = (
        db.query(GhostDuplicateIgnore)
        .filter(GhostDuplicateIgnore.family_id == family_id, GhostDuplicateIgnore.fingerprint == fingerprint)
        .delete(synchronize_session=False)
    )
    return bool(deleted)


def undo_ignore_by_id(db: Session, family_id: int, ignore_id: int) -> bool:
    """按记录 id 撤销（清单页用 id 更顺；语义与 `undo_ignore` 一致）。"""
    deleted = (
        db.query(GhostDuplicateIgnore)
        .filter(GhostDuplicateIgnore.id == ignore_id, GhostDuplicateIgnore.family_id == family_id)
        .delete(synchronize_session=False)
    )
    return bool(deleted)
