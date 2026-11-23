# -*- coding: utf-8 -*-
"""#3126「无归属流水」的只读暴露（不进域 F / 域 G / 归置的第三类界外流水）。

## 背景（真库 2026-11-15 实测，勿再推断）

254 条流水 ``symbol`` 为空且 ``position_id IS NULL``，在界面上完全不可见：

- 不进对账、不进域 F（``dangling_condition`` 要求 ``position_id IS NOT NULL``）；
- 不进域 G（``orphan_ledger_service`` 要求 ``ledger_id IS NULL``）；
- 不进「归置」（``orphan_coverage_service`` 只收 ``money_fund`` / ``reverse_repo``）。

其中 ``quantity != 0`` 的 10 条（9 笔基金卖出 + 1 笔转债兑付，``position_name`` 已填、
``asset_type`` 为 NULL、账本非空）意味着**历史卖出凭空消失**：持仓页份额、流水页
归属都对得上，唯独这批卖出的出账没有任何地方承接。

## 判据（谓词在 ``dangling_identity.unowned_condition``，本模块只消费）

逐条理由见该函数 docstring，此处只强调一条：**谓词刻意不看 ``symbol``**——补全
标的（``/dangling-refs/enrich/``）之后该行必须仍留在本清单，夜间回填会按
「同账本同标的」把它自动挂回持仓；谓词若看 symbol，补全动作会让它再次凭空消失。

## 写路径边界（与域 F 的区别，必须守住）

本模块**只有只读扫描**。unowned 行可走的写路径有三条：``enrich``（补全标的）、
``delete``（显式删除）与 ``rebuild``（按流水重建持仓）——后两者都靠
``_load_dangling_by_ids(..., include_unowned=True)`` 放行。``rebuild`` 的业务准入在
``dangling_ref_rebuild_service.plan_rebuild``：净额 > 0 且同账本无同标的持仓才成立
（净额 ≤ 0 只能删除，有同标的持仓行走夜间回填）。``reattach`` / ``mislink`` 仍按默认
口径（只认悬空）拒绝；``fixable`` 恒为 ``False``——``rebuild`` 可用不等于 ``fixable``。

## 事务边界

与同域其它服务同构：调用方传入 ``db``，本模块纯只读、不 ``flush`` 不 ``commit``。
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.dangling_identity import (
    display_name,
    identity_count,
    name_symbol_index,
    position_candidates,
    unowned_condition,
)

# 同包内部复用既有 helper 是本域既有风格（dangling_ref_mislink_service 同款）；
# 不复制净额 / 批次 / 序列化逻辑，保证两个清单的数字口径一致。
from app.services.dangling_ref_service import (
    _build_batches,
    _net_min_units,
    _shares,
    _txn_brief,
)

#: 组级说明不预设单一修法：写死「只能补全标的或删除」在 rebuild 放开后就是假话；
#: 「补全后自动挂回」由 flag ``auto_attach_after_enrich`` 表达（仅同账本唯一持仓时成立）。
_UNOWNED_BLOCK_REASON = '没有挂到任何持仓上：按组补全标的、按流水重建持仓或删除'


def _unowned_flags(symbol: str, cands: list[Position]) -> list[str]:
    """组标签：只给用户还不知道的两件事（缺代码 / 有没有可挂回的持仓）。

    刻意不产出 ``unowned``（身份由组字段给）与 ``has_symbol``（卡标题已显示代码）；
    ``candidates`` 恒空——列出候选会诱导用户去找一个不存在的挂回按钮。
    """
    flags = []
    if not symbol:
        flags.append('no_symbol')
    if len(cands) == 1:
        flags.append('auto_attach_after_enrich')
    elif not cands:
        flags.append('no_candidate')
    return flags


def _build_group(
    ledger_id,
    symbol: str,
    txns: list[Transaction],
    ledger_positions: list[Position],
    first_batch_id: int,
    batch_label: str,
    name_index: dict[str, set[str]],
) -> dict:
    """组装单个无归属分组；形状与域 F 的 ``DanglingRefGroup`` 结构兼容（前端同一张卡复用）。

    ``fixable`` 恒 ``False``、``dangling_position_ids`` 恒空（本类按定义
    ``position_id`` 全空）、``live_position`` / ``candidates`` 恒空——这三处不是
    忘了填，而是本类语义：没有持仓可挂、没有回补动作。
    """
    cands, _live = position_candidates(ledger_positions, symbol, txns[0].asset_type)
    identity = identity_count(txns, name_index)
    one_name = next((t.position_name for t in txns if t.position_name), None)
    name_key = (txns[0].position_name or '').strip() if not symbol else ''
    return {
        'key': f'unowned|{ledger_id}|{symbol}',
        'group_id': f'unowned|{ledger_id}|{symbol}|{name_key}' if name_key else f'unowned|{ledger_id}|{symbol}',
        'ledger_id': ledger_id,
        'symbol': symbol,
        'display_name': display_name(one_name, identity),
        'identity_count': identity,
        'txn_count': len(txns),
        'dangling_position_ids': [],
        'net_units': _shares(_net_min_units(txns)),
        'live_position': None,
        'candidates': [],
        'batch_id': first_batch_id,
        'batch_label': batch_label,
        'flags': _unowned_flags(symbol, cands),
        'fixable': False,
        'block_reason': _UNOWNED_BLOCK_REASON,
        'unowned': True,
        'transactions': [_txn_brief(t) for t in txns],
    }


def scan_unowned_flows(db: Session, family_id: int) -> dict:
    """列出当前家庭全部「无持仓承接」的流水（GET /dangling-refs/unowned/ 的数据源，纯只读）。

    返回结构与 ``scan_dangling_refs`` 同构（``total / group_count / batch_count /
    null_symbol / null_trade_date / fixable_count / groups / batches``），前端在同一
    loader 里合并；``fixable_count`` 恒 0（本类没有回补动作，如实显示，不假装可修）。
    """
    rows_unsorted = db.query(Transaction).filter(unowned_condition(family_id)).all()
    total = len(rows_unsorted)
    null_symbol = sum(1 for t in rows_unsorted if not t.symbol)
    null_trade_date = sum(1 for t in rows_unsorted if t.trade_date is None)

    rows = sorted(rows_unsorted, key=lambda t: (t.created_at is None, t.created_at or datetime.min, t.id))
    batches, txn_to_batch, batch_labels = _build_batches(rows)
    by_ledger = defaultdict(list)
    for p in db.query(Position).filter(Position.family_id == family_id).order_by(Position.id).all():
        by_ledger[p.ledger_id].append(p)
    name_index = name_symbol_index(db, family_id)

    # 分组键与 scan_dangling_refs 的缺码口径一致：(ledger, symbol or '', 标的名)。
    # symbol 为空时再按标的名拆——缺码的 9 笔卖出各自是不同标的，并成一组会被
    # 一次补全刷成同一代码（293 条 114 个标的事故的同款形态）。
    grouped = defaultdict(list)
    for t in rows:
        name_key = '' if t.symbol else (t.position_name or '').strip()
        grouped[(t.ledger_id, t.symbol or '', name_key)].append(t)

    groups = []
    for (ledger_id, symbol, _name_key), txns in grouped.items():
        # 组取组内最早一条流水所属批次（组内按 created_at 升序），与域 F 同口径。
        first_batch_id = txn_to_batch[txns[0].id]
        groups.append(
            _build_group(
                ledger_id,
                symbol,
                txns,
                by_ledger.get(ledger_id, []),
                first_batch_id,
                batch_labels[first_batch_id],
                name_index,
            )
        )

    return {
        'total': total,
        'group_count': len(groups),
        'batch_count': len(batches),
        'null_symbol': null_symbol,
        'null_trade_date': null_trade_date,
        'fixable_count': 0,
        'groups': groups,
        'batches': batches,
    }
