# -*- coding: utf-8 -*-
# File : views.py
# app/domains/insight/views.py
"""静态诊断提示接口（#1017）。

视图职责（AGENTS.md 视图层厚度守卫）：取值 → 调 service → 组响应。
规则与取数全在 `services/insight/`，本文件不做 ORM 查询、不做业务判断。

只读、不落库：提示是同一时点可由账户结构重算出来的派生结果，落库只会过期。
"""

from apiflask import APIBlueprint
from flask import jsonify

from app.core.auth import get_family_id
from app.core.database import get_db
from app.services.insight import build_tips

insight_bp = APIBlueprint('insight', __name__, url_prefix='/api/insight')


@insight_bp.get('/tips/')
def get_tips():
    """规则驱动静态诊断：返回当前账户触发的风险提示（家庭级）。

    没有 `ledger_id` / `portfolio_id` 参数是刻意的：规则里的「集中度」「分散度」都以
    **家庭投资持仓**为分母；按账户切分会让同一只标的在两个账户各算一次「不集中」，
    得出与事实相反的小贴士。
    """
    family_id = get_family_id()
    with get_db() as db:
        data = build_tips(db, family_id)
    return jsonify({'data': data, 'message': 'ok'})
