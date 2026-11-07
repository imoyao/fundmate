# -*- coding: utf-8 -*-
"""缺账本孤儿流水（``ledger_id IS NULL``）的只读暴露 / 显式回填 / 可撤销（#2875 后端）。

## 背景（已实证，勿再推断）

真库 ``backend/invest.db`` 有 **26 笔** ``ledger_id IS NULL AND position_id IS NULL`` 的
流水（25 dividend_tax + 1 bond_redeem，全部 ``symbol`` 为空、``is_income`` 为 NULL、
``account_name`` 全为「同花顺（银河证券）」）。#2918 已堵住导入侧入口并给了 CLI
``backend/scripts/fix_orphan_ledger_null.py --apply``，但那是一次性脚本、只在副本上演练过，
真库至今 26 笔未修。本模块把 CLI 的能力服务化：只读暴露 + 用户显式指定流水才回填 + 可撤销，
**零自动写入**：GET 不改任何东西，写只在用户 POST 且逐条通过校验后发生。

## 安全边界（已实证，作为前提而非本模块重新推导）

这 26 笔 ``symbol`` 全空 ⇒ ``core/symbol_utils.py::symbol_identity()`` 返回空串 ⇒ 夜间
``services/sync/jobs/orphan_backfill_job.py::_backfill`` 第一步计入 ``no_identity`` 跳过，
该判据不看 ``ledger_id``。因此补 ``ledger_id`` **不会**触发自动重挂、不会改 ``position_id``、
不会改份额。``amount`` 单位是「分」、``quantity`` 是 1/10000 最小单位，本接口
**一个字节都不碰** ``amount`` / ``quantity`` 两列。

## 口径与已知限制（如实标注，不许粉饰）

- **检出**：SQLAlchemy ORM（不裸 sqlite）``Transaction.family_id == family_id
  AND Transaction.ledger_id IS NULL AND Transaction.position_id IS NULL``。
  ``position_id IS NULL`` 是**硬条件**：挂了持仓的行由持仓自己的账本决定，绝不动。
  ``ledger_id IS NULL`` 同样是硬条件（见测试的变异探针：去掉它会把已有账本的行算进来）。
- **归属规则必须与 CLI ``fix_orphan_ledger_null.py::resolve_ledger`` 完全一致**：
  ``account_name`` 去空白后非空；在**同 family** 下查 ``ledgers.name`` **精确同名**
  （区分大小写、不模糊、不去空格猜测）；恰好 1 条 ⇒ 回填该 ledger；0 条 / >1 条（歧义）/
  空 account_name ⇒ 不可回填，并给出与 CLI **逐字相同**的中文 ``block_reason``。
  app 层不依赖 scripts（分层守卫），故此处按语义复刻并在测试中做逐例一致性比对。
  口径限制：因 CLI 用 ``WHERE family_id = ? AND name = ?``，「别家存在同名账本」在本接口里
  归到「同 family 下无匹配」，**没有**单独的「跨 family」分支（否则即与 CLI 漂移）。
- **批次**：按 ``created_at`` 升序，相邻间隔 > 600 秒切新批；``label`` 取该批首条
  ``created_at`` 的 ``YYYY-MM-DD HH:MM``。口径来源为
  ``services/dangling_ref_service.py::_cluster_batches``（#2866），本模块按语义重写、
  与之**逻辑等价**，不是照抄的第三份实现：created_at 为空的流水不参与间隔判定、附到当前批
  （无时间无法证明属于同一次写入），label 降级为 '未知时间'。若那份规则变更，请同步本处。
- **单位**：``amount`` 只在序列化边界经 ``Money.cents_to_yuan`` /100 换成「元」；其余字段
  原样，日期用 ``isoformat()`` 或 None。前端不得再换一次。``quantity`` 不出现在任何响应里。
- **分组**：按 ``resolved_ledger_id`` 分组（None 归到唯一的 ``blocked`` 组），组内按
  created_at 升序；``batch_id`` 取组内最早一条所属批次。block_reason 组级：若组内多条
  流水原因不同，组级给概括说明、**逐条真实原因在 ``transactions[].block_reason``**
  （如实标注，不假装全组一个原因）。
- **写入硬约束（写死，逐条由测试守住）**：``backfill_orphan_ledgers`` **只 UPDATE
  ``transactions.ledger_id`` 一列**。禁止改 ``position_id`` / ``quantity`` / ``amount`` /
  ``symbol`` / 任何持仓列，禁止调用任何重算或回填 job。审计写 ``adjustment_logs``
  （``action='orphan_ledger_backfill'``），``before_json=[{id, ledger_id: null}]``、
  ``after_json=[{id, ledger_id}]``，reason 取 body、operator 可空，含 ``family_id``
  （``FamilyScopedMixin``）。不改模型、不加列、不建表。
- **undo**：仅凭 ``orphan_ledger_backfill`` 日志撤销；逐条仅当该 txn 当前 ``ledger_id``
  仍等于 after 值时恢复成 before 值（NULL），否则跳过并计数；幂等；拒绝非本 action 的日志；
  每次另写一条 ``action='orphan_ledger_undo'`` 留痕（含 restored/skipped 计数）。

## 事务边界

所有函数接收调用方传入的 ``db: Session``，**不自己开会话、不 import Flask**（纯业务层）。
视图用 ``with user_session() as db:`` 提供「一个请求一个事务」，服务层只 ``flush()`` 不
``commit()``；服务层抛 ``ValueError`` 由视图转 ``abort(400)``，请求 teardown 收到异常会
rollback，保证「整体 400、零写入」。所有校验分支一律排在写操作之前。测试直接把 ``db``
fixture 传进来，天然落在同一事务里。
"""

import json
from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction

#: 批次切分阈值（秒）：相邻 created_at 间隔 > 该值即切新批（口径来源 dangling_ref_service）。
BATCH_GAP_SECONDS = 600

#: 单次回填上限（原始条数，去重前判定）。
MAX_TRANSACTION_IDS = 500

#: 审计日志 action（长度均 ≤ 模型的 String(30)）。
ACTION_BACKFILL = 'orphan_ledger_backfill'
ACTION_UNDO = 'orphan_ledger_undo'


def _orphan_condition(family_id: int):
    """检出条件（#2875 契约口径）：ledger_id / position_id 都为 NULL 且 family 匹配。

    ``ledger_id IS NULL`` 与 ``position_id IS NULL`` 都是硬条件；后者保证挂了持仓的行
    （由持仓自己的账本决定）绝不被本接口改动。变异探针见测试：
    去掉 ``ledger_id.is_(None)`` 会把「已有账本」的行算进检出集合。
    """
    return and_(
        Transaction.family_id == family_id,
        Transaction.ledger_id.is_(None),
        Transaction.position_id.is_(None),
    )


def _normalize_ids(raw) -> list[int]:
    """校验并归一化 transaction_ids：非空 int 列表、≤500、去重保序。

    bool 是 int 子类，显式排除，避免 ``True`` 被当成 id=1。长度按**去重前**的原始条数
    判定，避免用超长列表绕过上限。
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
    seen = set()
    uniq = []
    for v in normalized:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _load_orphans_by_ids(db: Session, family_id: int, ids: list[int]) -> list[Transaction]:
    """按 id 取流水，并**再次用完整检出条件校验**（硬约束 2）。

    防止把已修好（ledger_id / position_id 已不为空）的 id 重复回填；任一 id 不在检出集合里
    即整体抛 ValueError，不写任何东西。
    """
    rows = db.query(Transaction).filter(_orphan_condition(family_id), Transaction.id.in_(ids)).all()
    found = {t.id: t for t in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValueError(f'以下流水不属于当前家庭或已不满足检出条件（可能已被修复）：{missing}')
    return [found[i] for i in ids]


def resolve_ledger(db: Session, family_id: int, account_name: str | None) -> tuple[int | None, str]:
    """按 ``(family_id, name)`` 精确匹配唯一账本；返回 ``(ledger_id, 不可回填原因)``。

    **与 CLI ``fix_orphan_ledger_null.py::resolve_ledger`` 逐字同口径**（app 层不 import
    scripts，故此处按语义复刻，测试中做逐例一致性比对）：去空白后非空；同 family 下
    ``ledgers.name`` 精确同名（区分大小写、不模糊、不去空格猜测）；恰好 1 条 ⇒ 回填；
    0 / >1 / 空名 ⇒ 不可回填。成功时原因为空串（序列化边界据此转成 ``None``）。
    """
    name = (account_name or '').strip()
    if not name:
        return None, 'account_name 为空，无法归属'
    rows = db.query(Ledger.id).filter(Ledger.family_id == family_id, Ledger.name == name).all()
    if not rows:
        return None, f'同 family 下无名为 {name!r} 的账本'
    if len(rows) > 1:
        return None, f'同 family 下有 {len(rows)} 个同名账本，歧义'
    return rows[0][0], ''


def _resolve_all(db: Session, family_id: int, rows: list[Transaction]) -> dict:
    """逐条调用 ``resolve_ledger`` 得到 ``{txn_id: (ledger_id, reason)}``（GET 与写入共用判据）。"""
    resolved = {}
    for t in rows:
        resolved[t.id] = resolve_ledger(db, family_id, t.account_name)
    return resolved


def _sort_key(t: Transaction):
    """全局排序键：created_at 升序，无时间的排最前，id 兜底稳定（口径同 _cluster_batches）。"""
    return (t.created_at is None, t.created_at or datetime.min, t.id)


def _cluster_batches(rows: list[Transaction]) -> list[list[Transaction]]:
    """按 created_at 聚簇：相邻间隔 > BATCH_GAP_SECONDS 切新批。

    口径来源 ``services/dangling_ref_service.py::_cluster_batches``（#2866），本实现按语义
    重写、与之**逻辑等价**，不是照抄的第三份实现。rows 须已按 created_at 升序；created_at
    为空的流水不参与间隔判定、附到当前批（无时间无法证明属于同一次写入），且不推进时间基准。
    """
    clusters: list[list[Transaction]] = []
    last_timed = None
    for t in rows:
        ts = t.created_at
        if ts is None:
            if clusters:
                clusters[-1].append(t)
            else:
                clusters.append([t])
            continue
        gap_exceeded = last_timed is not None and (ts - last_timed).total_seconds() > BATCH_GAP_SECONDS
        if last_timed is None or gap_exceeded:
            clusters.append([t])
        else:
            clusters[-1].append(t)
        last_timed = ts
    return clusters


def _build_batches(rows: list[Transaction]):
    """聚簇成 ``(batches, txn_to_batch, batch_labels)``；label 取批内首条 created_at。

    ``batches`` 结构按契约只给 ``{id, label, txn_count}``；无时间的批 label 降级 '未知时间'。
    """
    batches = []
    txn_to_batch = {}
    batch_labels = {}
    for idx, cluster in enumerate(_cluster_batches(rows), 1):
        first_ts = cluster[0].created_at
        label = first_ts.strftime('%Y-%m-%d %H:%M') if first_ts else '未知时间'
        for t in cluster:
            txn_to_batch[t.id] = idx
        batches.append({'id': idx, 'label': label, 'txn_count': len(cluster)})
        batch_labels[idx] = label
    return batches, txn_to_batch, batch_labels


def _serialize_txn(t: Transaction, resolved: dict) -> dict:
    """单条流水明细（纯只读）。amount 经 Money /100 成「元」；日期 isoformat 或 None。

    ``block_reason`` 由 resolve_ledger 的空串原因转成 ``None``（契约 ``str|null``）。
    ``quantity`` 及任何持仓列都不出现在这里——本接口一个字节都不碰它们。
    """
    lid, reason = resolved[t.id]
    return {
        'id': t.id,
        'txn_type': t.txn_type,
        'trade_date': t.trade_date.isoformat() if t.trade_date else None,
        'confirm_date': t.confirm_date.isoformat() if t.confirm_date else None,
        'symbol': t.symbol,
        'asset_type': t.asset_type,
        'account_name': t.account_name,
        'amount': Money.cents_to_yuan(t.amount),
        'created_at': t.created_at.isoformat() if t.created_at else None,
        'resolved_ledger_id': lid,
        'block_reason': reason or None,
    }


def _load_ledger_names(db: Session, family_id: int) -> dict:
    """同 family 账本 ``{id: name}``，一次查完供分组/汇总回显。"""
    return {lg.id: lg.name for lg in db.query(Ledger.id, Ledger.name).filter(Ledger.family_id == family_id).all()}


def _build_group(
    lid: int, txns: list, resolved: dict, ledger_names: dict, txn_to_batch: dict, batch_labels: dict
) -> dict:
    """组装单个可回填分组（key ``ledger:{id}``，block_reason 为 None）。"""
    first_batch = txn_to_batch[txns[0].id]
    return {
        'key': f'ledger:{lid}',
        'resolved_ledger': {'id': lid, 'name': ledger_names.get(lid)},
        'txn_count': len(txns),
        'block_reason': None,
        'batch_id': first_batch,
        'batch_label': batch_labels[first_batch],
        'transactions': [_serialize_txn(t, resolved) for t in txns],
    }


def _blocked_group_reason(blocked: list, resolved: dict) -> str:
    """blocked 组的组级原因：全组同一原因则如实给出，否则给概括、逐条原因留给 transactions。"""
    reasons = [resolved[t.id][1] for t in blocked]
    if len(set(reasons)) == 1:
        return reasons[0]
    return '多笔流水无法唯一归属账本（逐条原因见 transactions[].block_reason）'


def _build_blocked_group(blocked: list, resolved: dict, txn_to_batch: dict, batch_labels: dict) -> dict:
    """组装唯一的 ``blocked`` 组（key 固定 'blocked'，resolved_ledger 为 None）。"""
    first_batch = txn_to_batch[blocked[0].id]
    return {
        'key': 'blocked',
        'resolved_ledger': None,
        'txn_count': len(blocked),
        'block_reason': _blocked_group_reason(blocked, resolved),
        'batch_id': first_batch,
        'batch_label': batch_labels[first_batch],
        'transactions': [_serialize_txn(t, resolved) for t in blocked],
    }


def _build_groups(rows: list, resolved: dict, ledger_names: dict, txn_to_batch: dict, batch_labels: dict) -> list:
    """按 resolved_ledger_id 分组（None → 单一 blocked 组）；组内沿用全局 created_at 升序。"""
    by_ledger = {}
    blocked = []
    for t in rows:
        lid = resolved[t.id][0]
        if lid is None:
            blocked.append(t)
        else:
            by_ledger.setdefault(lid, []).append(t)
    groups = []
    for lid in sorted(by_ledger):
        groups.append(_build_group(lid, by_ledger[lid], resolved, ledger_names, txn_to_batch, batch_labels))
    if blocked:
        groups.append(_build_blocked_group(blocked, resolved, txn_to_batch, batch_labels))
    return groups


def scan_orphan_ledgers(db: Session, family_id: int) -> dict:
    """GET /orphan-ledger/ 的数据源（**纯只读，绝不写库**）。

    结构逐项对应前端契约：total / fixable_count / blocked_count / batch_count 为全局计数，
    groups 按归属账本分组、无法归属的单独一组，batches 为全局按 created_at 聚簇的批次。
    只做查询与纯计算：不 UPDATE、不 add、不 flush、不调用任何重算/回填。
    """
    orphans = db.query(Transaction).filter(_orphan_condition(family_id)).all()
    rows = sorted(orphans, key=_sort_key)
    batches, txn_to_batch, batch_labels = _build_batches(rows)
    ledger_names = _load_ledger_names(db, family_id)
    resolved = _resolve_all(db, family_id, rows)
    groups = _build_groups(rows, resolved, ledger_names, txn_to_batch, batch_labels)
    fixable_count = sum(1 for t in rows if resolved[t.id][0] is not None)
    return {
        'total': len(rows),
        'fixable_count': fixable_count,
        'blocked_count': len(rows) - fixable_count,
        'batch_count': len(batches),
        'groups': groups,
        'batches': batches,
    }


def _plan_backfill(db: Session, family_id: int, txns: list[Transaction]) -> list:
    """重新逐条调用归属判定（硬约束 3：不信任 GET 结果），产出 ``[(txn, ledger_id)]``。

    任一条 ``block_reason`` 非空 ⇒ 整体抛 ValueError、零写入。全部校验排在写操作之前。
    """
    plans = []
    blocked = []
    for t in txns:
        lid, reason = resolve_ledger(db, family_id, t.account_name)
        if lid is None:
            blocked.append((t.id, reason))
        else:
            plans.append((t, lid))
    if blocked:
        detail = '；'.join(f'流水 {tid}：{reason}' for tid, reason in blocked)
        raise ValueError(f'以下流水无法唯一归属账本，整体拒绝回填：{detail}')
    return plans


def _summarize_ledgers(plans: list, ledger_names: dict) -> list:
    """按实际落到的账本汇总 ``[{id, name, count}]``，id 升序。"""
    counts = {}
    for _t, lid in plans:
        counts[lid] = counts.get(lid, 0) + 1
    return [{'id': lid, 'name': ledger_names.get(lid), 'count': counts[lid]} for lid in sorted(counts)]


def backfill_orphan_ledgers(
    db: Session,
    family_id: int,
    transaction_ids,
    reason=None,
    operator=None,
) -> dict:
    """POST /orphan-ledger/backfill/ 的数据源（用户显式指定才写）。

    **写入硬约束（写死）**：本函数**只 UPDATE ``transactions.ledger_id`` 一列**。
    禁止改 ``position_id`` / ``quantity`` / ``amount`` / ``symbol`` / 任何持仓列，
    禁止调用任何重算或回填 job。逐条硬约束：
    1. transaction_ids 非空 int 列表、≤500、去重（``_normalize_ids``）；
    2. 每条属于本 family 且再次用完整检出条件校验确实仍是孤儿（``_load_orphans_by_ids``）；
    3. 每条重新解析出唯一账本（``_plan_backfill``），任一 blocked ⇒ 整体 ValueError；
    4. 校验全部通过后才写：逐条 ``t.ledger_id = lid``，flush 拿审计日志 id；
    5. 写 ``adjustment_logs``：before_json/after_json 逐条记录 ledger_id 的 null→新值，
       reason 取 body、operator 可空、带 family_id。
    所有写都在调用方传入的单个 ``user_session()`` 事务里，服务层只 flush、不 commit；
    ValueError 由视图转 400，请求 teardown 回滚保证「整体 400、零写入」。
    """
    ids = _normalize_ids(transaction_ids)
    txns = _load_orphans_by_ids(db, family_id, ids)
    plans = _plan_backfill(db, family_id, txns)
    ledger_names = _load_ledger_names(db, family_id)

    # —— 以下才开始写；任何抛错分支都在上面，保证「整体 400、不写任何东西」——
    before = [{'id': t.id, 'ledger_id': None} for t in txns]
    for t, lid in plans:
        t.ledger_id = lid
    db.flush()
    after = [{'id': t.id, 'ledger_id': lid} for t, lid in plans]

    log = AdjustmentLog(
        family_id=family_id,
        action=ACTION_BACKFILL,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=reason,
        operator=operator,
    )
    db.add(log)
    db.flush()
    return {
        'log_id': log.id,
        'updated': len(plans),
        'ledgers': _summarize_ledgers(plans, ledger_names),
    }


def _parse_log_json(log: AdjustmentLog) -> tuple[list, list]:
    """解析 backfill 日志的 before/after JSON，结构异常一律 ValueError（不写任何东西）。"""
    try:
        before = json.loads(log.before_json or '[]')
        after = json.loads(log.after_json or '[]')
    except (TypeError, ValueError) as e:
        raise ValueError(f'撤销记录 JSON 损坏，无法解析：{e}') from e
    if not isinstance(before, list) or not isinstance(after, list):
        raise ValueError('撤销记录 before_json / after_json 结构异常，无法解析')
    return before, after


def _restore_txns(db: Session, family_id: int, before_map: dict, after_map: dict) -> tuple[int, int]:
    """逐条恢复：仅当 txn 当前 ledger_id 仍等于 after 值才恢复成 before 值（NULL），否则跳过。

    返回 ``(restored, skipped)``；幂等（重复撤销 restored=0）。family 过滤防越权。
    """
    restored = 0
    skipped = 0
    for tid, before_lid in before_map.items():
        txn = db.query(Transaction).filter(Transaction.id == tid, Transaction.family_id == family_id).first()
        if txn is None or txn.ledger_id != after_map.get(tid):
            skipped += 1
            continue
        txn.ledger_id = before_lid
        restored += 1
    return restored, skipped


def undo_backfill(db: Session, family_id: int, log_id) -> dict:
    """POST /orphan-ledger/undo/ 的数据源：撤销一次回填（幂等、留痕）。

    仅接受 ``action='orphan_ledger_backfill'`` 且属于本 family 的日志（拒绝非本 action）；
    逐条仅当当前 ledger_id 仍等于 after 值时恢复成 before 值（NULL），否则跳过并计数；
    每次另写一条 ``action='orphan_ledger_undo'`` 新日志留痕（含 restored/skipped）。
    """
    if isinstance(log_id, bool) or not isinstance(log_id, int):
        raise ValueError('log_id 必须是整数')
    log = (
        db.query(AdjustmentLog)
        .filter(
            AdjustmentLog.id == log_id,
            AdjustmentLog.family_id == family_id,
            AdjustmentLog.action == ACTION_BACKFILL,
        )
        .first()
    )
    if log is None:
        raise ValueError('撤销记录不存在或无权访问（仅能撤销 orphan_ledger_backfill 日志）')

    before, after = _parse_log_json(log)
    before_map = {item['id']: item['ledger_id'] for item in before}
    after_map = {item['id']: item['ledger_id'] for item in after}
    restored, skipped = _restore_txns(db, family_id, before_map, after_map)
    db.flush()

    db.add(
        AdjustmentLog(
            family_id=family_id,
            action=ACTION_UNDO,
            before_json=json.dumps({'ref_log_id': log_id}, ensure_ascii=False),
            after_json=json.dumps({'restored': restored, 'skipped': skipped}, ensure_ascii=False),
            reason=f'撤销 {ACTION_BACKFILL} 日志 {log_id}',
            operator=log.operator,
        )
    )
    db.flush()
    return {'restored': restored, 'log_id': log_id}
