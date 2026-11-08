# -*- coding: utf-8 -*-
"""导入侧卖出 / 取出的落账入口（#3004 从 ``position_orphan_flows`` 拆出）。

## 为什么单独一个模块

两件事让这段必须单独成文件：

1. ``position_orphan_flows.py`` 已贴着 services 体量闸门（``scripts/guard_service_size.py``）
   的基线；
2. 这段的返回值语义与同文件里的分红/送转**不同**——卖出要区分「清仓」与「没归位」，
   混在「孤儿流水」文件里最容易被误用成 ``position is None``（那正是旧 bug）。

## 返回值

:class:`SellOutcome`：``position is None`` 有两种含义，导入回执**必须分开**——

- ``is_orphan=False`` → 卖出成功且已清仓（#2343：行保留 + ``cleared``，持仓字段返回 None）；
- ``is_orphan=True``  → 没匹配到持仓，落的是孤儿流水（``position_id=NULL``）。

旧实现让调用方用 ``if result is None: orphan_count += 1`` 判定，于是「整只卖光」被记成
「没归位」——导入回执里的「孤立 N 笔」凭空虚高，用户以为卖出没挂上持仓。
"""

from typing import NamedTuple, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.services.position_orphan_flows import (
    _create_cash_transfer_transaction,
    _create_orphan_transaction,
)
from app.services.position_write_support import (
    _find_position_by_identity,
    _get_asset_type,
    _resolve_family_id,
)


class SellOutcome(NamedTuple):
    """卖出/取出的落账结果（与 ``BondRedeemOutcome`` 同构）。"""

    position: Optional[Position]
    is_orphan: bool


def process_sell_or_withdraw_import(db: Session, data: dict) -> SellOutcome:
    """导出侧卖出/取出：优先关联持仓，找不到（或数量不足）才落孤儿流水。"""
    from app.services.position_service import PositionService  # noqa: PLC0415  循环依赖：核心卖出命令仍在主模块

    asset_type = _get_asset_type(data)
    if asset_type in ('money_fund', 'reverse_repo'):
        # 货基/逆回购卖出走现金转移流水（不建仓），沿用原有「未归位」口径，
        # 与「清仓误计」区分开——那是两个不同语义。
        _create_cash_transfer_transaction(db, data, 'sell')
        return SellOutcome(position=None, is_orphan=True)

    symbol = data.get('symbol', '')
    qty = data.get('quantity', 0)
    price = data.get('avg_price', 0)
    name = (data.get('name') or data.get('position_name') or '').strip()

    # 尝试查找现有持仓（家庭维度）——身份键 (ledger_id, symbol)，无代码时才按
    # (ledger_id, name) 兜底（#1920 + #2372：账户 ID 收敛范围，名称不做跨账户键）
    existing = None
    if symbol:
        existing = _find_position_by_identity(db, data, symbol=symbol)
    if existing is None and name:
        # **symbol 缺失时的兜底关联**（#1920）
        # 券商交割单里「证券名称」常有而「证券代码」为空（实测真实库 1348/2051 笔
        # 无 symbol）。此前只按 symbol 匹配 ⇒ 必然查不到持仓 ⇒ 卖出退化成孤儿流水
        # ⇒ `realized_pnl` 无从计算而**静默丢 0**（真实库 649 笔卖出如此）。
        # 名称 + 账户 ID 在单个账户内足以唯一定位持仓，退化风险远低于丢成本基准。
        existing = _find_position_by_identity(db, data, name=name, active_only=True)
        if existing is not None:
            logger.info(
                '卖出/取出按名称兜底关联到持仓：symbol=%r name=%r ledger_id=%r → position_id=%s',
                symbol,
                name,
                data.get('ledger_id'),
                existing.id,
            )

    if existing:
        try:
            position = PositionService.process_sell_or_withdraw(
                db,
                {
                    'position_id': existing.id,
                    'quantity': qty,
                    'avg_price': price,
                    'trade_date': data.get('trade_date'),
                    'confirm_date': data.get('confirm_date'),
                    'op_type': data.get('op_type', 'sell'),
                    'fee': data.get('fee', 0.0),
                    'notes': data.get('notes', ''),
                    'import_hash': data.get('import_hash'),
                    'family_id': _resolve_family_id(data),
                },
                skip_lot_check=True,
            )
            # 返回 None 只代表「整只卖光已清仓」（#2343），不是没归位。
            return SellOutcome(position=position, is_orphan=False)
        except ValueError as e:
            if '持仓数量不足' not in str(e):
                raise
            logger.warning(f'持仓 {existing.symbol} 数量不足，转为孤儿交易')

    # 无持仓或数量不足，统一创建孤儿流水
    _create_orphan_transaction(
        db,
        data,
        txn_type=data.get('op_type', 'sell'),
        quantity=qty,
        price=price,
        amount=0,  # 自动计算
        notes=data.get('notes') or ('卖出' if data.get('op_type') == 'sell' else '取出'),
    )
    return SellOutcome(position=None, is_orphan=True)


def process_orphan_sell_or_withdraw(db: Session, data: dict) -> Optional[Position]:
    """旧契约（返回持仓，清仓 / 孤儿均为 None）；新代码请用 :func:`process_sell_or_withdraw_import`。"""
    return process_sell_or_withdraw_import(db, data).position
