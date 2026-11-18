# -*- coding: utf-8 -*-
"""账外类现金流水「归置」（#3089 / D116）。

## 表达的是什么

一笔钱可能同时出现在两处：某个货基持仓的市值，以及同一产品的一批孤儿流水净额。
系统猜不出「哪些孤儿流水其实已由持仓体现」（``symbol`` / ``trade_date`` 大面积为空），
只能由人显式指认。归置 = 给这批流水写 ``covered_position_id``，表达
「它们已由该持仓体现」，四处类现金口径据此排除它们（``summary_service``）。

## 硬边界

* **只改 ``covered_position_id`` 一列**：不动 ``position_id``（它是持仓成本/份额的输入，
  指过去会让成本翻倍，#3089 方案 B 已否决）、不动金额/日期/账本、不重算份额、不删流水。
* **可撤销**：清空该列即回到原状；本模块按 ``log_id`` 撤销并留审计日志，幂等。
* **家庭隔离**：流水与持仓都必须属于当前 family，任一不符整体拒绝、零写入
  （所有校验排在写操作之前，ValueError 由视图转 400）。
* **不自动回填存量**：哪些行该归置只能由人指认，迁移只加列不写数。

## 为什么放在对账域入口

与 #2875「缺账本孤儿流水回填」同形态：用户显式给出一批 id、服务层逐条硬校验、
只 UPDATE 一列、写 ``adjustment_logs`` 供 ``log_id`` 撤销。视图只做取参与组信封。
"""

import json
from typing import Any

from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services.summary_service import (
    ORPHAN_BUCKET_INCOME,
    ORPHAN_FLOW_ASSET_TYPES,
    orphan_flow_delta,
)

#: 单次最多归置 500 条（与 #2875 backfill 同上限：避免一次请求锁住整张流水表）。
MAX_TRANSACTION_IDS = 500
ACTION_COVER = 'orphan_flow_cover'
ACTION_UNCOVER = 'orphan_flow_uncover'


def _normalize_ids(raw) -> list[int]:
    """校验并归一化 transaction_ids：非空 int 列表、≤500、去重保序。

    bool 是 int 子类，显式排除，避免 ``True`` 被当成 id=1。长度按**去重前**判定。
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError('transaction_ids 必须是非空列表')
    if len(raw) > MAX_TRANSACTION_IDS:
        raise ValueError(f'transaction_ids 最多 {MAX_TRANSACTION_IDS} 条，收到 {len(raw)} 条')
    normalized = []
    for v in raw:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f'transaction_ids 元素必须是整数，收到 {v!r}')
        normalized.append(v)
    seen, uniq = set(), []
    for v in normalized:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _normalize_position_id(raw) -> int:
    """covered_position_id 必须是正整数；不接收 0 / 负数 / 字符串 id。"""
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError('covered_position_id 必须是正整数（指向已存在的持仓）')
    return raw


def _normalize_operator(raw):
    """operator 落 ``AdjustmentLog.operator``（Integer 列），字符串数字也接受。"""
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError('operator 必须是整数用户 ID')
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError('operator 必须是整数用户 ID') from None


def _load_uncovered(db, family_id: int, ids: list[int]) -> list[Transaction]:
    """按 id 取流水，并**再次用完整口径校验**（不信任调用方传来的 id）。

    任一行不属于本 family、不是 ``money_fund``/``reverse_repo`` 孤儿、
    或已被归置 ⇒ 整体 ValueError、零写入。
    """
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            Transaction.position_id.is_(None),
            Transaction.asset_type.in_(ORPHAN_FLOW_ASSET_TYPES),
            Transaction.covered_position_id.is_(None),
            Transaction.id.in_(ids),
        )
        .all()
    )
    found = {t.id: t for t in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValueError(f'以下流水不属于当前家庭、不是账外类现金或已被归置：{missing}')
    return [found[i] for i in ids]


def _excluded_cents(txns: list[Transaction]) -> tuple[int, int]:
    """这批流水从类现金口径里拿掉的金额（分）：``(本金净额, 收益桶)``。

    分桶判据复用 ``orphan_flow_delta``（与四处口径同源），不另写 elif 链；
    返回给用户看的是「总资产会少多少」，避免把修正误读成丢钱。
    """
    net = income = 0
    for t in txns:
        moved = orphan_flow_delta(t.txn_type, t.amount, t.is_income)
        if moved is None:
            continue
        bucket, delta = moved
        if bucket == ORPHAN_BUCKET_INCOME:
            income += delta
        else:
            net += delta
    return net, income


def cover_orphan_flows(
    db,
    family_id: int,
    transaction_ids,
    covered_position_id,
    reason=None,
    operator=None,
) -> dict[str, Any]:
    """把用户显式指认的一批孤儿流水标记为「已由某持仓体现」。

    返回归置条数、持仓名与**被排除的类现金金额**（元）；后者正是 ``total_assets``
    会下降的数，它不是钱消失，而是同一笔钱不再被算两遍。
    """
    ids = _normalize_ids(transaction_ids)
    pid = _normalize_position_id(covered_position_id)
    op = _normalize_operator(operator)
    txns = _load_uncovered(db, family_id, ids)
    position = db.query(Position).filter(Position.id == pid, Position.family_id == family_id).first()
    if position is None:
        raise ValueError('持仓不存在或不属于当前家庭')
    net_cents, income_cents = _excluded_cents(txns)

    # —— 校验全部通过后才写；任何抛错分支都在上面 ——
    before = [{'id': t.id, 'covered_position_id': None} for t in txns]
    for t in txns:
        t.covered_position_id = pid
    db.flush()
    after = [{'id': t.id, 'covered_position_id': pid} for t in txns]
    log = AdjustmentLog(
        family_id=family_id,
        action=ACTION_COVER,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=reason,
        operator=op,
    )
    db.add(log)
    db.flush()
    return {
        'log_id': log.id,
        'updated': len(txns),
        'covered_position_id': pid,
        'position_name': position.name,
        'excluded_net_amount': Money.cents_to_yuan(net_cents),
        'excluded_income_amount': Money.cents_to_yuan(income_cents),
        'excluded_total_amount': Money.cents_to_yuan(net_cents + income_cents),
    }


def _parse_log_json(log: AdjustmentLog) -> tuple[list, list]:
    """解析归置日志的 before/after JSON，结构异常一律 ValueError（不写任何东西）。"""
    try:
        before = json.loads(log.before_json or '[]')
        after = json.loads(log.after_json or '[]')
    except (TypeError, ValueError) as e:
        raise ValueError(f'撤销记录 JSON 损坏，无法解析：{e}') from e
    if not isinstance(before, list) or not isinstance(after, list):
        raise ValueError('撤销记录 before_json / after_json 结构异常，无法解析')
    try:
        after_map = {item['id']: item['covered_position_id'] for item in after}
        pairs = [(item['id'], item['covered_position_id']) for item in before]
    except (KeyError, TypeError) as e:
        raise ValueError(f'撤销记录条目缺少 id / covered_position_id：{e}') from e
    return pairs, after_map


def undo_cover(db, family_id: int, log_id) -> dict[str, Any]:
    """撤销一次归置：仅当当前值仍等于 after 值才清空，幂等且每次留痕。

    只接受 ``action=orphan_flow_cover`` 且属于本 family 的日志，防止拿别的
    操作日志把别人的归置清掉。
    """
    if isinstance(log_id, bool) or not isinstance(log_id, int):
        raise ValueError('log_id 必须是整数')
    log = (
        db.query(AdjustmentLog)
        .filter(
            AdjustmentLog.id == log_id,
            AdjustmentLog.family_id == family_id,
            AdjustmentLog.action == ACTION_COVER,
        )
        .first()
    )
    if log is None:
        raise ValueError('撤销记录不存在或无权访问（仅能撤销 orphan_flow_cover 日志）')
    pairs, after_map = _parse_log_json(log)

    restored = skipped = 0
    for tid, before_pid in pairs:
        txn = db.query(Transaction).filter(Transaction.id == tid, Transaction.family_id == family_id).first()
        if txn is None or txn.covered_position_id != after_map.get(tid):
            skipped += 1
            continue
        txn.covered_position_id = before_pid
        restored += 1
    db.flush()
    db.add(
        AdjustmentLog(
            family_id=family_id,
            action=ACTION_UNCOVER,
            before_json=json.dumps({'ref_log_id': log_id}, ensure_ascii=False),
            after_json=json.dumps({'restored': restored, 'skipped': skipped}, ensure_ascii=False),
            reason=f'撤销 {ACTION_COVER} 日志 {log_id}',
            operator=log.operator,
        )
    )
    db.flush()
    return {'restored': restored, 'skipped': skipped, 'log_id': log_id}


def cover_message(result: dict[str, Any]) -> str:
    """归置成功后的提示语：说清「净额下降是修正，不是丢钱」。"""
    return (
        f'已把 {result["updated"]} 笔流水归置到持仓 #{result["covered_position_id"]}'
        f'（{result["position_name"] or "未命名"}）：账外类现金少计 ¥{result["excluded_total_amount"]:.2f}，'
        '同一笔钱不再算两遍，持仓市值不变。'
    )
