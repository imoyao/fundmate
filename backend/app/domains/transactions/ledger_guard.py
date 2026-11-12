# -*- coding: utf-8 -*-
"""#2875：流水账本归属解析与导入错误条目（services 层体量守卫的职责下沉点）。

`scripts/guard_service_size.py` 把 services 层体量**冻结、只减不增**。#2875 新增的
两块规则若留在 `dividend_tax_service.py` / `orchestrator_commit.py`，会把 635 / 567
行的基线顶破（CI 红灯）。故把「查账本归属」「拼错误条目」这类不含编排语义的
纯规则收到本模块，services 里只留一次调用——与 #2914 把日期口径下沉到
`dates.py` 同一条路径。

- 红利税无持仓时，账本归属继承**最近一笔同标的分红流水**（红利税是分红的减项，
  语义同源）；连分红都没有 ⇒ ValueError，绝不落 `ledger_id=NULL` 的税行。
- 导入预览行缺账本 ⇒ 计入 `commit_errors`（与现金分支 B4 同口径），不静默落库。
"""

from app.domains.ledgers.models import Ledger
from app.domains.transactions.models import Transaction


def validate_ledger_ref(db, ledger_id, family_id=None) -> None:
    """非空的 ledger_id 必须指向本家庭真实存在的账本；NULL 保持合法（#2875 定案）。

    SQLite 的 FK 在 ``PRAGMA foreign_keys=OFF`` 下形同虚设，而迁移脚本大量在该
    模式下重建表，历史库因此留下「账本已删、流水还挂着旧 id」的悬空引用。导入
    预览行的 ledger_id 由前端回传、红利税补记继承历史流水的 id，二者此前都只判
    「非空」，不判存在性与家庭归属。故在唯一写入汇点 ``TransactionService.create``
    校验一次，堵住所有路径；NULL 是手工建仓 / 探市的合法形态，不在拦截范围。
    """
    if ledger_id is None:
        return
    ledger = db.get(Ledger, ledger_id)
    if ledger is None:
        raise ValueError(f'账本 {ledger_id} 不存在，不能写入流水')
    if family_id is not None and ledger.family_id != family_id:
        raise ValueError(f'账本 {ledger_id} 不属于当前家庭，不能写入流水')


def dividend_tax_source_fields(db, family_id, symbol, position, account_name=''):
    """返回可直接展开进 ``Transaction(**kwargs)`` 的账本归属字段。

    ``account_name`` 由调用方显式给出时优先（手工补记可指定账户），否则继承
    持仓 / 最近一笔同标的分红流水。两者都没有 ⇒ ValueError。继承来的 id 还要
    过 :func:`validate_ledger_ref`：账本可能已被删除，只判非空会复制悬空引用。
    """
    source = position
    if source is None:
        source = (
            db.query(Transaction)
            .filter(
                Transaction.family_id == family_id,
                Transaction.symbol == symbol,
                Transaction.txn_type == 'dividend',
                Transaction.ledger_id.isnot(None),
            )
            .order_by(Transaction.id.desc())
            .first()
        )
    if source is None or source.ledger_id is None:
        raise ValueError(f'无法定位账本：标的 {symbol} 的持仓 / 分红流水没有有效账本，请先归置账本')
    validate_ledger_ref(db, source.ledger_id, family_id)
    return {
        'account_name': account_name or source.account_name or '',
        'ledger_id': source.ledger_id,
        'asset_type': source.asset_type,
    }


def regular_field_error(data, needs_price):
    """常规投资品种的数量 / 价格校验（原两处 if 下沉），返回错误文案或 None。

    ``needs_price`` 由调用方按业务类型判定（BUY / DEPOSIT 才校验价格），
    domains 层因此不必认识 ``BusinessType``，依赖方向保持单向。
    """
    if data.get('quantity', 0) <= 0:
        return '数量必须大于 0'
    if needs_price and data.get('avg_price', 0) <= 0:
        return '价格必须大于 0'
    return None


def commit_error(record, error):
    """导入回执里单条错误的统一形状（原先多处各写一份同样的 dict）。"""
    return {'symbol': record.symbol, 'name': record.name, 'error': str(error)}


def missing_ledger_error(record):
    """缺账本行的错误条目（#2875 入口封堵）。"""
    return commit_error(record, '缺少目标账本（ledger_id），请选择账本后重试')


__all__ = ['commit_error', 'dividend_tax_source_fields', 'missing_ledger_error', 'regular_field_error']
