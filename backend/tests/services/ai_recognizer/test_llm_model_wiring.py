"""LLM 档位与参数接线（2026-10-25）：agent 走 ARK_MODEL_AGENT，OCR 走默认档且关深度思考。

背景与代价（两侧都会静默出事，故用不触网的确定性断言锁住）：

- `ARK_MODEL` 是 OCR 视觉档；账本精灵切到纯文本推理模型后单开 `ARK_MODEL_AGENT`。
  agent 漏传 `model=` → 对话回落到视觉档（换了模型等于没换）；
  把纯文本模型写进 `ARK_MODEL` → 图片识别直接 400（该模型 input 只有 text）。
- OCR 档必须关深度思考：实测 2-1-lite 开着思考时单张图 **112.2s / 9002 token**，
  超过 ARK_TIMEOUT(60s) 直接 ReadTimeout→503；关掉是 **5.9s / 1367 token**。
  故 `thinking` 参数必须真的进 payload，且换模型时能被置空。
"""

from app.domains.agent.models import AgentSession
from app.services.ai_recognizer import agent_loop
from app.services.ai_recognizer import llm as llm_mod

DECISION_JSON = '{"action":"execute_tool","tool_name":"get_market_temperature","tool_params":{}}'


class _FakeResp:
    status_code = 200
    headers: dict = {}

    def raise_for_status(self):
        return None

    def json(self):
        return {'choices': [{'message': {'content': 'ok'}}], 'usage': {'total_tokens': 1}}


def _capture_payload(monkeypatch):
    """把 requests.post 换成记录 payload 的假件（不触网），返回 captured 字典。"""
    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.clear()
        captured.update(json or {})
        return _FakeResp()

    monkeypatch.setattr(llm_mod.requests, 'post', fake_post)
    monkeypatch.setattr(llm_mod, 'ARK_API_KEY', 'test-key')
    monkeypatch.setattr(llm_mod, '_record_tokens', lambda tokens: None)
    return captured


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
    captured = _capture_payload(monkeypatch)
    content = [{'type': 'text', 'text': 'hi'}]

    llm_mod.call_llm(content, 'system')
    assert captured['model'] == llm_mod.ARK_MODEL

    llm_mod.call_llm(content, 'system', model='custom-model')
    assert captured['model'] == 'custom-model'


def test_call_llm_thinking_passthrough(monkeypatch):
    """thinking 只有 enabled/disabled 才进 payload；'none' 等值一律不传（换模型时留退路）。"""
    captured = _capture_payload(monkeypatch)
    content = [{'type': 'text', 'text': 'hi'}]

    llm_mod.call_llm(content, 'system', thinking='disabled')
    assert captured['thinking'] == {'type': 'disabled'}

    llm_mod.call_llm(content, 'system', thinking='enabled')
    assert captured['thinking'] == {'type': 'enabled'}

    llm_mod.call_llm(content, 'system', thinking='none')
    assert 'thinking' not in captured

    llm_mod.call_llm(content, 'system')
    assert 'thinking' not in captured
