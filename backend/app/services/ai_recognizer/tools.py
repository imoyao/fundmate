# -*- coding: utf-8 -*-
"""账本精灵工具包（ToolExecutor + 工具注册表）。

本模块不触碰账本 DB，只做数值计算（D19 铁律：模型只叙事，数值靠代码算）。

合并说明（2026-09-09）：原为 ``tools/`` 包（``__init__.py`` 仅 9 行转发 + ``executor.py``），
属「一个包只装一个文件」的空壳分层，已收敛为本单模块；对外符号不变。

职责（D19 铁律）：工具内只做**数值计算**，绝不让模型写代码、绝不直接碰账本；
执行结果只回传指标值给 AgentLoop 拼回 prompt 叙事。

- TOOLS_METADATA：工具元信息（name / description / parameters），同时给模型看 + 给代码做 schema 校验；
- ToolExecutor.run：按 name 找函数 → 校验 params → 执行 → 返回 {status, data|msg}；
- 出错时上层 AgentLoop 负责「最多 1 次重试」（把错误拼回 prompt 由模型重新决策），本层不重试、不崩。

真实工具实现（如调 summary_service 算 XIRR、调 xalpha 算最大回撤）在后续 issue 落地；
当前 `_demo_get_portfolio_performance` 仅为可运行占位，验证整条链路。
"""

import re
from typing import Any, Callable, Dict

from loguru import logger

# name -> 实现函数（注册表）；真实工具在此注册
_FUNCTION_MAP: Dict[str, Callable] = {}


def register_tool(name: str, func: Callable) -> None:
    """注册一个工具实现函数。"""
    _FUNCTION_MAP[name] = func


def _demo_get_portfolio_performance(params: dict) -> dict:
    """示例工具：真实实现应调 summary_service / xalpha 算 XIRR/回撤，这里返回占位指标。"""
    return {
        'annualized_return': None,
        'max_drawdown': None,
        'note': 'demo placeholder; 接入 summary_service/xalpha 后填充真实指标',
    }


register_tool('get_portfolio_performance', _demo_get_portfolio_performance)


# 工具元信息：模型据此选工具，代码据此校验参数（pattern/regex 大模型会遵循，代码也能复用）
TOOLS_METADATA = [
    {
        'name': 'get_portfolio_performance',
        'description': '获取指定账户或全持仓的收益表现指标（年化、最大回撤等）',
        'parameters': {
            'type': 'object',
            'properties': {
                'scope': {
                    'type': 'string',
                    'enum': ['all', 'account'],
                    'description': '分析范围：all=全部持仓，account=指定账户',
                },
                'account_id': {
                    'type': 'string',
                    'description': '账户 id（scope=account 时必填）',
                },
                'period': {
                    'type': 'string',
                    'pattern': r'^\d+[dwm]$',
                    'description': '分析区间，如 90d / 3m / 1w',
                },
            },
            'required': ['scope', 'period'],
        },
    },
]


def _validate_params(tool_name: str, params: Any) -> None:
    """按 TOOLS_METADATA 校验参数；非法即抛 ValueError（由 run 捕获为 error）。"""
    meta = next((t for t in TOOLS_METADATA if t['name'] == tool_name), None)
    if not meta:
        raise ValueError(f'未知工具: {tool_name}')
    props = meta['parameters']['properties']
    required = meta['parameters'].get('required', [])
    params = params or {}
    if not isinstance(params, dict):
        raise ValueError('params 必须为对象')
    for r in required:
        if r not in params:
            raise ValueError(f'缺少必填参数: {r}')
    for k, v in params.items():
        if k not in props:
            raise ValueError(f'未知参数: {k}')
        spec = props[k]
        if 'enum' in spec and v not in spec['enum']:
            raise ValueError(f'参数 {k}={v} 不在允许值 {spec["enum"]}')
        if 'pattern' in spec and not re.fullmatch(spec['pattern'], str(v)):
            raise ValueError(f'参数 {k}={v} 不匹配格式 {spec["pattern"]}')


class ToolExecutor:
    """工具执行原子刀：校验 → 派发 → 返回结构化结果（不崩、不重试）。"""

    @staticmethod
    def run(name: str, params: Any) -> dict:
        """执行工具，返回 {status:'success'|'error', data|msg}。"""
        try:
            _validate_params(name, params)
            func = _FUNCTION_MAP.get(name)
            if not func:
                return {'status': 'error', 'msg': f'未注册工具: {name}'}
            data = func(params or {})
            return {'status': 'success', 'data': data}
        except Exception as e:  # noqa: BLE001  兜底：工具内部异常不让 AgentLoop 崩
            logger.warning('工具执行失败 name={} params={}: {}', name, params, e)
            return {'status': 'error', 'msg': str(e)}


__all__ = ['TOOLS_METADATA', 'ToolExecutor', 'register_tool']
