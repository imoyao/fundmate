# -*- coding: utf-8 -*-
"""悬空流水「按流水重建持仓」（域 F 的第三条写路径）。

## 为什么需要这一刀

旧版「整笔卖出清仓」走 ``db.delete(position)``（见 ``core/migrations.py`` 与
``position_recompute`` 模块 docstring），持仓行被物理删除，而流水不级联。于是真库里
存在这样一类数据：买入流水还在、``position_id`` 指向一个不存在的行、账上份额 0。

用户拿它补录卖出会撞死在 ``reconciliation_service._resolve_sell_position_id``
（「找不到这笔持仓」）；补录买入又会把同一段历史再记一次。域 F 的既有两条路都救不了它：

- 「回补关联」（``dangling_ref_service.reattach_transactions``）只认**现存**候选持仓，
  ``_group_block_reason`` 对无候选的组直接判 ``fixable=False``；
- 「补全信息 / 显式删除」（``dangling_ref_remediation_service``）只改 symbol /
  trade_date，或把整行删掉，都不建持仓。

本模块补上第三条：**以流水为真相源**重建缺失的持仓行，并把这一组流水挂回去。建完
之后补录卖出 / 再次对账都能正常走。

## 为什么不是「自动重建」

存量 637 条悬空流水（#2866 实测）里，同一标的分属不同批次、不同账本的情况都存在，且
一组流水**未必是该标的的全部历史**（早期导入只留了卖出腿、或部分买入已挂在别的行上）。
自动重建会静默造出一个份额偏小的持仓，进而污染市值与收益。故本模块只提供
**用户显式指定 + 预览 + 二次确认**的写路径，``confirm`` 不是字符串「true」而是严格的
``True``（与既有两条写路径同一口径）。

## 口径（与 ``position_recompute`` 单一真相源对齐）

份额与成本**不在这里自己算**：复用 ``domains.positions.state.derive_state_from_txns``
（锚点为 0 的全量流水口径）与 ``position_recompute.rebuild_position_from_txns``。
两份实现必然分叉，这正是历史上「份额重复累加」的成因，不再制造第二份。

已知边界（如实标注，不粉饰）：

- ``Transaction`` 不携带 ``market`` / ``currency``，重建行取默认值（``CN_A`` / ``CNY``）；
- 重建行的 ``source`` 是模型默认值（``manual``）：流水里没有「这条持仓从哪来」的信息，
  来源以审计日志为准，不去猜 ``PositionSource`` 的枚举值；
- 净额 ≤ 0 的组**拒绝重建**：买卖已对冲、没有有效持仓可建，硬建只会得到一行 0 份额的
  空壳。这类组应走「回补关联」或「删除」。

## 事务边界

与同域其它服务同构：调用方传入 ``db``，只 ``flush()`` 不 ``commit()``；
``ValueError`` 由视图转 400，请求 teardown 时 rollback。所有校验排在写操作之前，
拒绝分支不得留下 ``db.new / db.dirty / db.deleted``，也不写审计日志。
"""

import json

from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.positions.state import derive_state_from_txns
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.dates import order_by_effective_day
from app.domains.transactions.models import Transaction
from app.services.dangling_ref_remediation_service import _load_log, _require_confirm
from app.services.dangling_ref_service import (
    _dangling_condition,
    _load_dangling_by_ids,
    _normalize_ids,
    scan_dangling_refs,
)
from app.services.position_recompute import rebuild_position_from_txns
from app.services.position_write_support import _find_existing_position

ACTION_REBUILD = 'dangling_ref_rebuild'
ACTION_REBUILD_UNDO = 'dangling_ref_rebuild_undo'

#: 净额必须严格大于 0：0 份额的空壳行既没有市值也无法再补卖出，建了只是换一种脏数据。
MIN_NET_MIN_UNITS = 1


def _block(plan: dict, reason: str) -> dict:
    """把不可重建的原因写进 plan（``rebuildable=False`` + 一句可执行的 ``block_reason``）。"""
    plan['rebuildable'] = False
    plan['block_reason'] = reason
    return plan


def _resolve_symbol_and_name(txns: list[Transaction]) -> tuple[str | None, str | None]:
    """组内标的代码与名称。名称优先流水快照（``position_name``），与前端展示同源。"""
    symbols = {t.symbol.strip() for t in txns if t.symbol and t.symbol.strip()}
    symbol = next(iter(symbols)) if len(symbols) == 1 else None
    name = next((t.position_name for t in txns if t.position_name), None)
    return symbol, name


def _identity_block(ordered: list[Transaction], symbol: str | None, ledger_id, asset_types: set) -> str | None:
    """身份类拒绝原因（标的 / 账本 / 资产类型）——这几条决定「要建的是哪一个持仓」。"""
    if any(not (t.symbol or '').strip() for t in ordered):
        return '这批流水里有的没填标的代码，无法确定要重建哪个持仓；先在「补全信息」里补上代码'
    if symbol is None:
        symbols = '、'.join(sorted({t.symbol or '' for t in ordered}))
        return f'这批流水含多个标的（{symbols}），不能合并成一个持仓'
    if ledger_id is None:
        return '这批流水跨多个账本或没有账本，无法确定持仓归属；先归置账本再重建'
    if len(asset_types) > 1:
        return f'组内资产类型不一致（{"、".join(sorted(asset_types))}），无法确定持仓类型'
    return None


def _cost_block(db: Session, family_id: int, ordered: list[Transaction], plan: dict, symbol: str) -> str | None:
    """成本类拒绝原因：缺成交价派生不出成本；已有同标的持仓行应走「回补关联」而不是重建。"""
    if any(t.price is None or t.quantity is None for t in ordered if t.txn_type in ('buy', 'deposit')):
        return '组内有买入流水缺成交价或份额，派生不出成本，重建会得到 0 成本持仓'
    existing = _find_existing_position(db, plan['ledger_id'], family_id, symbol, '')
    if existing is not None:
        return f'同账本已有「{existing.name or symbol}」的持仓行（#{existing.id}），请用「回补关联」而不是重建'
    return None


def plan_rebuild(db: Session, family_id: int, transaction_ids) -> dict:
    """纯只读：算出「重建会得到什么」，并给出不可重建的可执行原因。

    ``txns`` 放在返回值的内部键里供写入复用；对外序列化时由 ``public_plan`` 剥掉。
    所有判断都在写之前的这一次扫描里完成，写路径直接复用同一份 plan——
    预览与真正写入不可能给出两套结论。
    """
    ids = _normalize_ids(transaction_ids)
    loaded = _load_dangling_by_ids(db, family_id, ids)
    # 按生效日升序：重建行的 confirm_date / account_name 取**最早**那条（组内一致，取谁都不影响，
    # 但按日期排序后「最早」是确定的，不依赖调用方传参顺序）。
    ordered = order_by_effective_day(
        db.query(Transaction).filter(Transaction.id.in_([t.id for t in loaded])), descending=False
    ).all()
    ledger_ids = {t.ledger_id for t in ordered}
    asset_types = {t.asset_type for t in ordered if t.asset_type}
    symbol, display_name = _resolve_symbol_and_name(ordered)
    first, last = ordered[0], ordered[-1]
    plan = {
        'txns': ordered,
        'txn_count': len(ordered),
        'symbol': symbol,
        'display_name': display_name,
        'ledger_id': next(iter(ledger_ids)) if len(ledger_ids) == 1 else None,
        'asset_type': next(iter(asset_types)) if len(asset_types) == 1 else None,
        'first_date': (first.trade_date or first.confirm_date).isoformat()
        if (first.trade_date or first.confirm_date)
        else None,
        'last_date': (last.trade_date or last.confirm_date).isoformat()
        if (last.trade_date or last.confirm_date)
        else None,
        'net_min_units': 0,
        'avg_price_units': 0,
        'rebuildable': True,
        'block_reason': None,
        'warnings': [],
    }

    reason = _identity_block(ordered, symbol, plan['ledger_id'], asset_types)
    if reason is None:
        reason = _cost_block(db, family_id, ordered, plan, symbol or '')
    if reason is not None:
        return _block(plan, reason)

    net_qty, avg_price_units = derive_state_from_txns(ordered, 0, 0)
    plan['net_min_units'] = net_qty
    plan['avg_price_units'] = avg_price_units
    if net_qty < MIN_NET_MIN_UNITS:
        return _block(plan, '这批流水买卖已对冲（净额 ≤ 0），重建不出有效持仓；如这些流水是历史残留，走「删除」')
    plan['warnings'] = _rebuild_warnings(ordered)
    gap = _sibling_gap_warning(db, family_id, ordered, plan['symbol'] or '', plan['ledger_id'])
    if gap is not None:
        plan['warnings'].append(gap)
    return plan


def _sibling_gap_warning(db: Session, family_id: int, ordered: list[Transaction], symbol: str, ledger_id) -> str | None:
    """同账本同标的还有**没选进来**的悬空流水 → 重建出的份额会偏小，必须点出来。

    这是本动作最大的真实风险（不是「重建会算错」，而是「只用了一部分流水去算」）。
    检测得到就告知；检测不到也不算保证——用户仍要对照券商账单核对日期区间。
    """
    sibling_ids = {
        row.id
        for row in db.query(Transaction.id).filter(
            _dangling_condition(family_id),
            Transaction.ledger_id == ledger_id,
            Transaction.symbol == symbol,
        )
    }
    extra = sibling_ids - {t.id for t in ordered}
    if not extra:
        return None
    return f'同一账本同一标的还有 {len(extra)} 条流水没有选进来；只用选中的这批重建，份额会偏小。'


def _rebuild_warnings(txns: list[Transaction]) -> list[str]:
    """如实说明重建的口径与已知边界，不粉饰「重建 ≠ 还原历史」。"""
    warnings = [
        '份额与成本按这组流水派生：买入份额与成本加权、卖出份额扣减。'
        '若这组流水不是该标的的全部历史（例如早期只导入了卖出腿），重建出的份额会偏小，请对照券商账单核对。',
        '成交场所与币种取默认值（CN_A / CNY）：流水里没有这两个字段，这一层信息无法还原。',
        '重建后这几条流水的归属会指向新持仓，可在结果里凭日志编号撤销。',
    ]
    if not any(t.txn_type in ('buy', 'deposit') for t in txns):
        warnings.append('组内没有买入流水，成本均价会是 0，市值与收益将偏小，需在持仓页手工补成本。')
    return warnings


def public_plan(plan: dict) -> dict:
    """剥掉内部键（``txns``）并把份额 / 价格换成用户单位，得到前端契约。"""
    return {
        'txn_count': plan['txn_count'],
        'symbol': plan['symbol'],
        'display_name': plan['display_name'],
        'ledger_id': plan['ledger_id'],
        'asset_type': plan['asset_type'],
        'first_date': plan['first_date'],
        'last_date': plan['last_date'],
        'net_units': round(Money.min_unit_to_shares(plan['net_min_units']), 4),
        'avg_price': round(Money.price_units_to_yuan(plan['avg_price_units']), 4),
        'rebuildable': plan['rebuildable'],
        'block_reason': plan['block_reason'],
        'warnings': plan['warnings'],
    }


def preview_rebuild(db: Session, family_id: int, transaction_ids) -> dict:
    """重建前预览（GET /rebuild-preview/ 的数据源，**纯只读，绝不写库**）。"""
    plan = plan_rebuild(db, family_id, transaction_ids)
    data = public_plan(plan)
    ledger_id = plan['ledger_id']
    ledger = (
        db.query(Ledger).filter(Ledger.id == ledger_id, Ledger.family_id == family_id).first() if ledger_id else None
    )
    data['ledger_name'] = ledger.name if ledger else None
    return data


def rebuild_position(
    db: Session,
    family_id: int,
    transaction_ids,
    reason=None,
    operator=None,
    confirm=False,
) -> dict:
    """按流水重建持仓并把这一组流水挂回去（POST /rebuild/ 的数据源）。

    写之前必须过 ``confirm is True``（后端硬校验，不信任前端）。审计日志两侧都记：
    ``before_json`` 存每条流水原来的 ``position_id``（撤销据此还原成「悬空」），
    ``after_json`` 存新持仓 id、份额、成本与流水集合（撤销据此判断「期间有没有被改过」）。
    """
    _require_confirm(confirm)
    plan = plan_rebuild(db, family_id, transaction_ids)
    if not plan['rebuildable']:
        raise ValueError(plan['block_reason'] or '这批流水当前不能重建持仓')

    # —— 校验全部通过，以下才开始写 ——
    txns = plan['txns']
    before = {'txn_position_ids': {str(t.id): t.position_id for t in txns}}
    position = rebuild_position_from_txns(db, txns, plan['net_min_units'], plan['avg_price_units'])
    after = {
        'position_id': position.id,
        'symbol': position.symbol,
        'quantity': position.quantity,
        'avg_price': position.avg_price,
        'txn_ids': [t.id for t in txns],
    }
    log = AdjustmentLog(
        family_id=family_id,
        action=ACTION_REBUILD,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=reason,
        operator=operator,
    )
    db.add(log)
    db.flush()
    return {
        'log_id': log.id,
        'position_id': position.id,
        'symbol': position.symbol,
        'display_name': position.name,
        'quantity': round(Money.min_unit_to_shares(position.quantity), 4),
        'avg_price': round(Money.price_units_to_yuan(position.avg_price), 4),
        'txn_count': len(txns),
    }


def _undo_skip_reason(db: Session, family_id: int, after: dict) -> str | None:
    """撤销前的「期间有没有被改过」判据；返回 None 表示可以撤销。

    只有**原样未动**才允许撤销：持仓份额 / 成本被改过（例如用户已经补了卖出）、
    或流水的归属又变了，都说明这一行已经承载了新的业务事实，回滚会连带抹掉它们。
    """
    position = db.query(Position).filter(Position.id == after.get('position_id')).first()
    if position is None or position.family_id != family_id:
        return '重建出来的持仓已不存在'
    if position.quantity != after.get('quantity') or position.avg_price != after.get('avg_price'):
        return '持仓份额或成本已被改动（例如已补录卖出），撤销会抹掉后来的业务事实'
    current = {t.id for t in db.query(Transaction.id).filter(Transaction.position_id == position.id).all()}
    if current != set(after.get('txn_ids') or []):
        return '挂在这条持仓上的流水已变化，撤销会误伤后来的流水'
    return None


def undo_rebuild(db: Session, family_id: int, log_id) -> dict:
    """撤销一次重建：流水回到原来的悬空状态、新持仓删掉（POST /rebuild-undo/）。

    幂等：重复撤销时目标持仓已不存在，``restored=0`` 且追加留痕日志，数据不变。
    """
    log = _load_log(db, family_id, log_id, ACTION_REBUILD)
    after = json.loads(log.after_json or '{}')
    before = json.loads(log.before_json or '{}')
    skipped_reason = _undo_skip_reason(db, family_id, after)
    if skipped_reason is not None:
        _write_undo_log(db, family_id, log_id, log.operator, restored=0, skipped=1, reason=skipped_reason)
        return {'restored': 0, 'skipped': 1, 'log_id': log_id, 'skip_reason': skipped_reason}

    position_id = after['position_id']
    old_ids = before.get('txn_position_ids') or {}
    restored = 0
    for t in db.query(Transaction).filter(Transaction.position_id == position_id).all():
        t.position_id = old_ids.get(str(t.id))
        restored += 1
    position = db.query(Position).filter(Position.id == position_id).first()
    db.delete(position)
    db.flush()
    _write_undo_log(db, family_id, log_id, log.operator, restored=restored, skipped=0)
    return {'restored': restored, 'skipped': 0, 'log_id': log_id, 'skip_reason': None}


def _write_undo_log(db: Session, family_id: int, ref_log_id, operator, *, restored: int, skipped: int, reason=None):
    """每次撤销都留痕（包括 skipped 的那次）：审计要能解释「为什么没撤销成功」。"""
    db.add(
        AdjustmentLog(
            family_id=family_id,
            action=ACTION_REBUILD_UNDO,
            before_json=json.dumps({'ref_log_id': ref_log_id}, ensure_ascii=False),
            after_json=json.dumps(
                {'restored': restored, 'skipped': skipped, 'skip_reason': reason}, ensure_ascii=False
            ),
            reason=reason or f'撤销重建日志 {ref_log_id}',
            operator=operator,
        )
    )
    db.flush()


# ── 批量重建（一次请求内逐组 plan → 写） ────────────────────────────────────
#
# 为什么不是前端循环：真库 rebuild 阶段实测 90 组（2026-11-14），逐组「预览 + 写入」
# = 180 次往返，而组与组之间用户没有任何决策点。批量把往返压成 2 次（预览一次、
# 写入一次），但**没有**降低校验强度——写入侧仍逐组重新 plan，业务上不可重建的组
# 只跳过并报出原因，不静默、也不硬建。
#
# 风险口径与单组一致（见模块 docstring「为什么不是自动重建」）：批量不改变「以流水为
# 真相源」这件事，只是把用户点 90 次变成点 1 次。预览必须先把每组将建出的份额摊开，
# 用户仍要对照账单确认日期区间——这一步没有被批量省掉。

#: 一次批量最多几组 / 几条流水。上限只挡「误点清库」，不是性能调优：
#: 真库全量 rebuild 是 90 组，留一倍余量。
MAX_BATCH_GROUPS = 200
MAX_BATCH_TXN_IDS = 2000


def _normalize_groups(groups) -> list[list[int]]:
    """校验批量重建的组列表：非空、组数 ≤200、id 总数 ≤2000，单组沿用既有 500 条上限。"""
    if not isinstance(groups, (list, tuple)) or len(groups) == 0:
        raise ValueError('没有选中要重建的组')
    if len(groups) > MAX_BATCH_GROUPS:
        raise ValueError(f'一次最多重建 {MAX_BATCH_GROUPS} 组')
    normalized: list[list[int]] = []
    total = 0
    for raw in groups:
        ids = _normalize_ids(raw)
        total += len(ids)
        if total > MAX_BATCH_TXN_IDS:
            raise ValueError(f'一次最多处理 {MAX_BATCH_TXN_IDS} 条流水')
        normalized.append(ids)
    return normalized


def _ledger_names(db: Session, family_id: int, ledger_ids) -> dict:
    """一次查全部账本名：预览要逐组显示「建到哪个账本」，逐组查会变成 N+1。"""
    wanted = {lid for lid in ledger_ids if lid}
    if not wanted:
        return {}
    rows = db.query(Ledger.id, Ledger.name).filter(Ledger.family_id == family_id, Ledger.id.in_(wanted)).all()
    return {ledger_id: name for ledger_id, name in rows}


def _group_symbol(db: Session, family_id: int, ids: list[int]) -> str | None:
    """组内标的代码（给「被跳过」的组一个能认出来的名字）。取不到唯一值就返回 None。"""
    rows = db.query(Transaction.symbol).filter(Transaction.id.in_(ids), Transaction.family_id == family_id).all()
    symbols = {symbol.strip() for (symbol,) in rows if symbol and symbol.strip()}
    return next(iter(symbols)) if len(symbols) == 1 else None


def _blocked_preview(group: dict, ids: list[int], reason: str) -> dict:
    """plan 都取不到的组（例如流水刚被别处处理掉）在预览里如实标成不可重建，不吞掉整次预览。"""
    return {
        'txn_count': len(ids),
        'symbol': group.get('symbol'),
        'display_name': group.get('display_name'),
        'ledger_id': group.get('ledger_id'),
        'asset_type': None,
        'first_date': None,
        'last_date': None,
        'net_units': 0.0,
        'avg_price': 0.0,
        'rebuildable': False,
        'block_reason': reason,
        'warnings': [],
    }


def preview_rebuild_batch(db: Session, family_id: int) -> dict:
    """批量重建预览（GET /rebuild-batch-preview/，**纯只读**）。

    分组口径与 `/dangling-refs/` 同源（复用 ``scan_dangling_refs``），逐组跑同一份
    ``plan_rebuild``——预览与写入不可能给出两套结论。不可重建的组照常返回并带
    ``block_reason``，由前端摊开给用户看，而不是在服务端悄悄筛掉。
    """
    scan = scan_dangling_refs(db, family_id)
    ledger_names = _ledger_names(db, family_id, [g.get('ledger_id') for g in scan['groups']])
    groups = []
    for group in scan['groups']:
        ids = [t['id'] for t in group['transactions']]
        try:
            plan = public_plan(plan_rebuild(db, family_id, ids))
        except ValueError as e:
            plan = _blocked_preview(group, ids, str(e))
        plan['transaction_ids'] = ids
        plan['ledger_name'] = ledger_names.get(group.get('ledger_id'))
        groups.append(plan)
    rebuildable = [g for g in groups if g['rebuildable']]
    return {
        'group_count': len(groups),
        'rebuildable_count': len(rebuildable),
        'blocked_count': len(groups) - len(rebuildable),
        # 流水合计只算可重建的组：用户看到的「M 条流水」必须与「将重建 N 组」同一范围
        'txn_count': sum(g['txn_count'] for g in rebuildable),
        'groups': groups,
    }


def rebuild_batch(db: Session, family_id: int, groups, reason=None, operator=None, confirm=False) -> dict:
    """批量重建（POST /rebuild-batch/ 的数据源）：逐组 plan → 写。

    **部分成功是设计的一部分**：业务上不可重建的组（已有同标的持仓 / 净额 ≤ 0 /
    流水已不是悬空状态）记进 ``skipped`` 并给后端原话原因，其余组照常建成——
    否则一组脏数据就会卡住整批，用户只能回头逐组试。

    **意外异常不是**：除 ``ValueError`` 外的异常直接上抛，由视图的 ``user_session()``
    整批回滚，不会留下「建了一半的持仓 + 半批审计日志」这种谁都说不清的状态。
    """
    _require_confirm(confirm)
    normalized = _normalize_groups(groups)
    rebuilt: list[dict] = []
    skipped: list[dict] = []
    log_ids: list[int] = []
    for ids in normalized:
        try:
            # 逐组重新 plan：预览之后数据可能变了，这里不信任前端传回来的结论
            result = rebuild_position(db, family_id, ids, reason=reason, operator=operator, confirm=True)
        except ValueError as e:
            skipped.append({'transaction_ids': ids, 'symbol': _group_symbol(db, family_id, ids), 'reason': str(e)})
            continue
        rebuilt.append({**result, 'transaction_ids': ids})
        log_ids.append(result['log_id'])
    return {'rebuilt': rebuilt, 'skipped': skipped, 'log_ids': log_ids}


def undo_rebuild_batch(db: Session, family_id: int, log_ids) -> dict:
    """批量撤销重建（POST /rebuild-batch-undo/）：逐条 ``undo_rebuild``，互不牵连。

    单条撤销失败（日志不属于本家庭 / 持仓已被改动 / 日志类型不对）只记进 ``results``，
    不中断其余——撤销是「把能退的退掉」，不是全或无。重复撤销幂等
    （``restored=0, skipped=1`` 并留痕），与单组撤销同一口径。
    """
    ids = _normalize_ids(log_ids)
    results: list[dict] = []
    restored = 0
    skipped = 0
    for log_id in ids:
        try:
            result = undo_rebuild(db, family_id, log_id)
        except ValueError as e:
            result = {'restored': 0, 'skipped': 1, 'log_id': log_id, 'skip_reason': str(e)}
        results.append(result)
        restored += result['restored']
        skipped += result['skipped']
    return {'results': results, 'restored': restored, 'skipped': skipped}
