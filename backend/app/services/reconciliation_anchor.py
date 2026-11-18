# -*- coding: utf-8 -*-
"""对账工作台的「以此为准」写锚点动作（#3125 A 方案）。

## 为什么需要它（#3127 修订了适用范围）

域 B 的存量数量差异里，有一部分来自**无锚点持仓**（`snapshot_quantity IS NULL`）：
持仓份额来自券商快照，流水是另一条独立记录，缺基准时两者本来就不该互校。
对这部分，正确动作不是「补录这笔」——那等于让用户编造一笔不存在的交易去凑数；
而是「承认当前持仓为准」：写一条**人工锚点**，此后只核对锚点日之后的流水。

⚠️ 初版把 119 条整体判成「缺基准」（理由：101 条理论值 0、4 条为负，像是流水
没覆盖建仓）。#3127 用审计日志证伪了：**理论值 0 的那批是 `dangling_ref_rebuild`
只重建买入腿留下的幽灵持仓，份额是真错**，#3128 已按流水重算清仓；理论值为负的
超卖形态同样不能一键固化。故本动作只服务「流水净额 > 0、覆盖不全」这一支，
判据见 `reconciliation_theory.flow_disproves_position`（检测与动作共用）。

## 为什么不新增写库路径

`kind='set'` 已经是写人工锚点的唯一入口（`upsert_from_holding` + `anchor_kind=manual`
+ `allow_anchor_rewind=True`）。本动作与它的区别只有一个：**份额与成本取持仓当前值，
不由用户手填**。这不是新语义，是同一语义的「免手抄」形式——这类差异逐条手抄成本价，
等于把锚点债原样摊回给用户。

## 为什么不复用 `apply_decision` 的 set 分支

set 分支要求 payload 带 `quantity` 与 `avg_price`，而差异行只有份额（`actual_value`），
没有成本价。让它代劳要么让前端多取一次持仓（多一个失败点），要么让用户手填（正是要
避免的）。这里直接读持仓，两条都省掉；失败情形一律给出「改用哪个入口」的具体指引。

## 为什么写之前要重新判一次（#3127）

差异卡片是**某次 run** 生成的，用户点「以此为准」是之后的事，中间持仓/流水可能被
别的链路改过（真库实测：两次对账之间 #3128 把 101 条幽灵持仓重算成清仓）。所以不能
信任卡片类型，必须在写库这一刻用与检测同源的 `flow_disproves_position` 重新判：
流水净额 ≤ 0 而账上仍有份额 ⇒ 拒绝，指向「核对流水 / 按账单填 0」。少这一层就会把
#3127 已证明的真错固化成人工锚点，且 `anchor_kind=manual` 还会挡住后续快照覆盖。
（2026-11-16 起不再指向「按流水重算份额」：那条路已经被闸门挡住，不能再拿流水清仓。）
"""

from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import AnchorKind, PositionSource
from app.core.money import Money
from app.core.time_utils import today_shanghai
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.position_write_support import _find_existing_position
from app.services.reconciliation_theory import flow_disproves_position


def write_anchor_from_position(
    db: Session,
    family_id: int,
    disc,
) -> Position:
    """把差异对应持仓的**当前份额与成本**写成人工锚点，返回写入后的持仓。

    语义边界（三条都不是可选项）：

    1. **不改份额数值**：写入值就是持仓现值，`compute_anchored_state` 之后
       `quantity = 快照值 + Σ(归属日 > 快照日)`，锚点日取今天 ⇒ 今天之后无流水 ⇒ 不变。
       若真有未来确认日的流水，那不是「被改动」，是它们本来就还没反映在快照里。
    2. **`anchor_kind=manual`**：同日的外部快照不得覆盖用户的显式校准；
    3. **`allow_anchor_rewind=True`**：这是用户「以此刻为准」的人工校准，不属于「导入
       更旧的快照」，与 set 分支同理（守卫 docstring 已注明该参数只服务人工校准入口）。
    """
    if disc is None:
        raise ValueError('「以此为准」必须指定一条差异')
    if disc.ledger_id is None:
        raise ValueError('这条差异没有归入任何账本，无法写持仓基准。先归置账本再处理')
    if not disc.symbol:
        raise ValueError('这条差异没有标的，无法写持仓基准')

    position = _find_existing_position(db, disc.ledger_id, family_id, disc.symbol, '')
    if position is None:
        raise ValueError('找不到这只持仓（可能已被删除）。请改用「修正数据 → 按流水重建持仓」')
    if position.quantity <= 0:
        raise ValueError('这只持仓当前份额为 0，不能作为基准。请改用「按流水重建持仓」')
    if not position.avg_price:
        raise ValueError('这只持仓没有成本价，无法写基准。请改用「把持仓改成」并填成本单价')

    # 与域 B 检测同源的时点防线：卡片可能已过时，此处按**当前**流水重新判。
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            Transaction.ledger_id == disc.ledger_id,
            Transaction.symbol == disc.symbol,
        )
        .all()
    )
    if flow_disproves_position(txns, position):
        raise ValueError(
            '流水显示这只标的已经卖完或超卖，账上却仍有份额——这可能是流水缺了买入腿，'
            '也可能是持仓确实已清仓，系统分不清，所以不能把当前份额固定成基准。'
            '请先到「交易记录」核对流水；若账单确认已经没有这只，用「改成账单份额」填 0'
        )

    data = {
        'symbol': position.symbol,
        'ledger_id': position.ledger_id,
        'family_id': family_id,
        'quantity': Money.min_unit_to_shares(position.quantity),
        'avg_price': Money.price_units_to_yuan(position.avg_price),
        'snapshot_date': today_shanghai(),
        'anchor_kind': AnchorKind.MANUAL.value,
        'source': PositionSource.RECONCILIATION_ADJUSTMENT.value,
    }
    logger.info(
        '对账写锚点: family={} position={} symbol={} qty={} avg_price={}',
        family_id,
        position.id,
        position.symbol,
        data['quantity'],
        data['avg_price'],
    )
    # 延迟导入：position_service 在模块级导入本模块所属的对账链路之外的服务，
    # 顶层导入会在 position_service ←→ reconciliation_service 之间成环。
    from app.services.position_service import PositionService  # noqa: PLC0415

    return PositionService.upsert_from_holding(db, data, allow_anchor_rewind=True)


def anchor_after_payload(position: Optional[Position]) -> dict:
    """写锚点后的审计快照（与 set 分支的 after 同形，便于对账日志统一解读）。"""
    if position is None:
        return {}
    return {
        'position_id': position.id,
        'symbol': position.symbol,
        'quantity': position.quantity,
        'avg_price': position.avg_price,
        'snapshot_quantity': position.snapshot_quantity,
        'snapshot_date': str(position.snapshot_date) if position.snapshot_date else None,
        'anchor_kind': position.anchor_kind,
    }
