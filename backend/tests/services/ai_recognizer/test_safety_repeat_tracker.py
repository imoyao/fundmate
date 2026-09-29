# -*- coding: utf-8 -*-
"""重复追问检测（repeat_tracker）单测。

核心语义是「**连续**同问」：换问法即重新计数，不同问题互不相干——
若做不到这一点，正常的多轮追问会被误判成软化式越界。
"""

from app.services.ai_recognizer.safety.repeat_tracker import (
    STANDARD_REPLY,
    RepeatTracker,
    normalize,
)


def test_normalize_ignores_punctuation_and_width():
    """换个标点 / 全角就绕过计数 → 检测形同虚设，故归一化必须把它们拉平。"""
    assert normalize('近一年涨跌幅？') == normalize('近一年涨跌幅')
    assert normalize('近 一年 涨跌幅。') == normalize('近一年涨跌幅')
    assert normalize('ＡＢＣ１２３') == normalize('abc123')
    assert normalize('') == ''
    assert normalize(None) == ''


def test_same_question_reaches_threshold():
    t = RepeatTracker(threshold=3)
    sid = 'sess-r1'
    assert t.record(sid, '我该不该卖') is False
    assert t.record(sid, '我该不该卖?') is False  # 换标点仍算同一问
    assert t.record(sid, '我该不该卖') is True  # 第 3 次达阈
    assert t.count(sid) == 3


def test_different_question_resets_count():
    t = RepeatTracker(threshold=3)
    sid = 'sess-r2'
    t.record(sid, '问题A')
    t.record(sid, '问题A')
    assert t.record(sid, '问题B') is False  # 换问法 → 归零重数
    assert t.count(sid) == 1


def test_threshold_configurable():
    t = RepeatTracker(threshold=1)
    assert t.record('sess-r3', '同一问') is True  # 第 1 次即达阈


def test_reset_clears_session():
    t = RepeatTracker(threshold=2)
    t.record('sess-r4', '同一问')
    t.reset('sess-r4')
    assert t.count('sess-r4') == 0
    assert t.record('sess-r4', '同一问') is False  # 重新从 1 开始


def test_empty_inputs_not_tracked():
    t = RepeatTracker(threshold=1)
    assert t.record('', '问题') is False
    assert t.record('sess-r5', '') is False
    assert t.record('sess-r5', '   ') is False
    assert len(t) == 0


def test_sessions_are_independent():
    """计数按 session 隔离：A 会话达阈不得波及 B 会话（防串味）。"""
    t = RepeatTracker(threshold=2)
    assert t.record('sess-a', '同一问') is False
    assert t.record('sess-a', '同一问') is True
    assert t.record('sess-b', '同一问') is False
    assert t.record('sess-c', '同一问') is False


def test_max_sessions_eviction():
    """session_id 由前端生成、可任意构造 → 不做淘汰就是个内存放大器。"""
    t = RepeatTracker(threshold=3, max_sessions=3)
    for i in range(6):
        t.record(f'sess-evict-{i}', f'问题{i}')
        assert len(t) <= 3


def test_standard_reply_has_placeholder_and_safe_outlet():
    """话术带占位（第 N 次）且给的是替代查询，不是干瘪拒绝。"""
    reply = STANDARD_REPLY.format(3)
    assert '3' in reply
    assert '查' in reply or '数据' in reply
