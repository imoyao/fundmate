"""账本精灵模型档位接线（2026-10-25）：agent 走 ARK_MODEL_AGENT，OCR 走 ARK_MODEL。

背景：`ARK_MODEL` 是 OCR 视觉档（doubao，需支持图片输入）；账本精灵已切到纯文本推理
模型 `deepseek-v4-1-flash-economy-261017`。两侧接线错位都会静默出事：

- agent 漏传 `model=` → 对话回落到视觉档（换了模型却没用上，成本/效果都白改）；
- 把纯文本模型写进 `ARK_MODEL` → 图片识别直接 400（该模型 input 只有 text）。

故用两条确定性断言（mock `call_llm`，不触网）锁住两段接线。
"""

from app.domains.agent.models import AgentSession
from app.services.ai_recognizer import agent_loop
from app.services.ai_recognizer import llm as llm_mod

DECISION_JSON = '{"action":"execute_tool","tool_name":"get_market_temperature","tool_params":{}}'


def test_agent_calls_pass_agent_model(monkeypatch):
    """决策轮 + 叙事轮都必须显式传 ARK_MODEL_AGENT（两次调用）。"""
    seen: list = []

    def fake(content, system_prompt, **kwargs):
        seen.append(kwargs.get('model'))
        if kwargs.get('response_format'):  # 决策轮
            return DECISION_JSON
        return '短期档即贪恐指数 21。'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    out = agent_loop.run_agent('现在市场温度是多少？', AgentSession(session_id='model-wiring', user_id=1))

    assert out['type'] == 'result'
    assert seen == [llm_mod.ARK_MODEL_AGENT, llm_mod.ARK_MODEL_AGENT]


def test_summarize_passes_agent_model(monkeypatch):
    """记忆压缩也属对话链路（纯文本），同样走 agent 档。"""
    seen: list = []

    def fake(content, system_prompt, **kwargs):
        seen.append(kwargs.get('model'))
        return '{"digest": "摘要", "key_facts": {}}'

    monkeypatch.setattr(llm_mod, 'call_llm', fake)
    agent_loop._summarize([{'role': 'user', 'content': '看看收益'}], '目标')

    assert seen == [llm_mod.ARK_MODEL_AGENT]


def test_call_llm_model_override(monkeypatch):
    """call_llm：不传 model 用 ARK_MODEL（OCR 档），传了以传入值为准。"""
    captured: dict = {}

    class _Resp:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {'choices': [{'message': {'content': 'ok'}}], 'usage': {'total_tokens': 1}}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.clear()
        captured.update(json or {})
        return _Resp()

    monkeypatch.setattr(llm_mod.requests, 'post', fake_post)
    monkeypatch.setattr(llm_mod, 'ARK_API_KEY', 'test-key')
    monkeypatch.setattr(llm_mod, '_record_tokens', lambda tokens: None)
    content = [{'type': 'text', 'text': 'hi'}]

    llm_mod.call_llm(content, 'system')
    assert captured['model'] == llm_mod.ARK_MODEL

    llm_mod.call_llm(content, 'system', model='custom-model')
    assert captured['model'] == 'custom-model'
