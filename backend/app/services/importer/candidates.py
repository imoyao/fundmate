# -*- coding: utf-8 -*-
"""外部候选行（AI 识别）→ 导入预览行的**纯转换**（#1642 B 块，从 ocr 视图下沉）。

WHY 落在 importer 家族
    ``ImportOrchestrator.preview_records`` 的文档即「外部候选记录（如 AI 识别）→ 与
    ``parse_and_preview`` 相同的预览行」——本模块是该接缝的**输入侧**：把候选 dict 映射为
    ``StandardTransactionRecord``，并在预览行上回填展示字段（行结构与 ``parse_and_preview`` 一致），
    复用 importer 家族自己的 ``mappings`` 与共享件 ``import_records``。

边界（为什么只做纯转换）
    - **不建会话、不调 orchestrator、不读请求上下文**（``request`` / ``g`` / ``get_family_id``）：
      「开会话 + 调 orchestrator」是视图层编排（``decisions.md`` D26：视图只做入参解析 /
      调服务 / 组响应），故留在 ``domains/ocr/views.py``；
    - 纯函数 → 无 I/O、无 DB、无 Flask 上下文，可脱离 HTTP 栈直接单测；
    - 对外 API 契约零变更（``conventions.md`` §2.4）：转换口径与下沉前逐字段一致。
"""

from datetime import date
from decimal import Decimal

from app.core.constants import PositionSource
from app.services.import_records import StandardTransactionRecord
from app.services.importer.mappings import OP_TYPE_LABEL

# 支持的业务类型（AI 识别范围：基金申赎为主，股票买卖；与 TxnRecognizer 对齐）
SUPPORTED_OP_TYPES = {'buy', 'sell', 'dividend_cash', 'dividend_reinvest'}


def txn_candidates_to_records(items: list) -> list:
    """交易候选行 → StandardTransactionRecord 列表（``business_type`` 不在 SUPPORTED_OP_TYPES 的丢弃）。

    候选行字段（TxnRecognizer 输出，enrich 后）：
        code / name / business_type(buy|sell|dividend_*) / trade_date / confirm_date /
        amount / shares / nav / fee / symbol / type / market / venue

    日期口径：确认日优先，缺失回退申请日、再回退今日（截图通常只有申请日，前端预览可改）；
    金额缺失但份额 + 净值齐 → 推算（净值 × 份额），保证 amount > 0 可通过校验。
    """
    if not items:
        return []

    records = []
    for it in items:
        op_code = it.get('business_type', '')
        if op_code not in SUPPORTED_OP_TYPES:
            continue

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
    return records


def apply_row_display_fields(rows: list, items: list) -> list:
    """在预览行上回填前端表格所需展示字段（与 ``parse_and_preview`` 行结构一致）。

    ``warnings`` 按候选行的 code / name 反查（AI 侧给的识别告警），``op_type_label`` 走
    importer 自己的 ``OP_TYPE_LABEL`` 映射，``trade_date`` 缺失补空串（前端表格列要求）。
    """
    warnings_by_code = {it['code']: it.get('warnings') or [] for it in items}
    out = []
    for row in rows:
        row['op_type_label'] = OP_TYPE_LABEL.get(row.get('op_type', ''), '')
        row['warnings'] = warnings_by_code.get(row.get('symbol', ''), []) or warnings_by_code.get(row.get('name'), [])
        row['trade_date'] = row.get('trade_date') or ''
        out.append(row)
    return out
