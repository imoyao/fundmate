"""G7：L1 数据真实性铁律注入 system prompt（#1121，设计文档 §4）。

只断言 prompt **内容与注入点位**——L1 是确定性文本，不需要也不应该靠 mock LLM
「看它乖不乖」来验证；L1 是否真拦得住由 L3 输出过滤（test_safety_*）兜底。
"""

from app.domains.agent.models import AgentSession
from app.services.ai_recognizer import agent_loop
from app.services.ai_recognizer import llm as llm_mod

# 设计 §4 的核心要点：任意一条缺失即视为 L1 抽条/漂移
KEY_PHRASES = (
    '数据真实性铁律',
    '严禁编造',
    '宁可说「我不知道」，不可编造答案',  # §4 标注的最管用一句：给模型安全出口
    '自查三问',  # 回复前三条逐条确认
    '不能：预测涨跌；评判基金经理好坏；给出买卖建议；保证任何策略有效',  # can/cannot 清单
)


def test_decision_system_prompt_carries_l1_truth():
    """决策轮：契约 + 铁律 + 工具清单三段齐全，且铁律排在工具清单之前。"""
    prompt = agent_loop._decision_system_prompt()
    for phrase in KEY_PHRASES:
        assert phrase in prompt, f'决策轮 system prompt 缺 L1 铁律要点：{phrase}'
    # 顺序：铁律要在工具清单之前（先立规矩再给能力，避免清单里的工具描述淹没铁律）
    assert prompt.index('数据真实性铁律') < prompt.index('可用工具清单')


def test_narrative_system_prompt_carries_l1_truth(monkeypatch):
    """叙事轮（写数字的地方）同样注入铁律——mock call_llm 抓真实入参，不触网。"""
    seen: list = []

    def fake(content, system_prompt, **kwargs):
        seen.append(system_prompt)
        if kwargs.get('response_format'):  # 决策轮
            return '{"action":"execute_tool","tool_name":"get_market_temperature","tool_params":{}}'
        return '短期档即贪恐指数 21。'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('现在市场温度是多少？', AgentSession(session_id='l1-narrative', user_id=1))
    assert out['type'] == 'result'
    assert len(seen) == 2, '应发生决策轮 + 叙事轮两次调用'
    decision_system, narrative_system = seen
    for phrase in KEY_PHRASES:
        assert phrase in decision_system, f'决策轮缺：{phrase}'
        assert phrase in narrative_system, f'叙事轮缺：{phrase}'


def test_l1_is_single_constant_reused_by_decision_prompt():
    """决策轮拼的是常量本体（而非复制的相似文本）——两轮只能通过改这一处同步。"""
    assert agent_loop._L1_DATA_TRUTH in agent_loop._decision_system_prompt()
    assert agent_loop._L1_DATA_TRUTH.count('宁可说「我不知道」') == 1
