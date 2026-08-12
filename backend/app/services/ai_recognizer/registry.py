# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : registry.py
"""AI 识别器注册表（对称模板导入 registry.py）。

新增场景只需在此注册一行：register_recognizer(key, recognizer)，API 层按 scenario 取用。
"""

from typing import Optional

from app.services.ai_recognizer.base import BaseRecognizer

RECOGNIZER_REGISTRY: dict[str, BaseRecognizer] = {}

# 默认场景：缺省 scenario 参数时回退（兼容旧前端不传参）
DEFAULT_SCENARIO = 'watchlist_import'


def register_recognizer(key: str, recognizer: BaseRecognizer) -> None:
    """注册一个识别器实例。"""
    if not key or not isinstance(recognizer, BaseRecognizer):
        raise ValueError(f'非法识别器注册: key={key}')
    RECOGNIZER_REGISTRY[key] = recognizer


def get_recognizer(scenario: Optional[str] = None) -> BaseRecognizer:
    """根据场景标识获取识别器；缺省/未知场景回退默认（与旧 `/api/ocr/*` 行为一致）。"""
    key = scenario or DEFAULT_SCENARIO
    recognizer = RECOGNIZER_REGISTRY.get(key)
    if recognizer is None:
        recognizer = RECOGNIZER_REGISTRY.get(DEFAULT_SCENARIO)
    if recognizer is None:
        raise RuntimeError(f'AI 识别器未注册: {DEFAULT_SCENARIO}')
    return recognizer


def get_scenarios() -> list[str]:
    """返回所有已注册场景标识。"""
    return list(RECOGNIZER_REGISTRY.keys())


# ── 场景注册（对称 importer.registry：新场景在此加一行）──
from app.services.ai_recognizer.recognizers.txn_recognizer import TxnRecognizer  # noqa: E402
from app.services.ai_recognizer.recognizers.watchlist_recognizer import WatchlistRecognizer  # noqa: E402

register_recognizer(WatchlistRecognizer.key, WatchlistRecognizer())
register_recognizer(TxnRecognizer.key, TxnRecognizer())
