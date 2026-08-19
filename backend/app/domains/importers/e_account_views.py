# -*- coding: utf-8 -*-
"""E账户对账与归因 API（设计文档 e-account-reconciliation-design-2026-08-16）。

三个端点：
- POST /api/e-account/reconcile/        对账并落库（接收 parse 端点输出的 rows）
- POST /api/e-account/attribution/      处理冲突（cover/ignore，幂等）
- GET  /api/e-account/reconciliation/   对账中心（影子记录 + 状态推导）

鉴权：与 importers 现有端点一致（需登录，不在免登录白名单）。
错误统一 {data, message, error_code} 信封（abort/SBException 由全局异常处理器收敛）。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from loguru import logger

from app.core.auth import get_family_id
from app.core.database import get_db
from app.services.importer.orchestrator import ImportOrchestrator

e_account_bp = APIBlueprint('e_account', __name__, url_prefix='/api/e-account')


@e_account_bp.post('/reconcile/')
def reconcile():
    """对账并落库：接收 parse 端点输出的 rows，逐条处理（防复活 → 影子记录 → 渠道匹配 → 三分支）。"""
    payload = request.get_json() or {}
    rows = payload.get('rows') or []
    if not rows:
        abort(400, '请提供至少一条持仓记录')

    try:
        with get_db() as db:
            orch = ImportOrchestrator(db, get_family_id())
            result = orch.reconcile_holdings(rows)
        return jsonify({'data': result, 'message': '对账完成'})
    except Exception as e:
        logger.exception(f'E账户对账失败: {e}')
        abort(500, '对账失败，请稍后重试')


@e_account_bp.post('/attribution/')
def attribution():
    """处理对账冲突（cover/ignore），幂等：重复归因/忽略返回当前状态（HTTP 200）。"""
    payload = request.get_json() or {}
    decisions = payload.get('decisions') or []
    if not decisions:
        abort(400, '请提供至少一条处理决策')

    try:
        with get_db() as db:
            orch = ImportOrchestrator(db, get_family_id())
            result = orch.attribute_holdings(decisions)
        return jsonify({'data': result, 'message': '处理完成'})
    except Exception as e:
        logger.exception(f'E账户归因处理失败: {e}')
        abort(500, '处理失败，请稍后重试')


@e_account_bp.get('/reconciliation/')
def reconciliation():
    """对账中心：影子记录 + 状态推导 + 系统侧份额汇总（§5.4）。"""
    try:
        with get_db() as db:
            orch = ImportOrchestrator(db, get_family_id())
            result = orch.get_reconciliation()
        return jsonify({'data': result, 'message': 'ok'})
    except Exception as e:
        logger.exception(f'E账户对账中心查询失败: {e}')
        abort(500, '查询失败，请稍后重试')
