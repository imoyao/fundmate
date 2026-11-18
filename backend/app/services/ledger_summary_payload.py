# -*- coding: utf-8 -*-
"""账户列表 / 概览摘要的编排（含「累计盈亏」三段，2026-11-10）。

## 为什么下沉到 service

``domains/ledgers/views.py`` 的体量被 ``scripts/check_view_thickness.py`` 冻结
（视图层职责边界 #1606，存量只减不增）：把「按类型附加摘要 + 附加累计盈亏」继续写在
视图里会直接判红。而这件事本来就是**业务编排**而非 HTTP 编排——视图只负责取参、
鉴权、序列化。

## 为什么另起文件，而不是塞进 ``ledger_service.attach_ledger_summary``

那个函数同样在 ``guard_service_size.py`` 的冻结基线内；且它不该知道「列表页要不要
累计盈亏」这种展示取舍。本文件是新增文件，按 ``NEW_FILE_LIMITS`` 判。

## 依赖方向

本模块 import ``ledger_service``，故**不能**被 ``summary_service`` 反向 import
（``ledger_service`` 依赖 ``summary_service``，会成环）。三段口径本身在叶子模块
``ledger_cumulative_pnl`` 里。
"""

from sqlalchemy.orm import Session

from app.services.ledger_cumulative_pnl import (
    attach_cumulative_pnl,
    buy_fee_by_ledger,
    realized_pnl_by_ledger,
)
from app.services.ledger_presenter import ledger_to_dict
from app.services.ledger_service import LedgerService

# 只有这几类账户有「市值 − 成本」意义上的盈亏；bank / property 口径不同（不下发三段）
INVESTMENT_LEDGER_TYPES = ('stock', 'fund', 'e_account')


def build_ledger_list_items(
    db: Session,
    family_id: int,
    ledgers: list,
    last_used_map: dict,
    member_names: dict,
) -> list[dict]:
    """把账户 ORM 列表拼成 ``GET /api/ledgers/`` 的 items。

    已实现与买入费在循环**外**批量查一次（流水级聚合，含已清仓持仓），
    避免每账户两条 SQL 变成 2N。
    """
    realized_by_ledger = realized_pnl_by_ledger(db, family_id)
    fee_by_ledger = buy_fee_by_ledger(db, family_id)
    items: list[dict] = []
    for ledger in ledgers:
        item = ledger_to_dict(ledger, last_used_map.get(ledger.id), member_names)
        # 先落 0 占位：attach_ledger_summary 只会覆写该类型有口径的字段，
        # 未覆写的类型（如 property 无 pnl）保留 0.0，与拆分前逐字一致。
        item['total_market_value'] = 0.0
        item['pnl'] = 0.0
        item['position_count'] = 0
        item['cash_balance'] = 0.0
        LedgerService.attach_ledger_summary(db, ledger, item)
        if ledger.ledger_type in INVESTMENT_LEDGER_TYPES:
            attach_cumulative_pnl(item, realized_by_ledger.get(ledger.id, 0), fee_by_ledger.get(ledger.id, 0))
        items.append(item)
    return items


def attach_detail_cumulative_pnl(db: Session, family_id: int, ledger, data: dict) -> dict:
    """给单账户概览（``GET /api/ledgers/<id>/summary/``）附加累计盈亏三段。

    未实现直接取 ``data['position_pnl']``——同一张卡上已经展示的那个持仓盈亏——而不是
    从持仓再算一遍（理由见 ``ledger_cumulative_pnl.attach_cumulative_pnl``）。
    """
    if ledger.ledger_type not in INVESTMENT_LEDGER_TYPES:
        return data
    attach_cumulative_pnl(
        data,
        realized_pnl_by_ledger(db, family_id, [ledger.id]).get(ledger.id, 0),
        buy_fee_by_ledger(db, family_id, [ledger.id]).get(ledger.id, 0),
        unrealized_yuan=data.get('position_pnl'),
    )
    return data
