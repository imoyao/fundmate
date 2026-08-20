# -*- coding: utf-8 -*-
"""账本精灵对话循环（AgentLoop）：多轮追问收敛 + 工具调用。

设计（2026-08-18 与用户确认）：
- 不引 LangGraph；用轻量循环做状态路由（ask_clarification / execute_tool）；
- 多轮收敛上限复用 guards.repeat_tracker（G4），超限抛 AGENT_TURN_LIMIT_EXCEEDED；
- 强制结构化输出兜底：call_llm 传 response_format json_object；但 doubao-mini 仍可能漂移，
  故 parse_agent_action 复用 extract_json_array 的容错思路解析单对象，解析失败一律当澄清；
- 所有数值只在 ToolExecutor 执行后注入 prompt，追问阶段模型只聊逻辑，属防幻觉安全区；
- 「3~10 轮追问」由**前端驱动**（前端持有 session_state，每轮回传），repeat_tracker 跨请求计总轮次；
  本函数内只做「单次决策 + 工具失败最多 1 次重试」（共 2 次模型调用上限）。

后期接 DeepSeek：只需改 ARK_MODEL / base_url（OpenAI 兼容协议不变），架构零改动。
"""

import json
import re
from typing import Optional

from loguru import logger

from app.core.exceptions import ErrorCode, SBException
from app.services.ai_recognizer import guards, llm
from app.services.ai_recognizer.session_manager import (
    SessionState,
    merge_user_input,
    validate_session_state,
)
from app.services.ai_recognizer.tools.executor import ToolExecutor

AGENT_SYSTEM_PROMPT = """你是多多贝账本精灵（投顾助手）。
你的输出**必须**是单个 JSON 对象，不要包含任何解释文字或 markdown 围栏。
字段：
- action: "ask_clarification"（信息不足需追问）或 "execute_tool"（信息齐全可执行）
- missing_params: 信息不足时，缺失参数名的数组
- content: 向用户说的话（追问时即问题，执行前可简述即将做什么）
- tool_name: action=execute_tool 时，要调用的工具名（必须是已知工具）
- tool_params: action=execute_tool 时，工具参数对象
"""


def parse_agent_action(response_str: str) -> dict:
    """容错解析模型输出的 agent action（复用 extract_json_array 的兜底思路，针对单对象）。

    任何解析异常/非法 action 都降级为 ask_clarification，绝不误执行工具，保证不崩。
    """
    if not response_str or not isinstance(response_str, str):
        return {'action': 'ask_clarification', 'error': 'empty_response'}
    text = response_str
    # 去 ```json ... ``` 围栏
    fence = re.search(r'```(?:json)?\s*(.*?)```', text, re.S)
    if fence:
        text = fence.group(1)
    # 截取第一个 { 到最后一个 } 的片段
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return {'action': 'ask_clarification', 'error': 'no_json_object'}
    text = text[start : end + 1]
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {'action': 'ask_clarification', 'error': 'json_decode_error'}
    if not isinstance(obj, dict):
        return {'action': 'ask_clarification', 'error': 'not_object'}
    action = obj.get('action')
    if action not in ('ask_clarification', 'execute_tool'):
        # 模型没给合法 action：视为需澄清，避免误执行工具
        obj['action'] = 'ask_clarification'
        obj['error'] = 'invalid_action'
    return obj


def run_agent(
    user_input: str,
    session_state: Optional[dict],
    user_id: int,
    session_id: str,
    goal: str = '分析账户收益',
) -> dict:
    """单次对话决策：返回 clarify / result / error。

    多轮追问由前端驱动（前端持有 session_state 并每轮回传）；本函数内对工具失败做最多 1 次重试。
    """
    # G3：前端回传状态只做白名单校验，不执行任何 DB
    state: SessionState = validate_session_state(session_state or {})
    state = merge_user_input(state, user_input)

    # G4：跨请求收敛上限（总轮次由 repeat_tracker 统计）
    if guards.agent_turns_exceeded(user_id, session_id):
        raise SBException(
            ErrorCode.AGENT_TURN_LIMIT_EXCEEDED.code,
            '已超出分析轮次，请使用图表查看详细数据',
            ErrorCode.AGENT_TURN_LIMIT_EXCEEDED.http_status,
        )
    guards.record_agent_turn(user_id, session_id)

    def build_prompt() -> str:
        return (
            f'当前分析目标：{state.get("goal") or goal}\n'
            f'已收集参数：{json.dumps(state.get("collected_params", {}), ensure_ascii=False)}\n'
            f'对话历史摘要：{json.dumps(state.get("history", []), ensure_ascii=False)}\n'
            '请判断：信息是否齐全？齐全则 action=execute_tool，否则 action=ask_clarification 并列出 missing_params。'
        )

    prompt = build_prompt()
    result: dict = {}
    # 工具执行失败的最多重试：最多 2 次模型调用（带错误反馈 1 次）
    for attempt in range(2):
        raw = llm.call_llm(
            content=[{'type': 'text', 'text': prompt}],
            system_prompt=AGENT_SYSTEM_PROMPT,
            response_format={'type': 'json_object'},
            temperature=0.1,
        )
        action = parse_agent_action(raw)

        if action['action'] == 'ask_clarification':
            missing = action.get('missing_params') or []
            state['missing_params'] = missing
            return {
                'type': 'clarify',
                'content': action.get('content', ''),
                'session_state': state,
                'missing_params': missing,
            }

        # execute_tool：校验 + 执行工具
        tool_name = action.get('tool_name')
        tool_params = action.get('tool_params') or {}
        merged_params = {**state.get('collected_params', {}), **tool_params}
        result = ToolExecutor.run(tool_name, merged_params)
        if result['status'] == 'success':
            break
        # 工具失败：拼错误反馈，进入下一次循环（最多 1 次重试）；不再额外计轮次
        logger.warning('工具执行失败（第 {} 次），name={}：{}', attempt + 1, tool_name, result.get('msg'))
        if attempt < 1:
            prompt = (
                f'{build_prompt()}\n\n上一次工具调用失败：{result.get("msg")}。'
                '请修正工具选择或参数后重试，或改为 ask_clarification 向用户追问缺失信息。'
            )
    else:
        # 两次都失败（for 循环未被 break）
        logger.warning('工具执行最终失败（已重试 2 次），name={}', tool_name)
        return {'type': 'error', 'content': f'分析失败：{result.get("msg")}', 'session_state': state}

    # 叙事：再调一次纯逻辑模型，仅把指标喂入（防幻觉安全区：模型不接触账本、只转述）
    # 防御：真实工具可能返回 Decimal/datetime/自定义类等非 JSON 可序列化对象，
    # 序列化失败时回退为字符串表示，避免 AgentLoop 崩溃（与执行层「不崩」铁律一致）。
    try:
        data_json = json.dumps(result['data'], ensure_ascii=False)
    except TypeError:
        logger.warning('工具返回数据不可 JSON 序列化，叙事回退为字符串表示，name={}', tool_name)
        data_json = str(result['data'])
    narrative_prompt = (
        f'基于以下分析数据（来自工具 {tool_name}）：{data_json}\n' '用简单易懂的中文总结给用户，不要编造数据。'
    )
    narrative = llm.call_llm(
        content=[{'type': 'text', 'text': narrative_prompt}],
        system_prompt='你是多多贝账本精灵，负责把指标转成通俗总结，不编造数据。',
    )
    return {'type': 'result', 'content': narrative, 'data': result['data'], 'session_state': state}
