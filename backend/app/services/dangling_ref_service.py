# -*- coding: utf-8 -*-
"""悬空 position_id 引用（dangling ref）的只读暴露 / 显式挂回 / 可撤销（#2866 后端）。

## 背景（已实证，勿再推断）

``transactions.position_id`` 是裸 ``Column(Integer)``、无外键。历史「清仓删行」留下了
指向已删除 positions 行的流水（真库实测 637 条）。自动修复不安全：
``recompute_position_from_transactions`` 按 ``Transaction.position_id == position_id``
选流水派生份额，把流水挂回现存持仓可能把份额从 9000 改成 48300。因此本模块只做三件事：

1. **只读暴露**：把悬空流水按 (ledger, symbol) 分组、给出净额 / 候选持仓 / 风险 flags；
2. **用户显式指定目标持仓才写**：``reattach_transactions`` 默认只 UPDATE
   ``transactions.position_id``，绝不自动重算份额；
3. **可撤销**：每次挂回写 ``adjustment_logs``，``undo_reattach`` 按 before 值恢复。

## 事务边界（重要）

所有函数都接收调用方传入的 ``db: Session``，**不自己开会话、不 import Flask**：
视图层用 ``with user_session() as db:`` 提供「一个请求一个事务」，服务层只 ``flush()``
不 ``commit()``；服务层抛 ``ValueError`` 由视图转 ``abort(400)``，请求 teardown 收到
异常会 rollback，保证「整体 400、不写任何东西」。测试则直接把 ``db`` fixture 传进来，
天然落在同一事务里。校验分支一律排在写操作之前，即使没有 rollback 兜底也不会留下脏写。

## 口径与已知限制（如实标注，不许粉饰）

- **检出**：主查询 ``Transaction.family_id == family_id``；``position_id IS NOT NULL``；
  ``NOT EXISTS (SELECT ... FROM positions p WHERE p.id = transactions.position_id
  AND p.family_id = :family_id)`` 相关子查询。子查询**同时按主键与 family 匹配**：
  指向别家现存持仓的 position_id 对本家庭同样是悬空引用，按「正常」放过会漏报，
  且违反多家庭隔离。``Position.id`` 全局唯一，加 family 不会改变正常行的判定。
- **单位（对外统一换算，前端不许再换一次）**：库内 ``quantity`` /
  ``position.quantity`` 的最小单位 = 1/10000 份，``amount`` = 分。返回给前端的
  ``net_units``、``preview.quantity_*``、``groups[].transactions[].quantity``、
  ``live_position.quantity``、``candidates[].quantity``、``target_position.quantity``
  **一律是「份」**（已 /10000）；``transactions[].amount`` **一律是「元」**（分 /100）。
  内部计算仍用最小单位整数，只在序列化边界换算，避免浮点误差进入求和。
- **净额**：Σ(buy/deposit/split 的 quantity) − Σ(sell/withdraw 的 quantity)，再 /10000。
  其余 txn_type（分红/兑付/扣税等）不进净额；amount 不参与净额。
- **批次**：全部悬空流水按 created_at 排序，相邻间隔 **> 600 秒**切新批；``batch_label`` 取该批首条 created_at 的 ``YYYY-MM-DD HH:MM``。created_at 为空的流水
  不参与间隔判定、附到当前批（排序时排最前），label 降级为 '未知时间'。
- **候选与可否回补（判据只在后端一处）**：``candidates`` 只列「同账本且同标的」的
  现存持仓（reattach 会硬校验 symbol 一致，列别的标的等于诱导挂错）；空 symbol 组
  没有任何合法候选。``fixable`` / ``block_reason`` / 全局 ``fixable_count`` 由此推出，
  前端只显示、不自行推导。真库实测（2026-11-05）：637 条里 105 条可直接回补，
  295 条缺 symbol、237 条无同标的持仓行 —— 后两类必须如实显示，不许假装全部可修。
- **flags**：``no_symbol``（symbol 空）、``has_candidate``（有同标的现存持仓）、
  ``net_mismatch``（净额与 live_position 份额差异 > 0.0001）、``cleared_target``
  （同标的现存行是 cleared）、``blocked``（fixable=False）。live_position 为空时
  net_mismatch 不置位；candidates 最多 20 条、按 id 升序，首条即 live_position。
- **preview 的 quantity_if_recomputed 是「预估」不是精确重算结果**：口径为
  「目标持仓现存份额 + 本批流水净额」的保守近似。真正的 ``recompute_position_from_transactions`` 是「从该持仓全部流水派生」，含快照锚点、
  清仓复活 / 标记 cleared / 删行等状态变化，二者可能不一致。preview 纯只读，
  **绝不调用真正的 recompute 来预览**。
- **自动重算已禁用**：``recompute=true`` 一律 ``ValueError``（HTTP 400）。真正的
  ``recompute_position_from_transactions`` 会从该持仓全部流水派生份额，含快照锚点、
  清仓复活 / 标记 cleared / 删空壳行等状态变化，份额变更不可逆且 undo 无法回滚，
  不属于「安全的二次回补」。挂回只改 ``position_id``，份额一字不动
  （``quantity_after == quantity_before``）；用户如需对齐份额，到持仓页手动重算。
  ``preview.quantity_if_recomputed`` 仅用于让用户看清「手动重算会怎样」，不触发任何写。
- **undo 幂等但每次留痕**：仅当 txn 当前 position_id 仍等于 after 值才恢复；重复撤销 ``restored=0``、数据不变，但仍会追加一条 ``dangling_ref_undo`` 审计日志（如实记录每次操作）。
"""

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction

#: 净额方向：进入持仓 / 离开持仓（口径由契约给定，与 audit_orphan_batches 的 BUY/SELL 略不同：
#: 这里把 deposit/split/withdraw 也纳入，且 sell/withdraw 直接减 quantity、不取 abs）。
_IN_TYPES = frozenset({'buy', 'deposit', 'split'})
_OUT_TYPES = frozenset({'sell', 'withdraw'})

#: 批次切分阈值（秒）：相邻 created_at 间隔 > 该值即切新批。
BATCH_GAP_SECONDS = 600

#: 单批挂回上限（原始条数，去重前判定）。
MAX_TRANSACTION_IDS = 500

#: 净额与现存份额的可容忍差异（份），超过即 net_mismatch。
NET_MISMATCH_TOLERANCE = 0.0001

#: 候选持仓最多返回条数。
MAX_CANDIDATES = 20


def _dangling_condition(family_id: int):
    """悬空检出条件（#2866 契约口径），返回可直接喂给 ``filter()`` 的表达式。

    ``Transaction.position_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM positions p
                       WHERE p.id = transactions.position_id
                         AND p.family_id = :family_id)
       AND transactions.family_id = :family_id``

    ``.correlate(Transaction.__table__)`` 把 transactions 从子查询 FROM 里排除、作为外层
    引用：否则 EXISTS 会退化成「全库任意一条流水匹配任意持仓」的非相关子查询，库里只要
    存在一条正常流水 NOT EXISTS 就恒假，检出彻底失效。相关子查询能在「有持仓行 / 无持仓行」
    两种情况下精确区分，是本模块正确性的命门（见测试的变异探针）。
    """
    live = exists(
        select(Position.id)
        .where(Position.id == Transaction.position_id, Position.family_id == family_id)
        .correlate(Transaction.__table__)
    )
    return and_(
        Transaction.family_id == family_id,
        Transaction.position_id.isnot(None),
        ~live,
    )


def _normalize_ids(raw) -> list[int]:
    """校验并归一化 transaction_ids：非空 int 列表、最多 500 条、去重保序。

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
    seen, uniq = set(), []
    for v in normalized:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _load_dangling_by_ids(db: Session, family_id: int, ids: list[int]) -> list[Transaction]:
    """按 id 取流水，并**再次用 EXISTS 校验**每条确实属于本 family 且确实悬空。

    这是硬约束 2 的落点：防止把已修好（position_id 已指向现存持仓）的 id 再挂一次。
    任一 id 不在检出集合里 → 整体抛 ValueError，不写任何东西。
    """
    rows = db.query(Transaction).filter(_dangling_condition(family_id), Transaction.id.in_(ids)).all()
    found = {t.id: t for t in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValueError(f'以下流水不属于当前家庭或并非悬空（可能已被修复/已挂回现存持仓）：{missing}')
    return [found[i] for i in ids]


def _load_target(db: Session, family_id: int, pid) -> Position:
    """目标持仓必须存在且属于同一 family（硬约束 3 的一半）。"""
    if isinstance(pid, bool) or not isinstance(pid, int):
        raise ValueError('target_position_id 必须是整数')
    pos = db.query(Position).filter(Position.id == pid, Position.family_id == family_id).first()
    if pos is None:
        raise ValueError(f'目标持仓 {pid} 不存在或不属于当前家庭')
    return pos


def _net_min_units(txns: list[Transaction]) -> int:
    """组内流水净额（最小单位，未 /10000）。amount 是分，绝不混用。"""
    net = 0
    for t in txns:
        q = t.quantity or 0
        txn_type = t.txn_type or ''
        if txn_type in _IN_TYPES:
            net += q
        elif txn_type in _OUT_TYPES:
            net -= q
    return net


def _shares(min_units) -> float:
    """最小单位 → 份（1 份 = 10000 最小单位），走 Money 遵守仓库金融精度纪律。"""
    return Money.min_unit_to_shares(min_units or 0)


def _cluster_batches(rows: list[Transaction]) -> list[list[Transaction]]:
    """按 created_at 聚簇：相邻间隔 > BATCH_GAP_SECONDS 切新批。

    rows 须已按 (created_at, id) 升序。created_at 为空的流水不参与间隔判定、附到当前批，
    不与前后带时间的流水强行合并（无时间就无法证明属于同一次写入，保守处理）。
    """
    batches: list[list[Transaction]] = []
    prev_ts = None
    for t in rows:
        ts = t.created_at
        if ts is None:
            if not batches:
                batches.append([t])
            else:
                batches[-1].append(t)
            continue
        if prev_ts is None or (ts - prev_ts).total_seconds() > BATCH_GAP_SECONDS:
            batches.append([t])
        else:
            batches[-1].append(t)
        prev_ts = ts
    return batches


def _pos_brief(p: Position) -> dict:
    """持仓摘要。quantity 换算成「份」，与 net_units / preview.quantity_* 同口径；name 直出，供组级 display_name 取名。"""
    return {
        'id': p.id,
        'symbol': p.symbol,
        'name': p.name,
        'quantity': _shares(p.quantity),
        'ownership_status': p.ownership_status,
    }


def _txn_brief(t: Transaction) -> dict:
    """流水明细。quantity 换算成「份」、amount 换算成「元」；日期 isoformat 或 None。

    前端直接显示这两个数并标「份 / 元」，不得再做一次 /10000 或 /100；position_name 直出流水快照的标的名。
    """
    return {
        'id': t.id,
        'txn_type': t.txn_type,
        'trade_date': t.trade_date.isoformat() if t.trade_date else None,
        'confirm_date': t.confirm_date.isoformat() if t.confirm_date else None,
        'symbol': t.symbol,
        'position_name': t.position_name,
        'quantity': _shares(t.quantity),
        'amount': Money.cents_to_yuan(t.amount),
        'position_id': t.position_id,
    }


def _assess_safety(txns: list[Transaction], target: Position):
    """预估挂回 + 重算的效果，并给出 safe / warnings（纯计算、不写库、不调真重算）。

    ``quantity_if_recomputed`` 是**保守预估**（现存份额 + 本批净额），不是
    ``recompute_position_from_transactions`` 的精确结果。safe=False 当 net_mismatch、
    symbol 不一致或 ledger 不一致，三者都会在 warnings 里写明原因。
    """
    quantity_before = _shares(target.quantity)
    net_units = _shares(_net_min_units(txns))
    quantity_if_recomputed = quantity_before + net_units
    delta = quantity_if_recomputed - quantity_before

    warnings = []
    safe = True
    if abs(net_units - quantity_before) > NET_MISMATCH_TOLERANCE:
        safe = False
        warnings.append(
            f'净额 {net_units} 份与目标持仓现存份额 {quantity_before} 份差异超过 {NET_MISMATCH_TOLERANCE}（net_mismatch）'
        )
    bad_symbol = [t.id for t in txns if (t.symbol or '') != (target.symbol or '')]
    if bad_symbol:
        safe = False
        warnings.append(f'流水 {bad_symbol} 的 symbol 与目标持仓 {target.symbol!r} 不一致')
    bad_ledger = [t.id for t in txns if t.ledger_id is None or t.ledger_id != target.ledger_id]
    if bad_ledger:
        safe = False
        warnings.append(f'流水 {bad_ledger} 的 ledger_id 与目标持仓 ledger_id={target.ledger_id} 不一致（或为空）')
    # 口径限制如实告知：本预览不触发真正的重算，给的数只是近似。
    warnings.append(
        'quantity_if_recomputed 是「目标持仓现存份额 + 本批流水净额」的保守预估，不是精确重算结果：'
        '真正的 recompute_position_from_transactions 会从该持仓全部流水（含快照锚点、清仓复活、删行）'
        '派生份额，二者可能不一致；本预览绝不触发该重算'
    )
    return safe, warnings, quantity_before, quantity_if_recomputed, delta


def _load_positions_by_ledger(db: Session, family_id: int) -> dict:
    """同 family 全部现存持仓一次查完、按 ledger 索引，避免每组回表。"""
    positions = db.query(Position).filter(Position.family_id == family_id).order_by(Position.id).all()
    by_ledger = defaultdict(list)
    for p in positions:
        by_ledger[p.ledger_id].append(p)
    return by_ledger


def _build_batches(rows: list[Transaction]) -> tuple[list[dict], dict, dict]:
    """按 created_at 聚簇成批次，同时给出 txn_id → 批次映射与批次标签表。

    rows 须已按 (created_at, id) 升序；聚簇规则见 ``_cluster_batches``。
    """
    batches = []
    txn_to_batch = {}
    for idx, batch in enumerate(_cluster_batches(rows), 1):
        for t in batch:
            txn_to_batch[t.id] = idx
        ledgers = sorted({t.ledger_id for t in batch if t.ledger_id is not None})
        symbols = {t.symbol for t in batch if t.symbol}
        first_ts = batch[0].created_at
        batches.append(
            {
                'id': idx,
                'label': first_ts.strftime('%Y-%m-%d %H:%M') if first_ts else '未知时间',
                'txn_count': len(batch),
                'ledger_ids': ledgers,
                'symbol_count': len(symbols),
            }
        )
    return batches, txn_to_batch, {b['id']: b['label'] for b in batches}


def _group_candidates(ledger_positions: list[Position], symbol: str) -> tuple[list[Position], Position | None]:
    """候选只列「同账本且同标的」的现存持仓；空 symbol 一律不给候选。

    reattach 硬校验 symbol 一致，列出别的标的只会诱导用户挂错。真库最大一组是
    293 条空 symbol 卖出流水，旧实现给它 20 个无关候选（同账本任意持仓前 20 条），
    等于让用户瞎猜。
    """
    if not symbol:
        return [], None
    same_symbol = [p for p in ledger_positions if (p.symbol or '') == symbol]
    return same_symbol[:MAX_CANDIDATES], (same_symbol[0] if same_symbol else None)


def _group_block_reason(symbol: str, cands: list[Position]) -> tuple[bool, str | None]:
    """可否安全回补的单一真相源：前端只显示判据结果，不自行推导（避免两处口径漂移）。"""
    if not symbol:
        return False, '这批流水缺标的代码，无法判定归属；需先补全 symbol 才能回补'
    if not cands:
        # 文案必须指向**界面上真有的那个按钮**（「重建持仓」）：此前写「需先补建持仓或补录流水」，
        # 而这两条在弹窗里都没有入口 ⇒ 用户被指去另一个卡片，那个卡片又指回来（2026-11-13）。
        return False, '同账本没有同标的的现存持仓行，无法挂回；可按流水重建持仓'
    return True, None


def _group_flags(
    symbol: str,
    cands: list[Position],
    live: Position | None,
    net_units: float,
    fixable: bool,
) -> list[str]:
    """分组标签。net_mismatch 只作展示提示，不阻断「只改指针」的回补动作。"""
    flags = []
    if not symbol:
        flags.append('no_symbol')
    if cands:
        flags.append('has_candidate')
    if live is not None and abs(net_units - _shares(live.quantity)) > NET_MISMATCH_TOLERANCE:
        flags.append('net_mismatch')
    if any(p.ownership_status == 'cleared' for p in cands):
        flags.append('cleared_target')
    if not fixable:
        flags.append('blocked')
    return flags


def _build_group(
    ledger_id,
    symbol: str,
    txns: list[Transaction],
    ledger_positions: list[Position],
    first_batch_id: int,
    batch_label: str,
) -> dict:
    """组装单个 (ledger, symbol) 分组；判据全部来自 ``_group_*`` 系列函数。display_name 取名链 live→候选→流水快照，首个非空。"""
    cands, live = _group_candidates(ledger_positions, symbol)
    fixable, block_reason = _group_block_reason(symbol, cands)
    net_units = _shares(_net_min_units(txns))
    # display_name 与域 B/C 对齐：悬空流水引用的持仓已删，名字只能从 live / 候选 / 流水快照按优先级捞
    name_pool = [live.name if live is not None else None, *(p.name for p in cands), *(t.position_name for t in txns)]
    return {
        'key': f'{ledger_id}|{symbol}',
        'ledger_id': ledger_id,
        'symbol': symbol,
        'display_name': next((n for n in name_pool if n), None),
        'txn_count': len(txns),
        'dangling_position_ids': sorted({t.position_id for t in txns if t.position_id is not None}),
        'net_units': net_units,
        'live_position': _pos_brief(live) if live is not None else None,
        'candidates': [_pos_brief(p) for p in cands],
        'batch_id': first_batch_id,
        'batch_label': batch_label,
        'flags': _group_flags(symbol, cands, live, net_units, fixable),
        'fixable': fixable,
        'block_reason': block_reason,
        'transactions': [_txn_brief(t) for t in txns],
    }


def scan_dangling_refs(db: Session, family_id: int) -> dict:
    """列出当前家庭全部悬空流水（GET /dangling-refs/ 的数据源，纯只读）。

    返回结构与前端契约一一对应：total / group_count / batch_count / null_symbol /
    null_trade_date 为全局计数；groups 按 (ledger_id, symbol or '') 分组，空 symbol
    独立成组（不与有 symbol 的组混合）；batches 是全局按 created_at 聚簇的批次。

    职责拆成「取数 → 批次 → 分组 → 单组组装」四段，单函数圈复杂度留给
    ``scripts/guard_service_size.py`` 守住（新增服务 max_cc ≤ 20）。
    """
    dangling = db.query(Transaction).filter(_dangling_condition(family_id)).all()
    total = len(dangling)
    # 全局计数（对全部悬空流水统计，不是分组求和）
    null_symbol = sum(1 for t in dangling if not t.symbol)
    null_trade_date = sum(1 for t in dangling if t.trade_date is None)

    rows = sorted(dangling, key=lambda t: (t.created_at is None, t.created_at or datetime.min, t.id))
    batches, txn_to_batch, batch_labels = _build_batches(rows)
    by_ledger = _load_positions_by_ledger(db, family_id)

    # 分组键 (ledger_id, symbol or '')；rows 已按 created_at 排好，组内顺序稳定。
    grouped = {}
    for t in rows:
        grouped.setdefault((t.ledger_id, t.symbol or ''), []).append(t)

    groups = []
    for (ledger_id, symbol), txns in grouped.items():
        # 一个组可能跨多个批次，这里取组内最早一条流水所属的批次（组内按 created_at 升序）。
        first_batch_id = txn_to_batch[txns[0].id]
        groups.append(
            _build_group(
                ledger_id,
                symbol,
                txns,
                by_ledger.get(ledger_id, []),
                first_batch_id,
                batch_labels[first_batch_id],
            )
        )

    return {
        'total': total,
        'group_count': len(groups),
        'batch_count': len(batches),
        'null_symbol': null_symbol,
        'null_trade_date': null_trade_date,
        # 真库实测（2026-11-05）：637 条中 105 条可直接回补，295 条缺 symbol、
        # 237 条无同标的持仓行。这两类必须如实显示，不能假装「全部可修」。
        'fixable_count': sum(g['txn_count'] for g in groups if g['fixable']),
        'groups': groups,
        'batches': batches,
    }


def preview_reattach(db: Session, family_id: int, transaction_ids, target_position_id) -> dict:
    """挂回前预览（GET /dangling-refs/preview/ 的数据源，**纯只读，绝不写库**）。

    只做查询与纯计算：不 UPDATE、不 add、不 flush、不调用任何重算。
    ``quantity_if_recomputed`` 是「若用户将来手动重算」的预估、非精确结果，
    口径与 warnings 见 ``_assess_safety`` 及模块 docstring。
    ``safe=false`` 仅代表数据不自洽，**不作为禁止回补的判据**（回补只改指针）。
    """
    ids = _normalize_ids(transaction_ids)
    txns = _load_dangling_by_ids(db, family_id, ids)
    target = _load_target(db, family_id, target_position_id)
    safe, warnings, q_before, q_if, delta = _assess_safety(txns, target)
    return {
        'txn_count': len(txns),
        'target_position': _pos_brief(target),
        'quantity_before': q_before,
        'quantity_if_recomputed': q_if,
        'delta': delta,
        'safe': safe,
        'warnings': warnings,
    }


def reattach_transactions(
    db: Session,
    family_id: int,
    transaction_ids,
    target_position_id,
    reason=None,
    recompute=False,
    operator=None,
) -> dict:
    """把一批悬空流水挂回目标持仓（POST /dangling-refs/reattach/ 的数据源）。

    硬安全约束（逐条对应契约）：
    1. transaction_ids 非空 int 列表、≤500、去重（``_normalize_ids``）；
    2. 每条属于本 family 且**再次用 EXISTS 校验确实悬空**（``_load_dangling_by_ids``）；
    3. target 存在、同 family，且与每条 txn 的 ledger_id 一致（txn.ledger_id 为 NULL 拒绝）；
    3b. 每条 txn 的 symbol 必须非空且与 target.symbol 完全一致（缺代码 / 挂到别的标的
        一律拒绝；真库 295 条缺 symbol，不能靠「同账本任选一个持仓」猜归属）；
    4. 默认 recompute=False：只 UPDATE ``transactions.position_id``，绝不自动重算份额；
       ``recompute=true`` 一律 ValueError（400），理由见模块 docstring；
    5. 写 ``adjustment_logs``：before_json 记 [{id, position_id}] 原值，after_json 记新值
       （含 recompute 标记，供 undo 判断是否可撤销），reason 取 body、operator 可空；
    6. 所有写在本函数内、由视图的单个 ``user_session()`` 事务统一 flush / 回滚兜底。
    """
    if recompute is None:
        recompute = False
    if not isinstance(recompute, bool):
        raise ValueError('recompute 必须是布尔值')
    if recompute:
        raise ValueError(
            '自动重算份额已禁用：本接口只回补流水归属、不改动持仓份额。如需让份额与流水对齐，请在挂回后到持仓页手动重算'
        )

    ids = _normalize_ids(transaction_ids)
    txns = _load_dangling_by_ids(db, family_id, ids)
    target = _load_target(db, family_id, target_position_id)

    # 约束 3：ledger 一致，且 txn.ledger_id 不得为 NULL（否则无法判定归属）。
    for t in txns:
        if t.ledger_id is None:
            raise ValueError(f'流水 {t.id} 的 ledger_id 为空，无法判定目标持仓归属，拒绝挂回')
        if t.ledger_id != target.ledger_id:
            raise ValueError(
                f'流水 {t.id} 的 ledger_id={t.ledger_id} 与目标持仓 ledger_id={target.ledger_id} 不一致，拒绝跨账户挂回'
            )

    # 约束 3b：symbol 必须非空且与目标持仓完全一致。
    # 真库 295 条悬空流水缺 symbol、最大一组 293 条全是卖出；若只校验 ledger，
    # 用户从「同账本 20 个候选」里随手选一个就会把 A 标的流水挂到 B 标的上。
    # safe=false 只是数据不自洽的提示，不能替代这条硬校验（挂错标的比不改更坏）。
    for t in txns:
        if not t.symbol:
            raise ValueError(f'流水 {t.id} 缺标的代码，无法判定归属；请先补全 symbol 再回补')
        if t.symbol != target.symbol:
            raise ValueError(
                f'流水 {t.id} 的 symbol={t.symbol!r} 与目标持仓 {target.symbol!r} 不一致，拒绝挂到别的标的上'
            )

    # —— 以下才开始写；任何抛错分支都在上面，保证「整体 400、不写任何东西」——
    # 份额在挂回前后一字不动：这里取一次值，写后不重算、不读回（读回也只会相同）。
    q_before = _shares(target.quantity)
    before = [{'id': t.id, 'position_id': t.position_id} for t in txns]
    for t in txns:
        t.position_id = target.id
    db.flush()
    q_after = q_before

    after = {
        'recompute': False,
        'target_position_id': target.id,
        'transactions': [{'id': t.id, 'position_id': target.id} for t in txns],
    }
    log = AdjustmentLog(
        family_id=family_id,
        action='dangling_ref_reattach',
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=reason,
        operator=operator,
    )
    db.add(log)
    db.flush()
    return {
        'log_id': log.id,
        'updated': len(txns),
        'recompute': False,
        'quantity_before': q_before,
        'quantity_after': q_after,
    }


def undo_reattach(db: Session, family_id: int, log_id) -> dict:
    """撤销一次挂回（POST /dangling-refs/undo/ 的数据源）。

    按 log.before_json 把每个 txn 的 position_id 恢复成原值，**仅当该 txn 当前
    position_id 仍等于 log.after_json 里的 after 值**（否则跳过并计数）。幂等：重复撤销
    restored=0、数据不变，但仍追加一条 ``dangling_ref_undo`` 留痕日志。

    若该 log 标了 ``recompute=true``：份额已被全量重算、不可逆，按契约**拒绝撤销**并
    提示需人工处理，不改动任何 txn、不写 undo 日志。
    """
    if isinstance(log_id, bool) or not isinstance(log_id, int):
        raise ValueError('log_id 必须是整数')
    log = (
        db.query(AdjustmentLog)
        .filter(
            AdjustmentLog.id == log_id,
            AdjustmentLog.family_id == family_id,
            AdjustmentLog.action == 'dangling_ref_reattach',
        )
        .first()
    )
    if log is None:
        raise ValueError('撤销记录不存在或无权访问（仅能撤销 dangling_ref_reattach 日志）')
    try:
        before = json.loads(log.before_json or '[]')
        after = json.loads(log.after_json or '{}')
    except (TypeError, ValueError) as e:
        raise ValueError(f'撤销记录 JSON 损坏，无法解析：{e}') from e
    if not isinstance(before, list) or not isinstance(after, dict):
        raise ValueError('撤销记录 before_json / after_json 结构异常，无法解析')
    if after.get('recompute') is True:
        raise ValueError('该批次执行过 recompute=true 的份额全量重算，份额变更不可逆，拒绝自动撤销；请人工核对后处理')

    before_map = {item['id']: item['position_id'] for item in before}
    after_map = {item['id']: item['position_id'] for item in after.get('transactions', [])}
    restored, skipped = 0, 0
    for tid, before_pid in before_map.items():
        txn = db.query(Transaction).filter(Transaction.id == tid, Transaction.family_id == family_id).first()
        if txn is None or txn.position_id != after_map.get(tid):
            skipped += 1
            continue
        txn.position_id = before_pid
        restored += 1
    db.flush()

    db.add(
        AdjustmentLog(
            family_id=family_id,
            action='dangling_ref_undo',
            before_json=json.dumps({'ref_log_id': log_id}, ensure_ascii=False),
            after_json=json.dumps({'restored': restored, 'skipped': skipped}, ensure_ascii=False),
            reason=f'撤销 reattach 日志 {log_id}',
            operator=log.operator,
        )
    )
    db.flush()
    return {'restored': restored, 'log_id': log_id}
