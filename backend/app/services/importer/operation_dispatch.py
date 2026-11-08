# -*- coding: utf-8 -*-
"""导入落库的「常规操作」派发（#3004 拆分）。

## 为什么单独一个模块

``ImportOrchestrator.commit()`` 已经贴着 services 体量闸门（``scripts/guard_service_size.py``）
的基线，而「按业务类型选落库命令 + 判定这笔是否没归位」本身就是一段独立职责，
与 SAVEPOINT / 去重 / 计数无关。下沉后 commit() 只保留编排，新增一种业务类型也不必
再去动那个已经很长的方法。

## 返回值

``(position, is_orphan)``：``position is None`` 有两种含义——

- 卖出整只卖光（清仓，#2343 行保留 + cleared）；
- 没匹配到持仓，落的是孤儿流水。

两者靠 ``is_orphan`` 区分（见 :class:`app.services.position_orphan_flows.SellOutcome`），
调用方不要再拿 ``position is None`` 当「孤立」判据，否则整只卖光会被错报成「没归位」。

业务类型不受支持时返回 :data:`UNSUPPORTED`，调用方据此计入 ``skipped`` 并跳过。
"""

from typing import Any, Tuple

from app.services.importer.mappings import BusinessType
from app.services.position_sell_import import process_sell_or_withdraw_import
from app.services.position_service import PositionService

UNSUPPORTED = object()


def dispatch_standard_operation(db, data: dict, business_type: str) -> Tuple[Any, bool]:
    """按业务类型派发到持仓命令，返回 ``(position, is_orphan)``。"""
    if business_type in (BusinessType.BUY.code, BusinessType.DEPOSIT.code):
        return PositionService.process_buy_or_deposit(db, data), False
    if business_type in (BusinessType.SELL.code, BusinessType.WITHDRAW.code):
        outcome = process_sell_or_withdraw_import(db, data)
        return outcome.position, outcome.is_orphan
    if business_type == BusinessType.DIVIDEND_REINVEST.code:
        position = PositionService.process_orphan_dividend_reinvest(db, data)
    elif business_type == BusinessType.SPLIT.code:
        position = PositionService.process_orphan_split(db, data)
    elif business_type in (BusinessType.DIVIDEND_CASH.code, BusinessType.DIVIDEND.code):
        # #541：自动抓取路径用的通用「分红」码（与手动导入的 dividend_cash 同落
        # txn_type='dividend'，只是不带再投语义）
        position = PositionService.process_orphan_dividend(db, data)
    else:
        return UNSUPPORTED, False
    # 分红/送转没有「清仓」语义：返回 None 就是没匹配到持仓（孤儿流水）。
    return position, position is None
