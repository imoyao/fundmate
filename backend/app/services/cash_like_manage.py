# -*- coding: utf-8 -*-
"""账外类现金流水（孤儿货基 / 逆回购）的增删改 / 补录 / 归置。

## 为什么单独一个模块

「类现金」在本仓**不建 positions 行**：导入路径只落 `transactions`
（`position_id IS NULL`，净额由 `summary_service.orphan_flow_delta` 单点判定），
因此持仓列表查不到、以 `position_id` 为主键的增删改也没有对象。
本模块给这批流水补一套管理能力，**不改任何既有口径代码**：

- 不改 `summary_service.py`（冻结基线、只减不增）：净额桶仍由
  `orphan_flow_delta` 判定，四处汇总消费方自动收敛、无需清缓存；
- 归置只改 `position_id` + `extra` 标记（复用 `_reattach_orphan_flows` 的
  「只改 position_id、不重算份额、金额由持仓市值承接」语义），归置后流水退出
  孤儿净额桶 ⇒ 同一笔钱不再被算两次；
- 不批量回填 `trade_date` / `symbol` / `import_hash`（D99：系统派生回填＝造数）。
  存量 162 笔无交易日、158 笔无代码，一个字节都不改；用户可**单笔显式**手填，
  「从同产品持仓带入」的代码会写 `cash_like_symbol_source='inferred_from_position'`
  标注为推断；补录**新行**的 `trade_date` 沿用唯一写入口径
  `dates.prepare_write_kwargs`（由用户给的 `confirm_date` 兜底），不是回填。

## 补录「到期回款」

真库账本 12 的逆回购 4 笔全是 `buy`、没有一笔到期回款 ⇒ 净额恒为 +20.2 万的
在途额，用户看到的是一个只增不减的数。`kind='repayment'` 一次落「负向本金流水
（`sell`）+ 可选收益流水（`dividend_cash`）」，让净额真正减下去；两笔共用同一个
`client_token` 派生的确定性幂等键，不重算、不占用既有 `import_hash` 空间
（重算会与 `uq_txn_import_hash` 复合唯一索引撞车，也会让历史文件重新导入去重失效）。

## 不做的事

- 不建 `Position` 行（#1233 决策 5）；
- 不提供批量补元数据端点（D99 只允许「用户逐条录入自己知道的历史事实」）；
- 归置后的流水禁止直接编辑 / 删除：它们已由目标持仓体现，须先撤销归置，
  否则会绕过 `DELETE` 路径的持仓份额重算、形成两处真相。
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.asset_types import get_asset_type_label
from app.core.constants import POSITION_SOURCE_LABELS, PositionSource
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.summary_service import orphan_flow_delta
from app.services.trading import TransactionService

#: 与 `summary_service._ORPHAN_FLOW_ASSET_TYPES` 同值；刻意不私有 import，
#: 由 `tests/services/test_cash_like_manage.py` 的常量同源断言钉住漂移。
CASH_LIKE_ASSET_TYPES = ('money_fund', 'reverse_repo')
#: 允许补录的流水类型；`repayment` 是「本金回款 + 可选利息」的组合动作。
FLOW_KINDS = ('buy', 'sell', 'withdraw', 'dividend_cash', 'dividend_tax', 'repayment')
#: 编辑允许改的字段；`trade_date` 只允许单笔显式手填，且留空＝不改。
EDITABLE_FIELDS = ('amount', 'confirm_date', 'trade_date', 'position_name', 'symbol', 'source', 'notes', 'txn_type')
FORBIDDEN_FIELDS = ('import_hash', 'position_id', 'ledger_id', 'asset_type', 'quantity', 'price', 'fee', 'family_id')

RECONCILED_KEY = 'cash_like_reconciled'
SYMBOL_SOURCE_KEY = 'cash_like_symbol_source'
MANUAL_KEY = 'cash_like_manual'
IMPORT_HASH_PREFIX = 'cash_like|manual|'
MAX_BATCH = 500
MAX_PER_PAGE = 100


def _load_extra(txn: Transaction) -> dict[str, Any]:
    """`extra` 是自由 Text JSON；坏数据按空字典处理，绝不让一条脏行炸掉整个列表。"""
    if not txn.extra:
        return {}
    try:
        parsed = json.loads(txn.extra)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _save_extra(txn: Transaction, data: dict[str, Any]) -> None:
    txn.extra = json.dumps(data, ensure_ascii=False) if data else None


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value).strip()[:10]
    return text or None


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} 不能为空')
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as e:
        raise ValueError(f'{field} 格式须为 YYYY-MM-DD') from e


def _amount_cents(value: Any, field: str = 'amount') -> int:
    try:
        yuan = float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f'{field} 必须是数字') from e
    if yuan <= 0:
        raise ValueError(f'{field} 必须大于 0')
    return Money.yuan_to_cents(yuan)


def _row(txn: Transaction, ledger_names: dict[int, str] | None = None) -> dict[str, Any]:
    """列表行；`bucket` 直接复用净额判据，让「这笔进哪个桶」可逐笔核对。"""
    extra = _load_extra(txn)
    reconciled = extra.get(RECONCILED_KEY)
    moved = orphan_flow_delta(txn.txn_type, txn.amount, txn.is_income)
    return {
        'id': txn.id,
        'ledger_id': txn.ledger_id,
        'ledger_name': (ledger_names or {}).get(txn.ledger_id) or '未归属账户',
        'asset_type': txn.asset_type,
        'asset_type_label': get_asset_type_label(txn.asset_type),
        'txn_type': txn.txn_type,
        'amount': round(Money.cents_to_yuan(txn.amount or 0), 2),
        'position_name': txn.position_name or '',
        'symbol': txn.symbol or '',
        'symbol_inferred': extra.get(SYMBOL_SOURCE_KEY) == 'inferred_from_position',
        'source': txn.source or '',
        'trade_date': _date_text(txn.trade_date),
        'confirm_date': _date_text(txn.confirm_date),
        'entry_status': txn.entry_status,
        'notes': txn.notes or '',
        'is_income': bool(txn.is_income),
        'position_id': txn.position_id,
        'reconciled': reconciled if isinstance(reconciled, dict) else None,
        'bucket': moved[0] if moved else None,
        'is_manual': bool(extra.get(MANUAL_KEY)),
    }


def _scope(db: Session, family_id: int, include_reconciled: bool):
    """孤儿类现金流水的作用域。

    `include_reconciled=True` 时把「已归置」的流水也纳入：它们的 `position_id`
    已非空，只能靠 `extra` 里的归置标记认出来（`extra` 是 Text，用 LIKE 足够，
    精确判定仍在 `_row` / `reconcile_flows` 里做 `json.loads` 复核）。
    """
    query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.asset_type.in_(CASH_LIKE_ASSET_TYPES),
    )
    if include_reconciled:
        return query.filter(or_(Transaction.position_id.is_(None), Transaction.extra.like(f'%{RECONCILED_KEY}%')))
    return query.filter(Transaction.position_id.is_(None))


def list_flows(
    db: Session,
    family_id: int,
    *,
    ledger_id: int | None = None,
    asset_type: str | None = None,
    q: str | None = None,
    include_reconciled: bool = False,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """逐笔列出账外类现金流水（分页、可按账户 / 类型 / 名称代码搜索）。

    搜索命中给「持仓明细」页用：它查的是**流水**而不是 `positions`，
    所以结果必须带口径标签、不进持仓合计（前端职责）。
    """
    page = max(1, int(page or 1))
    per_page = min(MAX_PER_PAGE, max(1, int(per_page or 50)))
    query = _scope(db, family_id, include_reconciled)
    if ledger_id is not None:
        query = query.filter(Transaction.ledger_id == int(ledger_id))
    if asset_type:
        if asset_type not in CASH_LIKE_ASSET_TYPES:
            raise ValueError(f'不支持的资产类型: {asset_type}')
        query = query.filter(Transaction.asset_type == asset_type)
    keyword = (q or '').strip()
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(or_(Transaction.position_name.ilike(like), Transaction.symbol.ilike(like)))
    total = query.count()
    rows = (
        query.order_by(Transaction.confirm_date.desc(), Transaction.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    ledger_names = dict(db.query(Ledger.id, Ledger.name).filter(Ledger.family_id == family_id).all())
    return {
        'items': [_row(t, ledger_names) for t in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'has_more': page * per_page < total,
    }


def list_targets(
    db: Session, family_id: int, *, ledger_id: int | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    """归置目标候选：同家庭（可收窄到同账户）的活跃持仓，最多 50 条。"""
    query = db.query(Position).filter(
        Position.family_id == family_id,
        or_(Position.ownership_status.is_(None), Position.ownership_status == 'active'),
    )
    if ledger_id is not None:
        query = query.filter(Position.ledger_id == int(ledger_id))
    keyword = (q or '').strip()
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(or_(Position.name.ilike(like), Position.symbol.ilike(like)))
    rows = query.order_by(Position.id.desc()).limit(50).all()
    return [
        {
            'id': p.id,
            'name': p.name or '',
            'symbol': p.symbol or '',
            'asset_type': p.asset_type or '',
            'ledger_id': p.ledger_id,
            'is_money_fund': bool(p.is_money_fund),
        }
        for p in rows
    ]


def _common_create_kwargs(db: Session, family_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """补录新行的公共字段；`trade_date` 刻意不传，交给唯一写入汇点按 confirm_date 兜底。"""
    ledger_id = payload.get('ledger_id')
    if ledger_id is None:
        raise ValueError('缺少 ledger_id')
    ledger = db.query(Ledger).filter(Ledger.id == int(ledger_id), Ledger.family_id == family_id).first()
    if ledger is None:
        raise ValueError('目标账本不存在或无权访问')
    asset_type = payload.get('asset_type')
    if asset_type not in CASH_LIKE_ASSET_TYPES:
        raise ValueError(f'asset_type 须为 {CASH_LIKE_ASSET_TYPES}')
    confirm_date = _parse_date(payload.get('confirm_date'), 'confirm_date')
    source = (payload.get('source') or '').strip() or PositionSource.MANUAL.value
    if source not in POSITION_SOURCE_LABELS:
        raise ValueError(f'非法来源 source={source!r}')
    extra: dict[str, Any] = {MANUAL_KEY: True, 'kind': payload.get('kind', 'buy')}
    if payload.get('link_flow_id') is not None:
        extra['link_flow_id'] = int(payload['link_flow_id'])
    if payload.get('symbol_inferred'):
        extra[SYMBOL_SOURCE_KEY] = 'inferred_from_position'
    elif (payload.get('symbol') or '').strip():
        extra[SYMBOL_SOURCE_KEY] = 'user'
    return {
        'position_id': None,
        'ledger_id': ledger.id,
        'account_name': ledger.name,
        'asset_type': asset_type,
        'confirm_date': confirm_date,
        'quantity': 0,
        'price': 0,
        'fee': 0,
        'status': 'success',
        'entry_status': 'orphan',
        'position_name': (payload.get('position_name') or '').strip() or '未命名',
        'symbol': (payload.get('symbol') or '').strip() or None,
        'source': source,
        'notes': (payload.get('notes') or '').strip() or None,
        'family_id': family_id,
        'extra': json.dumps(extra, ensure_ascii=False),
    }


def create_flows(db: Session, family_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """补录一笔（或「到期回款」组合），返回新建 / 已存在的流水 id。

    幂等：同一 `client_token` 重放命中既有 `import_hash` 时直接复用（不重复落行）。
    `import_hash` 用 `cash_like|manual|<token>[|principal|interest]` 独立命名空间，
    **不重算**任何既有行的哈希（`uq_txn_import_hash` 是 ledger 级复合唯一索引）。
    """
    kind = payload.get('kind', 'buy')
    if kind not in FLOW_KINDS:
        raise ValueError(f'不支持的补录类型: {kind}')
    amount_cents = _amount_cents(payload.get('amount'))
    common = _common_create_kwargs(db, family_id, payload)
    token = (payload.get('client_token') or '').strip() or uuid.uuid4().hex
    specs: list[tuple[str, int, str]] = []
    if kind == 'repayment':
        specs.append(('sell', amount_cents, f'{token}|principal'))
        interest = payload.get('interest')
        if interest not in (None, '', 0, 0.0):
            specs.append(('dividend_cash', _amount_cents(interest, 'interest'), f'{token}|interest'))
    else:
        specs.append((kind, amount_cents, token))

    created: list[Transaction] = []
    reused: list[int] = []
    for txn_type, cents, suffix in specs:
        import_hash = f'{IMPORT_HASH_PREFIX}{suffix}'
        existing = (
            db.query(Transaction)
            .filter(Transaction.family_id == family_id, Transaction.import_hash == import_hash)
            .first()
        )
        if existing is not None:
            reused.append(existing.id)
            continue
        created.append(
            TransactionService.create(
                db,
                **common,
                txn_type=txn_type,
                amount=cents,
                import_hash=import_hash,
            )
        )
    db.flush()
    ids = reused + [t.id for t in created]
    logger.info('类现金补录: kind={} ledger={} new={} reused={}', kind, common['ledger_id'], len(created), len(reused))
    return {'ids': ids, 'created': len(created), 'reused': len(reused), 'kind': kind}


def _find_editable(db: Session, family_id: int, txn_id: int) -> Transaction:
    txn = (
        db.query(Transaction)
        .filter(
            Transaction.id == txn_id,
            Transaction.family_id == family_id,
            Transaction.asset_type.in_(CASH_LIKE_ASSET_TYPES),
        )
        .first()
    )
    if txn is None:
        raise ValueError('流水不存在或不是账外类现金流水')
    if txn.position_id is not None:
        raise ValueError('该流水已归置到持仓，请先撤销归置再编辑 / 删除')
    return txn


def _apply_edit_field(txn: Transaction, extra: dict[str, Any], field: str, value: Any, payload: dict[str, Any]) -> None:
    """单字段写入。拆出来让 `update_flow` 与字段分派各自的圈复杂度都留在预算内。"""
    if field == 'amount':
        txn.amount = _amount_cents(value)
    elif field == 'confirm_date':
        txn.confirm_date = _parse_date(value, 'confirm_date')
    elif field == 'trade_date':
        # D99：只接受用户单笔显式手填；留空＝不改，绝不从 confirm_date 派生回填。
        if value not in (None, ''):
            txn.trade_date = datetime.combine(_parse_date(value, 'trade_date'), datetime.min.time())
    elif field == 'txn_type':
        if value not in FLOW_KINDS or value == 'repayment':
            raise ValueError(f'不支持的流水类型: {value}')
        txn.txn_type = value
    elif field == 'symbol':
        txn.symbol = str(value).strip() or None
        extra.pop(SYMBOL_SOURCE_KEY, None)
        if txn.symbol:
            extra[SYMBOL_SOURCE_KEY] = 'inferred_from_position' if payload.get('symbol_inferred') else 'user'
    elif field == 'source':
        source = str(value).strip() or None
        if source is not None and source not in POSITION_SOURCE_LABELS:
            raise ValueError(f'非法来源 source={source!r}')
        txn.source = source
    else:
        setattr(txn, field, (str(value).strip() or None) if field == 'notes' else str(value).strip())


def update_flow(db: Session, family_id: int, txn_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """单笔编辑。**不动** `import_hash` / `position_id` / `asset_type` / `ledger_id`。

    ⚠️ 与 `ledger_write_svc.update_ledger_transaction` 刻意分开：那个函数在任一
    字段被改动时清空 `import_hash`（去重不变式被破坏），且表单字段是持仓型的，
    不适合类现金流水。
    """
    forbidden = [k for k in FORBIDDEN_FIELDS if k in payload]
    if forbidden:
        raise ValueError(f'以下字段不可修改: {", ".join(forbidden)}')
    touched = [f for f in EDITABLE_FIELDS if f in payload and not (f == 'trade_date' and payload[f] in (None, ''))]
    if not touched:
        raise ValueError('没有可更新的字段')
    txn = _find_editable(db, family_id, txn_id)
    extra = _load_extra(txn)
    for field in touched:
        _apply_edit_field(txn, extra, field, payload[field], payload)
    _save_extra(txn, extra)
    db.flush()
    return _row(txn)


def delete_flow(db: Session, family_id: int, txn_id: int) -> None:
    """删除单笔未归置流水。孤儿行 `position_id IS NULL`，不触发持仓份额重算。"""
    txn = _find_editable(db, family_id, txn_id)
    db.delete(txn)
    db.flush()


def _batch(db: Session, family_id: int, ids: list[Any]) -> list[Transaction]:
    if not ids:
        raise ValueError('transaction_ids 不能为空')
    if len(ids) > MAX_BATCH:
        raise ValueError(f'单次最多处理 {MAX_BATCH} 笔')
    try:
        id_list = [int(i) for i in ids]
    except (TypeError, ValueError) as e:
        raise ValueError('transaction_ids 必须是整数列表') from e
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.id.in_(id_list),
            Transaction.family_id == family_id,
            Transaction.asset_type.in_(CASH_LIKE_ASSET_TYPES),
        )
        .all()
    )
    if len(rows) != len(set(id_list)):
        raise ValueError('部分流水不存在、重复或不是账外类现金流水')
    return rows


def reconcile_flows(db: Session, family_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """归置 / 撤销归置一批流水，表达「这批流水已由某持仓体现」。

    - `attach`：只把 `position_id` 指向目标持仓 + 写 `extra` 审计标记。
      不改 amount / trade_date / symbol / import_hash；流水因此退出孤儿净额桶，
      `summary_service` 四处消费方自动收敛 ⇒ 不再是「两笔钱」。
    - `detach`：把 `position_id` 置回 NULL + 清标记，流水重回孤儿净额桶。

    目标持仓不做 symbol 硬校验：真库 158 笔 `symbol` 为空，按 symbol 匹配
    会把绝大多数流水挡在门外；由用户在候选列表里显式挑目标，语义更诚实。
    """
    action = payload.get('action')
    if action not in ('attach', 'detach'):
        raise ValueError("action 须为 'attach' 或 'detach'")
    rows = _batch(db, family_id, payload.get('transaction_ids') or [])
    target: Position | None = None
    if action == 'attach':
        target_id = payload.get('target_position_id')
        if target_id is None:
            raise ValueError('归置缺少 target_position_id')
        target = db.query(Position).filter(Position.id == int(target_id), Position.family_id == family_id).first()
        if target is None:
            raise ValueError('目标持仓不存在或无权访问')
        if any(t.position_id is not None for t in rows):
            raise ValueError('所选流水中有已归置项，请先撤销归置')
    else:
        if not all(_load_extra(t).get(RECONCILED_KEY) for t in rows):
            raise ValueError('只能撤销带归置标记的流水')

    stamp = datetime.now().isoformat(timespec='seconds')
    for txn in rows:
        extra = _load_extra(txn)
        if action == 'attach':
            txn.position_id = target.id
            extra[RECONCILED_KEY] = {
                'position_id': target.id,
                'position_name': target.name or '',
                'at': stamp,
            }
        else:
            txn.position_id = None
            extra.pop(RECONCILED_KEY, None)
        _save_extra(txn, extra)
    db.flush()
    logger.info('类现金归置: action={} count={} target={}', action, len(rows), target.id if target else None)
    return {
        'changed': len(rows),
        'action': action,
        'target_position_id': target.id if target else None,
        'target_position_name': target.name if target else None,
    }
