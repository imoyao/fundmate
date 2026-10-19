# -*- coding: utf-8 -*-
"""交易流水展示名称的 **ID 回解析**（#2372）。

WHY
    ``transactions.position_name`` / ``transactions.account_name`` 是**冗余快照**，
    真外键是 ``position_id`` / ``ledger_id``。历史数据与多个写入路径（基金转换
    转入腿等）会漏写快照，快照落 NULL 后各列表直接显示「未知资产 / 未知账户」
    （真库实测：48 笔 ``position_name`` 为空、转换流水两个快照全 NULL）。
    名称只是展示、且账户名是**可编辑字段**，ID 才是权威——快照缺失时必须按 ID
    回解析，而不是把「快照没写」当成「数据未知」展示给用户。

口径
    - 批量两步查（``IN`` + 映射），**不做跨域 JOIN**（双库硬规则：market / user
      分引擎，路由会话按表分发，点查/批查安全）；
    - 三级回解析 ``position_name``：快照 → ``position_id`` 点查持仓 → ``position_id``
      悬空（真库实测 621 笔指向不存在的持仓）时按 ``symbol`` 点查 market 名录；
      ``account_name``：快照 → ``ledger_id`` 点查账户；
    - 只解析「快照缺失」的行；快照已在的行不进映射（调用方优先用快照，行为零变化）；
    - 纯读：不写库、不改快照——写入侧的自愈回填在 ``position_service``
      （#2372），两处分工明确，不重复实现。
"""

from typing import Dict, Iterable, Tuple

from sqlalchemy.orm import Session

from app.core.symbol_utils import strip_exchange_prefix
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction


def resolve_transaction_display_names(db: Session, txns: Iterable[Transaction]) -> Tuple[Dict[int, str], Dict[int, str]]:
    """批解析流水行的展示名称。

    Args:
        db: 路由会话（按表分发到 market / user 引擎）。
        txns: 本页/本批的 Transaction ORM 行（通常已按家庭过滤）。

    Returns:
        ``(position_name_by_txn_id, account_name_by_txn_id)``——仅含**回解析出的**
        键；调用方写法 ``t.position_name or pos.get(t.id) or '未知资产'``。
    """
    txn_list = list(txns)
    pos_by_txn: Dict[int, str] = {}
    ledger_by_txn: Dict[int, str] = {}
    if not txn_list:
        return pos_by_txn, ledger_by_txn

    # ── position_name：快照缺失的行才解析 ──
    missing_pos = [t for t in txn_list if not t.position_name]
    pos_ids = {t.position_id for t in missing_pos if t.position_id}
    if pos_ids:
        id_to_name = {
            pid: pname for pid, pname in db.query(Position.id, Position.name).filter(Position.id.in_(pos_ids)).all() if pname
        }
        for t in missing_pos:
            name = id_to_name.get(t.position_id) if t.position_id else None
            if name:
                pos_by_txn[t.id] = name

    # position_id 悬空/无持仓行时，按 symbol 点查 market 名录兜底（代码比名称稳）。
    dangling = [t for t in missing_pos if t.id not in pos_by_txn and t.symbol]
    if dangling:
        codes = {strip_exchange_prefix(str(t.symbol)) for t in dangling}
        codes.discard('')
        if codes:
            code_to_name = {
                code: name for code, name in db.query(Fund.fund_code, Fund.name).filter(Fund.fund_code.in_(codes)).all() if name
            }
            for t in dangling:
                name = code_to_name.get(strip_exchange_prefix(str(t.symbol)))
                if name:
                    pos_by_txn[t.id] = name

    # ── account_name：快照缺失且 ledger_id 有值的行按 ID 点查账户 ──
    missing_ledger = [t for t in txn_list if not t.account_name and t.ledger_id]
    if missing_ledger:
        ledger_ids = {t.ledger_id for t in missing_ledger}
        id_to_name = {
            lid: lname for lid, lname in db.query(Ledger.id, Ledger.name).filter(Ledger.id.in_(ledger_ids)).all() if lname
        }
        for t in missing_ledger:
            name = id_to_name.get(t.ledger_id)
            if name:
                ledger_by_txn[t.id] = name

    return pos_by_txn, ledger_by_txn
