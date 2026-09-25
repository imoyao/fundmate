# -*- coding: utf-8 -*-
"""position_service 的 family 归属解析（#1305 #22）。

WHY 要钉住这个：`data.get('family_id', 1)` 在多家庭场景下不是「默认值不好看」，
而是**数据越权** —— 缺字段时流水/持仓被静默挂到 family 1，别人家里凭空长出一笔资产，
而原主人按 family 过滤后反而看不到自己的数据。

修法：显式入参 → 请求上下文 `g.family_id` → 单用户遗留口径 1（**仅无上下文时**，
因为离线脚本直接调本服务，那时 `g` 不可用）。
"""

from pathlib import Path

from flask import g

_SERVICE = Path(__file__).resolve().parents[2] / 'app' / 'services' / 'position_service.py'


def test_explicit_family_id_wins(app) -> None:
    """显式入参优先于上下文（视图层已注入，见 positions/views.py）。"""
    from app.services.position_service import _resolve_family_id

    with app.test_request_context():
        g.family_id = 9
        assert _resolve_family_id({'family_id': 3}) == 3


def test_missing_family_id_falls_back_to_request_context(app) -> None:
    """核心回归（#22）：缺字段时取请求上下文，而不是硬编码 1。

    改回 `data.get('family_id', 1)` 这条会立刻翻红。
    """
    from app.services.position_service import _resolve_family_id

    with app.test_request_context():
        g.family_id = 9
        assert _resolve_family_id({}) == 9
        assert _resolve_family_id({'family_id': None}) == 9


def test_legacy_default_without_request_context() -> None:
    """离线脚本（backend/scripts/*.py 直接调本服务）无请求上下文 → 退回遗留口径 1。

    关键是**不能抛异常**：`getattr(g, 'family_id', ...)` 在上下文外会 RuntimeError，
    所以实现里必须先 `has_app_context()` 判一下。
    """
    from app.services.position_service import _resolve_family_id

    assert _resolve_family_id({}) == 1


def test_no_hardcoded_family_default_left() -> None:
    """源码级回归守卫：position_service 里不许再出现「取不到就填 1」的写法。

    （这正是 review 意见 #22 的原始形态，防止后续改动悄悄带回。）
    """
    src = _SERVICE.read_text(encoding='utf-8')
    assert "get('family_id', 1)" not in src, 'position_service 里又出现了 family_id 硬编码默认值'
