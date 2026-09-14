# -*- coding: utf-8 -*-
"""测试 jitter 工具（#1400）：优先级解析 + 随机延迟范围 + 边界。"""

import app.core.jitter as jitter


def test_resolve_cli_wins(monkeypatch):
    monkeypatch.setenv('SYNC_JITTER_SECONDS', '999')
    assert jitter.resolve_jitter_seconds(30) == 30


def test_resolve_env_fallback(monkeypatch):
    monkeypatch.setenv('SYNC_JITTER_SECONDS', '120')
    assert jitter.resolve_jitter_seconds() == 120


def test_resolve_default_without_env(monkeypatch):
    monkeypatch.delenv('SYNC_JITTER_SECONDS', raising=False)
    assert jitter.resolve_jitter_seconds() == jitter.DEFAULT_JITTER_SECONDS


def test_resolve_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv('SYNC_JITTER_SECONDS', 'abc')
    assert jitter.resolve_jitter_seconds() == jitter.DEFAULT_JITTER_SECONDS


def test_resolve_negative_clamped_to_zero(monkeypatch):
    assert jitter.resolve_jitter_seconds(-5) == 0


def test_apply_jitter_zero_window_no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(jitter.time, 'sleep', lambda s: slept.append(s))
    assert jitter.apply_jitter(0) == 0
    assert slept == []


def test_apply_jitter_sleeps_within_window(monkeypatch):
    slept = []
    monkeypatch.setattr(jitter.time, 'sleep', lambda s: slept.append(s))
    result = jitter.apply_jitter(600, label='test')
    assert len(slept) == 1
    assert 0 <= slept[0] <= 600
    # 返回值为整数秒（日志友好），且与睡眠时长一致（向下取整）
    assert result == int(slept[0])


def test_random_gap_distinct_and_bounded(monkeypatch):
    slept = []
    monkeypatch.setattr(jitter.time, 'sleep', lambda s: slept.append(s))
    gap = jitter.random_gap(min_seconds=1, max_seconds=5)
    assert len(slept) == 1
    assert 1 <= gap <= 5


def test_random_gap_disabled(monkeypatch):
    slept = []
    monkeypatch.setattr(jitter.time, 'sleep', lambda s: slept.append(s))
    assert jitter.random_gap(max_seconds=0) == 0.0
    assert slept == []


def test_resolve_job_gap_cli_wins(monkeypatch):
    monkeypatch.setenv('SYNC_JOB_GAP_SECONDS', '99')
    assert jitter.resolve_job_gap_seconds(3) == 3
    monkeypatch.delenv('SYNC_JOB_GAP_SECONDS', raising=False)
    assert jitter.resolve_job_gap_seconds() == jitter.DEFAULT_JOB_GAP_SECONDS
