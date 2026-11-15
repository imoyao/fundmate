# -*- coding: utf-8 -*-
"""对账工作台的**数据可信闸门**（三处「说的和事实不一致」）。

## 一、域 C 的孤儿卡只在导入时重算 ⇒ 修完数据卡还在

域 C 由「导入 commit 后自动触发」产生（`run_reconciliation(..., DOMAIN_C)`），
判据与域 B 的孤儿检测是同一个（`reconciliation_theory.find_holding`）：流水净额 > 0
但没有持仓行。可是数据修复（补全归属、按流水重建持仓、挂回、删除流水）**不会**触发
域 C 重算，于是卡片永远停在导入那一刻。

真库实测（2026-11-15）：`pending` 的域 C 孤儿卡 94 张，逐张复核**全部已不成立**
（那些代码现在都有持仓，或流水净额已归零）。用户在「孤儿流水」页看见的是一批
早已修好的东西 —— 与「数据又矛盾了」是同一类故障。

修法：域 B 的 run 覆盖「所有有流水的 (ledger_id, symbol)」，是域 C 检测范围的超集，
故在域 B 的 run 末尾用**同一份结果**刷新域 C 的孤儿卡。这不是跨域污染：两张卡描述的
是同一个事实，只是一个按导入产生、一个按流水产生。

## 二、补录不查重 ⇒ 同一笔被记第二遍

差异卡只比「理论份额 vs 实际份额」两组数字，它不知道那笔卖出其实已经在库里
（只是挂错了代码）。用户照对账单再录一遍，`recompute_linked_discrepancy` 只看聚合计
有没有轧平 ⇒ 差异「消失」（假修复）⇒ 下一张卡。2026-11-15 的 8 对重复行就是这么来的。

修法：补录（`kind='increment'`）落地前查「同账本 + 同标的 + 同类型 + 同日 + 同数量 +
同单价」的既有流水，命中即拒绝并给出流水 id。**只拦补录**：常规「记一笔」不拦
（同一天同价成交两笔是真实业务），补录是修差异，重复必然是错。

## 三、同标的还有流水缺归属时补录 ⇒ 双计

今天那 8 对的根因不是手滑：114 个标的的流水被写成同一个代码，域 B 按
`(账本, 代码)` 聚合时，每个真实代码的桶「只有买入没有卖出」，于是差异卡建议补一笔
卖出 —— 而那批卖出正躺在悬空流水里（挂错的代码甚至完全不同，`127078` vs `SZ127033`）。

修法：补录前查同账本悬空流水里有没有**同一标的**的（代码归一后相同，或标的名相同）。
命中即拒绝并指向「修正数据 · 悬空流水」。名称匹配是必需的那一半：挂错的代码可能
是另一只标的的代码，逐字比或比归一码都看不见它。
"""

from sqlalchemy.orm import Session  # noqa: F401  （类型标注用，运行时不参与）

from app.core.money import Money
from app.domains.positions.models import Position  # noqa: F401  （查询构造用）
from app.domains.reconciliation.models import ReconciliationDiscrepancy
from app.domains.transactions.models import Transaction
from app.services.dangling_identity import dangling_condition, same_identity

_DOMAIN_C = 'C'
_ORPHAN = 'orphan'
#: 「同日同量同价」判重时最多提示的既有流水条数（提示文案不刷屏）
_SAMPLE_LIMIT = 3


def refresh_domain_c_orphans(
    db: Session, family_id: int, run_id: int, orphan_qty: dict[tuple, int], summary: dict
) -> int:
    """用域 B 本次的孤儿实测结果刷新域 C 的孤儿卡；返回清掉的条数。

    `orphan_qty` 是 `{(ledger_id, symbol): 理论份额}`，只含本次**仍然**成立的孤儿；
    不在其中的域 C 待处理卡一律置 cleared（它们描述的事实已不存在）。

    只动 `pending`：`ignored`（含永久忽略）是用户裁决，系统不替他翻案。
    """
    rows = (
        db.query(ReconciliationDiscrepancy)
        .filter(
            ReconciliationDiscrepancy.family_id == family_id,
            ReconciliationDiscrepancy.domain == _DOMAIN_C,
            ReconciliationDiscrepancy.status == 'pending',
        )
        .all()
    )
    cleared = 0
    for d in rows:
        qty = orphan_qty.get((d.ledger_id, d.symbol))
        if qty is None:
            d.status = 'cleared'
            cleared += 1
        else:
            d.expected_value = qty
            d.actual_value = 0
            d.diff = qty
        d.last_run_id = run_id
    if cleared:
        summary['cleared'] = summary.get('cleared', 0) + cleared
    db.flush()
    return cleared


def _duplicate_of(db: Session, family_id: int, data: dict) -> Transaction | None:
    """找「同账本 + 同标的 + 同类型 + 同日 + 同数量 + 同单价」的既有流水。

    缺日期或缺数量的一律不判（这类补录是纯现金事件，`0` 会把所有分红记成一类）。
    """
    symbol = (data.get('symbol') or '').strip()
    confirm_date = data.get('confirm_date')
    qty_units = Money.shares_to_min_unit(data.get('quantity'))
    price_units = Money.yuan_to_price_units(data.get('avg_price'))
    if not symbol or confirm_date is None or qty_units <= 0:
        return None
    return (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            Transaction.ledger_id == data.get('ledger_id'),
            Transaction.symbol == symbol,
            Transaction.txn_type == data.get('op_type'),
            Transaction.confirm_date == confirm_date,
            Transaction.quantity == qty_units,
            Transaction.price == price_units,
        )
        .order_by(Transaction.id)
        .first()
    )


def _dangling_same_identity(db: Session, family_id: int, data: dict) -> list[Transaction]:
    """同账本悬空流水里「同一标的」的那些（代码归一相同，或标的名相同）。"""
    ledger_id = data.get('ledger_id')
    symbol = (data.get('symbol') or '').strip()
    if ledger_id is None or not symbol:
        return []
    rows = (
        db.query(Transaction)
        .filter(dangling_condition(family_id), Transaction.ledger_id == ledger_id)
        .order_by(Transaction.id)
        .all()
    )
    if not rows:
        return []
    own_name = _position_name(db, family_id, ledger_id, symbol)
    hits = []
    for t in rows:
        if same_identity(t.symbol, t.asset_type, symbol, data.get('asset_type')):
            hits.append(t)
            continue
        name = (t.position_name or '').strip()
        if own_name and name and name == own_name:
            hits.append(t)
    return hits


def _position_name(db: Session, family_id: int, ledger_id: int, symbol: str) -> str:
    """该标的在本账本的显示名（用于按名字认出「挂错代码」的悬空流水）。"""
    row = (
        db.query(Position.name)
        .filter(
            Position.family_id == family_id,
            Position.ledger_id == ledger_id,
            Position.symbol == symbol,
            Position.name.isnot(None),
        )
        .first()
    )
    return (row[0] or '').strip() if row else ''


def assert_supplement_is_new(db: Session, family_id: int, data: dict) -> None:
    """补录（对账增量裁决）落地前的两道闸门，命中即抛 `ValueError`。

    顺序有意义：先判「这笔已经在库里」（最确定、最好修：去交易记录改那一笔），
    再判「这个标的还有流水缺归属」（要先去修正数据）。
    """
    dup = _duplicate_of(db, family_id, data)
    if dup is not None:
        raise ValueError(
            f'这笔已经记过了：流水 #{dup.id}（{dup.confirm_date} {dup.txn_type} '
            f'{Money.min_unit_to_shares(dup.quantity)} 份 @ {Money.price_units_to_yuan(dup.price)} 元）。'
            '重复录入会把同一笔经济事件记两遍（卖出双计、盈亏失真）；'
            '若那一笔本身有误，请到「交易记录」改它，不要在这里再录一笔。'
        )

    hits = _dangling_same_identity(db, family_id, data)
    if hits:
        sample = '、'.join(f'#{t.id}' for t in hits[:_SAMPLE_LIMIT])
        more = '' if len(hits) <= _SAMPLE_LIMIT else f' 等 {len(hits)} 条'
        raise ValueError(
            f'{data.get("symbol")} 在这个账户还有 {len(hits)} 条流水没挂到持仓上（{sample}{more}）。'
            '这些流水很可能就是这笔买卖的原始记录，先补录会造成重复记账。'
            '请到「修正数据 · 悬空流水」把它们挂回或删除，再回来核对差异。'
        )
