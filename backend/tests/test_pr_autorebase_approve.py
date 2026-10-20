# -*- coding: utf-8 -*-
"""`scripts/pr_autorebase_approve.py` 的回归网（源 GitHub #2419）。

钉的是**四件曾经同时失效的事**：

1. 该批准的 run 必须真的被批准，且**不重复批准**；
2. 「有 run 但不需要批准」与「一条 run 都没看到」**必须分开**——
   旧实现（内联 shell + `status=action_required` 过滤）把两者都读成「无需批准」，
   于是窗口一短就静默通过，CI 永久挂死；
3. 查询失败不许退化成「无需批准」（`rc 2`）；
4. 批准失败不许退化成成功（`rc 3`）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO / 'scripts' / 'pr_autorebase_approve.py'

_MOD = None


def _load():
    global _MOD
    if _MOD is None:
        spec = importlib.util.spec_from_file_location('pr_autorebase_approve', _SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['pr_autorebase_approve'] = module
        spec.loader.exec_module(module)
        _MOD = module
    return _MOD


@pytest.fixture()
def m():
    return _load()


def _args(**kw):
    base = dict(repo='imoyao/fundmate', sha='a' * 40, interval=0.0, max_wait=0.0, dry_run=False)
    base.update(kw)
    return argparse.Namespace(**base)


class FakeApi:
    """假 `gh api`：按轮次吐出 runs，记录调用。"""

    def __init__(self, rounds, *, list_ok=True, approve_ok=True):
        self.rounds = [list(r) for r in rounds]
        self.list_ok = list_ok
        self.approve_ok = approve_ok
        self.list_calls = 0
        self.approved: list[int] = []

    def __call__(self, path: str, method: str = 'GET'):
        if method == 'POST' and path.endswith('/approve'):
            rid = int(path.split('/')[-2])
            if not self.approve_ok:
                return 1, ''
            self.approved.append(rid)
            return 0, ''
        self.list_calls += 1
        if not self.list_ok:
            return 1, ''
        idx = min(self.list_calls - 1, len(self.rounds) - 1)
        return 0, json.dumps({'workflow_runs': self.rounds[idx]})


def _run(run_id: int, conclusion: str = 'action_required') -> dict:
    return {'id': run_id, 'conclusion': conclusion, 'status': 'completed', 'name': f'wf-{run_id}'}


def test_四条待批_run_全部批准_且命中后提前收工(m, monkeypatch, capsys):
    """一次变基通常同时产生 3~4 个 run；批准后复检一轮确认没有新增即可返回（不拖满窗口）。"""
    api = FakeApi([[_run(1), _run(2), _run(3), _run(4)]])
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=60)) == 0
    out = capsys.readouterr().out
    assert 'AUTOREBASE_APPROVE seen=4 approved=4 failed=0' in out
    assert sorted(api.approved) == [1, 2, 3, 4]
    assert api.list_calls == 2, '批准后应只复检一轮就收工'


def test_同一批_run_不会被批准两次(m, monkeypatch):
    """幂等：第二轮仍然返回同一批 action_required 时，不许重复 POST。"""
    api = FakeApi([[_run(7)], [_run(7)], [_run(7)]])
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=60)) == 0
    assert api.approved == [7]


def test_status形态的action_required也要批准(m, monkeypatch):
    """GitHub 两种写法都出现过：`conclusion=action_required` 与 `status=action_required`。

    只认一种会漏批（旧实现在 URL 上用 `status=` 过滤能筛出来，说明后一种真实存在）。
    """
    api = FakeApi([[{'id': 11, 'status': 'action_required', 'conclusion': None}]])
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=0)) == 0
    assert api.approved == [11]


def test_有run但无需批准_不进警告(m, monkeypatch, capsys):
    """「有 run、都不需要批准」是正常结论：不打 warning、不调用批准。"""
    api = FakeApi([[_run(1, 'success'), _run(2, 'failure')]])
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=0)) == 0
    out = capsys.readouterr().out
    assert '都无需批准' in out
    assert '::warning::' not in out
    assert api.approved == []
    assert api.list_calls == 1


def test_一条run都没看到_必须打warning注解(m, monkeypatch, capsys):
    """#2419 的病根：索引没跟上时是「空」，不是「无需批准」。两者必须分得开。"""
    api = FakeApi([[]])
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=0)) == 0
    out = capsys.readouterr().out
    assert '::warning::' in out
    assert '一条 run 都没看到' in out
    assert '无需批准' in out  # 提醒语里明确「不要读成」，不是结论
    assert '都不需要批准' not in out


def test_查询全失败_rc2_不许退化成无需批准(m, monkeypatch, capsys):
    api = FakeApi([[]], list_ok=False)
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=0)) == 2
    err = capsys.readouterr().err
    assert '结论不可信' in err
    assert '无需批准' in err


def test_批准失败_rc3(m, monkeypatch, capsys):
    api = FakeApi([[_run(9)]], approve_ok=False)
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=0)) == 3
    err = capsys.readouterr().err
    assert '人工点 Approve' in err
    assert api.approved == []


def test_dry_run_只报告不批准(m, monkeypatch, capsys):
    api = FakeApi([[_run(5), _run(6)]])
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=0, dry_run=True)) == 0
    out = capsys.readouterr().out
    assert '[dry-run]' in out
    assert '未真批准' in out
    assert api.approved == []


def test_窗口给足_但没东西就按时收工(m, monkeypatch):
    """max_wait / interval 是**上限**：没东西可批时不许无限轮询。"""
    api = FakeApi([[_run(1, 'success')]])
    monkeypatch.setattr(m, '_gh_api', api)
    assert m.run(_args(max_wait=0, interval=0)) == 0
    assert api.list_calls == 1
