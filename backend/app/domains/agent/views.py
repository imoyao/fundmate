# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/9/26
# File : views.py
"""账本精灵对话端点（#1121 S1；S2 起服务端权威会话）.

路由：POST /api/agent/chat/（尾斜杠；不在 check_api_conventions 例外清单内）
三态响应：data = {type: clarify|result|error, content, data?, missing_params?, session_id}

S2 契约演化（#1121 步骤卡 #4 文档化，同 PR 已同步前端 / 测试）：
- 请求 {message, session_id?, goal?}：不再回传 session_state（状态服务端持有），
  session_id 缺省即新建（服务端生成 uuid），提供但不存在 / 越权 → 404；
- 响应三态统一携带 session_id，前端下轮回带即可续接（修 P2 丢历史 / P4 可篡改）。

鉴权：非白名单接口，需登录（core/auth.py 注入 g.current_user / g.family_id）。
越权防护（P1）：工具执行所需的 family_id 一律取服务端上下文 get_family_id()，
模型 / 客户端回传的参数只是候选值，由 ToolExecutor 强制覆盖（tools.apply_server_context）。
"""

from apiflask import APIBlueprint
from flask import g, jsonify

from app.core import database  # 晚绑定：属性在调用时解析（#1608）
from app.core.auth import get_family_id
from app.core.exceptions import SBException
from app.core.validation import parse_body
from app.domains.agent.schemas import AgentChatRequest
from app.services.ai_recognizer import guards, session_store
from app.services.ai_recognizer.agent_loop import run_agent

agent_bp = APIBlueprint('agent', __name__, url_prefix='/api/agent')


def _current_user_id() -> int:
    user = getattr(g, 'current_user', None)
    if user is None:
        raise SBException(code=1005, message='未授权，请先登录', status_code=401)
    return user.id


@agent_bp.post('/chat/', strict_slashes=False)
def agent_chat():
    """单轮对话：返回 clarify / result / error 三态（均含 session_id）。

    闸门分工：第 1~3 道（限流 / 熔断 / token 预算）在 assert_available；
    第 4 道（轮次上限）在 run_agent 内按 agent_session.turn_count 计数（S2 落库），
    视图不得再计数，否则重复。会话行经请求级会话加载，提交由 teardown 统一执行（§2.13）。
    """
    user_id = _current_user_id()
    payload = parse_body(AgentChatRequest)
    guards.assert_available(user_id)
    with database.user_session() as db:
        session_row = session_store.load_or_create(
            db,
            session_id=payload.session_id,
            user_id=user_id,
            goal=payload.goal,
        )
        out = run_agent(
            user_input=payload.message,
            session=session_row,
            # P1：服务端权威上下文，工具参数中的 family_id 只认这里，候选值一律被覆盖
            server_ctx={'family_id': get_family_id()},
        )
    return jsonify({'data': out, 'message': 'ok'})
