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
  429 再分一层（2026-11-18）：额度/模型限额（`SetLimitExceeded`/`QuotaExceeded`）
  同样立即终止，只有限流类才退避——判据与话术见 `retry_policy`；
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
from app.services.ai_recognizer import retry_policy
from app.services.ai_recognizer.guards import _record_tokens

load_dotenv()  # 独立脚本直接 import 时也能读到 .env（main.py 已 load 则幂等）

# ── 环境配置 ──
ARK_ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
ARK_API_KEY = os.getenv('ARK_API_KEY', '')
# OCR / 结构化识别档（默认档）：必须**支持图片输入**，故保留 doubao 视觉模型。
# 2026-10-25 起缺省换 2-1-lite：原 2-0-mini 实测 429 SetLimitExceeded（账号用量上限暂停），
# 报错文案指向方舟控制台「安全体验模式」，不是 key 失效。
# ⚠️ 换成纯文本模型（如 deepseek 系）会让图片识别直接 400，OCR 请勿走这一档。
ARK_MODEL = os.getenv('ARK_MODEL', 'doubao-seed-2-1-lite-260915')
# OCR 档的深度思考开关：'disabled' / 'enabled' / 'none'（none = 不传该参数）。
# 实测（2026-10-25，2-1-lite 识一张 260x80 的代码图）：
#   默认（不传，服务端开思考）→ 112.2s / 9002 token，且漏识别一个代码；
#   thinking=disabled          →   5.9s / 1367 token，三个代码全对。
# 不关思考会超过 ARK_TIMEOUT(60s) 直接 ReadTimeout→503，故默认 disabled；
# 若换回不支持该参数的模型（如 doubao-seed-2-0 系）置 none。
ARK_OCR_THINKING = os.getenv('ARK_OCR_THINKING', 'disabled').strip().lower()
# 账本精灵（对话 Agent）档：与 OCR 解耦（2026-11-17 起 glm-5-2-260617，纯文本推理系）；
# 旧 deepseek-v4-1-flash-economy 触发 429 SetLimitExceeded（按模型封顶，非账号级）。
# 思考缺省不传（服务端默认）；实测开思考会推理失控（单次叙事 37k token / 200s+），A/B 见下。
ARK_MODEL_AGENT = os.getenv('ARK_MODEL_AGENT', 'glm-5-2-260617')
# LLM 单次请求超时（秒）：图片/长文本识别较慢，30s 在数据量大时易 ReadTimeout → 503
ARK_TIMEOUT = int(os.getenv('ARK_TIMEOUT', '60'))
# 可重试类失败（限流/未知类 429、5xx、超时、响应体异常）的最大重试次数（0 = 不重试）
# 注意：额度类 429（SetLimitExceeded 等）不计入重试，见 retry_policy.retry_decision
ARK_RETRIES = int(os.getenv('ARK_RETRIES', '1'))


def _classify_failure(err: Exception) -> Tuple[bool, str]:
    """把失败分为「可重试」与「立即终止」，返回 (是否可重试, 原因标签)。

    - 429 分两类（判定见 `retry_policy.retry_decision`）：额度/模型限额 → 立即终止，
      限流与未知类 → 可重试；
    - 5xx / 超时 / 连接失败 / 响应体异常 → 可重试（瞬态，等一等可能变好）；
    - 其余 4xx → 立即终止（客户端错误，重试不可能让坏请求变好）。

    顺序敏感：HTTPError 也是 RequestException，requests 的 JSONDecodeError 也是
    ValueError，先特后泛才能贴对标签（否则坏 JSON 会被误标成 network）。
    """
    if isinstance(err, requests.HTTPError):
        status = getattr(err.response, 'status_code', None)
        if status is None:
            return True, 'http-unknown'  # 理论上 raise_for_status 必带 response，兜底按瞬态处理
        if status == 429:
            return retry_policy.retry_decision(err.response)
        if status >= 500:
            return True, f'http={status}'
        return False, f'http={status}'  # 其余 4xx/3xx：立即终止
    if isinstance(err, (requests.Timeout, requests.ConnectionError)):
        return True, 'network'
    if isinstance(err, (ValueError, KeyError, IndexError, TypeError)):
        return True, 'bad-body'  # 坏 JSON / choices 缺失等响应体异常
    if isinstance(err, requests.RequestException):
        return True, 'network'
    return False, 'unexpected'


def call_llm(
    content: List[dict],
    system_prompt: str,
    temperature: float = 0.1,
    timeout: Optional[int] = None,
    response_format: Optional[dict] = None,
    usage_sink: Optional[dict] = None,
    model: Optional[str] = None,
    thinking: Optional[str] = os.getenv('ARK_AGENT_THINKING'),
) -> str:
    """调用火山方舟 OpenAI 兼容端点，返回 choices[0].message.content。

    Args:
        content: 用户消息（文本 / 图片 base64 构成的 OpenAI content 数组）。
        system_prompt: 场景化系统指令（约束输出 JSON schema）。
        temperature / timeout: 覆盖默认值；timeout 缺省用 ARK_TIMEOUT。
        response_format: OpenAI 兼容的响应格式约束（如 {'type': 'json_object'}），
            缺省不传——部分模型/端点不支持该参数，由调用方按需开启。
        usage_sink: 可选 token 汇出槽（#1736 S4 trace）——传 dict 则每次成功调用累加
            {'tokens': int}，供调用方按轮汇总；缺省 None 零影响，重试路径不累加（失败无 usage）。
        model: 覆盖默认档（缺省 ARK_MODEL）。**图片输入必须留在默认档**；
            账本精灵等纯文本对话传 ARK_MODEL_AGENT（见该常量注释）。
        thinking: 深度思考开关，仅取 'enabled' / 'disabled'（其余值不传）。缺省读 ARK_AGENT_THINKING，
            空 = 不传（服务端默认）：实测 glm 开思考会推理失控（37k token / 200s+），关思考 5~17s；
            OCR 链路传 ARK_OCR_THINKING，见该常量注释。

    兜底设计（用户反馈 503 直报问题）：
    - 超时放宽到 ARK_TIMEOUT（默认 60s，图片/长文本识别慢，30s 易 ReadTimeout）；
    - 可重试失败按 _classify_failure 分类退避重试 ARK_RETRIES 次（Retry-After 见 retry_policy）；
    - 其余 4xx 与 429 里的**额度/模型限额**立即终止（重试无解），只有限流才退避；
    - 重试耗尽 / 立即终止都抛 503 由 views 返还配额，但话术分开：额度类说「额度已用尽」，
      瞬态类才说「请稍后重试」；成功打一行 [llm.call] ok，失败打 retry / fail-fast / fail 行。
    """
    if not ARK_API_KEY:
        raise SBException(
            code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
            message='服务端未配置 ARK_API_KEY，AI 识别功能暂不可用',
            status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
        )
    timeout = timeout or ARK_TIMEOUT
    used_model = model or ARK_MODEL
    payload = {
        'model': used_model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': content},
        ],
        'temperature': temperature,
    }
    if response_format:
        payload['response_format'] = response_format
    if thinking in ('enabled', 'disabled'):
        payload['thinking'] = {'type': thinking}

    attempts = ARK_RETRIES + 1
    last_err: Optional[Exception] = None
    made = 0  # 实际发出的请求数（fail-fast 时可能 < attempts，日志别报虚数）
    fail_reason = ''  # 最近一次失败的原因标签：决定收尾话术（额度类不能说「稍后重试」）
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
            if usage_sink is not None:
                usage_sink['tokens'] = usage_sink.get('tokens', 0) + tokens
            text = data['choices'][0]['message']['content']
            logger.info(
                '[llm.call] ok attempt={} model={} tokens={} elapsed={:.2f}s',
                attempt + 1,
                used_model,
                tokens,
                time.monotonic() - started,
            )
            return text
        except Exception as e:  # noqa: BLE001  收全再分类：分类表见 _classify_failure
            last_err = e
            retryable, fail_reason = _classify_failure(e)
            if not retryable:
                logger.error('[llm.call] fail-fast attempt={} reason={} err={}', attempt + 1, fail_reason, e)
                break
            if attempt < ARK_RETRIES:
                delay = retry_policy.backoff_seconds(attempt, resp)
                logger.warning(
                    '[llm.call] retry attempt={}/{} reason={} backoff={:.2f}s err={}',
                    attempt + 1,
                    ARK_RETRIES,
                    fail_reason,
                    delay,
                    e,
                )
                time.sleep(delay)
    logger.error('[llm.call] fail attempts={} last_err={}', made, last_err)
    raise SBException(
        code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
        message=retry_policy.failure_message(fail_reason),  # 额度类换话术，错误码不变
        status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
    )
