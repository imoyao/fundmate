# -*- coding: utf-8 -*-
"""账本精灵工具包（ToolExecutor + 工具注册表）。

职责（D19 铁律）：工具内只做**只读查询与数值计算**，绝不让模型写代码；
执行结果只回传指标值给 AgentLoop 拼回 prompt 叙事。

- TOOLS_METADATA：工具元信息（name / description / parameters），同时给模型看 + 给代码做 schema 校验；
- ToolExecutor.run：服务端上下文覆盖（P1）→ schema 校验 → 派发 → {status, data|msg}；
- 出错时上层 AgentLoop 负责「最多 1 次重试」（error-as-observation），本层不重试、不崩；
- 每次执行必留 `[agent.tool]` 结构化日志（成功 ok / 失败 fail，含耗时），
  线上排障按 tag 过滤（#1121 S1-C）。

P1 越权防护（2026-09-26，#1121 S1-A）：
前端回传的 collected_params 与模型生成的 tool_params 都只是**候选值**；
服务端权威值（server_ctx，如 family_id）在 run() 内强制覆盖同名候选。
覆盖只对「该工具 schema 声明过的键」生效——未声明 family_id 的工具（如 get_fund_nav）
若被塞入 family_id，会在校验期被当**未知参数**拒绝，两头都堵死。
服务端不传 server_ctx 时 family_id 回退 1，与 core.auth.get_family_id 的单用户口径一致；
HTTP 路径由 views 层必传，不存在「前端可指定」的入口。
"""

import re
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from app.core import database  # 模块级引用，禁止 from-import get_session（#1608 晚绑定守卫）
from app.services.nav_service import NavService
from app.services.performance.calculators import calculate_portfolio_xirr
from app.services.summary_service import get_summary_data
from app.services.thermometer.service import TemperatureService
from app.services.watchlist_service import build_home_summary

# name -> 实现函数（注册表）
_FUNCTION_MAP: Dict[str, Callable] = {}


def register_tool(name: str, func: Callable) -> None:
    """注册一个工具实现函数。"""
    _FUNCTION_MAP[name] = func


# ── P1：服务端权威上下文 ────────────────────────────────────────────────────
def apply_server_context(tool_name: str, params: dict, server_ctx: dict) -> dict:
    """把服务端权威值覆盖进候选参数（只覆盖该工具 schema 声明过的键）。

    候选参数 = 前端 collected_params + 模型 tool_params；权威值 = 鉴权上下文。
    返回新 dict，不原地修改入参。
    """
    if not server_ctx:
        return params
    meta = next((t for t in TOOLS_METADATA if t['name'] == tool_name), None)
    if not meta:
        return params  # 未知工具：原样交给 _validate_params 报「未知工具」
    props = meta['parameters'].get('properties', {})
    merged = dict(params)
    for key, value in server_ctx.items():
        if key in props:
            merged[key] = value
    return merged


def _server_family_id(params: dict) -> int:
    """取注入后的 family_id；缺省回退 1（与 core.auth.get_family_id 口径一致）。"""
    try:
        return int(params.get('family_id') or 1)
    except (TypeError, ValueError):
        return 1


def _jsonable(value: Any) -> Any:
    """date/datetime → isoformat 递归转换（工具数据进 JSON 信封的兜底）。"""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


# ── 工具实现（全部只读，复用既有 service，零裸 SQL） ────────────────────────
def _tool_get_assets_overview(params: dict) -> dict:
    """家庭资产总览：总资产 / 负债 / 净资产 / 已实现与未实现盈亏（元）。"""
    with database.get_session() as db:
        return get_summary_data(db, family_id=_server_family_id(params))


def _tool_get_portfolio_performance(params: dict) -> dict:
    """组合年化收益 XIRR：投入 / 市值 / 总收益（元，family 维度）。"""
    with database.get_session() as db:
        return calculate_portfolio_xirr(
            db,
            family_id=_server_family_id(params),
            include_cash_equivalents=bool(params.get('include_cash_equivalents', False)),
        )


def _tool_get_fund_nav(params: dict) -> dict:
    """基金最新净值（只读本地已同步净值；allow_remote=False，工具自身不出网）。"""
    fund_codes: List[str] = params.get('fund_codes') or []
    with database.get_session() as db:
        dated = NavService.get_latest_navs_with_dates(db, fund_codes, allow_remote=False)
    return {
        'navs': [
            {'fund_code': code, 'unit_nav': nav, 'nav_date': nav_date.isoformat()}
            for code, (nav, nav_date) in dated.items()
        ]
    }


def _tool_get_market_temperature(params: dict) -> dict:
    """市场温度计概览：综合温度 / 短中长期档位 / 结论 / 数据新鲜度。"""
    overview = TemperatureService.get_overview()
    composites = overview.get('composites') or {}
    return {
        'composite_temperature': composites.get('composite_temperature'),
        'temperature_bands': composites.get('temperature_bands'),
        'conclusion': overview.get('conclusion'),
        'freshness': overview.get('freshness'),
        'updated_at': overview.get('updated_at'),
    }


def _tool_get_watchlist_overview(params: dict) -> dict:
    """自选首页摘要：置顶与持仓标的最新价 / 涨跌幅 / 持仓市值（最多 5 条）。"""
    with database.get_session() as db:
        items = build_home_summary(db, family_id=_server_family_id(params))
    return {'items': _jsonable(items)}


register_tool('get_assets_overview', _tool_get_assets_overview)
register_tool('get_portfolio_performance', _tool_get_portfolio_performance)
register_tool('get_fund_nav', _tool_get_fund_nav)
register_tool('get_market_temperature', _tool_get_market_temperature)
register_tool('get_watchlist_overview', _tool_get_watchlist_overview)


# 工具元信息：模型据此选工具，代码据此校验参数。
# family_id 只出现在 properties、不进 required——它是服务端注入字段，
# 模型/前端提供也无效（会被覆盖）；required 里放它会让离线直调误报缺参。
TOOLS_METADATA = [
    {
        'name': 'get_assets_overview',
        'description': '获取家庭资产总览：总资产/总负债/净资产/已实现与未实现盈亏（单位：元）',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
            },
        },
    },
    {
        'name': 'get_portfolio_performance',
        'description': '计算整个投资组合的年化收益率 XIRR：总投入/当前市值/总收益（单位：元）',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
                'include_cash_equivalents': {
                    'type': 'boolean',
                    'description': '是否把现金/货基/逆回购并入分母，默认 false（仅投资类资产）',
                },
            },
        },
    },
    {
        'name': 'get_fund_nav',
        'description': '查询基金最新单位净值与净值日期（只读本地已同步数据，支持多只批量）',
        'parameters': {
            'type': 'object',
            'properties': {
                'fund_codes': {
                    'type': 'array',
                    'items': {'type': 'string', 'pattern': r'^\d{6}$'},
                    'description': '基金代码列表，6 位数字字符串，如 ["110011"]',
                },
            },
            'required': ['fund_codes'],
        },
    },
    {
        'name': 'get_market_temperature',
        'description': '获取市场温度计概览：综合温度、短/中/长期档位、结论副文案与数据新鲜度',
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'get_watchlist_overview',
        'description': '获取自选列表首页摘要：置顶与持仓标的的最新价/涨跌幅/持仓市值（最多 5 条）',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
            },
        },
    },
]


# 类型检查表：schema type -> 断言函数（integer 显式排除 bool，Python 里 bool 是 int 子类）
_TYPE_CHECKS: Dict[str, Callable[[Any], bool]] = {
    'string': lambda v: isinstance(v, str),
    'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    'boolean': lambda v: isinstance(v, bool),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
}


def _validate_value(key: str, value: Any, spec: dict) -> None:
    """按单个参数的 schema 校验值（类型 / enum / pattern / 数组元素递归）。"""
    check = _TYPE_CHECKS.get(spec.get('type', ''))
    if check is not None and not check(value):
        raise ValueError(f'参数 {key} 类型应为 {spec.get("type")}')
    if 'enum' in spec and value not in spec['enum']:
        raise ValueError(f'参数 {key}={value} 不在允许值 {spec["enum"]}')
    if 'pattern' in spec and not re.fullmatch(spec['pattern'], str(value)):
        raise ValueError(f'参数 {key}={value} 不匹配格式 {spec["pattern"]}')
    if isinstance(value, list) and isinstance(spec.get('items'), dict):
        for i, item in enumerate(value):
            _validate_value(f'{key}[{i}]', item, spec['items'])


def _validate_params(tool_name: str, params: Any) -> None:
    """按 TOOLS_METADATA 校验参数；非法即抛 ValueError（由 run 捕获为 error）。"""
    meta = next((t for t in TOOLS_METADATA if t['name'] == tool_name), None)
    if not meta:
        raise ValueError(f'未知工具: {tool_name}')
    props = meta['parameters'].get('properties', {})
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
        _validate_value(k, v, props[k])


class ToolExecutor:
    """工具执行原子刀：P1 覆盖 → schema 校验 → 派发 → 结构化结果（不崩、不重试）。"""

    @staticmethod
    def run(name: str, params: Any, server_ctx: Optional[dict] = None) -> dict:
        """执行工具，返回 {status:'success'|'error', data|msg}。

        server_ctx：服务端权威上下文（如 {'family_id': int}），在 schema 校验前
        覆盖同名候选值——保证「进工具的 scope 字段只可能是服务端给的值」。
        """
        started = time.monotonic()
        try:
            candidate: Any = params if isinstance(params, dict) else (params or {})
            merged = apply_server_context(name, candidate, server_ctx or {})
            _validate_params(name, merged)
            func = _FUNCTION_MAP.get(name)
            if not func:
                logger.warning(
                    '[agent.tool] fail name={} reason=未注册 elapsed={:.2f}s',
                    name,
                    time.monotonic() - started,
                )
                return {'status': 'error', 'msg': f'未注册工具: {name}'}
            data = func(merged)
            logger.info('[agent.tool] ok name={} elapsed={:.2f}s', name, time.monotonic() - started)
            return {'status': 'success', 'data': data}
        except Exception as e:  # noqa: BLE001  兜底：工具内部异常不让 AgentLoop 崩
            logger.warning(
                '[agent.tool] fail name={} params={} elapsed={:.2f}s err={}',
                name,
                params,
                time.monotonic() - started,
                e,
            )
            return {'status': 'error', 'msg': str(e)}


__all__ = ['TOOLS_METADATA', 'ToolExecutor', 'apply_server_context', 'register_tool']
