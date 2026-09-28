# -*- coding: utf-8 -*-
"""G6 意图路由注册表测试（#1742，设计 §8）。

registry.py 里两个注册表并存：scenario → recognizer（OCR 场景）与 category → route
（对话精灵意图路由）。本文件证明：
① 五类意图按设计分发，未知类别回退工具链（宁走默认路径，不误拦）；
② register_intent_route 校验非法输入，且注册不影响 scenario 注册表；
③ 路由到「拦截」的类别都取得到非空标准话术（与 intent_guard 的映射一致性——
   两模块各自维护，接线处靠这份一致性才敢直接拦截）。
不触网：本文件不含模型调用。
"""

import pytest

from app.services.ai_recognizer import registry
from app.services.ai_recognizer.safety import intent_guard
from app.services.ai_recognizer.safety.intent_guard import (
    CATEGORY_ADVICE,
    CATEGORY_EMOTION,
    CATEGORY_KNOWLEDGE,
    CATEGORY_PREDICTION,
    CATEGORY_QUERY,
)


def test_five_categories_route_as_designed():
    """设计口径：预测 / 建议 → 标准话术；查询 / 知识 / 情绪 → 查询工具链。"""
    assert registry.route_intent(CATEGORY_QUERY) == registry.ROUTE_TOOL_CHAIN
    assert registry.route_intent(CATEGORY_KNOWLEDGE) == registry.ROUTE_TOOL_CHAIN
    assert registry.route_intent(CATEGORY_EMOTION) == registry.ROUTE_TOOL_CHAIN
    assert registry.route_intent(CATEGORY_PREDICTION) == registry.ROUTE_STANDARD_REPLY
    assert registry.route_intent(CATEGORY_ADVICE) == registry.ROUTE_STANDARD_REPLY


def test_unknown_category_falls_back_to_tool_chain():
    """classify 之外的类别回退工具链：宁可交给模型裁决，也不能误拦成空白回复。"""
    assert registry.route_intent('nonsense') == registry.ROUTE_TOOL_CHAIN
    assert registry.route_intent('') == registry.ROUTE_TOOL_CHAIN


def test_register_intent_route_validates_and_overrides():
    registry.register_intent_route('custom', registry.ROUTE_STANDARD_REPLY)
    try:
        assert registry.route_intent('custom') == registry.ROUTE_STANDARD_REPLY
    finally:
        registry._INTENT_ROUTES.pop('custom', None)  # 测试自建路由不留痕（同包测试，允许触私有）
    with pytest.raises(ValueError):
        registry.register_intent_route('x', 'not-a-route')  # 非法路由值
    with pytest.raises(ValueError):
        registry.register_intent_route('', registry.ROUTE_TOOL_CHAIN)  # 空类别


def test_intent_route_does_not_touch_recognizer_registry():
    """G6 验收：意图路由与既有 scenario 静态注册互不干扰。"""
    scenarios_before = set(registry.get_scenarios())
    registry.register_intent_route('custom2', registry.ROUTE_TOOL_CHAIN)
    try:
        assert set(registry.get_scenarios()) == scenarios_before
    finally:
        registry._INTENT_ROUTES.pop('custom2', None)


def test_standard_reply_mapping_covers_all_blocked_routes():
    """凡路由到 standard_reply 的类别必须有非空话术，否则接线处会回退工具链（防御分支）。"""
    for category, route in registry._INTENT_ROUTES.items():
        if route == registry.ROUTE_STANDARD_REPLY:
            assert intent_guard.standard_reply(category), f'{category} 缺标准话术'
    # 非拦截类别返回空串：调用方不应在非拦截路径取话术
    assert intent_guard.standard_reply(CATEGORY_QUERY) == ''
