# -*- coding: utf-8 -*-
"""策略引擎接口（#2224 框架 / #2225 诊断 + 行为反推）。

除 `POST /reminders/refresh/` 外**只读**，不写库——该端点写的是 #2236 的站内通知表，
不在此处另建存储。

视图层职责边界（AGENTS.md 视图层厚度守卫）
    视图只做：入参解析 → 归属校验 → 调服务 → 组响应。
    业务编排全在 `services/strategy_engine/`，本文件不写 ORM 查询、不做事务。

合规
    接口只返回「规则触发」的客观陈述（趋势成立 / 走弱 / 结束），
    不含任何买入卖出建议。前端与文档站措辞须与此保持一致。
"""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.services.strategy_engine import allocation as allocation_service
from app.services.strategy_engine.data_provider import DataProvider
from app.services.strategy_engine.diagnosis import (
    behavior_profiles,
    diagnose_holdings,
    diagnose_symbol,
    list_strategies,
)

strategy_engine_bp = APIBlueprint('strategy_engine', __name__, url_prefix='/api/strategy/engine')


@strategy_engine_bp.get('/strategies/')
def list_engine_strategies():
    """当前数据条件下可运行的策略及其元信息（供策略卡片使用）。"""
    return jsonify({'data': list_strategies(), 'message': 'ok'})


@strategy_engine_bp.get('/diagnosis/')
def get_holdings_diagnosis():
    """持仓诊断（只读，实时计算，不落库）。

    query: strategy=xxx 指定策略（可重复）；symbol=xxx 只看单个标的。
    """
    family_id = get_family_id()
    codes = request.args.getlist('strategy') or None
    symbol = request.args.get('symbol')
    with get_db() as db:
        provider = DataProvider(db)
        if symbol:
            data = diagnose_symbol(provider, symbol=symbol, strategy_codes=codes)
        else:
            data = diagnose_holdings(provider, family_id, strategy_codes=codes)
    return jsonify({'data': data, 'message': 'ok'})


@strategy_engine_bp.get('/behavior/')
def get_behavior_profile():
    """行为反推：用真实流水 + 净值算用户**实际**的交易风格与其代价（#2225）。

    只陈述用户自己的历史事实，不对未来给出倾向性意见。
    """
    family_id = get_family_id()
    symbols = request.args.getlist('symbol') or None
    with get_db() as db:
        data = behavior_profiles(DataProvider(db), family_id, symbols=symbols)
    return jsonify({'data': data, 'message': 'ok'})


@strategy_engine_bp.post('/reminders/refresh/')
def refresh_reminders():
    """跑一次偏离扫描，把越线的配比写成站内通知（#2237）。

    query:
        threshold: 偏离阈值（百分点，默认 5）。

    为什么是 POST 而不是「查列表时顺带生成」：写操作不该藏在 GET 里——
    GET 会被预取/缓存/重试，把副作用放在 GET 上迟早会写出意料之外的消息。
    幂等由 `dedup_key`（含日期）保证，重复调用不会刷屏。
    """
    raw = request.args.get('threshold', type=float)
    threshold = allocation_service.DEFAULT_THRESHOLD_PCT if raw is None else min(max(raw, 0.0), 100.0)
    with get_db() as db:
        created = allocation_service.refresh_reminders(db, get_family_id(), threshold_pct=threshold)
        return jsonify({'data': {'created': created}, 'message': 'ok'})
