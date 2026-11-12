# -*- coding: utf-8 -*-
"""P&E 最小编排：模型给结构，代码按序执行（owner 裁定 D101，#3049/#3050 后续）。

分工（D19 在计划型执行下的边界细化，见 docs/spec/decisions.md D101）：
- 模型只输出 plan **结构**：工具名顺序 + 参数引用占位；决策轮不接触任何工具数值；
- 代码按序调 ToolExecutor，把上一步结果按占位路径注入下一步参数，真实数值不经模型；
- 一次决策执行完整个 plan，不做「观察 → 再决策」循环（不引 ReAct）；
- 叙事轮仍只见最终聚合数据，与既有防幻觉安全区一致。

零新增外部依赖：不接 MCP、不做向量检索、不碰凭证；工具名一律过 TOOLS_METADATA 白名单。
单工具路径（action 不含 plan）逐键等价于改造前的 ToolExecutor.run 调用，既有 47 条
评估用例与全部 run_agent 单测行为不变。
"""

from typing import Any, Callable, Optional

from loguru import logger

from app.services.ai_recognizer.tools import TOOLS_METADATA, ToolExecutor

MAX_STEPS = 4
_REF_KEY = '$from_step'
_TOOL_NAMES = frozenset(m['name'] for m in TOOLS_METADATA)

PLAN_INSTRUCTION = (
    '\n多子问编排（plan）：一次提问含 2 个及以上独立子问、或后一问依赖前一问结果时，'
    '仍用 action=execute_tool，但改输出 plan 数组，不要输出 tool_name。\n'
    '每步形如 {"tool":"清单里的 name","tool_params":{...},"params_from":<更早步骤序号,可选>}；'
    '按依赖顺序排列，最多 ' + str(MAX_STEPS) + ' 步，每步 tool 必须取自上面的工具清单。\n'
    '后一步需要前一步的结果时，把该参数值写成引用占位对象 '
    '{"$from_step":0,"path":"rows.0.symbol"}（path 用点号分隔，数字表示数组下标），'
    'params_from 写被引用的步骤序号。占位**必须是一个 JSON 对象**：不要写成字符串、'
    '不要用 {{ }} 或 ${} 包裹、也不要把键名与序号拼成 $from_step:0,path:x 这类文本。'
    '完整示例（两步，第 2 步取第 1 步结果的字段）：'
    '{"action":"execute_tool","plan":['
    '{"tool":"list_position_pnl","tool_params":{}},'
    '{"tool":"get_fund_nav","tool_params":{"symbol":{"$from_step":0,"path":"rows.0.symbol"}},'
    '"params_from":0}]}。'
    '不要凭空猜测任何数值，也不要把中间数值写进参数。\n'
    '服务端按序执行、把真实数值注入下一步参数，你不会看到中间结果。\n'
    '覆盖要求：先把用户提问拆成独立子问；每个能由工具回答的子问在 plan 里各占一步，'
    '不要用一步数据敷衍多个子问，也不要丢弃任何一个子问；同一工具可重复出现在不同步骤'
    '（用不同参数或引用不同上一步结果）。方向性建议类子问只用提供客观参考的工具回答，'
    '不给买卖结论。最终按全部步骤的数据逐个回答用户的每个子问。\n'
    '单一子问仍用 tool_name + tool_params，不要输出 plan。'
)


def primary_tool(action: dict) -> Optional[str]:
    """取主工具名：单工具取 tool_name，多步取首步 tool（供日志 / 错误 / trace 兜底）。"""
    steps = action.get('plan')
    if isinstance(steps, list) and steps and isinstance(steps[0], dict):
        name = steps[0].get('tool')
        return name if isinstance(name, str) else None
    name = action.get('tool_name')
    return name if isinstance(name, str) else None


def _valid_steps(plan: Any):
    """校验模型给的 plan；返回 (steps, error)。steps 为 None 表示退回单工具路径。"""
    if plan is None or plan == []:
        return None, None
    if not isinstance(plan, list):
        return None, 'plan 必须是数组'
    if len(plan) > MAX_STEPS:
        return None, f'plan 最多 {MAX_STEPS} 步'
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            return None, f'第 {i + 1} 步必须是映射'
        tool = step.get('tool')
        if tool not in _TOOL_NAMES:
            return None, f'第 {i + 1} 步工具不在白名单：{tool!r}'
        raw_params = step.get('tool_params')
        # 不用 `or {}`：空 list / 空串 / 0 这类 falsy 非映射会被它静默吞成合法值
        if raw_params is not None and not isinstance(raw_params, dict):
            return None, f'第 {i + 1} 步 tool_params 必须是映射'
        ref = step.get('params_from')
        if ref is not None and (isinstance(ref, bool) or not isinstance(ref, int) or ref < 0 or ref >= i):
            return None, f'第 {i + 1} 步 params_from 必须引用更早步骤'
    return plan, None


def _dig(obj: Any, path: str) -> Any:
    """按 a.b.0.c 取嵌套值；路径不存在即抛错，绝不静默补 None（防把缺失当 0）。"""
    cur = obj
    if not path:
        return cur
    for part in str(path).split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, (list, tuple)) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise ValueError(f'引用路径不可解析：{path}')
    return cur


_DANGLING_HINT = (
    '引用占位必须是一个 JSON 对象 {"$from_step":0,"path":"rows.0.symbol"}，'
    '不能写成字符串，也不能用 {{ }} / ${} 包裹或拼成 $from_step:0,path:x'
)


def _reject_dangling_ref(value: str) -> str:
    """字符串里残留 `$from_step` ⇒ 模型把占位写成了文本模板，提前给出可照做的错误。

    WHY：这类占位若原样透传，报错出在工具参数校验里（「symbol 类型不对」），
    模型看不出真正原因是占位格式，2026-11-11 真实数据 eval 就因此连错两轮、
    整轮 0 步成功。在这里拦下，错误信息直接说明正确写法，主循环的
    「带错误反馈重试一次」才有机会救回来。
    """
    if _REF_KEY in value:
        raise ValueError(f'参数值 {value!r} 是未展开的引用占位文本：{_DANGLING_HINT}')
    return value


def _resolve(value: Any, outputs: list) -> Any:
    """把参数里的引用占位换成上一步真实数值；这是纯代码侧注入，模型看不到。"""
    if isinstance(value, dict):
        if _REF_KEY not in value:
            return {k: _resolve(v, outputs) for k, v in value.items()}
        idx = value[_REF_KEY]
        if isinstance(idx, bool) or not isinstance(idx, int) or idx < 0 or idx >= len(outputs):
            raise ValueError(f'参数引用步骤越界：{idx!r}')
        return _dig(outputs[idx], value.get('path', ''))
    if isinstance(value, list):
        return [_resolve(v, outputs) for v in value]
    if isinstance(value, str):
        return _reject_dangling_ref(value)
    return value


def execute(
    action: dict,
    merged_params: dict,
    server_ctx: Optional[dict] = None,
    runner: Optional[Callable] = None,
) -> dict:
    """执行一次决策：无 plan 走原单工具路径；有 plan 按序执行并注入参数。

    runner 由主循环显式传入（默认 ToolExecutor.run），既保留既有
    `monkeypatch(agent_loop.ToolExecutor, 'run', ...)` 的可观察面，也让本模块
    的单测无需 patch 全局注册表。
    """
    run = runner or ToolExecutor.run
    plan, err = _valid_steps(action.get('plan'))
    if err:
        return {'status': 'error', 'msg': f'plan 非法：{err}'}
    if plan is None:
        return run(primary_tool(action), merged_params, server_ctx=server_ctx)

    outputs: list = []
    trace_steps: list = []
    data_steps: list = []
    for i, step in enumerate(plan):
        tool = step['tool']
        raw_params = step.get('tool_params') or {}
        # 首步沿用 collected_params（既有工作内存语义）；后续步只认模型给的结构
        if i == 0:
            raw_params = {**merged_params, **raw_params}
        try:
            params = _resolve(raw_params, outputs)
        except ValueError as exc:
            return {'status': 'error', 'msg': f'第 {i + 1} 步参数注入失败：{exc}'}
        out = run(tool, params, server_ctx=server_ctx)
        if out.get('status') != 'success':
            return {'status': 'error', 'msg': f'第 {i + 1} 步 {tool} 失败：{out.get("msg")}'}
        outputs.append(out.get('data'))
        data_steps.append({'tool': tool, 'data': out.get('data')})
        # trace 只记模型给的结构占位，不记注入后的真实数值
        trace_steps.append({'tool': tool, 'params': raw_params})
    logger.info('[agent.plan] ok steps={} tools={}', len(plan), [s['tool'] for s in data_steps])
    return {
        'status': 'success',
        'data': {'steps': data_steps},
        '_plan': {'tools': [s['tool'] for s in data_steps], 'trace_steps': trace_steps},
    }


def _description_of(name: Optional[str]) -> str:
    return next((str(m.get('description') or '') for m in TOOLS_METADATA if m.get('name') == name), '')


def describe(result: dict, tool_name: Optional[str]) -> str:
    """叙事轮的字段语义说明：单工具与改造前按名取 description 的结果逐字等价。"""
    tools = (result.get('_plan') or {}).get('tools')
    if not tools:
        return _description_of(tool_name)
    return '；'.join(f'{t}：{_description_of(t)}' for t in tools)


def source_line(result: dict, tool_name: Optional[str], data_json: str) -> str:
    """叙事 prompt 的数据来源行：单工具与原 f-string 逐字等价。"""
    tools = (result.get('_plan') or {}).get('tools')
    if not tools:
        return f'基于以下分析数据（来自工具 {tool_name}）：{data_json}\n'
    return (
        f'基于以下按步骤分组的分析数据（来自 {len(tools)} 个工具，'
        f'steps 数组按执行顺序给出每步的 tool 与 data）：{data_json}\n'
        '必须逐个覆盖用户提问中能被对应步骤数据回答的每个子问，'
        '不要遗漏任何一步，也不要把某一步的数据说成另一步的。\n'
    )


def write_traces(
    writer: Callable,
    session: Any,
    result: dict,
    *,
    tool_name: Optional[str],
    tool_params: dict,
    latency_ms: Optional[int],
    tokens: int,
    guard_hits: list,
) -> None:
    """落 trace：单工具一条（与原调用逐参等价）；多步每步一条成功 execute_tool。

    统计口径只记在最后一条，避免多步时把 token / 耗时重复计数。
    """
    steps = (result.get('_plan') or {}).get('trace_steps')
    if not steps:
        writer(
            session,
            intent='execute_tool',
            status='result',
            tool_name=tool_name,
            tool_params=tool_params,
            latency_ms=latency_ms,
            tokens=tokens,
            guard_hits=guard_hits,
        )
        return
    for i, step in enumerate(steps):
        last = i == len(steps) - 1
        writer(
            session,
            intent='execute_tool',
            status='result',
            tool_name=step['tool'],
            tool_params=step['params'],
            latency_ms=latency_ms if last else None,
            tokens=tokens if last else 0,
            guard_hits=guard_hits if last else [],
        )


__all__ = [
    'MAX_STEPS',
    'PLAN_INSTRUCTION',
    'describe',
    'execute',
    'primary_tool',
    'source_line',
    'write_traces',
]
