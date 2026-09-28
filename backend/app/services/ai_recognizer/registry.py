# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : registry.py
"""AI 识别器注册表（对称模板导入 registry.py）+ 意图路由表（G6，#1742）。

两个注册表并存、互不影响：
- scenario → recognizer：OCR 场景静态注册，新增场景一行 register_recognizer(key, recognizer)，
  API 层按 scenario 取用；
- 意图类别 → 路由：对话精灵用，A 前置分类结果决定走「查询工具链」还是「直接拦截 / 标准话术」
  （设计 §8「registry.py 扩展：引入意图路由」），见下方 route_intent。
"""

from typing import Optional

from app.services.ai_recognizer.base import BaseRecognizer
from app.services.ai_recognizer.safety.intent_guard import (
    CATEGORY_ADVICE,
    CATEGORY_EMOTION,
    CATEGORY_KNOWLEDGE,
    CATEGORY_PREDICTION,
    CATEGORY_QUERY,
)

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


# ── 意图路由（G6，设计 §8；#1742）──────────────────────────────────────
# 对话精灵用：A 前置分类（safety.intent_guard.classify）的类别决定本条输入走
# 「查询工具链」还是「直接拦截 / 标准话术」。
# 为什么单独一张表：check_input 只按 B 规则**窄**命中拦截，而 classify 的预测 / 建议句式
# （_PREDICTION_CUE / _ADVICE_CUE）比 B 规则宽——宽命中的越界输入此前会照常进模型、占轮次，
# 违反护栏层验收「预测 / 建议类不进入查询链路」。路由表把这条口径收敛到一处，
# 与上方 scenario 注册同为注册表模式（G6 验收之一：二者不冲突）。

ROUTE_TOOL_CHAIN = 'tool_chain'  # 进模型 → 决策 → 查询工具链
ROUTE_STANDARD_REPLY = 'standard_reply'  # 不进模型，直接回标准话术（零 token、不占轮次）
_VALID_ROUTES = frozenset({ROUTE_TOOL_CHAIN, ROUTE_STANDARD_REPLY})

# 五类意图的路由。未知类别（classify 返回值之外）回退工具链：
# 宁可把裁决交给模型，也不能把没设计过话术的输入误拦成空白回复。
_INTENT_ROUTES: dict[str, str] = {
    CATEGORY_QUERY: ROUTE_TOOL_CHAIN,  # 数据查询：正常进模型
    CATEGORY_KNOWLEDGE: ROUTE_TOOL_CHAIN,  # 通用知识：交模型裁决（不含用户数据断言，风险低）
    CATEGORY_EMOTION: ROUTE_TOOL_CHAIN,  # D 情绪复合：不拦，risk_notice 由接线处加前缀
    CATEGORY_PREDICTION: ROUTE_STANDARD_REPLY,  # 预测：拦
    CATEGORY_ADVICE: ROUTE_STANDARD_REPLY,  # 建议：拦
}


def register_intent_route(category: str, route: str) -> None:
    """注册 / 覆盖一条意图路由（类别 → 路由值）。"""
    if not category or not isinstance(route, str) or route not in _VALID_ROUTES:
        raise ValueError(f'非法意图路由注册: category={category} route={route}')
    _INTENT_ROUTES[category] = route


def route_intent(category: str) -> str:
    """A 前置分类 → 路由值；未知类别回退 `ROUTE_TOOL_CHAIN`（默认进链，宁可交给模型也不误拦）。"""
    return _INTENT_ROUTES.get(category, ROUTE_TOOL_CHAIN)


# ── 场景注册（对称 importer.registry：新场景在此加一行）──
from app.services.ai_recognizer.recognizers.holding_recognizer import HoldingRecognizer  # noqa: E402
from app.services.ai_recognizer.recognizers.txn_recognizer import TxnRecognizer  # noqa: E402
from app.services.ai_recognizer.recognizers.watchlist_recognizer import WatchlistRecognizer  # noqa: E402

register_recognizer(WatchlistRecognizer.key, WatchlistRecognizer())
register_recognizer(TxnRecognizer.key, TxnRecognizer())
register_recognizer(HoldingRecognizer.key, HoldingRecognizer())
