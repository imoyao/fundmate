# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : ocr_service.py
"""OCR 截图导入 / AI 批量导入服务（火山方舟 doubao 全模态）。

技术决策（见 explore-watchlist-enhancement-2026-08-12.md §6）：
- OCR 引擎走火山方舟 OpenAI 兼容端点，纯 HTTP 调用，零本地依赖（否决前端 tesseract / 本地 PaddleOCR）。
- 一次调用同时完成「图像理解 + 结构化 JSON 提取」，前端只传图 + 展示结果。
- 用量经 `user_usage` 表按 (user_id, feature, period_date) 限次（免费 5 次/天）。

调用示例：
    https://ark.cn-beijing.volces.com/api/v3/chat/completions
    Authorization: Bearer <ARK_API_KEY>
"""

import base64
import json
import os
import re
from datetime import date
from typing import List, Optional

import requests
from dotenv import load_dotenv
from loguru import logger

from app.core.database import SessionLocal
from app.core.exceptions import ErrorCode, SBException
from app.domains.usage.models import UserUsage

load_dotenv()  # 独立脚本直接 import 时也能读到 .env（main.py 已 load 则幂等）

# ── 环境配置 ──
ARK_ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
ARK_API_KEY = os.getenv('ARK_API_KEY', '')
ARK_MODEL = os.getenv('ARK_MODEL', 'doubao-seed-2-1-pro-260628')
OCR_DAILY_QUOTA = int(os.getenv('OCR_DAILY_QUOTA', '5'))
OCR_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 图片上限 5MB

_SYSTEM_PROMPT = (
    '你是一个基金/股票代码提取助手。请从用户提供的持仓截图或文本中，'
    '提取所有基金/股票的代码与名称。'
    '只输出 JSON 数组，数组元素为对象：{"code": "6位数字代码", "name": "名称"}。'
    '识别不出名称时 name 可为空字符串。若无有效内容，输出 []。'
    '不要输出任何其他文字或解释。'
)


# ── 用量（user_usage）──
def _get_usage(db, user_id: int, feature: str, period: date) -> UserUsage:
    """取当日用量行，不存在则创建（带默认 quota）。"""
    row = (
        db.query(UserUsage)
        .filter(UserUsage.user_id == user_id, UserUsage.feature == feature, UserUsage.period_date == period)
        .first()
    )
    if row is None:
        row = UserUsage(user_id=user_id, feature=feature, period_date=period, count=0, quota=OCR_DAILY_QUOTA)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def check_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> dict:
    """查询某用户某功能当日用量，返回 {used, quota, remaining, period_date}。"""
    period = period or date.today()
    with SessionLocal() as db:
        row = _get_usage(db, user_id, feature, period)
        return {
            'used': row.count,
            'quota': row.quota,
            'remaining': max(0, row.quota - row.count),
            'period_date': period.isoformat(),
        }


def consume_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> dict:
    """消费一次用量；超限抛 SBException（429 语义，错误码 3004）。"""
    period = period or date.today()
    with SessionLocal() as db:
        row = _get_usage(db, user_id, feature, period)
        if row.count >= row.quota:
            raise SBException(
                code=ErrorCode.USAGE_LIMIT_EXCEEDED.code,
                message=f'今日 {feature} 识别次数已用完（{row.quota} 次/天），请明日再试',
                status_code=ErrorCode.USAGE_LIMIT_EXCEEDED.http_status,
            )
        row.count += 1
        db.commit()
        db.refresh(row)
        return {
            'used': row.count,
            'quota': row.quota,
            'remaining': max(0, row.quota - row.count),
            'period_date': period.isoformat(),
        }


# ── LLM 调用 ──
def _call_ark(content: List[dict], temperature: float = 0.1, timeout: int = 30) -> str:
    """调用火山方舟 OpenAI 兼容端点，返回 choices[0].message.content。"""
    if not ARK_API_KEY:
        raise SBException(
            code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
            message='服务端未配置 ARK_API_KEY，OCR 功能暂不可用',
            status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
        )
    payload = {
        'model': ARK_MODEL,
        'messages': [
            {'role': 'system', 'content': _SYSTEM_PROMPT},
            {'role': 'user', 'content': content},
        ],
        'temperature': temperature,
    }
    try:
        resp = requests.post(
            ARK_ENDPOINT,
            headers={'Authorization': f'Bearer {ARK_API_KEY}', 'Content-Type': 'application/json'},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']
    except requests.RequestException as e:
        logger.error('火山方舟调用失败: {}', e)
        raise SBException(
            code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
            message=f'OCR 识别服务暂时不可用：{e}',
            status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
        )


def _extract_json(text: str) -> List[dict]:
    """从模型输出中稳健提取 JSON 数组（去掉 markdown 围栏/解释文字）。"""
    if not text:
        return []
    # 去掉 ```json ... ``` 围栏
    fence = re.search(r'```(?:json)?\s*(.*?)```', text, re.S)
    if fence:
        text = fence.group(1)
    # 找到第一个 [ 到最后一个 ] 的片段
    start, end = text.find('['), text.rfind(']')
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning('OCR 输出 JSON 解析失败: {}; 原文: {}', e, text[:200])
        return []
    return []


def _validate_items(items: List[dict]) -> List[dict]:
    """清洗识别结果：只保留 6 位数字代码，name 取字符串。"""
    cleaned = []
    for it in items:
        code = str(it.get('code', '') or '').strip()
        name = str(it.get('name', '') or '').strip()
        if re.fullmatch(r'\d{6}', code):
            cleaned.append({'code': code, 'name': name})
    return cleaned


# ── 对外接口 ──
def recognize(image_bytes: bytes) -> List[dict]:
    """图片 → 火山方舟 vision → 基金/股票代码列表。"""
    if not image_bytes:
        raise SBException(code=ErrorCode.INVALID_PARAMS.code, message='图片内容为空', status_code=400)
    if len(image_bytes) > OCR_MAX_IMAGE_BYTES:
        raise SBException(
            code=ErrorCode.INVALID_PARAMS.code, message='图片超过 5MB 上限，请压缩后重试', status_code=400
        )
    b64 = base64.b64encode(image_bytes).decode('ascii')
    content = [
        {'type': 'text', 'text': '请识别图片中的所有基金/股票代码与名称。'},
        {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
    ]
    raw = _call_ark(content)
    return _validate_items(_extract_json(raw))


def parse_text(text: str) -> List[dict]:
    """纯文本 → LLM → 基金/股票代码列表（AI 批量导入，无需图片）。"""
    if not text or not text.strip():
        raise SBException(code=ErrorCode.INVALID_PARAMS.code, message='文本内容为空', status_code=400)
    content = [{'type': 'text', 'text': f'请从以下文本中提取基金/股票代码与名称：\n\n{text[:8000]}'}]
    raw = _call_ark(content)
    return _validate_items(_extract_json(raw))
