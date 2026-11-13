# -*- coding: utf-8 -*-
"""错挂流水（``position_id`` 指向**别的标的**的现存持仓）的检出与改挂（域 F 第四类脏数据）。

## 为什么需要这一刀

``transactions.position_id`` 是裸 ``Column(Integer)``、无外键，历史写入路径留下过一种
既有的两条修法都够不到的脏数据：``position_id`` 指向的持仓**存在**，但那条持仓属于
**另一个标的**（真库 2026-11-13 只读实测 3 条：流水 1954/2355/2785）。

- 「回补关联」只认 ``_dangling_condition``（持仓行不存在），这里持仓存在 ⇒ 判「并非悬空」；
- 「按流水重建持仓」的前置同样是该条件 ⇒ 重建端点拒绝；
- 于是这笔流水被算进**错误标的**的持仓推演（污染 B 标的份额与成本），而对账按
  ``(ledger_id, symbol)`` 建 ``pos_by_key`` —— 流水自己的 ``symbol`` 名下没有持仓行，
  每轮对账都重新产出 orphan 差异、``_clear_stale_discrepancies`` 永远清不掉。

## 检出判据（只用「代码」比，不用 ``symbol_norm``）

判据是**归一后的证券代码不同**（``core.symbol_utils.strip_exchange_prefix``）：
``SZ127041`` → ``127041``、``014847`` → ``014847``。

为什么不比 ``symbol_norm``：它含**交易场所**（``EXCHANGE:014847`` vs ``OTC:014847``）。
真库实测 24 条 ``symbol_norm`` 不等的挂接里 **21 条是同一代码、两侧 ``asset_type``
不一致**（流水记 ``stock``、持仓记 ``fund``），拿 ``symbol_norm`` 当判据会把这 21 条
当成「挂错标的」推给用户 —— 那是场所标注问题，不是归属错误，按它改挂会改坏真实持仓。

``NULL`` 一侧的 ``symbol_norm`` 用 ``COALESCE`` 兜底；SQL 预筛之后仍在 Python 里用
代码再判一次（SQL 表达不了「剥前缀」，预筛只是把候选压到个位数）。

## 修复动作（一条命令做完，不留中间态）

按组（同 ``ledger_id`` + 同 ``symbol``）**改挂到正确标的**：

1. 同账本已有**同身份**（``symbol_norm`` 相等）的持仓行 ⇒ 只把 ``position_id`` 指过去
   （``mode=remount``，与「回补关联」同性质：只改指针、份额一字不动）；
2. 没有 ⇒ 以这组流水为真相源重建一行（``mode=rebuild``，复用
   ``position_recompute.rebuild_position_from_txns``，份额/成本口径与单一真相源同源）。

不提供「只摘下来（``position_id → NULL``）」的半个动作：摘下来只是把脏数据换成悬空数据，
用户还得再走一遍重建，中途失败就停在更差的状态。

**绝不**在对账里静默改 ``position_id``：那是用户没看见的情况下改账，且与
``position_recompute`` 的单一真相源口径冲突。故本模块只有「预览 + ``confirm is True``
+ ``adjustment_logs`` 可撤销」这一条写路径。

## 已知边界（如实标注，不粉饰）

- **错误持仓的现存份额不会被重算**：本动作只改流水归属，不碰 ``positions.quantity``
  （静默改份额比脏数据更坏）。改挂后错误持仓的份额会与「按流水派生」不一致，下一次
  域 B 对账会把它报成数量差异，由用户决定是否手动重算；预览的 ``warnings`` 明说这一点。
- 重建模式的份额只由**选中的流水**派生；同账本同标的还有没选进来的流水时，重建份额
  会偏小 —— 预览给 ``warnings`` 提示，不阻断（阻断会让「一次只能修一半」变成死锁）。
- 重建行取默认 ``market=CN_A`` / ``currency=CNY`` / ``source=manual``（流水里没有这些字段）。

## 事务边界

与同域其它服务同构：调用方传入 ``db``，只 ``flush()`` 不 ``commit()``；``ValueError``
由视图转 400，请求 teardown 回滚。所有校验排在写操作之前，拒绝分支不得留下
``db.new / db.dirty / db.deleted``，也不写审计日志。
"""

import json
from collections import defaultdict

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.money import Money
from app.core.symbol_utils import strip_exchange_prefix
from app.domains.positions.models import Position
from app.domains.positions.state import derive_state_from_txns
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.dates import order_by_effective_day
from app.domains.transactions.models import Transaction
from app.services.dangling_ref_remediation_service import _load_log, _require_confirm
from app.services.dangling_ref_service import (
    _net_min_units,
    _normalize_ids,
    _pos_brief,
    _shares,
    _txn_brief,
)
from app.services.position_recompute import rebuild_position_from_txns

ACTION_MISLINK = 'dangling_ref_mislink'
ACTION_MISLINK_UNDO = 'dangling_ref_mislink_undo'

#: 改挂到同账本同身份的现存持仓（只改指针）
MODE_REMOUNT = 'remount'
#: 同账本没有同身份持仓行，按这组流水重建一行再挂回
MODE_REBUILD = 'rebuild'

#: 重建模式下净额必须严格大于 0（0 份额空壳行只是换一种脏数据，与重建服务同口径）
MIN_NET_MIN_UNITS = 1

#: 候选持仓最多返回条数（与 dangling_ref_service 同口径）
MAX_CANDIDATES = 20


def code_of(symbol) -> str:
    """标的代码的**场所无关**形态：``SZ127041`` / ``127041.SZ`` / ``sz127041`` → ``127041``。

    「是不是同一个标的」只用这一层判（见模块 docstring：``symbol_norm`` 含场所，
    会把「同一代码、场所标注不一致」误判成挂错标的）。
    """
    return strip_exchange_prefix((symbol or '').strip().upper())


def _mislinked_pairs(db: Session, family_id: int) -> list[tuple[Transaction, Position]]:
    """本家庭里「流水挂着的持仓存在、但代码不同」的 (流水, 持仓) 对。

    SQL 预筛用 ``symbol_norm`` 不等（含场所，是**超集**，包含要排除的场所噪声），
    再在 Python 里按代码判一次得到真集合；两边都要求非空 symbol（空 symbol 的流水
    属于「缺代码」而不是「挂错标的」，归域 F 既有阶段处理）。
    """
    rows = (
        db.query(Transaction, Position)
        .join(Position, and_(Position.id == Transaction.position_id, Position.family_id == family_id))
        .filter(
            Transaction.family_id == family_id,
            Transaction.position_id.isnot(None),
            func.coalesce(Transaction.symbol_norm, '') != func.coalesce(Position.symbol_norm, ''),
        )
        .order_by(Transaction.created_at, Transaction.id)
        .all()
    )
    return [(t, p) for t, p in rows if (t.symbol or '').strip() and code_of(t.symbol) != code_of(p.symbol)]


def _target_of(
    db: Session, family_id: int, txns: list[Transaction], ledger_id
) -> tuple[Position | None, Position | None]:
    """组内流水的**正确**目标持仓：同账本、同代码。

    返回 ``(同身份持仓, 同代码但场所不同的持仓)``：后者只用于把「为什么不能直接改挂」
    说清楚（例如 ``SZ004369`` 流水 + ``004369`` 场外基金持仓），绝不自动选它 ——
    场所决定 ``asset_type``，猜错就是把流水挂进了另一类资产。
    """
    symbol = txns[0].symbol
    code = code_of(symbol)
    exact = None
    near = None
    rows = (
        db.query(Position)
        .filter(Position.family_id == family_id, Position.ledger_id == ledger_id)
        .order_by(Position.id)
    )
    for pos in rows:
        if code_of(pos.symbol) != code:
            continue
        if pos.symbol_norm and pos.symbol_norm == txns[0].symbol_norm:
            exact = exact or pos
        else:
            near = near or pos
    return exact, near


def _group_pairs(pairs) -> dict:
    """按 (ledger_id, symbol or '') 分组；pairs 已按 created_at 升序，组内顺序稳定。"""
    grouped = defaultdict(list)
    for txn, pos in pairs:
        grouped[(txn.ledger_id, txn.symbol or '')].append((txn, pos))
    return grouped


def _block_reason(txns: list[Transaction], exact: Position | None, near: Position | None) -> str | None:
    """不可改挂的可执行原因。判据与「按流水重建持仓」同源（缺代码 / 缺价 / 净额 ≤ 0）。"""
    if near is not None and exact is None:
        return (
            f'同账本有代码相同但交易场所不同的持仓（#{near.id} {near.symbol!r}），'
            '无法判定该挂哪一个；请先在持仓页核对场所标注'
        )
    if exact is not None:
        return None
    if any(t.price is None or t.quantity is None for t in txns if t.txn_type in ('buy', 'deposit')):
        return '组内有买入流水缺成交价或份额，派生不出成本，重建会得到 0 成本持仓'
    if _net_min_units(txns) < MIN_NET_MIN_UNITS:
        return '这批流水买卖已对冲（净额 ≤ 0），重建不出有效持仓；如这些流水是历史残留，走「删除」'
    return None


def _mislink_flags(exact: Position | None, near: Position | None, fixable: bool) -> list[str]:
    """组标签。``mislinked`` 是阶段判据（前端据此归到「挂错标的」），其余是展示提示。"""
    flags = ['mislinked']
    flags.append('has_candidate' if exact is not None else 'no_target')
    if near is not None and exact is None:
        flags.append('venue_conflict')
    if not fixable:
        flags.append('blocked')
    return flags


def _build_group(ledger_id, symbol: str, items, exact: Position | None, near: Position | None) -> dict:
    """组装单个错挂分组；形状与``dangling_ref_service`` 的组**结构兼容**（前端复用同一张卡）。"""
    txns = [t for t, _ in items]
    wrong = [p for _, p in items]
    reason = _block_reason(txns, exact, near)
    name_pool = [
        *(p.name for p in [exact] if p is not None),
        *(t.position_name for t in txns),
        *(p.name for p in [near] if p is not None),
    ]
    return {
        'key': f'mislink|{ledger_id}|{symbol}',
        'ledger_id': ledger_id,
        'symbol': symbol,
        'display_name': next((n for n in name_pool if n), None),
        'txn_count': len(txns),
        'dangling_position_ids': sorted({t.position_id for t in txns if t.position_id is not None}),
        'net_units': _shares(_net_min_units(txns)),
        'live_position': _pos_brief(exact) if exact is not None else None,
        'candidates': [_pos_brief(exact)] if exact is not None else [],
        'batch_id': None,
        'batch_label': '',
        'flags': _mislink_flags(exact, near, reason is None),
        'fixable': reason is None,
        'block_reason': reason,
        'mislinked': True,
        'fix_mode': MODE_REMOUNT if exact is not None else MODE_REBUILD,
        'wrong_positions': [_pos_brief(p) for p in _unique_positions(wrong)],
        'transactions': [_txn_brief(t) for t in txns],
    }


def _unique_positions(rows: list[Position]) -> list[Position]:
    """按 id 去重、保序（同一错误持仓可能被多条流水共用）。"""
    seen, out = set(), []
    for p in rows:
        if p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out


def scan_mislinked_refs(db: Session, family_id: int) -> dict:
    """列出当前家庭的错挂流水（GET /dangling-refs/mislinked/ 的数据源，纯只读）。

    返回 ``{total, group_count, fixable_count, groups}``；``groups`` 元素与域 F 的
    ``DanglingRefGroup`` 结构兼容，另有 ``mislinked`` / ``fix_mode`` / ``wrong_positions``
    三个本类特有字段，供前端单独成阶段并说明「这笔现在挂在哪」。
    """
    pairs = _mislinked_pairs(db, family_id)
    groups = []
    for (ledger_id, symbol), items in _group_pairs(pairs).items():
        txns = [t for t, _ in items]
        exact, near = _target_of(db, family_id, txns, ledger_id)
        groups.append(_build_group(ledger_id, symbol, items, exact, near))
    return {
        'total': len(pairs),
        'group_count': len(groups),
        'fixable_count': sum(g['txn_count'] for g in groups if g['fixable']),
        'groups': groups,
    }


def _load_mislinked_by_ids(db: Session, family_id: int, ids: list[int]) -> list[tuple[Transaction, Position]]:
    """按 id 取流水，并**再次校验**每条确实属于本 family、且确实错挂。

    防的是「已经被修好 / 已被删除」的 id 再挂一次；任一不满足整体抛 ``ValueError``、
    零写入（与 ``dangling_ref_service._load_dangling_by_ids`` 同一纪律）。
    """
    live = {t.id: (t, p) for t, p in _mislinked_pairs(db, family_id)}
    missing = [i for i in ids if i not in live]
    if missing:
        raise ValueError(f'以下流水不属于当前家庭或并非「挂错标的」（可能已被修复/已删除）：{missing}')
    return [live[i] for i in ids]


def _identity_block(ordered: list[Transaction], ledger_id) -> tuple[str | None, str | None]:
    """身份类拒绝原因：本动作一次只改挂「一个账本 + 一个标的」。"""
    symbols = sorted({t.symbol or '' for t in ordered})
    if len(symbols) > 1:
        return None, f'这批流水含多个标的（{"、".join(symbols)}），一次只能改挂一个标的'
    if ledger_id is None:
        return symbols[0], '这批流水跨多个账本或没有账本，无法判定目标持仓归属'
    return symbols[0], None


def plan_mislink_fix(db: Session, family_id: int, transaction_ids) -> dict:
    """纯只读：算出「改挂会落到哪条持仓、份额是多少」，并给出不可改挂的可执行原因。

    所有判断都在写之前的这一次扫描里完成，写路径直接复用同一份 plan ——
    预览与真正写入不可能给出两套结论。
    """
    ids = _normalize_ids(transaction_ids)
    loaded = _load_mislinked_by_ids(db, family_id, ids)
    ordered = order_by_effective_day(
        db.query(Transaction).filter(Transaction.id.in_([t.id for t, _ in loaded])), descending=False
    ).all()
    ledger_ids = {t.ledger_id for t in ordered}
    ledger_id = next(iter(ledger_ids)) if len(ledger_ids) == 1 else None
    symbol, reason = _identity_block(ordered, ledger_id)
    exact, near = _target_of(db, family_id, ordered, ledger_id) if symbol is not None else (None, None)
    if reason is None:
        reason = _block_reason(ordered, exact, near)

    plan = {
        'txns': ordered,
        'txn_count': len(ordered),
        'symbol': symbol,
        'ledger_id': ledger_id,
        'asset_type': next((t.asset_type for t in ordered if t.asset_type), None),
        'target_position': exact,
        'mode': MODE_REMOUNT if exact is not None else MODE_REBUILD,
        'net_min_units': 0,
        'avg_price_units': 0,
        'wrong_position_ids': sorted({t.position_id for t in ordered if t.position_id is not None}),
        'fixable': reason is None,
        'block_reason': reason,
        'warnings': [],
        'display_name': next((t.position_name for t in ordered if t.position_name), None),
    }
    if reason is not None:
        return plan
    plan['warnings'] = _fix_warnings(db, family_id, ordered, ledger_id, exact)
    if exact is None:
        net_qty, avg_price_units = derive_state_from_txns(ordered, 0, 0)
        plan['net_min_units'] = net_qty
        plan['avg_price_units'] = avg_price_units
    return plan


def _fix_warnings(
    db: Session, family_id: int, ordered: list[Transaction], ledger_id, exact: Position | None
) -> list[str]:
    """如实说明本动作改了什么、没改什么（尤其「错误持仓份额不会自动重算」）。"""
    warnings = [
        '本次只改这几笔流水指向的持仓，**不会**重算任何持仓的份额与成本。'
        '错误的那条持仓份额会与「按流水派生」不一致，下一次对账会报成数量差异，需你决定是否手动重算。',
        '改挂后这几笔流水不再计入原持仓的推演；原持仓的现存份额列一字未动。',
        '每次改挂都写审计日志，可凭日志编号撤销（撤销会把流水放回原来的持仓）。',
    ]
    if exact is None:
        warnings.append(
            '同账本没有同标的的持仓行，本次会按这几笔流水新建一条（份额与成本由流水派生，'
            '不是还原历史）；若这不是该标的的全部流水，新建的份额会偏小，请对照券商账单核对。'
        )
    siblings = _sibling_count(db, family_id, ordered, ledger_id)
    if siblings:
        warnings.append(f'同账本同标的还有 {siblings} 条流水没有选进来；只用选中的这批改挂，新建份额会偏小。')
    return warnings


def _sibling_count(db: Session, family_id: int, ordered: list[Transaction], ledger_id) -> int:
    """同账本同标的、**没被选中**的流水条数（不含已挂到目标持仓上的那些）。"""
    symbol = ordered[0].symbol
    chosen = {t.id for t in ordered}
    target_ids = {t.position_id for t in ordered}
    rows = (
        db.query(Transaction.id, Transaction.position_id)
        .filter(
            Transaction.family_id == family_id,
            Transaction.ledger_id == ledger_id,
            Transaction.symbol == symbol,
        )
        .all()
    )
    return sum(1 for tid, pid in rows if tid not in chosen and pid not in target_ids)


def public_plan(plan: dict) -> dict:
    """剥掉内部键并把份额 / 价格换成用户单位，得到前端契约。"""
    target = plan['target_position']
    net_units = (
        _shares(plan['net_min_units']) if plan['mode'] == MODE_REBUILD else _shares(_net_min_units(plan['txns']))
    )
    return {
        'txn_count': plan['txn_count'],
        'symbol': plan['symbol'],
        'display_name': plan['display_name'],
        'ledger_id': plan['ledger_id'],
        'asset_type': plan['asset_type'],
        'mode': plan['mode'],
        'target_position': _pos_brief(target) if target is not None else None,
        'wrong_position_ids': plan['wrong_position_ids'],
        'net_units': round(net_units, 4),
        'avg_price': round(Money.price_units_to_yuan(plan['avg_price_units']), 4),
        'fixable': plan['fixable'],
        'block_reason': plan['block_reason'],
        'warnings': plan['warnings'],
    }


def preview_mislink_fix(db: Session, family_id: int, transaction_ids) -> dict:
    """改挂前预览（GET /dangling-refs/mislink-preview/ 的数据源，**纯只读，绝不写库**）。"""
    return public_plan(plan_mislink_fix(db, family_id, transaction_ids))


def _create_target(db: Session, plan: dict) -> Position:
    """重建模式：以这组流水为真相源建一行正确标的的持仓（份额/成本口径与重算引擎同源）。"""
    return rebuild_position_from_txns(db, plan['txns'], plan['net_min_units'], plan['avg_price_units'])


def fix_mislink(db: Session, family_id: int, transaction_ids, reason=None, operator=None, confirm=False) -> dict:
    """把一批错挂流水改挂到正确标的（POST /dangling-refs/mislink/ 的数据源）。

    写之前必须过 ``confirm is True``（后端硬校验，不信任前端）。审计日志两侧都记，
    撤销据此把流水放回原来的持仓、并删掉本次新建的持仓行。
    """
    _require_confirm(confirm)
    plan = plan_mislink_fix(db, family_id, transaction_ids)
    if not plan['fixable']:
        raise ValueError(plan['block_reason'] or '这批流水当前不能改挂')

    # —— 校验全部通过，以下才开始写 ——
    txns = plan['txns']
    before = [{'id': t.id, 'position_id': t.position_id} for t in txns]
    created = None
    target = plan['target_position']
    if target is None:
        target = created = _create_target(db, plan)
    for t in txns:
        t.position_id = target.id
    db.flush()

    after = {
        'mode': plan['mode'],
        'symbol': plan['symbol'],
        'ledger_id': plan['ledger_id'],
        'position_id': target.id,
        'created_position_id': created.id if created is not None else None,
        'quantity': target.quantity,
        'avg_price': target.avg_price,
        'txn_ids': [t.id for t in txns],
    }
    log = AdjustmentLog(
        family_id=family_id,
        action=ACTION_MISLINK,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=reason,
        operator=operator,
    )
    db.add(log)
    db.flush()
    return {
        'log_id': log.id,
        'mode': plan['mode'],
        'position_id': target.id,
        'created_position_id': after['created_position_id'],
        'symbol': target.symbol,
        'display_name': target.name,
        'quantity': round(Money.min_unit_to_shares(target.quantity), 4),
        'avg_price': round(Money.price_units_to_yuan(target.avg_price), 4),
        'txn_count': len(txns),
    }


def _undo_skip_reason(db: Session, family_id: int, after: dict) -> str | None:
    """撤销前的「期间有没有被改过」判据；返回 None 表示可以撤销。

    重建模式要删掉本次新建的持仓，故比「回补关联」多两道校验：持仓份额/成本被改过、
    或挂在上面的流水集合变了，都说明这行已承载新的业务事实，删掉会连带抹掉它们。
    """
    position_id = after.get('position_id')
    position = db.query(Position).filter(Position.id == position_id).first()
    if position is None or position.family_id != family_id:
        return '目标持仓已不存在'
    expected = set(after.get('txn_ids') or [])
    current = {t.id for t in db.query(Transaction.id).filter(Transaction.position_id == position_id).all()}
    if current != expected:
        return '挂在这条持仓上的流水已变化，撤销会误伤后来的流水'
    if after.get('created_position_id') is not None and (
        position.quantity != after.get('quantity') or position.avg_price != after.get('avg_price')
    ):
        return '新建的持仓份额或成本已被改动（例如已补录卖出），撤销会抹掉后来的业务事实'
    return None


def undo_mislink(db: Session, family_id: int, log_id) -> dict:
    """撤销一次改挂（POST /dangling-refs/mislink-undo/ 的数据源）。

    按 ``before_json`` 把每笔流水的 ``position_id`` 放回原值（仅当它当前仍等于改挂后的
    值，否则跳过）；重建模式下再删掉本次新建的持仓行。幂等：重复撤销 ``restored=0``，
    数据不变但仍追加留痕日志。
    """
    log = _load_log(db, family_id, log_id, ACTION_MISLINK)
    try:
        before = json.loads(log.before_json or '[]')
        after = json.loads(log.after_json or '{}')
    except (TypeError, ValueError) as e:
        raise ValueError(f'撤销记录 JSON 损坏，无法解析：{e}') from e
    if not isinstance(before, list) or not isinstance(after, dict):
        raise ValueError('撤销记录 before_json / after_json 结构异常，无法解析')

    skip = _undo_skip_reason(db, family_id, after)
    if skip is not None:
        _write_undo_log(db, family_id, log_id, log.operator, restored=0, skipped=1, reason=skip)
        return {'restored': 0, 'skipped': 1, 'log_id': log_id, 'skip_reason': skip}

    target_id = after['position_id']
    before_map = {item['id']: item['position_id'] for item in before if isinstance(item, dict)}
    restored = 0
    for tid, before_pid in before_map.items():
        txn = db.query(Transaction).filter(Transaction.id == tid, Transaction.family_id == family_id).first()
        if txn is None or txn.position_id not in (target_id, None):
            continue
        txn.position_id = before_pid
        restored += 1
    if after.get('created_position_id') is not None:
        created = db.query(Position).filter(Position.id == after['created_position_id']).first()
        if created is not None:
            db.delete(created)
    db.flush()
    _write_undo_log(db, family_id, log_id, log.operator, restored=restored, skipped=0)
    return {'restored': restored, 'skipped': 0, 'log_id': log_id, 'skip_reason': None}


def _write_undo_log(db: Session, family_id: int, ref_log_id, operator, *, restored: int, skipped: int, reason=None):
    """每次撤销都留痕（包括 skipped 的那次）：审计要能解释「为什么没撤销成功」。"""
    db.add(
        AdjustmentLog(
            family_id=family_id,
            action=ACTION_MISLINK_UNDO,
            before_json=json.dumps({'ref_log_id': ref_log_id}, ensure_ascii=False),
            after_json=json.dumps(
                {'restored': restored, 'skipped': skipped, 'skip_reason': reason}, ensure_ascii=False
            ),
            reason=reason or f'撤销改挂日志 {ref_log_id}',
            operator=operator,
        )
    )
    db.flush()
