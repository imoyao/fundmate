# -*- coding: utf-8 -*-
"""决策轮工具装载预算（``tool_budget``）回归网。

三条不可退让的性质，逐条单独用例：
1. **集合相等**：注册表里的工具必须**全部**被归类（常驻或某域）。新增工具忘了归类时
   它只会在窄域提问里永久隐身——最隐蔽的一类能力丢失，故用集合相等而不是「至少一个」。
2. **fail-open**：无域命中必须与预筛前**逐字相同**（含工具顺序），否则就是「拿不准就少给」。
3. **只影响可见性**：预筛没装进 prompt 的工具，``ToolExecutor`` 仍能校验、仍能派发。
"""

import json

from app.services.ai_recognizer import agent_loop, tool_budget
from app.services.ai_recognizer import tools as tools_mod

#: 代表性问句 → 该问句**必须**能看见的工具。线索改了也要全绿，否则就是漏能力。
GOLDEN = (
    ('我有多少资产', 'get_assets_overview'),
    ('我今年的收益率是多少', 'get_portfolio_performance'),
    ('我跑赢沪深300了吗', 'get_portfolio_vs_benchmark'),
    ('我持仓哪些亏得最多', 'list_position_pnl'),
    ('我最近交易太频繁了吗', 'get_trading_behavior'),
    ('我的收益主要来自哪里', 'get_return_attribution'),
    ('帮我看下 000001 的净值', 'get_fund_nav'),
    ('现在市场温度多少', 'get_market_temperature'),
    ('我的自选表现怎么样', 'get_watchlist_overview'),
    ('帮我做个再平衡建议', 'get_rebalance_reference'),
    ('易方达蓝筹的基金经理是谁', 'get_fund_profile'),
    ('005827 近三年业绩如何', 'get_fund_performance'),
    ('这只基金重仓了什么', 'get_fund_holdings'),
    ('它的风格漂移了吗', 'get_fund_style'),
    ('我的账户总盈亏', 'list_position_pnl'),
    ('市场拥挤吗', 'get_market_temperature'),
    ('110011 的持仓和风格', 'get_fund_holdings'),
    ('我买卖基金的频率正常吗', 'get_trading_behavior'),
    ('今年赚了多少', 'get_portfolio_performance'),
    ('估值分位高不高', 'get_market_temperature'),
    ('最近 GDP 增速多少', 'query_macro_indicator'),
    ('CPI 高不高', 'query_macro_indicator'),
    ('制造业 PMI 是多少', 'query_macro_indicator'),
    ('现在 LPR 多少', 'query_macro_indicator'),
)


def _registered_names() -> set:
    return {m['name'] for m in tools_mod.TOOLS_METADATA}


def test_every_registered_tool_is_classified():
    """集合相等：注册表 = 常驻 ∪ 各域。新增工具漏归类 → 红。"""
    grouped = set(tool_budget._CORE_TOOLS)
    for names in tool_budget._DOMAIN_TOOLS.values():
        grouped |= set(names)
    missing = _registered_names() - grouped
    assert not missing, f'这些工具没归类，窄域提问里会永久看不见：{sorted(missing)}'
    assert not grouped - _registered_names(), f'归类里有不存在的工具：{sorted(grouped - _registered_names())}'


def test_domain_cues_cover_every_domain():
    """每个域都要有线索，否则该域永远不命中（等同没分组）。"""
    assert set(tool_budget._DOMAIN_CUES) == set(tool_budget._DOMAIN_TOOLS)


def test_fail_open_returns_full_catalog_verbatim():
    """无域命中 → 与预筛前逐字相同（含顺序），预筛退化为空操作。"""
    for text in ('', '   ', '你好', '帮我看看这个'):
        assert tool_budget.matched_domains(text) == ()
        assert tool_budget.select_tools(text) == list(tools_mod.TOOLS_METADATA)
        assert tool_budget.tool_catalog(text) == json.dumps(tools_mod.TOOLS_METADATA, ensure_ascii=False)


def test_golden_questions_keep_required_tool_visible():
    """20 条代表问句，所需工具必须在本轮清单里（线索漂移的正向网）。"""
    for question, required in GOLDEN:
        names = [t['name'] for t in tool_budget.select_tools(question)]
        assert required in names, f'「{question}」看不见 {required}（命中域：{tool_budget.matched_domains(question)}）'


def test_narrow_question_actually_saves_budget():
    """窄域提问要真省——否则预筛没有存在意义（基金域省一半以上，市场域省八成以上）。"""
    fund = tool_budget.budget_stats('帮我看下 000001 的净值')
    assert fund['saved_ratio'] > 0.5, fund
    market = tool_budget.budget_stats('现在市场温度多少')
    assert market['saved_ratio'] > 0.8, market


def test_macro_question_is_narrow_and_saves_budget():
    """宏观域只装「常驻 2 + 宏观 1」：15 个工具里只给 3 个。"""
    stats = tool_budget.budget_stats('最近 GDP 增速多少')

    assert stats['domains'] == ('macro',)
    assert stats['tools'] == 3
    assert stats['saved_ratio'] > 0.75, stats


def test_macro_cues_do_not_leak_into_fund_or_account_questions():
    """「同比 / 增长 / 数据」这类词在基金与账户提问里也出现——宏观线索刻意不含它们。

    漏配这几条，纯基金提问会把宏观工具白装进去（省 60% 掉回省 50%），
    而错配的代价不会报错，只会悄悄变贵。
    """
    for question in (
        '这只基金近一年同比涨了多少',
        '基金规模增长快吗',
        '帮我看看持仓数据',
        '我的收益同比增长了吗',
    ):
        assert 'macro' not in tool_budget.matched_domains(question), question


def test_subset_keeps_full_metadata_order():
    """子集按原表顺序输出：人工核对与 diff 都按原表读，避免「顺序也是逻辑」被悄悄改。"""
    names = [t['name'] for t in tools_mod.TOOLS_METADATA]
    picked = [t['name'] for t in tool_budget.select_tools('这只基金重仓了什么')]
    assert picked == [n for n in names if n in set(picked)]


def test_decision_prompt_is_prefiltered_but_validation_stays_full():
    """预筛只决定「模型看见什么」，不影响「能不能调」——这是本设计的安全底线。"""
    question = '帮我看下 000001 的净值'
    prompt = agent_loop._decision_system_prompt(question)
    assert 'get_fund_nav' in prompt
    assert 'get_rebalance_reference' not in prompt, '账户域工具不该出现在纯基金提问里'
    # 但派发侧仍认它：ToolExecutor 按全量 TOOLS_METADATA 校验
    tools_mod._validate_params('get_rebalance_reference', {})
    assert 'get_rebalance_reference' in tools_mod._FUNCTION_MAP


def test_decision_prompt_default_keeps_full_catalog():
    """既有调用点（无 user_input）必须拿到全量清单——不能因预筛改变默认行为。"""
    prompt = agent_loop._decision_system_prompt()
    for meta in tools_mod.TOOLS_METADATA:
        assert meta['name'] in prompt
