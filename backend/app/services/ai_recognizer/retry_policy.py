# -*- coding: utf-8 -*-
"""上游失败的分类 / 退避 / 话术策略（纯标准库，可被 CI 探针按文件直接加载）。

这里只放**纯策略**：不碰 HTTP 客户端、不打日志、不依赖 Flask/DB。

1. `classify_429(body)`：429 响应体 → `quota` / `rate_limit` / `unknown`；
2. `retry_decision(resp)`：429 该不该重试（额度类终止、限流/未知类重试）；
3. `backoff_seconds(attempt, resp)`：第 n 次失败后睡多久（429 认 Retry-After，封顶）；
4. `failure_message(reason)`：收尾话术——额度类不能说「请稍后重试」。

WHY 独立成模块（2026-11-18）：

- **单一真源**：`llm._classify_failure`（运行时重试）与 `scripts/llm_health_probe.py`
  （CI 探测）曾各写了一份 429 判断，症状是「探针报额度耗尽、运行时还在白重试」——
  同一判断手写多份，改一处漏一处；
- **依赖边界**：探针要在没有后端依赖的 CI job 里跑，所以本模块只用标准库；需要
  `requests` 的 isinstance 判定（Timeout / ConnectionError / 4xx…）留在
  `llm._classify_failure`；
- **体量**：`llm.py` 有「只减不增」的体量闸门（`scripts/guard_service_size.py`），
  纯策略本来就该下沉到子模块。

429 的两类处置完全相反：额度/模型限额（`SetLimitExceeded`/`QuotaExceeded`，方舟「安全
体验模式」按模型封顶）重试必然再失败，只能等额度恢复或换模型；限流
（`RateLimitExceeded`）退避几秒通常就过。**未知类故意不预设结论**，由调用方按各自代价
选边：运行时倾向「先重试一次」（漏判只多一次请求，误判终止则白丢一次用户请求）；
探针倾向「当作额度类」（它的代价是再跑一整轮必然失败的 CI）。
"""

import json
from typing import Tuple

# 分类标签：调用方按标签决定处置，**不要解析 detail 文案**（文案会随排障需要改）
QUOTA = 'quota'
RATE_LIMIT = 'rate_limit'
UNKNOWN = 'unknown'

# 限流词优先于额度词：两者同时出现时，重试的代价（多一次请求）远小于误判终止
RATE_LIMIT_WORDS = (
    'ratelimit',
    'rate_limit',
    'rate limit',
    'rpm',
    'tpm',
    'qps',
    'too_many_requests',
    'too many requests',
)
# 额度 / 模型限额词：方舟实测 QuotaExceeded、SetLimitExceeded（文案含 model service has been paused）
QUOTA_WORDS = ('quota', 'setlimit', 'limit_exceeded', 'exhausted', 'paused')

# 收尾话术：额度类与瞬态类刻意分开——「请稍后重试」是瞬态暗示，额度用尽时照着做只会再撞一次
QUOTA_EXHAUSTED_MESSAGE = 'AI 服务额度已用尽（上游模型限额），需等待额度恢复或更换模型'
SERVICE_UNAVAILABLE_MESSAGE = 'AI 识别服务暂时不可用，请稍后重试'

# 指数退避基数（秒）：第 n 次失败（n 从 0 计）后睡 base * 2**n → 1.5 / 3 / 6 …
BACKOFF_BASE_SECONDS = 1.5
# 429 的 Retry-After 头封顶（秒）：防服务端回超大值把工作线程挂死
RETRY_AFTER_CAP_SECONDS = 30.0


def error_code(body: str) -> str:
    """从 429 响应体里取上游错误码（`error.code` / `error.type` / 顶层 `code`）。

    兼容三种形态：OpenAI 风格的 `{"error": {"code": ...}}`、方舟个别端点的
    `{"error": {"type": ...}}`、以及顶层平铺的 `{"code": ...}`。取不到返回空串
    （非 JSON 响应体、网关纯文本都在此列）。
    """
    try:
        payload = json.loads(body or '{}')
    except (TypeError, ValueError):
        return ''
    if not isinstance(payload, dict):
        return ''
    err = payload.get('error')
    if isinstance(err, dict):
        return str(err.get('code') or err.get('type') or '')
    if isinstance(payload.get('code'), str):
        return str(payload['code'])
    return ''


def classify_429(body: str) -> Tuple[str, str]:
    """429 响应体 → (分类标签, 上游错误码)。只分类，不处置。"""
    code = error_code(body)
    haystack = f'{code} {body or ""}'.lower()
    if any(word in haystack for word in RATE_LIMIT_WORDS):
        return (RATE_LIMIT, code)
    if any(word in haystack for word in QUOTA_WORDS):
        return (QUOTA, code)
    return (UNKNOWN, code)


def response_text(resp) -> str:
    """取响应体原文；读不到（流已关闭 / 编码异常 / 没有该属性）返回空串。

    鸭子类型而非 `requests.Response`：本模块要保持零第三方依赖。
    """
    try:
        return resp.text or ''
    except Exception:  # noqa: BLE001  读不到响应体不该让分类本身失败
        return ''


def retry_decision(resp) -> Tuple[bool, str]:
    """429 的处置 → (是否可重试, 原因标签)。

    额度类给 `quota:<上游错误码>`（排障能直接归因到具体码），其余给 `http=429`。
    """
    label, code = classify_429(response_text(resp))
    if label == QUOTA:
        return False, f'quota:{code or "no-code"}'
    return True, 'http=429'


def backoff_seconds(attempt: int, resp=None) -> float:
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


def failure_message(reason: str) -> str:
    """终止态原因标签 → 对外话术（额度类换话术，对外错误码不变）。"""
    return QUOTA_EXHAUSTED_MESSAGE if reason.startswith('quota') else SERVICE_UNAVAILABLE_MESSAGE
