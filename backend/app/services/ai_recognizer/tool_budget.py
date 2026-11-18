# -*- coding: utf-8 -*-
"""账本精灵·决策轮工具装载预算（按问题域预筛）。

为什么需要
----------
决策轮 system prompt 每轮把整份 ``TOOLS_METADATA`` 序列化进 context
（``agent_loop._decision_system_prompt``）。2026-11-16 实测：**15 个工具、7213 字符**
（≈3.5k token），且**与提问无关**——问「000001 净值多少」也要付「再平衡 / 归因 / 宏观」
的 schema 钱。工具只会越加越多（基金 5 个 #3111、宏观 #1502、投顾还会加），不预筛则
每轮固定成本随工具数单调上升。

三条硬约束（保证「省 token」不变成「丢能力」）
--------------------------------------------
1. **fail-open**：无域线索命中 → 原样返回全量，与预筛前**逐字相同**。只允许「有把握时
   少给」，绝不允许「拿不准就不给」——漏一个工具等于该能力本轮不可用。
2. **只影响「模型看见什么」**：``ToolExecutor`` 仍按全量 ``TOOLS_METADATA`` 校验派发。
3. **零 token**：域线索是正则，不额外调模型（与 ``safety.intent_guard`` 同哲学：顺序即成本）。

分组口径按「用户问的是哪一类问题」划分，不按实现文件划分——模型选工具看的是语义。
``_DOMAIN_TOOLS`` 与注册表**集合相等**由单测钉住：新增工具忘归类立刻红（漏归类 = 窄域
提问里它永远看不见）。``_CORE_TOOLS``（账户总览 + 组合绩效）常驻，宁可多 786 字符。
"""

import json
import re
from typing import Dict, List, Tuple

from app.services.ai_recognizer.tools import TOOLS_METADATA

#: 常驻工具（不参与域判断）：账户总览 + 组合绩效，任何提问都保留。
_CORE_TOOLS: Tuple[str, ...] = (
    'get_assets_overview',
    'get_portfolio_performance',
)

#: 域 → 该域工具。域内工具只在命中该域时装载。
_DOMAIN_TOOLS: Dict[str, Tuple[str, ...]] = {
    # 基金个体维度（「这只基金」而不是「我的账户」）
    'fund': (
        'get_fund_nav',
        'get_fund_profile',
        'get_fund_performance',
        'get_fund_holdings',
        'get_fund_style',
    ),
    # 我的账户 / 组合维度
    'account': (
        'get_portfolio_vs_benchmark',
        'list_position_pnl',
        'get_trading_behavior',
        'get_return_attribution',
        'get_watchlist_overview',
        'get_rebalance_reference',
    ),
    # 市场环境维度
    'market': ('get_market_temperature',),
    # 宏观环境维度（国家级指标，不是我的账户也不是某只基金）
    'macro': ('query_macro_indicator',),
}

#: 域线索（顺序无关，可多域同时命中）。线索要「窄而准」：
#: 宁可漏（fail-open 兜底成全量），不可错（错命中会挤掉真正需要的域）。
_DOMAIN_CUES: Dict[str, 're.Pattern[str]'] = {
    # 「净值 / 重仓 / 风格 / 基金经理」这类词只在问某只基金时出现；
    # 6 位数字代码是最强信号（用户直接贴代码）。注意别把日期 / 金额当代码：
    # 要求前后不是数字，且不是「20xx 年」形态。
    'fund': re.compile(
        r'基金|净值|重仓|十大持仓|持仓明细|风格|基金经理|费率|跟踪误差|规模变动'
        r'|这只基|那只基|(?<![0-9])(?!(?:19|20)\d{2}(?!\d))\d{6}(?![0-9])'
    ),
    # 刻意**不含**「持仓 / 仓位」：这两个词在「这只基金重仓什么」里也会出现，
    # 命中账户域会把 13/14 个工具全装进来（实测省 4.2%，等于没筛）。
    # 账户类提问的真实线索是「亏 / 账户 / 收益」这些，不靠「持仓」白名单。
    'account': re.compile(
        r'账户|资产|收益|年化|XIRR|xirr|赚|亏|盈亏|成本'
        r'|交易|买卖|买入|卖出|清仓|加仓|减仓|调仓|再平衡|自选|基准|跑赢|跑输|归因|回撤'
    ),
    'market': re.compile(r'市场|温度|情绪|估值|分位|拥挤|大盘|指数点位|普涨|普跌'),
    # 线索口径见 tools_macro 模块头（刻意不含「同比 / 增长 / 数据」）
    'macro': re.compile(
        r'宏观|GDP|CPI|PPI|PMI|M2|M1|社融|工业增加值|固定资产投资|社会消费品|进出口|贸易顺差|失业率'
        r'|LPR|MLF|逆回购|存款准备金|降准|降息|汇率|美元指数|国债收益率|通胀|通缩|经济增速|国民经济',
        re.IGNORECASE,
    ),
}

#: 域 → 中文名（日志 / 测试可读性）
_DOMAIN_LABELS: Dict[str, str] = {'fund': '基金', 'account': '账户', 'market': '市场', 'macro': '宏观'}

_FULL_CATALOG: str = json.dumps(TOOLS_METADATA, ensure_ascii=False)

#: 工具清单小节的引导语。措辞与顺序属行为契约（「服务端自动注入」那句防止模型
#: 自己编 family_id），故随预筛一起收在本模块，改文案只有一处。
_TOOL_LIST_HEADER = (
    '\n可用工具清单（tool_name 必须取自 name，tool_params 必须符合 parameters 约束；'
    'description 标注「服务端自动注入」的参数不要由你提供）：\n'
)


def decision_prompt(agent_prompt: str, l1_truth: str, plan_instruction: str, user_input: str = '') -> str:
    """拼决策轮 system prompt：角色 + L1 铁律 + **预筛后的**工具清单 + Plan 指令。

    顺序有语义：铁律必须排在清单之前（先立规矩再给能力；清单里的工具描述会淹没铁律，
    ``test_l1_prompt`` 钉着这条顺序）。``user_input`` 为空 → 清单回全量（fail-open）。
    """
    return agent_prompt + '\n' + l1_truth + _TOOL_LIST_HEADER + tool_catalog(user_input) + plan_instruction


def matched_domains(user_input: str) -> Tuple[str, ...]:
    """命中的域名（按 ``_DOMAIN_TOOLS`` 声明顺序），空元组表示「无把握，走全量」。"""
    text = user_input or ''
    if not text.strip():
        return ()
    return tuple(domain for domain, cue in _DOMAIN_CUES.items() if cue.search(text))


def select_tools(user_input: str) -> List[dict]:
    """该轮要装进 prompt 的工具子集。

    无域命中 → **全量**（fail-open，与预筛前行为逐字一致）；
    有域命中 → 常驻工具 + 命中域工具，按 ``TOOLS_METADATA`` 原顺序输出
    （顺序不变，测试与人工核对都按原表读）。
    """
    domains = matched_domains(user_input)
    if not domains:
        return list(TOOLS_METADATA)
    wanted = set(_CORE_TOOLS)
    for domain in domains:
        wanted.update(_DOMAIN_TOOLS[domain])
    return [m for m in TOOLS_METADATA if m['name'] in wanted]


def tool_catalog(user_input: str) -> str:
    """决策轮 prompt 里的工具清单（JSON 文本）。

    这是 ``agent_loop`` 的唯一入口：预筛只改这里序列化出来的内容。
    """
    tools = select_tools(user_input)
    if len(tools) == len(TOOLS_METADATA):
        return _FULL_CATALOG  # 全量走预序列化常量：零重复序列化成本，且逐字可比
    return json.dumps(tools, ensure_ascii=False)


def budget_stats(user_input: str) -> dict:
    """预筛效果（留痕 / 测试用）：命中域、工具数、字符数与相对全量的压缩比。"""
    tools = select_tools(user_input)
    chars = len(tool_catalog(user_input))
    return {
        'domains': matched_domains(user_input),
        'tools': len(tools),
        'chars': chars,
        'full_chars': len(_FULL_CATALOG),
        'saved_ratio': round(1 - chars / len(_FULL_CATALOG), 4) if _FULL_CATALOG else 0.0,
    }


__all__ = ['budget_stats', 'decision_prompt', 'matched_domains', 'select_tools', 'tool_catalog']
