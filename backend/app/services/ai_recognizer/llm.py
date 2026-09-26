# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : llm.py
"""AI 识别域 LLM 调用层：火山方舟 OpenAI 兼容端点（doubao 全模态）。

从旧 `ocr_service.py` 的 `_call_ark` 迁出并泛化（P1 抽象）：
- 系统 prompt 改为按场景传入（自选 / 持仓识别各不相同）；
- 超时/token 记账逻辑原样保留；重试升级为**分类退避**（#1121 S1-C）：
  429/5xx/超时/响应体异常才重试，其余 4xx（401 key 错、400 参数错、
  422 schema 错…）立即终止——重试不可能让坏请求变好，只白白拖长失败路径；
- 成功与失败都打 `[llm.call]` 结构化日志行，排障按 tag 过滤；
- 技术决策见 explore-watchlist-enhancement-2026-08-12.md §6。
"""

import os
import time
from typing import List, Optional, Tuple

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
# 可重试类失败（429/5xx/超时/响应体异常）的最大重试次数（0 = 不重试）
ARK_RETRIES = int(os.getenv('ARK_RETRIES', '1'))
# 指数退避基数（秒）：第 n 次失败（n 从 0 计）后睡 base * 2**n → 1.5 / 3 / 6 …
BACKOFF_BASE_SECONDS = 1.5
# 429 的 Retry-After 头封顶（秒）：防服务端回超大值把工作线程挂死
RETRY_AFTER_CAP_SECONDS = 30.0


def _classify_failure(err: Exception) -> Tuple[bool, str]:
    """把失败分为「可重试」与「立即终止」，返回 (是否可重试, 原因标签)。

    - 429 / 5xx / 超时 / 连接失败 / 响应体异常 → 可重试（瞬态，等一等可能变好）；
    - 其余 4xx → 立即终止（客户端错误，重试不可能让坏请求变好）。

    顺序敏感：HTTPError 也是 RequestException，requests 的 JSONDecodeError 也是
    ValueError，先特后泛才能贴对标签（否则坏 JSON 会被误标成 network）。
    """
    if isinstance(err, requests.HTTPError):
        status = getattr(err.response, 'status_code', None)
        if status is None:
            return True, 'http-unknown'  # 理论上 raise_for_status 必带 response，兜底按瞬态处理
        if status == 429 or status >= 500:
            return True, f'http={status}'
        return False, f'http={status}'  # 其余 4xx/3xx：立即终止
    if isinstance(err, (requests.Timeout, requests.ConnectionError)):
        return True, 'network'
    if isinstance(err, (ValueError, KeyError, IndexError, TypeError)):
        return True, 'bad-body'  # 坏 JSON / choices 缺失等响应体异常
    if isinstance(err, requests.RequestException):
        return True, 'network'
    return False, 'unexpected'


def _backoff_seconds(attempt: int, resp: Optional[requests.Response] = None) -> float:
    """第 attempt 次（从 0 计）失败后的睡眠秒数。

    429 带合法**数值型** Retry-After 头时听服务端的（封顶 RETRY_AFTER_CAP_SECONDS），
    否则回落指数退避 base * 2**attempt → 1.5 / 3 / 6 …。
    HTTP-date 形式的 Retry-After 不解析（少见且解析依赖额外依赖），回落指数退避。
    """
    headers = getattr(resp, 'headers', None)
    if headers:
        raw = headers.get('Retry-After')
        if raw not in (None, ''):
            try:
                seconds = float(raw)
            except (TypeError, ValueError):
                seconds = -1.0
            if seconds >= 0:
                return min(seconds, RETRY_AFTER_CAP_SECONDS)
    return BACKOFF_BASE_SECONDS * (2**attempt)


def call_llm(
    content: List[dict],
    system_prompt: str,
    temperature: float = 0.1,
    timeout: Optional[int] = None,
    response_format: Optional[dict] = None,
) -> str:
    """调用火山方舟 OpenAI 兼容端点，返回 choices[0].message.content。

    Args:
        content: 用户消息（文本 / 图片 base64 构成的 OpenAI content 数组）。
        system_prompt: 场景化系统指令（约束输出 JSON schema）。
        temperature / timeout: 覆盖默认值；timeout 缺省用 ARK_TIMEOUT。
        response_format: OpenAI 兼容的响应格式约束（如 {'type': 'json_object'}），
            缺省不传——部分模型/端点不支持该参数，由调用方按需开启。

    兜底设计（用户反馈 503 直报问题）：
    - 超时放宽到 ARK_TIMEOUT（默认 60s，图片/长文本识别慢，30s 易 ReadTimeout）；
    - 可重试失败按 _classify_failure 分类，指数退避重试 ARK_RETRIES 次
      （429 认 Retry-After，见 _backoff_seconds）；其余 4xx 立即终止不重试；
    - 重试耗尽 / 立即终止都抛 503（OCR_SERVICE_UNAVAILABLE），由 views 层返还配额；
    - 每次成功打一行 [llm.call] ok …，失败打 retry / fail-fast / fail 行。
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
    if response_format:
        payload['response_format'] = response_format

    attempts = ARK_RETRIES + 1
    last_err: Optional[Exception] = None
    made = 0  # 实际发出的请求数（fail-fast 时可能 < attempts，日志别报虚数）
    for attempt in range(attempts):
        resp: Optional[requests.Response] = None
        made = attempt + 1
        started = time.monotonic()
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
            tokens = int(usage.get('total_tokens') or 0)
            _record_tokens(tokens)
            text = data['choices'][0]['message']['content']
            logger.info(
                '[llm.call] ok attempt={} model={} tokens={} elapsed={:.2f}s',
                attempt + 1,
                ARK_MODEL,
                tokens,
                time.monotonic() - started,
            )
            return text
        except Exception as e:  # noqa: BLE001  收全再分类：分类表见 _classify_failure
            last_err = e
            retryable, reason = _classify_failure(e)
            if not retryable:
                logger.error('[llm.call] fail-fast attempt={} reason={} err={}', attempt + 1, reason, e)
                break
            if attempt < ARK_RETRIES:
                delay = _backoff_seconds(attempt, resp)
                logger.warning(
                    '[llm.call] retry attempt={}/{} reason={} backoff={:.2f}s err={}',
                    attempt + 1,
                    ARK_RETRIES,
                    reason,
                    delay,
                    e,
                )
                time.sleep(delay)
    logger.error('[llm.call] fail attempts={} last_err={}', made, last_err)
    raise SBException(
        code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
        message='AI 识别服务暂时不可用，请稍后重试',
        status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
    )
