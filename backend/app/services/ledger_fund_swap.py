# -*- coding: utf-8 -*-
"""活期+ 换绑的写入边（#1137）——从 `ledger_write_service` 抽出的单一边。

换绑要一次做两件事：把账户内原绑定货基 A 的净额持仓赎回、再申购新绑定货基 B。
货基以**孤儿流水**记账（不建持仓），故「持仓」= 该账户下 A 的 `money_fund` 流水净额。
抽成独立模块的唯一理由是体积：这段自查净额 + 造两条孤儿流水的逻辑有 90 余行，
留在 `ledger_write_service` 里会把该文件顶破 `guard_service_size` 的冻结基线，
而它与「交易编辑审计」那次改动无关（同 PR 出现只是同行者）。

行为与抽取前**逐字一致**：净额口径、身份键匹配、失败只告警不抛出，全部原样搬来。
"""

from datetime import datetime

from loguru import logger
from sqlalchemy import func, or_

from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.transactions.models import Transaction
from app.services.symbol_scope import build_transaction_symbol_conditions
from app.services.trading import TransactionService


def swap_linked_money_fund(db, ledger: Ledger, old_fund: Fund, new_fund: Fund, family_id: int) -> None:
    """#1137 换绑活期+：将账户内原绑定货基 A 的净额持仓赎回，并申购新绑定货基 B（业务规则下沉）。

    货基以孤儿流水记账（不建持仓），故「持仓」= 该账户下 A 的 money_fund 流水净额。
    净额<=0 表示无实际持仓，跳过（避免凭空造流水）。仅生成两条孤儿流水（赎回 A /
    申购 B），资产中性、不影响其他账户；失败仅记录告警不抛出，避免阻断换绑主流程。
    """
    family_id = family_id
    # 货基以孤儿流水记账（不建持仓），净额口径与 summary_service.orphan_money_fund_totals_by_ledger
    # 一致：buy/deposit 加、sell/withdraw 减，且仅计 position_id IS NULL 的孤儿流水，全程整数分。
    positive = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.ledger_id == ledger.id,
            Transaction.family_id == family_id,
            Transaction.asset_type == 'money_fund',
            # 身份键匹配（#1662 遗留项）：货基流水的 symbol 快照可能是带前缀形态，
            # 字面量等值会把净额算成 0（→ 换绑时误判「无持仓」而跳过）。
            or_(*build_transaction_symbol_conditions(old_fund.fund_code)),
            Transaction.position_id.is_(None),
            Transaction.covered_position_id.is_(None),
            Transaction.txn_type.in_(('buy', 'deposit')),
        )
        .scalar()
        or 0
    )
    negative = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.ledger_id == ledger.id,
            Transaction.family_id == family_id,
            Transaction.asset_type == 'money_fund',
            # 身份键匹配（#1662 遗留项）：货基流水的 symbol 快照可能是带前缀形态，
            # 字面量等值会把净额算成 0（→ 换绑时误判「无持仓」而跳过）。
            or_(*build_transaction_symbol_conditions(old_fund.fund_code)),
            Transaction.position_id.is_(None),
            Transaction.covered_position_id.is_(None),
            Transaction.txn_type.in_(('sell', 'withdraw')),
        )
        .scalar()
        or 0
    )
    net_cents = int(positive) - int(negative)
    if net_cents <= 0:
        return
    today = datetime.now().date()
    # 赎回原绑定货基 A
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=old_fund.fund_code,
        txn_type='sell',
        trade_date=today,
        confirm_date=today,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=net_cents,
        status='success',
        position_name=old_fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='更换活期+，赎回原绑定产品',
        entry_status='orphan',
        family_id=family_id,
    )
    # 申购新绑定货基 B（活期+内迁移，保持资产中性）
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=new_fund.fund_code,
        txn_type='buy',
        trade_date=today,
        confirm_date=today,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=net_cents,
        status='success',
        position_name=new_fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='更换活期+，申购新绑定产品',
        entry_status='orphan',
        family_id=family_id,
    )
    logger.info(
        f'账户 {ledger.id} 换绑活期+：{old_fund.fund_code} → {new_fund.fund_code}，'
        f'净额 {net_cents} 分已迁移（赎回 A / 申购 B）'
    )
