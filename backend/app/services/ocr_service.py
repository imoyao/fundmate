# -*- coding: utf-8 -*-
"""OCR/AI 识别域的交易候选行转换服务（#1642 B 块，从 views 下沉，承 #1606）。

WHY 下沉
    ``_txn_candidates_to_rows`` 长在视图模块（69 行）：候选行字段映射 + 日期/金额推算 +
    enrich/哈希/去重（委托 ImportOrchestrator.preview_records）+ 展示字段回填，属纯转换，
    却挂在视图模块下。本模块收口，视图只做「调服务 + 组响应」。

边界
    - 内部仍按原口径开 ``get_session``（preview_records）与 ``get_db``（ledger 名回填）；
      family_id 经 ``get_family_id()`` 取当前请求上下文，无请求上下文时不可单测；
    - 只读解析/预览：不写库、不提交事务（落库走 /api/importers/confirm）；
    - 对外 API 契约零变更（``conventions.md`` §2.4）：返回行结构与下沉前逐字一致。
"""

from datetime import date
from decimal import Decimal

from app.core.constants import PositionSource
from app.core.database import get_session
from app.domains.ledgers.models import Ledger
from app.services.import_records import StandardTransactionRecord
from app.services.importer.mappings import OP_TYPE_LABEL
from app.services.importer.orchestrator import ImportOrchestrator


def _ledger_name(ledger_id) -> str:
    """按 ledger_id 取账户名（解析阶段用于回填 account_name，与 importers/parse 口径一致）。"""
    if not ledger_id:
        return ''
    from app.core.auth import get_family_id
    from app.core.database import get_db

    with get_db() as db:
        ledger = db.query(Ledger).filter(Ledger.id == ledger_id, Ledger.family_id == get_family_id()).first()
        return ledger.name if ledger else ''


def txn_candidates_to_rows(items: list, ledger_id) -> list:
    """交易候选行 → importer 预览行（enrich/哈希/去重走 ImportOrchestrator.preview_records）。

    与下沉前逐字段一致：候选行 business_type 仅保留 SUPPORTED_OP_TYPES；确认日优先、
    缺失回退申请日、再回退今日；金额缺失但份额+净值齐 → 推算（净值*份额）；映射为
    StandardTransactionRecord 后复用既有管线；提交阶段由前端 POST /api/importers/confirm
    处理。返回行回填 op_type_label / warnings / trade_date 展示字段。
    """
    SUPPORTED_OP_TYPES = {'buy', 'sell', 'dividend_cash', 'dividend_reinvest'}
    if not items:
        return []
    records = []
    for it in items:
        op_code = it.get('business_type', '')
        if op_code not in SUPPORTED_OP_TYPES:
            continue
        # 入账日期：优先确认日；截图通常只有申请日 → 用申请日（前端预览可改）
        row_date = it.get('confirm_date') or it.get('trade_date') or ''
        try:
            confirm_date = date.fromisoformat(row_date) if row_date else date.today()
        except ValueError:
            confirm_date = date.today()
        trade_date_str = it.get('trade_date') or ''
        try:
            trade_date = date.fromisoformat(trade_date_str) if trade_date_str else None
        except ValueError:
            trade_date = None

        amount = it.get('amount') or 0
        # 金额缺失但份额+净值齐 → 推算金额（净值*份额），保证 amount>0 可通过校验
        if amount <= 0 and it.get('shares') and it.get('nav'):
            amount = float(it['shares']) * float(it['nav'])

        records.append(
            StandardTransactionRecord(
                confirm_date=confirm_date,
                trade_date=trade_date,
                asset_type=it.get('type') or 'fund',
                symbol=it.get('symbol') or it['code'],
                name=it.get('name') or '',
                business_type=op_code,
                amount=Decimal(str(round(amount, 2))),
                account_name='',
                shares=Decimal(str(it['shares'])) if it.get('shares') else None,
                nav=Decimal(str(it['nav'])) if it.get('nav') else None,
                fee=Decimal(str(it.get('fee') or 0)),
                raw_op_type=it.get('business_type', ''),
                source=PositionSource.AI_TXN.value,
            )
        )

    from app.core.auth import get_family_id

    with get_session() as db:
        orch = ImportOrchestrator(db, get_family_id())
        result = orch.preview_records(records, _ledger_name(ledger_id), ledger_id, source=PositionSource.AI_TXN.value)

    # 回填前端表格所需展示字段（与 parse_and_preview 行结构一致）
    rows = []
    warnings_by_code = {it['code']: it.get('warnings') or [] for it in items}
    for row in result['rows']:
        row['op_type_label'] = OP_TYPE_LABEL.get(row.get('op_type', ''), '')
        row['warnings'] = warnings_by_code.get(row.get('symbol', ''), []) or warnings_by_code.get(row.get('name'), [])
        row['trade_date'] = row.get('trade_date') or ''
        rows.append(row)
    return rows
