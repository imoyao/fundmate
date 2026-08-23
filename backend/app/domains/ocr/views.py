# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : views.py
"""AI 识别 API：图片识别 / 文本批量识别 / 用量查询（场景参数驱动注册表）。

鉴权：非白名单接口，需登录；当前用户从 g.current_user 取（core/auth.py 注入）。

场景（scenario 参数，缺省 watchlist_import 兼容旧前端）：
    watchlist_import  自选：返回基金/股票候选列表（code/name/type/venue/symbol）
    txn_import        交易：返回 importer 预览行（含买卖/日期/金额/份额，前端逐行核对后
                      复用 /api/importers/confirm 入库）
    holding_import    持仓：返回 importer 持仓预览行（含份额/成本/市值/快照日，前端逐行核对后
                      复用 /api/importers/holdings/confirm 入库，绝不建交易流水）——见 #1018
"""

from datetime import date

from apiflask import APIBlueprint
from flask import g, jsonify, request
from loguru import logger

from app.core.auth import get_family_id
from app.core.constants import PositionSource
from app.core.database import get_db
from app.core.exceptions import SBException
from app.core.validation import parse_body
from app.domains.ledgers.models import Ledger
from app.domains.ocr.schemas import OCRParseTextRequest, OCRRecognizeRequest
from app.services.ai_recognizer import guards
from app.services.ai_recognizer.registry import get_recognizer
from app.services.importer.mappings import OP_TYPE_LABEL
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.importer.records import StandardHoldingRecord, StandardTransactionRecord

ocr_bp = APIBlueprint('ocr', __name__, url_prefix='/api/ocr')

# 单次最多返回多少条（防单次调用爆量）
OCR_MAX_ITEMS = 30

# 支持的业务类型（AI 识别范围：基金申赎为主，股票买卖；与 TxnRecognizer 对齐）
SUPPORTED_OP_TYPES = {'buy', 'sell', 'dividend_cash', 'dividend_reinvest'}


def _current_user_id() -> int:
    user = getattr(g, 'current_user', None)
    if user is None:
        raise SBException(code=1005, message='未授权，请先登录', status_code=401)
    return user.id


def _ledger_name(ledger_id) -> str:
    """按 ledger_id 取账户名（解析阶段用于回填 account_name，与 importers/parse 口径一致）。"""
    if not ledger_id:
        return ''
    with get_db() as db:
        ledger = db.query(Ledger).filter(Ledger.id == ledger_id, Ledger.family_id == get_family_id()).first()
        return ledger.name if ledger else ''


def _txn_candidates_to_rows(items: list, ledger_id) -> list:
    """交易候选行 → importer 预览行（enrich/哈希/去重走 ImportOrchestrator.preview_records）。

    候选行字段（TxnRecognizer 输出）：
        code / name / business_type(buy|sell|dividend_*) / trade_date / confirm_date /
        amount / shares / nav / fee / symbol / type / market / venue
    映射为 StandardTransactionRecord 后复用既有管线；提交阶段由前端 POST
    /api/importers/confirm（commit_from_preview）处理。
    """
    from datetime import date
    from decimal import Decimal

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

    from app.core.database import SessionLocal

    with SessionLocal() as db:
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


def _holding_candidates_to_rows(items: list, ledger_id) -> list:
    """持仓候选行 → importer 持仓预览行（走 ImportOrchestrator.preview_holding_records）。

    与 _txn_candidates_to_rows 完全独立：本函数产出的是「持仓」，提交阶段由前端
    POST /api/importers/holdings/confirm（commit_holdings）落库，绝不经过
    process_buy_or_deposit 交易管线——修复 #1018（AI 持仓识别误建流水）。

    候选行字段（HoldingRecognizer 输出，已 enrich）：
        code / symbol / asset_type / name / shares / avg_cost / market_value / snapshot_date
    """
    if not items:
        return []

    records = []
    for it in items:
        snap_raw = it.get('snapshot_date') or ''
        snap = None
        if snap_raw:
            try:
                snap = date.fromisoformat(snap_raw)
            except ValueError:
                snap = None
        records.append(
            StandardHoldingRecord(
                symbol=it.get('symbol') or it.get('code', ''),
                name=it.get('name') or '',
                asset_type=it.get('asset_type') or '',
                shares=it.get('shares') or 0,
                nav=it.get('avg_cost') or 0,
                market_value=it.get('market_value') or 0,
                snapshot_date=snap,
                currency='CNY',
                source=PositionSource.AI_HOLDING.value,
                ledger_id=ledger_id,
                account_name='',
                import_hash='',
            )
        )

    from app.core.database import SessionLocal

    with SessionLocal() as db:
        orch = ImportOrchestrator(db, get_family_id())
        result = orch.preview_holding_records(
            records, _ledger_name(ledger_id), ledger_id, source=PositionSource.AI_HOLDING.value
        )

    return result['rows']


@ocr_bp.get('/usage')
def get_ocr_usage():
    """查询某功能当日 AI 识别剩余次数（进入弹窗前展示余量）。

    feature 查询参数：ocr_import（默认，自选）/ txn_import（持仓）。
    """
    user_id = _current_user_id()
    feature = request.args.get('feature', 'ocr_import')
    return jsonify({'data': guards.check_usage(user_id, feature=feature), 'message': 'ok'})


@ocr_bp.post('/recognize')
def ocr_recognize():
    """上传图片（base64）→ 方案方舟识别 → 候选列表/预览行；消耗 1 次当日配额。"""
    user_id = _current_user_id()
    payload = parse_body(OCRRecognizeRequest)
    import base64

    try:
        image_bytes = base64.b64decode(payload.image_base64)
    except Exception as e:
        logger.warning('AI 识别 base64 解码失败: {}', e)
        raise SBException(code=1001, message='图片 base64 无效', status_code=400)

    recognizer = get_recognizer(payload.scenario)
    # 防护闸：限流 / 连续失败熔断 / 全站 token 预算——全部在真实调用之前，
    # 恶意刷接口在此被拦截，不产生 token 费用与服务器开销（见 ai_recognizer.guards）
    guards.assert_available(user_id)
    # 先消费配额再识别：识别失败会返还（refund_usage），防恶意刷取免费额度
    usage = guards.consume_usage(user_id, feature=recognizer.feature)
    try:
        items = recognizer.recognize_image(image_bytes)
    except SBException:
        # 识别失败（服务不可用/超时等）返还本次配额，避免测试期一次失败即白耗额度
        guards.refund_usage(user_id, feature=recognizer.feature)
        guards.record_failure(user_id)
        raise
    guards.record_success(user_id)
    logger.info('AI 图片识别完成 user={} scenario={} items={}', user_id, recognizer.key, len(items))
    if recognizer.key == 'txn_import':
        rows = _txn_candidates_to_rows(items, request.args.get('ledger_id', type=int))
        return jsonify(
            {
                'data': {'scenario': recognizer.key, 'rows': rows[:OCR_MAX_ITEMS], 'usage': usage},
                'message': 'ok',
            }
        )
    if recognizer.key == 'holding_import':
        rows = _holding_candidates_to_rows(items, request.args.get('ledger_id', type=int))
        return jsonify(
            {
                'data': {'scenario': recognizer.key, 'rows': rows[:OCR_MAX_ITEMS], 'usage': usage},
                'message': 'ok',
            }
        )
    return jsonify({'data': {'items': items[:OCR_MAX_ITEMS], 'usage': usage}, 'message': 'ok'})


@ocr_bp.post('/parse')
def ocr_parse_text():
    """纯文本 → LLM 批量提取（AI 批量导入）；消耗 1 次当日配额。"""
    user_id = _current_user_id()
    payload = parse_body(OCRParseTextRequest)
    recognizer = get_recognizer(payload.scenario)
    # 防护闸同上（限流 / 熔断 / token 预算），在真实调用之前拦截
    guards.assert_available(user_id)
    usage = guards.consume_usage(user_id, feature=recognizer.feature)
    try:
        items = recognizer.recognize_text(payload.text)
    except SBException:
        guards.refund_usage(user_id, feature=recognizer.feature)
        guards.record_failure(user_id)
        raise
    guards.record_success(user_id)
    logger.info('AI 文本识别完成 user={} scenario={} items={}', user_id, recognizer.key, len(items))
    if recognizer.key == 'txn_import':
        rows = _txn_candidates_to_rows(items, request.args.get('ledger_id', type=int))
        return jsonify(
            {
                'data': {'scenario': recognizer.key, 'rows': rows[:OCR_MAX_ITEMS], 'usage': usage},
                'message': 'ok',
            }
        )
    if recognizer.key == 'holding_import':
        rows = _holding_candidates_to_rows(items, request.args.get('ledger_id', type=int))
        return jsonify(
            {
                'data': {'scenario': recognizer.key, 'rows': rows[:OCR_MAX_ITEMS], 'usage': usage},
                'message': 'ok',
            }
        )
    return jsonify({'data': {'items': items[:OCR_MAX_ITEMS], 'usage': usage}, 'message': 'ok'})
