# -*- coding: utf-8 -*-
"""账本精灵·投顾调仓解读工具包（#3259 · L4）。

承载「调仓解读」场景的工具：输入某投顾组合 code，输出最近一次调仓的结构化解读
（方向 / 成分变化 / 说的 vs 做的分歧标记）。

为什么单独一个模块（与 ``tools_fund`` 同源理由）：``tools.py`` 已被
``scripts/guard_service_size.py`` 冻结在 644 行，新工具塞进去必然红灯；且投顾调仓是
独立的域（market 域 ``advisor_adjust_histories``），与基金级、账户级工具都不同源。

三条硬纪律（对齐 ``tools_fund`` 的 docstring）：
1. **严格只读**：不 commit、不回填、不出网。``build_rebalance_interpretation`` 只查
   ``advisor_adjust_histories`` 与名录，零写路径。
2. **出参投影**：只保留叙事需要的字段（最近一次调仓的日期/理由/成分/方向/分歧），
   不铺开多期回溯（口径 = 最近一次调仓，见 #3259）。
3. **缺数据如实**：组合不存在回 ``found: false``；存在但无调仓回 ``has_rebalance: false``。
   不编造调仓、不补零占比。

DB 会话走路由会话（``database.get_session``，与 L3 ``advisor_comparison`` 的跨域读同源）：
``advisor_adjust_histories`` 在 market 域，但路由会话在单库下与 user/market 同库，
双库下由 ``_engines`` 路由。工具经 ``get_session()`` 拿会话，模块级引用（#1608 晚绑定守卫）。
"""

from __future__ import annotations

from typing import Callable, Dict, List

from app.core import database  # 模块级引用，禁止 from-import get_session（#1608）
from app.services.rebalance_interpretation import build_rebalance_interpretation

# 投影上限：成分基金条数（最近一次调仓一般 ≤ 20 只，截断防 prompt 撑爆）
_MAX_COMPONENTS = 20


def _tool_get_advisor_rebalance(params: dict) -> dict:
    """某投顾组合最近一次调仓的结构化解读（方向 + 成分变化 + 说的 vs 做的分歧）。

    只读保证：``build_rebalance_interpretation`` 只查 ``advisor_adjust_histories`` 与基金名录，
    零写库、零外部请求。

    消费方必须守住的四条（否则会误读或越界）：
    - 本工具只回**最近一次**调仓，不铺开多期回溯；用户要历史对比需另取；
    - ``direction.action`` 是「净权益方向」（add/reduce/None），由成分基金类型 + 操作方向
      聚合；「混合型」库里无偏股/偏债二级分类，归入权益类兜底（与 L3 同口径）；
    - ``divergence.divergence`` 三态：``true``（说的与做的相反）、``false``（一致）、
      ``unknown``（reason 无信息量或无法判定）——unknown 时**不要**强行说「他说的未必是他做的」；
    - 只转述客观数据，**不预测、不评价主理人好坏、不给买卖方向**；措辞避开「建议/推荐/
      应该买入/卖出/替换」，由输出范式 prompt + output_filter 兜底。
    """
    code = (params.get('code') or '').strip()
    if not code:
        return {'code': '', 'found': False, 'error': '缺少 code'}

    with database.get_session() as db:
        result = build_rebalance_interpretation(db, code)

    if not result.get('found'):
        return {'code': code, 'found': False}
    if not result.get('has_rebalance'):
        return {
            'code': result.get('code'),
            'name': result.get('name'),
            'platform': result.get('platform'),
            'found': True,
            'has_rebalance': False,
        }

    # 投影：成分只保留叙事需要的字段，截断超长
    components = [
        {
            'fund_code': c.get('fund_code'),
            'fund_name': c.get('fund_name'),
            'pre_ratio': c.get('pre_ratio'),
            'after_ratio': c.get('after_ratio'),
            'delta': c.get('delta'),
            'op_name': c.get('op_name'),
        }
        for c in (result.get('components') or [])[:_MAX_COMPONENTS]
    ]

    return {
        'code': result.get('code'),
        'name': result.get('name'),
        'platform': result.get('platform'),
        'found': True,
        'has_rebalance': True,
        'adjust_date': result.get('adjust_date'),
        'reason': result.get('reason'),
        'components': components,
        'direction': result.get('direction'),
        'divergence': result.get('divergence'),
    }


_ADVISOR_TOOL_FUNCS: Dict[str, Callable[[dict], dict]] = {
    'get_advisor_rebalance': _tool_get_advisor_rebalance,
}

# 组合 code 不做 strict pattern：且慢 ZHxxxx / LONG_WIN / 天天 combo 等命名空间不统一，
# 无法用单一正则约束（#1392「禁止按代码前缀判定平台」同源）。
_ADVISOR_CODE_SCHEMA = {'type': 'string', 'description': '投顾组合代码（如且慢 ZH012926、天天 XCOVSEX）'}

ADVISOR_TOOLS_METADATA: List[dict] = [
    {
        'name': 'get_advisor_rebalance',
        'description': '查某个投顾组合最近一次调仓的结构化解读：调仓日期、调仓理由、'
        '成分基金的前后占比变化（加仓/减仓/建仓/清仓）、净权益方向（加权益还是减权益）、'
        '以及「说的 vs 做的」分歧标记（调仓理由文本与实际动作方向是否一致）。'
        '当用户问「XX组合最近调仓了是什么意思」「它这次加仓了什么」「主理人说的和做的'
        '一不一致」「这次调仓方向是加权益还是加债」时使用。'
        '只回最近一次调仓的客观数据：不预测涨跌、不评价主理人好坏、不给买卖方向；'
        'divergence 为 unknown 时不要强行说「他说的未必是他做的」，如实告知无法判定。'
        '若要「我的持仓 vs 它的持仓」的重合对照，用 get_advisor_comparison（L3 已有端点），'
        '本工具只回答「这次调仓本身做了什么」',
        'parameters': {
            'type': 'object',
            'properties': {'code': _ADVISOR_CODE_SCHEMA},
            'required': ['code'],
        },
    },
]


def install_advisor_tools(register: Callable[[str, Callable], None], metadata: List[dict]) -> None:
    """把投顾调仓解读工具接入 ``tools.py`` 的注册表与元数据清单。

    显式调用而非 import 副作用：调用点只有一处（``tools_domain.py`` 的装配器），
    「是否真的接上了」由单测集合相等断言钉住。
    """
    for name, func in _ADVISOR_TOOL_FUNCS.items():
        register(name, func)
    metadata.extend(ADVISOR_TOOLS_METADATA)


__all__ = ['ADVISOR_TOOLS_METADATA', 'install_advisor_tools']
