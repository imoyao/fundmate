# -*- coding: utf-8 -*-
"""家庭财务规划 API（财务晴雨表 v2）。

端点（尾斜杠，见 docs/spec/conventions.md §2.2）：
- GET /api/financial-plan/  读取本家庭配置（未配置返回两个 null）
- PUT /api/financial-plan/  设置 / 更新（只改显式传入的字段）

视图只做参数校验与编排；金额单位换算、null 语义在 services/financial_plan_service.py。
"""

from apiflask import APIBlueprint
from flask import jsonify

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.financial_plan.schemas import FinancialPlanUpdate
from app.services.financial_plan_service import read_plan, upsert_plan

financial_plan_bp = APIBlueprint('financial_plan', __name__, url_prefix='/api/financial-plan')


@financial_plan_bp.get('/')
def get_financial_plan():
    """读取家庭财务规划配置；未配置时两个字段都是 null（不是 0）。"""
    with get_db() as db:
        return jsonify({'data': read_plan(db, get_family_id()), 'message': 'ok'})


@financial_plan_bp.put('/')
def put_financial_plan():
    """设置 / 更新家庭财务规划。只改 payload 显式传入的字段。"""
    payload: FinancialPlanUpdate = parse_body(FinancialPlanUpdate)
    with get_db() as db:
        data = upsert_plan(db, get_family_id(), payload)
        db.commit()
        return jsonify({'data': data, 'message': 'ok'})
