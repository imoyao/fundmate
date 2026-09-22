# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : ocr_service.py
"""OCR 截图导入 / AI 批量导入服务 —— 兼容外观层（thin facade）。

P1 重构（ai-recognizer-architecture-2026-08-13.md）后，业务逻辑已全部迁入
`app/services/ai_recognizer/` 分层包：

    guards.py    用量 / 限流 / 连续失败熔断 / token 预算（按 feature 独立限次）
    llm.py       火山方舟调用（便宜模型 doubao mini + 超时/重试/token 记账）
    catalog.py   类型/名称反查（证券/基金表消歧、场内基金优先）
    recognizers/watchlist_recognizer.py   自选场景（本文件对外接口的默认实现）
    recognizers/txn_recognizer.py         持仓场景

本模块保留旧接口（供 `domains/ocr/views.py` 与既有测试引用），行为与重构前完全一致；
新增场景请走 `get_recognizer(scenario)`，不要在本文件继续堆业务逻辑。
"""

from app.services.ai_recognizer.catalog import (
    _enrich_items,
    _is_listed_fund_code,
    _name_hits,
    is_listed_fund_code,
    name_hits,
)
from app.services.ai_recognizer.catalog import (
    enrich as enrich_items,
)
from app.services.ai_recognizer.guards import (
    ARK_DAILY_TOKEN_BUDGET,
    OCR_DAILY_QUOTA,
    OCR_MELTDOWN_COOLDOWN,
    OCR_MELTDOWN_THRESHOLD,
    OCR_RATE_LIMIT_MAX,
    assert_available,
    check_usage,
    consume_usage,
    record_failure,
    record_success,
    refund_usage,
)
from app.services.ai_recognizer.llm import (
    ARK_API_KEY,
    ARK_ENDPOINT,
    ARK_MODEL,
    ARK_RETRIES,
    ARK_TIMEOUT,
)
from app.services.ai_recognizer.llm import (
    call_llm as _call_ark,
)
from app.services.ai_recognizer.recognizers.watchlist_recognizer import WatchlistRecognizer

# 默认场景识别器（watchlist_import = 旧 /api/ocr/* 行为）
_RECOGNIZER = WatchlistRecognizer()


# ── 兼容入口（委托默认场景识别器）──
def recognize(image_bytes: bytes) -> list:
    """图片 → 火山方舟 vision（默认 mini 便宜模型）→ 基金/股票代码列表。"""
    return _RECOGNIZER.recognize_image(image_bytes)


def parse_text(text: str) -> list:
    """纯文本 → 基金/股票代码列表（AI 批量导入，无需图片）。

    分层策略：1. 正则层（简单排版「代码 名称」零成本）；2. LLM 层（复杂排版 mini 兜底）。
    """
    return _RECOGNIZER.recognize_text(text)


__all__ = [
    'ARK_API_KEY',
    'ARK_DAILY_TOKEN_BUDGET',
    'ARK_ENDPOINT',
    'ARK_MODEL',
    'ARK_RETRIES',
    'ARK_TIMEOUT',
    'OCR_DAILY_QUOTA',
    'OCR_MELTDOWN_COOLDOWN',
    'OCR_MELTDOWN_THRESHOLD',
    'OCR_RATE_LIMIT_MAX',
    '_call_ark',
    '_enrich_items',
    '_is_listed_fund_code',
    '_name_hits',
    'assert_available',
    'check_usage',
    'consume_usage',
    'enrich_items',
    'is_listed_fund_code',
    'name_hits',
    'parse_text',
    'recognize',
    'record_failure',
    'record_success',
    'refund_usage',
]
