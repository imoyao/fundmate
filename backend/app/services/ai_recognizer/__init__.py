# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : ai_recognizer/__init__.py
"""AI 识别域（对称模板导入 importer 的分层架构，见 ai-recognizer-architecture-2026-08-13.md）。

结构：
    base.py        BaseRecognizer 抽象基类（模板方法：正则层 → LLM 层 → validate → enrich）
    guards.py      用量（user_usage）+ 限流/连续失败熔断/token 预算
    llm.py         火山方舟调用（便宜模型 + 超时/重试/token 记账）
    catalog.py     类型/名称反查（证券/基金表消歧）
    registry.py    识别器注册表（按 scenario 取用）
    recognizers/   场景识别器（watchlist_import / txn_import）
    schemas.py     候选行数据契约

导入本包即完成场景注册；API 层用 get_recognizer(scenario) 取用。
"""

import app.services.ai_recognizer.recognizers  # noqa: F401  触发场景注册
from app.services.ai_recognizer.base import BaseRecognizer
from app.services.ai_recognizer.catalog import enrich as catalog_enrich
from app.services.ai_recognizer.guards import assert_available, check_usage, consume_usage
from app.services.ai_recognizer.registry import get_recognizer, get_scenarios, register_recognizer

__all__ = [
    'BaseRecognizer',
    'assert_available',
    'catalog_enrich',
    'check_usage',
    'consume_usage',
    'get_recognizer',
    'get_scenarios',
    'register_recognizer',
]
