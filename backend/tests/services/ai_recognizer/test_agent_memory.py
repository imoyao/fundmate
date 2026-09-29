# -*- coding: utf-8 -*-
"""S2 分层记忆测试（#1121 步骤卡 #4）：20 轮保留 / prompt 有界 / 压缩与降级。

三条验收的自动化对应：
1. 20 轮后仍能正确回答第 1 轮标的（摘要层回灌，mock 压缩做「完美压缩」）；
2. 单轮 prompt 有固定上界（每层硬截断 → 上界与轮次无关）；
3. 压缩失败降级为硬截断（不中断对话，prompt 依然有界）。
"""

import json
import re

from app.domains.agent.models import AgentSession
from app.services.ai_recognizer import agent_loop, guards
from app.services.ai_recognizer import llm as llm_mod

# 单轮 prompt 理论上界（最坏情形 = 硬截断原文层 + 摘要层 + 关键卡层 + 固定开销），
# 直接由 agent_loop 的层常量推导，改常量时自动跟随
PROMPT_BOUND = (
    agent_loop.HARD_RAW_CAP * 2 * agent_loop.TURN_SIDE_CAP
    + agent_loop.SUMMARY_CAP
    + agent_loop.KEY_FACTS_CAP
    + 1500  # goal / 已收集参数 / 本轮指令等固定开销
)

CLARIFY = '{"action":"ask_clarification","missing_params":["period"],"content":"想看多久？"}'


def _install_spy(monkeypatch, prompts):
    """决策 prompt 全量入列；压缩调用回灌原文（模拟完美压缩），不触网。"""

    def fake(content, system_prompt, **kwargs):
        text = content[0]['text']
        if '记忆压缩器' in system_prompt:
            # 从压缩 prompt 里抠出旧轮次 JSON，把原文逐字拼进摘要——验证「第 1 轮信息
            # 经摘要层活到第 20 轮」这条链路，而不只是「压缩被调用了」
            m = re.search(r'需要压缩的更早对话轮次：(.+?)\n只输出', text, re.S)
            old = json.loads(m.group(1))
            digest = '；'.join(t.get('user', '') for t in old)
            return json.dumps({'digest': digest, 'key_facts': {'标的': '110011'}}, ensure_ascii=False)
        prompts.append(text)
        return CLARIFY

    monkeypatch.setattr(llm_mod, 'call_llm', fake)


def test_twenty_turns_retain_first_turn_and_prompt_bounded(monkeypatch):
    """验收①②：20 轮后仍记得第 1 轮标的；每轮 prompt 有固定上界。"""
    monkeypatch.setattr(guards, 'AGENT_MAX_TURNS', 30)  # 默认 10 轮闸，本例专测 20 轮
    prompts = []
    _install_spy(monkeypatch, prompts)
    session = AgentSession(session_id='mem-1', user_id=1)

    for i in range(1, 21):
        text = '帮我看看汇添富短债(110011)近一年表现' if i == 1 else f'第{i}轮补充'
        out = agent_loop.run_agent(text, session)

    assert len(prompts) == 20
    assert all(len(p) <= PROMPT_BOUND for p in prompts)
    assert '110011' in prompts[19]  # 第 1 轮标的经摘要层活到第 20 轮（P2 修复验收）
    assert session.summary  # 压缩确实发生
    assert len(session.messages) <= agent_loop.COMPRESS_WINDOW  # 原文层被压回窗口
    assert len(session.summary) <= agent_loop.SUMMARY_CAP
    assert out['type'] == 'clarify'


def test_compress_failure_degrades_to_hard_cap(monkeypatch):
    """验收③：压缩失败不中断对话，原文层硬截断 → prompt 仍有界。"""
    monkeypatch.setattr(guards, 'AGENT_MAX_TURNS', 30)
    prompts = []

    def fake(content, system_prompt, **kwargs):
        if '记忆压缩器' in system_prompt:
            raise RuntimeError('compress boom')  # 模拟便宜模型调用挂掉
        prompts.append(content[0]['text'])
        return CLARIFY

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    session = AgentSession(session_id='mem-2', user_id=1)

    for i in range(1, 16):
        out = agent_loop.run_agent(f'第{i}轮输入', session)

    assert out['type'] == 'clarify'  # 对话未被压缩异常打断
    assert not session.summary  # 未产出摘要（降级而非半写）
    assert len(session.messages) <= agent_loop.HARD_RAW_CAP  # 降级截断生效
    assert all(len(p) <= PROMPT_BOUND for p in prompts)
