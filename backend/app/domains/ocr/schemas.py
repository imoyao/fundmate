# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : schemas.py
"""OCR API 请求/响应 Schema."""

from pydantic import BaseModel, Field


class OCRRecognizeRequest(BaseModel):
    """图片 OCR 识别请求（multipart 上传场景用 files，此处兼容 JSON base64 方式）。"""

    image_base64: str = Field(..., description='图片 base64 字符串')


class OCRParseTextRequest(BaseModel):
    """纯文本 AI 批量导入请求."""

    text: str = Field(..., max_length=8000, description='用户粘贴的持仓文本')


class OCRItemOut(BaseModel):
    """识别出的单个基金候选."""

    code: str
    name: str = ''


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
