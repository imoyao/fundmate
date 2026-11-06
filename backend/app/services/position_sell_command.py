# -*- coding: utf-8 -*-
"""持仓**卖出/取出命令**（#2873 第六抽）。

`PositionService.process_sell_or_withdraw` 曾是一个 167 行、圈复杂度 28 的单方法（第五抽
收尾后 `position_service.py` 里最大的函数）。它和买入命令是镜像关系，但比买入多两层判断：

    解析校验（含锚点内卖出豁免） → 扣减/清仓 → 落流水 → 回款自动申购 → 自选对齐

本模块承接整条链路，主模块只留转发薄壳（签名与行为逐字不变）。顺带把
`auto_purchase_money_fund`（60 行）整段搬来：它只服务「卖出回款自动申购」这一条边，
全仓除本路径外无调用点，留在主模块等于让卖出语义分散在两处。

## 三段与 `SellIntent`

    prepare_sell           解析 + 定位持仓 + 自愈回填 + 数量/批次校验 + 已实现盈亏
    apply_sell_to_position 扣减份额 / 清仓标记 / flush，返回「是否清仓」
    write_sell_transaction 落卖出流水 + 回款自动申购 + 自选对齐

段间原本共享 11 个局部变量。与买入命令同理，**刻意不做各段重算**：
`sell_asset_type` 要取持仓品种而不是请求体（见 `_get_asset_type` 的 fallback 说明）、
`realized_cents` 必须在份额扣减**之前**用当时的 `avg_price` 算、`covered_by_anchor`
判一次就决定了「扣不扣份额」，重算一次就多一次走错的机会。

`SellIntent` 里带着本单要写的 `Position` 行（frozen 只冻结字段绑定，不冻结对象本身）：
同一 Session 的 identity map 保证后续段落拿到的是同一实例，避免「二次查询 → 二次判定 →
两段看到不同状态」。这也正是清仓判定（`quantity == 0`）必须与扣减在同一段的原因。

## 顺序是这条链路的一部分

1. **`covered_by_anchor` 在任何扣减之前判**：被快照包含的卖出不再扣份额，否则会把
   「快照已反映卖出的份额」再减一遍；同时它**豁免**数量校验（那笔卖出已经发生过了）；
2. **`realized_cents` 在扣减之前算**（#1183）：移动加权下卖出不改均价，但显式提前取值
   可避免后续重构引入顺序依赖；
3. **清仓不删行**（#2343）：`mark_position_cleared` 打 `ownership_status='cleared'` +
   `cleared_at`，锚点与成本基线原样留存——历史那次 `db.delete()` 正是「锚点随行消失 →
   删流水后重建退回全量口径 → 二次累加复发」的源头；
4. **清仓仍返回 `None`**：调用方「None = 已清仓」的契约不动。

## 依赖方向

`position_service` 在模块级导入本模块（转发薄壳）；本模块只在**函数内**延迟导入主模块的
`_silent_reconcile_watchlist`（卖出、买入、快照导入三条路径都要用它，留主模块才不制造
双向依赖）。与 `position_buy_command` / `position_snapshot_command` 同一范式。

## 刻意不做的事

- **不改 `skip_lot_check` / `auto_purchase` 语义**：前者是导入回放用的校验开关，后者是
  基金转换专用（`conversion_service` 自己落退款腿，这里再自动申购会导致同一笔回款记两次）；
- **不把卖出流水与转换腿合并**：转换＝卖 A + 买 B，由 `conversion_service` 编排，
  拆到本模块只会把两层逻辑再叠一层；
- **异常日志仍只盖写阶段**：`prepare_sell` 的校验失败（数量不足、批次不合规）照旧**不**打
  `logger.exception`——那是用户输入问题，不是系统故障；把它圈进写阶段的日志会让正常拒绝
  刷成错误日志。
"""

from dataclasses import dataclass
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import PositionSource
from app.core.money import Money
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.positions.state import is_covered_by_anchor, mark_position_cleared
from app.services.pnl_service import compute_sell_realized_cents
from app.services.position_write_support import (
    _fee_breakdown_kwargs,
    _get_asset_type,
    _resolve_family_id,
    _resolve_fund_name_by_code,
    _resolve_ledger_name_by_id,
)
from app.services.trading import TransactionService, validate_sell


@dataclass(frozen=True)
class SellIntent:
    """校验并派生完成的卖出入参（不可变）。

    `position` 是本单要写的持仓行——同一 Session 的 identity map 保证三段看到同一个实例。
    """

    position: Position
    position_id: int
    op_type: str
    qty_units: int
    price_units: int
    fee_cents: int
    realized_cents: int
    covered_by_anchor: bool
    family_id: int
    ledger_id: Optional[int]
    position_name: str
    account_name: str
    sell_asset_type: str
    auto_purchase: bool


def prepare_sell(
    db: Session,
    data: dict,
    *,
    skip_lot_check: bool = False,
    auto_purchase: bool = True,
) -> SellIntent:
    """解析 + 校验 + 自愈回填，产出不可变 intent。

    校验口径（既有行为，勿单方面放宽）：
    - 持仓必须存在（按 `family_id` 限定，越权 id 一律当不存在）；
    - 操作份额必须 > 0；
    - 未被锚点覆盖时：份额不得超持有量；`skip_lot_check=False` 时还要过 `validate_sell`。

    自愈回填（#2372）：存量持仓快照缺 `name` / `account_name` 时按 ID 反查补上，修复上游
    漏写导致的「未知资产 / 未知账户」；绝不留 NULL 给前端。
    """
    position_id = data['position_id']
    op_type = data['op_type']
    qty_shares = data['quantity']

    qty_units = Money.shares_to_min_unit(qty_shares)
    price_units = Money.yuan_to_price_units(data['avg_price'])
    family_id = _resolve_family_id(data)

    existing = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
    if not existing:
        raise ValueError('指定的持仓不存在')
    if qty_units <= 0:
        raise ValueError('操作数量必须大于 0')

    # 锚点判定：这笔卖出若已包含在快照里（confirm_date <= 锚点日），快照份额已经
    # 反映了它，**不再扣减** quantity，否则会把快照值减成「快照 - 已含卖出」。
    # 同时跳过数量校验：被包含的卖出不该受当前派生份额约束（它已经发生过了）。
    covered_by_anchor = is_covered_by_anchor(existing, data.get('confirm_date'))

    if not covered_by_anchor:
        if existing.quantity < qty_units:
            raise ValueError(
                f'持仓数量不足：当前持有 {Money.min_unit_to_shares(existing.quantity)}，拟操作 {qty_shares}'
            )

        if not skip_lot_check:
            valid, err_msg = validate_sell(
                existing.symbol or '',
                existing.market or '',
                existing.asset_type or 'stock',
                Money.min_unit_to_shares(existing.quantity),  # 转回份
                Money.min_unit_to_shares(qty_units),
            )
            if not valid:
                raise ValueError(err_msg)

    # 自愈回填（#2372）：仅在缺失时写，与买入路径同口径。
    if not existing.name:
        existing.name = _resolve_fund_name_by_code(db, existing.symbol)
    if not existing.account_name and existing.ledger_id:
        existing.account_name = _resolve_ledger_name_by_id(db, existing.ledger_id)
    # 快照仍缺失（如 market 名录无该代码）时按 ID 兜底反查。
    position_name = existing.name or _resolve_fund_name_by_code(db, existing.symbol)
    account_name = existing.account_name or _resolve_ledger_name_by_id(db, existing.ledger_id)

    # 品种以**持仓**为准（理由见 `_get_asset_type` 的 `fallback` 说明）：卖出请求不带 type
    # 时若兜底成 'stock'，场外基金的卖出流水会与买入分属两个身份键，清仓周期永远闭合不上。
    sell_asset_type = _get_asset_type(data, fallback=existing.asset_type)

    # ── 已实现盈亏结转（#1183）──
    # 必须在份额扣减前取成本均价（移动加权下卖出本不改均价，提前取值可避免后续重构
    # 引入顺序依赖）。结果落在流水的 realized_pnl 上而不是持仓上——清仓时记在持仓上
    # 会随持仓的可追溯性一起变味。
    fee_cents = Money.yuan_to_cents(data.get('fee', 0) or 0)
    realized_cents = compute_sell_realized_cents(
        price_units=price_units,
        avg_price_units=existing.avg_price or 0,
        qty_units=qty_units,
        fee_cents=fee_cents,
    )

    return SellIntent(
        position=existing,
        position_id=position_id,
        op_type=op_type,
        qty_units=qty_units,
        price_units=price_units,
        fee_cents=fee_cents,
        realized_cents=realized_cents,
        covered_by_anchor=covered_by_anchor,
        family_id=family_id,
        # 清仓不再删行（#2343），ledger_id 提前取出保留（#1137 自动申购要用）——
        # 防御性写法：即使行保留，也避免依赖「事后仍可读 existing」的顺序耦合。
        ledger_id=existing.ledger_id,
        position_name=position_name,
        account_name=account_name,
        sell_asset_type=sell_asset_type,
        auto_purchase=auto_purchase,
    )


def apply_sell_to_position(db: Session, intent: SellIntent, data: dict) -> bool:
    """扣减份额并处理清仓，返回 `is_cleared`。"""
    existing = intent.position
    is_cleared = False

    if not intent.covered_by_anchor:
        existing.quantity -= intent.qty_units
        is_cleared = existing.quantity == 0
        if is_cleared:
            # 清仓不再删行（#2343）：行保留 = 锚点不灭 + 成本基线可追溯。
            # cleared_at 取清仓流水的确认日（业务事实），不是墙钟时间。
            mark_position_cleared(existing, data.get('confirm_date') or data.get('trade_date'))
    else:
        logger.debug(
            '卖出已含在快照锚点内，仅落流水: position={} symbol={} confirm={} anchor={}',
            existing.id,
            existing.symbol,
            data.get('confirm_date'),
            existing.snapshot_date,
        )

    db.flush()
    return is_cleared


def write_sell_transaction(
    db: Session,
    intent: SellIntent,
    data: dict,
    *,
    is_cleared: bool,
) -> Optional[Position]:
    """落卖出流水 → 回款自动申购 → 自选对齐；清仓返回 `None`（既有契约）。"""
    from app.services.position_service import _silent_reconcile_watchlist  # noqa: PLC0415

    existing = intent.position
    TransactionService.create(
        db=db,
        position_id=intent.position_id,
        # symbol 以持仓为准（#2855）：卖出请求漏带 symbol 时若落 NULL，产品详情「交易记录」
        # （按 symbol 身份匹配）与清仓周期（按 symbol 分组）都看不见这笔卖出——已清仓产品
        # 于是「有买无卖」。与 bond_redeem 路径的 `data.get('symbol') or existing.symbol`
        # 同一条纪律。
        symbol=data.get('symbol') or existing.symbol,
        txn_type=intent.op_type,
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        asset_type=intent.sell_asset_type,
        link_group_id=data.get('link_group_id'),
        quantity=intent.qty_units,
        price=intent.price_units,
        fee=intent.fee_cents,
        # #2137 费用拆分：data 带明细才落四列，否则四列留 NULL（未拆分）
        **_fee_breakdown_kwargs(data),
        amount=Money.multiply_price_quantity(intent.price_units, intent.qty_units),
        realized_pnl=intent.realized_cents,
        status='success',
        position_name=intent.position_name,
        ledger_id=intent.ledger_id,
        account_name=intent.account_name,
        notes=data.get('notes') or ('卖出' if intent.op_type == 'sell' else '取出'),
        import_hash=data.get('import_hash'),
        family_id=intent.family_id,
        # #1232 决策 11：流水来源透传（记一笔默认 manual）
        source=data.get('source') or PositionSource.MANUAL.value,
        # 转换等成组交易经 data 透传 extra.conversion 元数据（§3.2）
        extra=data.get('extra'),
    )

    # #1137 卖出回款自动申购账户绑定的类现金产品（余额宝）。
    # 净额 = 成交额 - 手续费；货基/逆回购自身的卖出不触发，避免「赎回 → 自动申购」死循环。
    # 基金转换传 auto_purchase=False：退款腿由转换服务按用户选择显式落账（见主模块 docstring）。
    # 判据用 `sell_asset_type`（持仓品种）而非 `_get_asset_type(data)`：请求体没带 type 时
    # 后者会把货基赎回判成股票卖出去自动申购，正是它要防的那个死循环。
    if intent.auto_purchase and intent.sell_asset_type not in ('money_fund', 'reverse_repo'):
        gross_cents = Money.multiply_price_quantity(intent.price_units, intent.qty_units)
        auto_purchase_money_fund(
            db,
            ledger_id=intent.ledger_id,
            amount_cents=gross_cents - intent.fee_cents,
            trade_date=data.get('trade_date'),
            confirm_date=data.get('confirm_date'),
            family_id=intent.family_id,
        )

    db.flush()
    # #1458 后续：卖出/清仓后对齐自选状态（静默，失败不影响主链路）
    _silent_reconcile_watchlist(db, intent.family_id, existing.symbol)
    if is_cleared:
        return None
    db.refresh(existing)
    return existing


def run_sell_or_withdraw(
    db: Session,
    data: dict,
    *,
    skip_lot_check: bool = False,
    auto_purchase: bool = True,
) -> Optional[Position]:
    """卖出/取出入口：校验（不打错误日志）→ 写阶段（异常记 `卖出/取出操作失败`）。"""
    intent = prepare_sell(db, data, skip_lot_check=skip_lot_check, auto_purchase=auto_purchase)
    try:
        is_cleared = apply_sell_to_position(db, intent, data)
        return write_sell_transaction(db, intent, data, is_cleared=is_cleared)
    except Exception:
        logger.exception('卖出/取出操作失败')
        raise


def auto_purchase_money_fund(
    db: Session,
    ledger_id: Optional[int],
    amount_cents: int,
    trade_date=None,
    confirm_date=None,
    family_id: Optional[int] = None,
) -> None:
    """#1137 卖出/赎回回款自动申购账户绑定的类现金产品（「余额宝」）。

    仅在账户显式开启 `auto_purchase_money_fund` 且绑定了有效货基时执行——
    遵循「用户不操作，系统不代劳」，开关由用户在账户设置里自行开启。

    - 回款净额 <= 0 时不申购；
    - 生成**孤儿流水**（asset_type='money_fund'）：货基不建持仓，与导入器、
      `money_fund_income` 的既有口径一致（货基市值按流水净额计入总资产）；
    - 调用方须自行排除货基 / 逆回购自身的卖出，避免「赎回 → 自动申购」死循环
      （货基卖出在 `process_orphan_sell_or_withdraw` 里走现金转移分支，不进入本函数）。

    失败（绑定产品缺失等）仅告警不抛出：自动申购是增值行为，不应阻断卖出主流程。
    """
    # #1305 #22：缺省不再硬编码 1，走与写入链路一致的解析（入参 → 上下文 → 遗留口径）
    family_id = family_id or _resolve_family_id({})
    if not ledger_id or amount_cents <= 0:
        return
    ledger = db.query(Ledger).filter_by(id=ledger_id, family_id=family_id).first()
    if not ledger or not ledger.auto_purchase_money_fund or not ledger.linked_money_fund_id:
        return
    fund = db.get(Fund, ledger.linked_money_fund_id)
    if not fund:
        logger.warning(f'账户 {ledger_id} 绑定的类现金产品 {ledger.linked_money_fund_id} 不存在，跳过自动申购')
        return
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=fund.fund_code,
        txn_type='buy',
        trade_date=trade_date,
        confirm_date=confirm_date,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=amount_cents,
        status='success',
        position_name=fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='卖出回款自动申购类现金产品',
        entry_status='orphan',
        family_id=family_id,
    )
