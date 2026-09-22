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
from app.services.import_records import StandardHoldingRecord
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.ocr_service import txn_candidates_to_rows as svc_txn_candidates_to_rows

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

    from app.core.database import get_session

    with get_session() as db:
        orch = ImportOrchestrator(db, get_family_id())
        result = orch.preview_holding_records(
            records, _ledger_name(ledger_id), ledger_id, source=PositionSource.AI_HOLDING.value
        )

    return result['rows']


@ocr_bp.post('/recognize/', strict_slashes=False)
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
        rows = svc_txn_candidates_to_rows(items, request.args.get('ledger_id', type=int))
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


@ocr_bp.post('/parse/', strict_slashes=False)
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
        rows = svc_txn_candidates_to_rows(items, request.args.get('ledger_id', type=int))
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
