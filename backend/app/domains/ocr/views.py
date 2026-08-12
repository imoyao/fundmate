# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : views.py
"""OCR 识别 API：图片识别 / 文本批量导入 / 用量查询.

鉴权：非白名单接口，需登录；当前用户从 g.current_user 取（core/auth.py 注入）。
"""

from apiflask import APIBlueprint
from flask import g, jsonify
from loguru import logger

from app.core.exceptions import SBException
from app.core.validation import parse_body
from app.domains.ocr.schemas import OCRParseTextRequest, OCRRecognizeRequest
from app.services import ocr_service

ocr_bp = APIBlueprint('ocr', __name__, url_prefix='/api/ocr')

# 图片 OCR 单次最多识别多少条（防单次调用爆量）
OCR_MAX_ITEMS = 30


def _current_user_id() -> int:
    user = getattr(g, 'current_user', None)
    if user is None:
        raise SBException(code=1005, message='未授权，请先登录', status_code=401)
    return user.id


@ocr_bp.get('/usage')
def get_ocr_usage():
    """查询当日 OCR 剩余次数（进入弹窗前展示余量）。"""
    user_id = _current_user_id()
    return jsonify({'data': ocr_service.check_usage(user_id), 'message': 'ok'})


@ocr_bp.post('/recognize')
def ocr_recognize():
    """上传图片（base64）→ 火山方舟识别 → 基金候选列表；消耗 1 次当日配额。"""
    user_id = _current_user_id()
    payload = parse_body(OCRRecognizeRequest)
    import base64

    try:
        image_bytes = base64.b64decode(payload.image_base64)
    except Exception as e:
        logger.warning('OCR base64 解码失败: {}', e)
        raise SBException(code=1001, message='图片 base64 无效', status_code=400)

    # 先消费配额再识别：识别失败会返还（refund_usage），防恶意刷取免费额度
    usage = ocr_service.consume_usage(user_id)
    try:
        items = ocr_service.recognize(image_bytes)
    except SBException:
        # 识别失败（服务不可用/超时等）返还本次配额，避免测试期一次失败即白耗额度
        ocr_service.refund_usage(user_id)
        raise
    logger.info('OCR 识别完成 user={} items={}', user_id, len(items))
    return jsonify({'data': {'items': items[:OCR_MAX_ITEMS], 'usage': usage}, 'message': 'ok'})


@ocr_bp.post('/parse')
def ocr_parse_text():
    """纯文本 → LLM 批量提取基金代码（AI 批量导入）；消耗 1 次当日配额。"""
    user_id = _current_user_id()
    payload = parse_body(OCRParseTextRequest)
    usage = ocr_service.consume_usage(user_id)
    try:
        items = ocr_service.parse_text(payload.text)
    except SBException:
        ocr_service.refund_usage(user_id)
        raise
    logger.info('文本批量导入解析完成 user={} items={}', user_id, len(items))
    return jsonify({'data': {'items': items[:OCR_MAX_ITEMS], 'usage': usage}, 'message': 'ok'})
