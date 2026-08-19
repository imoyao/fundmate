# -*- coding: utf-8 -*-
"""账本精灵多轮会话状态管理（前端持有模式，后端无状态）。

设计（2026-08-18 与用户确认）：
- 会话状态由**前端持有**（选项 c）：后端不存储、不持久化，每轮由前端回传 session_state；
- 后端在接收时仅做**字段格式校验**（G3 防篡改）：只认白名单字段，不执行任何 DB/SQL；
- 收敛轮次上限由 guards.repeat_tracker（G4）统一管控，不在本模块另起一套。

后期如需 (a) Supabase / (b) SQLite 持久化，只替换存储层，本模块的白名单校验不变。
"""

from typing import List, TypedDict

from app.core.exceptions import ErrorCode, SBException


# 会话状态结构：目标 / 缺失参数 / 已收集参数 / 对话历史摘要
class SessionState(TypedDict, total=False):
    goal: str
    missing_params: List[str]
    collected_params: dict
    history: List[dict]


# G3 白名单：前端回传的 session_state 只能含这些字段，否则视为篡改拒绝
ALLOWED_KEYS = {'goal', 'missing_params', 'collected_params', 'history'}


def init_session(goal: str) -> SessionState:
    """前端开启新会话时初始化状态（也可由前端自行构造）。"""
    return SessionState(goal=goal, missing_params=[], collected_params={}, history=[])


def validate_session_state(state) -> SessionState:
    """白名单校验前端回传的 session_state（G3 防篡改）。

    只认 ALLOWED_KEYS，字段类型不符即拒绝；不碰 DB、不执行任何危险逻辑。
    """
    if not isinstance(state, dict):
        raise SBException(ErrorCode.INVALID_PARAMS.code, 'session_state 必须为对象', 400)
    cleaned: SessionState = SessionState()
    for k, v in state.items():
        if k not in ALLOWED_KEYS:
            # 未知字段：拒绝，防止前端被篡改后注入非法状态
            raise SBException(ErrorCode.INVALID_PARAMS.code, f'session_state 含未授权字段: {k}', 400)
        if k == 'goal' and not isinstance(v, str):
            raise SBException(ErrorCode.INVALID_PARAMS.code, 'goal 必须为字符串', 400)
        if k == 'missing_params' and not isinstance(v, list):
            raise SBException(ErrorCode.INVALID_PARAMS.code, 'missing_params 必须为数组', 400)
        if k == 'collected_params' and not isinstance(v, dict):
            raise SBException(ErrorCode.INVALID_PARAMS.code, 'collected_params 必须为对象', 400)
        if k == 'history' and not isinstance(v, list):
            raise SBException(ErrorCode.INVALID_PARAMS.code, 'history 必须为数组', 400)
        cleaned[k] = v  # type: ignore[literal-required]
    return cleaned


def merge_user_input(state: SessionState, user_input: str) -> SessionState:
    """把本轮用户输入追加进 history（轻量摘要，不存全量原文）。"""
    history = list(state.get('history', []))
    history.append({'role': 'user', 'content': user_input})
    updated = SessionState(**state)
    updated['history'] = history
    return updated
