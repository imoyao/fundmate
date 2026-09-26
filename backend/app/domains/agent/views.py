# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/9/26
# File : views.py
"""账本精灵对话端点（#1121 S1）.

路由：POST /api/agent/chat/（尾斜杠；不在 check_api_conventions 例外清单内）
三态响应：data = {type: clarify|result|error, content, data?, session_state, ...}

鉴权：非白名单接口，需登录（core/auth.py 注入 g.current_user / g.family_id）。
越权防护（P1）：工具执行所需的 family_id 一律取服务端上下文 get_family_id()，
前端回传的 session_state.collected_params 只是候选值，由 run_agent 合并进
ToolExecutor 时被服务端权威值强制覆盖（见 tools.apply_server_context）。
"""

from apiflask import APIBlueprint
from flask import g, jsonify

from app.core.auth import get_family_id
from app.core.exceptions import SBException
from app.core.validation import parse_body
from app.domains.agent.schemas import AgentChatRequest
from app.services.ai_recognizer import guards
from app.services.ai_recognizer.agent_loop import run_agent

agent_bp = APIBlueprint('agent', __name__, url_prefix='/api/agent')


def _current_user_id() -> int:
    user = getattr(g, 'current_user', None)
    if user is None:
        raise SBException(code=1005, message='未授权，请先登录', status_code=401)
    return user.id


@agent_bp.post('/chat/', strict_slashes=False)
def agent_chat():
    """单轮对话：返回 clarify / result / error 三态。

    闸门分工：第 1~3 道（限流 / 熔断 / token 预算）在 assert_available；
    第 4 道（轮次上限）在 run_agent 内按 user_id+session_id 计数，
    视图不得再调 record_agent_turn，否则重复计数。
    """
    user_id = _current_user_id()
    payload = parse_body(AgentChatRequest)
    guards.assert_available(user_id)
    out = run_agent(
        user_input=payload.message,
        session_state=payload.session_state,
        user_id=user_id,
        session_id=payload.session_id,
        goal=payload.goal or '分析账户收益',
        # P1：服务端权威上下文，工具参数中的 family_id 只认这里，前端值一律被覆盖
        server_ctx={'family_id': get_family_id()},
    )
    return jsonify({'data': out, 'message': 'ok'})
