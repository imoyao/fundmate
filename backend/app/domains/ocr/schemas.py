# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : schemas.py
"""OCR API 请求/响应 Schema."""

from typing import Optional

from pydantic import BaseModel, Field


class OCRRecognizeRequest(BaseModel):
    """图片 OCR 识别请求（multipart 上传场景用 files，此处兼容 JSON base64 方式）。"""

    image_base64: str = Field(..., description='图片 base64 字符串')


class OCRParseTextRequest(BaseModel):
    """纯文本 AI 批量导入请求."""

    text: str = Field(..., max_length=8000, description='用户粘贴的持仓文本')


class OCRItemOut(BaseModel):
    """识别出的单个基金候选.

    symbol/type/market/venue 由后端反查 Securities/Funds 表补充（_enrich_items），
    前端导入时直接透传，避免按代码前缀猜测导致股票/深市 ETF 误判为场外基金。
    """

    code: str
    name: str = ''
    symbol: Optional[str] = None
    type: Optional[str] = None
    market: Optional[str] = None
    venue: Optional[str] = None


class OCRResultOut(BaseModel):
    """识别结果 + 本次消耗后的用量快照."""

    items: list[OCRItemOut]
    usage: dict


class OCRUsageOut(BaseModel):
    """OCR 用量查询响应."""

    feature: str = 'ocr_import'
    used: int
    quota: int
    remaining: int
    period_date: str
