# -*- coding: utf-8 -*-
"""持仓**债券兑付命令**（到期还本付息 / 强赎 / 回售，#2832）。

`PositionService.process_bond_redeem` 曾是 128 行、圈复杂度 26 的方法（第六抽收尾后
`position_service.py` 里最大的函数）。它与卖出命令形似而神不同——差异全在「金额从哪来」
和「校验失败怎么办」这两件事上，混在卖出路径里会被下一次重构顺手抹平。

    解析校验（金额口径 + 单价反算 + 数量校验 + 已实现盈亏）
      → 扣减/清仓 → 落流水 + 自选对齐

## 与卖出路径的三处刻意不同

1. **金额口径是「到账净额」而不是「价格 × 数量」**。交割单兑付行的「发生金额」＝面值 +
   应计利息 − 代扣费，而 `price` 只是券商给的成交均价（通常等于面值 100）。付息 / 强赎
   溢价时两者本来不等，若照卖出路径用 `price × qty` 记金额，利息会被静默丢掉——用户看到
   「到账 1035，账面 1000」。详见 `pnl_service.compute_redeem_realized_cents`。
2. **已实现盈亏不再减 fee**：`amount` 已经是扣费后的净额（同花顺 / 东财的「发生金额」口径
   一致），再减一次是双扣。卖出路径的 `amount` 是毛额，所以那边必须减，两个口径不能
   互相套用。
3. **份额不足直接报错，不降级成孤儿**：兑付量 > 持仓量只可能是买入流水缺失（或上次只导了
   兑付没导买入），静默记孤儿会把差额藏起来——用户看到的是「钱到账了，持仓还在」。让这一
   行进 `commit_errors` / 400 让人看见，比记一笔谁也不会去核的孤儿流水有用。卖出路径的降级
   是历史遗留（真实库 649 笔卖出无 symbol 可匹配），兑付没有那个包袱。

## 顺序是这条链路的一部分

1. **金额三级回退**：`net_amount`（交割单发生金额）→ `amount`（手动记账实收）→
   `price × qty`。前两者都是「实收」，只有都缺时才退回乘法——顺序反了会把利息丢掉；
2. **单价缺失时按到账额 ÷ 份数反算**：兑付行常常只给发生金额、不给成交均价。不反算的话
   「金额 / 单价 / 数量」三者不自洽，前端在金额列旁展开时会显示 0 单价。换算一律走
   `Money` 的既有链路，不手推「分 × 份额最小单位 × 价格单位」的系数（那三个 10_000 / 100
   混乘极易差两个数量级，测试里也看不出来）；
3. **`covered_by_anchor` 在任何扣减之前判**：若这笔记兑付已含在快照里（`confirm_date`
   <= 锚点日），快照份额已反映它，不再扣减；流水照落——它确实是发生过的业务事实。它同时
   **豁免**数量校验（那笔兑付已经发生过了）；
4. **`realized_cents` 在扣减之前算**：用扣减前的 `avg_price`，与卖出同口径；
5. **清仓不删行**（#2343）：`mark_position_cleared` 打 `ownership_status='cleared'` +
   `cleared_at`，锚点与成本基线原样留存；**清仓仍返回 `None`**，调用方契约不动。

## 依赖方向

`position_service` 在模块级导入本模块（转发薄壳）；本模块只在**函数内**延迟导入主模块的
`_silent_reconcile_watchlist`（买入 / 卖出 / 快照 / 兑付四条路径都要用它，留主模块才不制造
双向依赖）。与 `position_buy_command` / `position_sell_command` / `position_snapshot_command`
同一范式。

## 刻意不做的事

- **不套用卖出的批次校验**：兑付是到期事件，不存在「先进先出挑批次」的选择空间；
- **不自动申购回款**：兑付到账是现金，与卖出回款（#1137 可选自动申购货基）语义不同，
  用户拿到兑付款有别的用途；
- **异常日志只盖写阶段**：`resolve_redeem_intent` 的校验失败（持仓不存在、数量 <= 0、
  份额不足）照旧**不**打 `logger.exception`——那是数据 / 用户输入问题，不是系统故障。
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Union

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import PositionSource
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.positions.state import is_covered_by_anchor, mark_position_cleared
from app.services.pnl_service import compute_redeem_realized_cents
from app.services.position_write_support import (
    _fee_breakdown_kwargs,
    _get_asset_type,
    _resolve_family_id,
    _resolve_fund_name_by_code,
    _resolve_ledger_name_by_id,
)
from app.services.trading import TransactionService

DateLike = Union[date, datetime, str, None]


@dataclass(frozen=True)
class RedeemIntent:
    """一次兑付的**已校验**输入与派生量（段间唯一真相源）。

    刻意带着 ORM 行 `position`：frozen 只冻结字段绑定，不冻结对象本身。同一 Session 的
    identity map 保证 `apply_redeem_to_position` 与 `write_redeem_transaction` 拿到同一实例，
    避免「二次查询 → 二次判定 → 两段看到不同状态」。

    刻意**不**带 `position_name` / `account_name`：它们要靠写阶段的自愈回填才能确定
    （快照缺名称 / 账户时按 ID 反查），提前算出来会让「回填」与「取用」分处两段。
    """

    position: Position
    family_id: int
    quantity_units: int
    amount_cents: int
    price_units: int
    fee_cents: int
    realized_cents: int
    covered_by_anchor: bool
    symbol: str
    trade_date: DateLike
    confirm_date: DateLike
    link_group_id: Optional[str]
    notes: str
    import_hash: Optional[str]
    source: str
    # 费用拆分四列（#2137）：`_fee_breakdown_kwargs` 已做完四键齐全校验与元 → 分换算。
    fee_breakdown: dict = field(default_factory=dict)


def resolve_redeem_intent(db: Session, data: dict) -> RedeemIntent:
    """解析并校验兑付输入，产出 `RedeemIntent`。**不含任何写操作**。

    金额三级回退、单价反算、锚点覆盖判定、数量校验、已实现盈亏都在这段完成，且全部在
    写阶段之前——任何一条校验失败都不该留下半条写入痕迹。
    """
    position_id = data.get('position_id')
    family_id = _resolve_family_id(data)
    position = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
    if not position:
        raise ValueError('指定的持仓不存在')

    qty_shares = data.get('quantity') or 0
    qty_units = Money.shares_to_min_unit(qty_shares)
    if qty_units <= 0:
        raise ValueError('兑付数量必须大于 0')

    # 金额三级回退：net_amount（交割单发生金额）→ amount（手动记账实收）→ 价格 × 数量
    raw_amount = data.get('net_amount')
    if raw_amount is None:
        raw_amount = data.get('amount')
    price_units = Money.yuan_to_price_units(data.get('avg_price') or 0)
    if raw_amount is None:
        amount_cents = Money.multiply_price_quantity(price_units, qty_units)
    else:
        amount_cents = Money.yuan_to_cents(abs(raw_amount))

    # 均价缺失（兑付行常常只给发生金额、不给成交均价）：按到账额 ÷ 份数反算，
    # 让「金额 / 单价 / 数量」三者自洽，前端在金额列旁展开时才不会显示 0 单价。
    if price_units <= 0 and qty_units > 0:
        per_share_yuan = Money.cents_to_yuan(amount_cents) / Money.min_unit_to_shares(qty_units)
        price_units = Money.yuan_to_price_units(per_share_yuan)

    fee_cents = Money.yuan_to_cents(data.get('fee') or 0)

    # 锚点判定与卖出同口径：若这笔记兑付已含在快照里（confirm_date <= 锚点日），
    # 快照份额已反映它，不再扣减；流水照落（它确实是发生过的业务事实）。
    covered_by_anchor = is_covered_by_anchor(position, data.get('confirm_date'))
    if not covered_by_anchor and position.quantity < qty_units:
        raise ValueError(
            f'兑付数量超过持仓：当前持有 {Money.min_unit_to_shares(position.quantity)}，'
            f'本次兑付 {qty_shares}。请检查买入流水是否已完整导入'
        )

    # 必须在扣减之前算：用扣减前的 avg_price，与卖出路径 #1183 同口径。
    realized_cents = compute_redeem_realized_cents(
        amount_cents=amount_cents,
        avg_price_units=position.avg_price or 0,
        qty_units=qty_units,
    )

    return RedeemIntent(
        position=position,
        family_id=family_id,
        quantity_units=qty_units,
        amount_cents=amount_cents,
        price_units=price_units,
        fee_cents=fee_cents,
        realized_cents=realized_cents,
        covered_by_anchor=covered_by_anchor,
        symbol=data.get('symbol') or position.symbol,
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        link_group_id=data.get('link_group_id'),
        notes=data.get('notes') or '债券到期兑付',
        import_hash=data.get('import_hash'),
        source=data.get('source') or PositionSource.MANUAL.value,
        fee_breakdown=_fee_breakdown_kwargs(data),
    )


def apply_redeem_to_position(db: Session, intent: RedeemIntent) -> bool:
    """自愈回填 + 扣减份额 + 清仓标记，返回「是否已清仓」。

    自愈回填（快照缺名称 / 账户时按 ID 反查）放在本段而非上一段：它读的是「当前行」，
    与扣减同处一个写事务才不会被中间 flush 打断。
    """
    position = intent.position

    # 自愈回填（与卖出路径同口径）：快照缺名称 / 账户时按 ID 反查，绝不留 NULL
    if not position.name:
        position.name = _resolve_fund_name_by_code(db, position.symbol)
    if not position.account_name and position.ledger_id:
        position.account_name = _resolve_ledger_name_by_id(db, position.ledger_id)

    is_cleared = False
    if not intent.covered_by_anchor:
        position.quantity -= intent.quantity_units
        is_cleared = position.quantity == 0
        if is_cleared:
            # 清仓不清行（#2343）：锚点与成本基线原样留存，二次累加才不会复发。
            # `cleared_at` 取清仓流水的确认日（缺则交易日，再缺退墙钟），与卖出同口径。
            mark_position_cleared(position, intent.confirm_date or intent.trade_date)

    db.flush()
    return is_cleared


def write_redeem_transaction(db: Session, intent: RedeemIntent) -> None:
    """落兑付流水 + 对齐自选状态。

    品种取**持仓**而不是请求体（`fallback=position.asset_type`）：请求体不带 type 时若兜底
    成 stock，兑付流水会与买入分属两个身份键，清仓周期永远闭合不上。
    """
    # 函数内导入：该辅助同时服务买入 / 卖出 / 快照 / 兑付四条路径，留主模块才不制造双向依赖。
    from app.services.position_service import _silent_reconcile_watchlist  # noqa: PLC0415

    position = intent.position
    # 自愈回填的结果在写阶段才取：`apply_redeem_to_position` 可能刚填好名称 / 账户。
    position_name = position.name or _resolve_fund_name_by_code(db, position.symbol)
    account_name = position.account_name or _resolve_ledger_name_by_id(db, position.ledger_id)
    redeem_asset_type = _get_asset_type({'asset_type': position.asset_type}, fallback=position.asset_type)

    TransactionService.create(
        db=db,
        position_id=position.id,
        symbol=intent.symbol,
        txn_type='bond_redeem',
        trade_date=intent.trade_date,
        confirm_date=intent.confirm_date,
        asset_type=redeem_asset_type,
        link_group_id=intent.link_group_id,
        quantity=intent.quantity_units,
        price=intent.price_units,
        fee=intent.fee_cents,
        **intent.fee_breakdown,
        amount=intent.amount_cents,
        realized_pnl=intent.realized_cents,
        status='success',
        position_name=position_name,
        ledger_id=position.ledger_id,
        account_name=account_name,
        notes=intent.notes,
        import_hash=intent.import_hash,
        family_id=intent.family_id,
        # #1232 决策 11：流水来源透传（记一笔默认 manual）
        source=intent.source,
    )
    db.flush()
    # 兑付即退出持仓，与卖出 / 清仓后同样对齐自选状态（静默，失败不影响主链路）
    _silent_reconcile_watchlist(db, intent.family_id, position.symbol)


def run_bond_redeem(db: Session, data: dict) -> Optional[Position]:
    """债券兑付入口（`PositionService.process_bond_redeem` 的实现）。

    返回 `None` 表示已清仓——与卖出路径的「None = 已清仓」契约一致，调用方无需区分。
    """
    intent = resolve_redeem_intent(db, data)
    try:
        is_cleared = apply_redeem_to_position(db, intent)
        write_redeem_transaction(db, intent)
        if is_cleared:
            return None
        db.refresh(intent.position)
        return intent.position
    except Exception:
        logger.exception('债券兑付操作失败')
        raise
