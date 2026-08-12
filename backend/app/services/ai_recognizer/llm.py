# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : llm.py
"""AI 识别域 LLM 调用层：火山方舟 OpenAI 兼容端点（doubao 全模态）。

从旧 `ocr_service.py` 的 `_call_ark` 迁出并泛化（P1 抽象）：
- 系统 prompt 改为按场景传入（自选 / 持仓识别各不相同）；
- 超时/重试/token 记账逻辑原样保留；
- 技术决策见 explore-watchlist-enhancement-2026-08-12.md §6。
"""

import os
import time
from typing import List, Optional

import requests
from dotenv import load_dotenv
from loguru import logger

from app.core.exceptions import ErrorCode, SBException
from app.services.ai_recognizer.guards import _record_tokens

load_dotenv()  # 独立脚本直接 import 时也能读到 .env（main.py 已 load 则幂等）

# ── 环境配置 ──
ARK_ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
ARK_API_KEY = os.getenv('ARK_API_KEY', '')
# 默认用便宜的 doubao mini（文本/图片都支持，成本约为旗舰 pro 的 1/10，识别基金/股票
# 代码+名称这类简单结构化任务是杀鸡用牛刀，无需顶级模型；如需提精度可在 .env 覆盖 ARK_MODEL。
ARK_MODEL = os.getenv('ARK_MODEL', 'doubao-seed-2-0-mini-260428')
# LLM 单次请求超时（秒）：图片/长文本识别较慢，30s 在数据量大时易 ReadTimeout → 503
ARK_TIMEOUT = int(os.getenv('ARK_TIMEOUT', '60'))
# 网络异常/超时/5xx 时的重试次数（0 = 不重试）；重试间隔 1.5s
ARK_RETRIES = int(os.getenv('ARK_RETRIES', '1'))


def call_llm(content: List[dict], system_prompt: str, temperature: float = 0.1, timeout: int = None) -> str:
    """调用火山方舟 OpenAI 兼容端点，返回 choices[0].message.content。

    Args:
        content: 用户消息（文本 / 图片 base64 构成的 OpenAI content 数组）。
        system_prompt: 场景化系统指令（约束输出 JSON schema）。
        temperature / timeout: 覆盖默认值；timeout 缺省用 ARK_TIMEOUT。

    兜底设计（用户反馈 503 直报问题）：
    - 超时放宽到 ARK_TIMEOUT（默认 60s，图片/长文本识别慢，30s 易 ReadTimeout）；
    - 网络异常/超时/5xx 自动重试 ARK_RETRIES 次（默认 1 次，间隔 1.5s）；
    - 重试耗尽才抛 503（OCR_SERVICE_UNAVAILABLE），由 views 层返还配额。
    """
    if not ARK_API_KEY:
        raise SBException(
            code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
            message='服务端未配置 ARK_API_KEY，AI 识别功能暂不可用',
            status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
        )
    timeout = timeout or ARK_TIMEOUT
    payload = {
        'model': ARK_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': content},
        ],
        'temperature': temperature,
    }

    last_err: Optional[Exception] = None
    for attempt in range(ARK_RETRIES + 1):
        try:
            resp = requests.post(
                ARK_ENDPOINT,
                headers={'Authorization': f'Bearer {ARK_API_KEY}', 'Content-Type': 'application/json'},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            # 费用护栏：累计本次调用 token 消耗（图片输入按 token 计费，见 issue #823）
            usage = data.get('usage') or {}
            _record_tokens(int(usage.get('total_tokens') or 0))
            return data['choices'][0]['message']['content']
        except (requests.RequestException, KeyError, ValueError) as e:
            last_err = e
            logger.warning('火山方舟调用失败（第 {} 次）: {}', attempt + 1, e)
            if attempt < ARK_RETRIES:
                time.sleep(1.5)
    logger.error('火山方舟调用重试 {} 次后仍失败: {}', ARK_RETRIES, last_err)
    raise SBException(
        code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
        message='AI 识别服务暂时不可用，请稍后重试',
        status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
    )
