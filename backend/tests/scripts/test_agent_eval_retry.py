# -*- coding: utf-8 -*-
"""`agent_eval.run_case_with_retry` 的重试口径单测（#2621）。

钉死一条纪律：**只有「一行 trace 都没落」才重试**（429 / 异常 = 设施故障）；
模型选错工具（`turns>0` 但 `ok=False`）**不重试**——否则就是用采样次数掩盖真实退化，
评估集也就失去了「改完变好没有」的判据意义。
"""

import os
import sys

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import agent_eval as m  # noqa: E402


def _result(turns, ok):
    return {'id': 'x', 'turns': turns, 'ok': ok, 'why': '' if ok else 'tool 不符'}


def test_retries_when_no_trace(monkeypatch):
    """429 时 turns=0：必须重试，且退避按 delay 指数增长（2s → 4s）。"""
    calls = []
    sleeps = []

    def fake_run(db, case):
        calls.append(case)
        return _result(0 if len(calls) == 1 else 1, len(calls) > 1)

    monkeypatch.setattr(m, 'run_case', fake_run)
    monkeypatch.setattr(m.time, 'sleep', lambda s: sleeps.append(s))

    result = m.run_case_with_retry(None, {'id': 'x'}, delay=2.0, retries=2)

    assert len(calls) == 2, '首次无 trace 应重试一次'
    assert result['turns'] == 1, '应返回重试后的结果'
    assert sleeps == [4.0], f'退避应为 delay * 2**(attempt+1)=4.0，实际 {sleeps}'


def test_no_retry_when_tool_mismatch(monkeypatch):
    """模型选了别的工具（turns>0）：这是真实退化信号，不许重试刷成绿。"""
    calls = []

    def fake_run(db, case):
        calls.append(case)
        return _result(1, False)

    monkeypatch.setattr(m, 'run_case', fake_run)
    monkeypatch.setattr(m.time, 'sleep', lambda s: None)

    result = m.run_case_with_retry(None, {'id': 'x'}, delay=2.0, retries=3)

    assert len(calls) == 1, f'工具选错不该重试，实际调用 {len(calls)} 次'
    assert result['ok'] is False


def test_gives_up_after_retries(monkeypatch):
    """重试用尽：返回最后一次结果，不无限循环。"""
    calls = []

    def fake_run(db, case):
        calls.append(case)
        return _result(0, False)

    monkeypatch.setattr(m, 'run_case', fake_run)
    monkeypatch.setattr(m.time, 'sleep', lambda s: None)

    result = m.run_case_with_retry(None, {'id': 'x'}, delay=1.0, retries=2)

    assert len(calls) == 3, f'1 次 + 2 次重试 = 3 次，实际 {len(calls)}'
    assert result['turns'] == 0
