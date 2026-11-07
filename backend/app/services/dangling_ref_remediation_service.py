# -*- coding: utf-8 -*-
"""#2866 后续：悬空流水的「补全信息 / 显式删除」（后端服务层）。

## 为什么需要这一刀

``dangling_ref_service`` 只让 105 条「能确定归属」的流水挂回现存持仓。真库另有
532 条 blocked：295 条缺 symbol、593 条缺 trade_date、42 条两者都有却没有同标的
持仓行（数字有交集，2026-11-07 只读实测）。这些数据既不进任何按标的的统计，
也没有入口让用户处置，成了「看得见却动不了」的死数据。本模块补上两条显式写路径：

1. **补全信息**：只补 ``symbol`` / ``trade_date`` 的**空值**，已有值绝不覆盖；
2. **显式删除**：物理删除，删除前存**完整行快照**进 ``adjustment_logs``，可凭
   ``log_id`` 精确恢复。

## 安全边界（每条都有测试钉死）

- 目标必须**再次**通过 ``_load_dangling_by_ids``：仍属于本 family 且 position_id
  仍悬空。任一不满足整体抛 ``ValueError``、零写入，防止把已修好的流水再动一次。
- 所有校验（含 confirm / confirm_phrase / updated==0）**排在写操作之前**：拒绝分支
  不得留下 ``db.new / db.dirty / db.deleted``，也不得写审计日志。
- 删除要求 ``confirm is True`` **且** ``confirm_phrase == '删除'``（后端硬校验，
  不信任前端）；补全要求 ``confirm is True``。
- ``symbol_norm`` 是 mapper ``before_insert`` / ``before_update`` 按
  ``symbol_identity(symbol, asset_type)`` 重算的**派生列**：补全、撤销、删除恢复
  一律不手改，否则会与单一真相源漂移。撤销删除构造 ``Transaction(**payload)`` 时
  刻意排除该列，交给事件重算；审计快照仍记录原值，满足「完整快照」要求。
- 快照键用 **ORM 属性名**（``txn_type`` 而非 DB 列名 ``type``），datetime/date 转
  isoformat 字符串；恢复时按列类型 parse 回 ``datetime`` / ``date``，否则 SQLAlchemy
  的 DateTime 列拒收字符串。
- 不动 ``quantity`` / ``amount`` / ``realized_pnl`` / ``import_hash`` / ``source`` /
  任何持仓份额列；删除会改变已实现盈亏与收益统计（如实写在 warnings 里），
  但**不会改动现存持仓份额**（这些流水的 position_id 指向已删除行，不参与
  现存持仓的重算）。

## 事务边界（与 dangling_ref_service 同构）

所有函数接收调用方传入的 ``db: Session``，不自己开会话、不 import Flask；
只 ``flush()`` 不 ``commit()``。视图用 ``with user_session() as db:`` 提供
「一个请求一个事务」，``ValueError`` 转 400 后由 teardown rollback。

## 单位

对外 ``quantity`` 一律是「份」（最小单位 /10000），``amount`` / ``realized_pnl`` /
``total_amount`` 一律是「元」（分 /100），走 ``Money`` 换算；``before_json``
完整快照里存的是**库内原始整数**（最小单位 / 分），二者不许混用。
"""

import json
from datetime import date, datetime

from sqlalchemy import Date, DateTime
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services.dangling_ref_service import (
    _load_dangling_by_ids,
    _normalize_ids,
    _shares,
)

#: 删除动作的二次确认词（后端硬校验，前端输入框必须逐字一致）。
DELETE_CONFIRM_PHRASE = '删除'

ACTION_ENRICH = 'dangling_ref_enrich'
ACTION_ENRICH_UNDO = 'dangling_ref_enrich_undo'
ACTION_DELETE = 'dangling_ref_delete'
ACTION_DELETE_UNDO = 'dangling_ref_delete_undo'

#: 候选持仓最多返回条数（与 dangling_ref_service 同口径）。
MAX_CANDIDATES = 20

#: 前端预览里每类明细最多展示条数（后端仍返回全量，由调用方裁剪）。
_SNAPSHOT_COLUMNS_CACHE = None


def _column_attrs():
    """返回 [(ORM 属性名, Column)]，全局缓存一次。

    ``Transaction.txn_type`` 映射到 DB 列 ``type``，直接遍历 ``__table__.columns``
    再用 ``getattr(t, 'type')`` 会取不到值。走 mapper 的 ``column_attrs`` 才能同时
    拿到「可 getattr 的属性名」与「列类型」，这是完整快照正确性的命门。
    """
    global _SNAPSHOT_COLUMNS_CACHE
    if _SNAPSHOT_COLUMNS_CACHE is None:
        _SNAPSHOT_COLUMNS_CACHE = [(attr.key, attr.columns[0]) for attr in sa_inspect(Transaction).column_attrs]
    return _SNAPSHOT_COLUMNS_CACHE


def _iso(value):
    """datetime/date → isoformat 字符串；None 原样。"""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _parse_dt(value):
    """快照里的 isoformat 字符串 → datetime；None / datetime 原样。"""
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError(f'撤销记录里的日期值类型异常：{value!r}')


def _is_blank(value) -> bool:
    """symbol 是否可视为「未填写」：None / 空串 / 全空白。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _normalize_symbol(raw):
    """补全用的 symbol：None / 空串 = 不补；非 str、超 30 字符一律拒绝。"""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError('symbol 必须是字符串')
    value = raw.strip()
    if not value:
        return None
    if len(value) > 30:
        raise ValueError(f'symbol 长度不能超过 30 字符，收到 {len(value)} 个字符')
    return value


def _normalize_trade_date(raw):
    """补全用的 trade_date：None / 空串 = 不补；字符串按 ISO 解析成 datetime。"""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day)
    if not isinstance(raw, str):
        raise ValueError('trade_date 日期格式非法：必须是 YYYY-MM-DD 字符串')
    value = raw.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f'trade_date 日期格式非法：{raw!r}，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS') from e


def _require_confirm(confirm) -> None:
    """写入前二次确认：`is True` 严格判定，1 / 'true' 都不算（bool 之外一律拒绝）。"""
    if confirm is not True:
        raise ValueError('confirm 必须为 true：需要二次确认后才允许写入')


def _require_field(symbol, trade_date) -> None:
    if symbol is None and trade_date is None:
        raise ValueError('至少需要提供一个待补全字段（symbol 或 trade_date）')


def _plan_enrichment(txns, symbol, trade_date) -> list[dict]:
    """纯计算：算出每条流水「补什么」，不写库。

    ``_fill_symbol`` / ``_fill_date`` 是内部标记（下划线开头），返回给前端前会被
    ``_public_change`` 剥掉。已有值一律保持原样，绝不覆盖。
    """
    plan = []
    for t in txns:
        fill_symbol = symbol is not None and _is_blank(t.symbol)
        fill_date = trade_date is not None and t.trade_date is None
        plan.append(
            {
                'id': t.id,
                'symbol_before': t.symbol,
                'symbol_after': symbol if fill_symbol else t.symbol,
                'trade_date_before': _iso(t.trade_date),
                'trade_date_after': (_iso(trade_date) if fill_date else _iso(t.trade_date)),
                'asset_type': t.asset_type,
                '_fill_symbol': fill_symbol,
                '_fill_date': fill_date,
            }
        )
    return plan


def _public_change(item: dict) -> dict:
    """剥掉内部标记，只留前端契约里声明的字段。"""
    return {k: v for k, v in item.items() if not k.startswith('_')}


def _candidate_positions(db: Session, family_id: int, txns, symbol) -> list[dict]:
    """补全后可能可挂回的现存持仓：同 family + 同账本 + 同新标的，最多 20 条。

    空 symbol 或组内没有 ledger_id 时不给候选（回补会硬校验 ledger 一致，
    列出别的账本等于诱导挂错）。quantity 换算成「份」。
    """
    ledger_ids = {t.ledger_id for t in txns if t.ledger_id is not None}
    if symbol is None or not ledger_ids:
        return []
    rows = (
        db.query(Position)
        .filter(
            Position.family_id == family_id,
            Position.symbol == symbol,
            Position.ledger_id.in_(ledger_ids),
        )
        .order_by(Position.id)
        .limit(MAX_CANDIDATES)
        .all()
    )
    return [
        {
            'id': p.id,
            'symbol': p.symbol,
            'ledger_id': p.ledger_id,
            'quantity': _shares(p.quantity),
            'ownership_status': p.ownership_status,
        }
        for p in rows
    ]


def _enrichment_warnings(plan, cands, symbol) -> list[str]:
    """如实说明口径限制，不粉饰「补全 ≠ 能挂回」。"""
    warnings = [
        '本次只补 symbol / trade_date 的空值，已有值不会被覆盖；份额、金额、已实现盈亏一律不动。',
        '补全标的代码后仍未必能补上关联：还需要同账本存在同标的的现存持仓行，系统不会替你猜测归属。',
        'symbol_norm 会由系统按标的代码与资产类型自动重算，不需要也不允许手工填写。',
    ]
    if any(p['asset_type'] is None for p in plan):
        warnings.append('组内存在缺 asset_type 的流水，身份键会降级，补全后仍可能无法与现存持仓匹配。')
    if symbol is not None and not cands:
        warnings.append('当前没有同账本同标的的现存持仓行；补全后仍需先补建持仓或补录流水。')
    return warnings


def preview_enrichment(db: Session, family_id: int, transaction_ids, symbol=None, trade_date=None) -> dict:
    """补全前预览（GET /enrich-preview/ 的数据源，**纯只读，绝不写库**）。

    只用查询与纯计算：不 UPDATE、不 add、不 flush。``candidate_positions``
    帮用户判断「补这个代码之后有没有现存持仓可挂回」，避免补完仍卡在 blocked。
    """
    ids = _normalize_ids(transaction_ids)
    new_symbol = _normalize_symbol(symbol)
    new_date = _normalize_trade_date(trade_date)
    _require_field(new_symbol, new_date)
    txns = _load_dangling_by_ids(db, family_id, ids)
    plan = _plan_enrichment(txns, new_symbol, new_date)
    cands = _candidate_positions(db, family_id, txns, new_symbol)
    return {
        'txn_count': len(txns),
        'fill_symbol_count': sum(1 for p in plan if p['_fill_symbol']),
        'fill_date_count': sum(1 for p in plan if p['_fill_date']),
        'unchanged_count': sum(1 for p in plan if not (p['_fill_symbol'] or p['_fill_date'])),
        'symbol': new_symbol,
        'trade_date': _iso(new_date),
        'candidate_positions': cands,
        'changes': [_public_change(p) for p in plan],
        'warnings': _enrichment_warnings(plan, cands, new_symbol),
    }


def enrich_transactions(
    db: Session,
    family_id: int,
    transaction_ids,
    symbol=None,
    trade_date=None,
    reason=None,
    operator=None,
    confirm=False,
) -> dict:
    """补全一批悬空流水的空字段（POST /enrich/ 的数据源）。

    硬约束见模块 docstring：confirm 二次确认、只补空值、目标仍悬空、
    校验全在写之前、审计日志 before/after 逐条记录、可凭 log_id 撤销。
    ``updated==0`` 也整体拒绝，避免产生「什么都没改」的假成功日志。
    """
    _require_confirm(confirm)
    ids = _normalize_ids(transaction_ids)
    new_symbol = _normalize_symbol(symbol)
    new_date = _normalize_trade_date(trade_date)
    _require_field(new_symbol, new_date)
    txns = _load_dangling_by_ids(db, family_id, ids)
    plan = _plan_enrichment(txns, new_symbol, new_date)
    to_change = [p for p in plan if p['_fill_symbol'] or p['_fill_date']]
    if not to_change:
        raise ValueError('没有需要补全的字段：这些流水均已填写 symbol 与 trade_date（updated=0）')

    # —— 校验全部通过，以下才开始写 ——
    by_id = {t.id: t for t in txns}
    before = []
    after = []
    for item in to_change:
        t = by_id[item['id']]
        before.append({'id': t.id, 'symbol': t.symbol, 'trade_date': _iso(t.trade_date)})
        if item['_fill_symbol']:
            t.symbol = new_symbol
        if item['_fill_date']:
            t.trade_date = new_date
        after.append({'id': t.id, 'symbol': t.symbol, 'trade_date': _iso(t.trade_date)})
    db.flush()

    log = AdjustmentLog(
        family_id=family_id,
        action=ACTION_ENRICH,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=reason,
        operator=operator,
    )
    db.add(log)
    db.flush()
    return {
        'log_id': log.id,
        'updated': len(to_change),
        'skipped': len(plan) - len(to_change),
        'symbol': new_symbol,
        'trade_date': _iso(new_date),
    }


def _full_snapshot(t: Transaction) -> dict:
    """完整行快照：所有 ORM 列，日期转 isoformat 字符串，键用属性名。"""
    out = {}
    for key, _col in _column_attrs():
        out[key] = _iso(getattr(t, key))
    return out


def _restore_payload(row: dict) -> dict:
    """快照 → 可喂给 ``Transaction(**payload)`` 的字典。

    排除 ``symbol_norm``（派生列，由 mapper before_insert 重算）；
    日期字符串按列类型 parse 回 datetime / date。
    """
    out = {}
    for key, col in _column_attrs():
        if key == 'symbol_norm':
            continue
        value = row.get(key)
        if isinstance(value, str):
            if isinstance(col.type, Date) and not isinstance(col.type, DateTime):
                value = date.fromisoformat(value)
            elif isinstance(col.type, DateTime):
                value = datetime.fromisoformat(value)
        out[key] = value
    return out


def _delete_preview_row(t: Transaction) -> dict:
    """删除预览用精简行：只放用户能读懂的字段，单位已换算。"""
    return {
        'id': t.id,
        'txn_type': t.txn_type,
        'trade_date': _iso(t.trade_date),
        'symbol': t.symbol,
        'quantity': _shares(t.quantity),
        'amount': Money.cents_to_yuan(t.amount),
        'position_id': t.position_id,
        'realized_pnl': Money.cents_to_yuan(t.realized_pnl),
        'is_income': t.is_income,
    }


def _delete_warnings() -> list[str]:
    """删除的三层风险如实告知，前端另有一句静态硬文案。"""
    return [
        '删除会影响已实现盈亏与收益统计：这些流水虽不进现存持仓份额，但仍是历史交易记录。',
        '现存持仓份额不会改变：这些流水的 position_id 指向已删除的持仓行，不参与现存持仓的重算。',
        '删除前会保存每一行的完整快照到审计日志，可凭日志编号撤销；若期间新增流水占用了原编号，该行会跳过恢复。',
        '不改 import_hash / source / 金额 / 份额等其它列，撤销按快照原样恢复。',
    ]


def preview_delete(db: Session, family_id: int, transaction_ids) -> dict:
    """删除前预览（GET /delete-preview/ 的数据源，**纯只读，绝不写库**）。"""
    ids = _normalize_ids(transaction_ids)
    txns = _load_dangling_by_ids(db, family_id, ids)
    return {
        'txn_count': len(txns),
        'transactions': [_delete_preview_row(t) for t in txns],
        'snapshot_columns': len(_column_attrs()),
        'total_amount': sum(Money.cents_to_yuan(t.amount) for t in txns),
        'warnings': _delete_warnings(),
    }


def delete_transactions(
    db: Session,
    family_id: int,
    transaction_ids,
    reason=None,
    operator=None,
    confirm=False,
    confirm_phrase=None,
) -> dict:
    """物理删除一批悬空流水（POST /delete/ 的数据源）。

    后端硬校验 ``confirm is True`` 且 ``confirm_phrase == '删除'``，前端的
    二次确认只是第一道门。删除前把**完整行快照**写进 ``before_json``，
    ``after_json`` 记 deleted_ids；撤销端点据此逐行恢复。
    """
    _require_confirm(confirm)
    if confirm_phrase != DELETE_CONFIRM_PHRASE:
        raise ValueError(f'confirm_phrase 必须严格等于「{DELETE_CONFIRM_PHRASE}」二字，才能二次确认删除')
    ids = _normalize_ids(transaction_ids)
    txns = _load_dangling_by_ids(db, family_id, ids)

    # —— 校验全部通过，以下才开始写 ——
    before = [_full_snapshot(t) for t in txns]
    total_amount = sum(Money.cents_to_yuan(t.amount) for t in txns)
    for t in txns:
        db.delete(t)
    db.flush()

    log = AdjustmentLog(
        family_id=family_id,
        action=ACTION_DELETE,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps({'deleted_ids': ids, 'count': len(ids)}, ensure_ascii=False),
        reason=reason,
        operator=operator,
    )
    db.add(log)
    db.flush()
    return {
        'log_id': log.id,
        'deleted': len(ids),
        'total_amount': total_amount,
        'confirm_phrase': DELETE_CONFIRM_PHRASE,
    }


def _load_log(db: Session, family_id: int, log_id, action: str) -> AdjustmentLog:
    """按 (id, family, action) 取审计日志；非本类日志一律拒绝。"""
    if isinstance(log_id, bool) or not isinstance(log_id, int):
        raise ValueError('log_id 必须是整数')
    log = (
        db.query(AdjustmentLog)
        .filter(
            AdjustmentLog.id == log_id,
            AdjustmentLog.family_id == family_id,
            AdjustmentLog.action == action,
        )
        .first()
    )
    if log is None:
        raise ValueError(f'撤销记录不存在或无权访问（仅能撤销 {action} 日志）')
    return log


def _parse_rows(raw, label: str) -> list:
    """审计 JSON → 逐条列表；兼容裸列表与 {'transactions': [...]} 包装。"""
    try:
        data = json.loads(raw or '[]')
    except (TypeError, ValueError) as e:
        raise ValueError(f'撤销记录 {label} JSON 损坏，无法解析：{e}') from e
    if isinstance(data, dict):
        data = data.get('transactions', data.get('rows', []))
    if not isinstance(data, list):
        raise ValueError(f'撤销记录 {label} 结构异常，无法解析')
    return data


def _write_undo_log(db: Session, family_id: int, action: str, ref_log_id, restored, skipped, operator) -> None:
    """每次撤销都留痕（幂等撤销 restored=0 也要记录这次操作）。"""
    db.add(
        AdjustmentLog(
            family_id=family_id,
            action=action,
            before_json=json.dumps({'ref_log_id': ref_log_id}, ensure_ascii=False),
            after_json=json.dumps({'restored': restored, 'skipped': skipped}, ensure_ascii=False),
            reason=f'撤销日志 {ref_log_id}',
            operator=operator,
        )
    )
    db.flush()


def undo_enrichment(db: Session, family_id: int, log_id) -> dict:
    """撤销一次补全（POST /enrich-undo/ 的数据源）。

    仅当流水当前 symbol / trade_date **仍等于 after 值**才恢复（用户后来手工改过
    就跳过，不覆盖）。幂等：重复撤销 restored=0，但每次追加留痕日志。
    ``symbol_norm`` 交给 mapper 事件按恢复后的 symbol / asset_type 重算。
    """
    log = _load_log(db, family_id, log_id, ACTION_ENRICH)
    before = _parse_rows(log.before_json, 'before_json')
    after = _parse_rows(log.after_json, 'after_json')
    after_map = {e.get('id'): e for e in after if isinstance(e, dict)}
    restored = 0
    skipped = 0
    for entry in before:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        tid = entry.get('id')
        expected = after_map.get(tid)
        txn = db.query(Transaction).filter(Transaction.id == tid, Transaction.family_id == family_id).first()
        if txn is None or expected is None:
            skipped += 1
            continue
        same_symbol = (txn.symbol or None) == (expected.get('symbol') or None)
        same_date = _iso(txn.trade_date) == expected.get('trade_date')
        if not (same_symbol and same_date):
            skipped += 1
            continue
        txn.symbol = entry.get('symbol')
        txn.trade_date = _parse_dt(entry.get('trade_date'))
        restored += 1
    db.flush()
    _write_undo_log(db, family_id, ACTION_ENRICH_UNDO, log_id, restored, skipped, log.operator)
    return {'restored': restored, 'skipped': skipped, 'log_id': log_id}


def undo_delete(db: Session, family_id: int, log_id) -> dict:
    """撤销一次删除（POST /delete-undo/ 的数据源）。

    按完整行快照逐条恢复（含原 id / created_at / updated_at）；若该 id 已被新流水
    占用则跳过，绝不覆盖新数据。幂等：全部已存在时 restored=0，仍追加留痕。
    """
    log = _load_log(db, family_id, log_id, ACTION_DELETE)
    rows = _parse_rows(log.before_json, 'before_json')
    restored = 0
    skipped = 0
    for row in rows:
        if not isinstance(row, dict) or row.get('id') is None:
            skipped += 1
            continue
        tid = row['id']
        exists = db.query(Transaction).filter(Transaction.id == tid).first()
        if exists is not None:
            skipped += 1
            continue
        db.add(Transaction(**_restore_payload(row)))
        restored += 1
    db.flush()
    _write_undo_log(db, family_id, ACTION_DELETE_UNDO, log_id, restored, skipped, log.operator)
    return {'restored': restored, 'skipped': skipped, 'log_id': log_id}
