# -*- coding: utf-8 -*-
"""视图层厚度守卫的回归网（#1606）。

`scripts/check_view_thickness.py` 是「视图层只做 HTTP 编排」这条判据的执行者
（`decisions.md` 2026-09-19），它有两个容易静默失效的点，本文件各钉一条：

1. **基线必须与真实文件集一致**——新增 `domains/*/views.py` 若漏登记，守卫会静默
   放行（没有基线也不在新增上限内就什么都不查？不：新文件走上限校验，但基线虚胖
   会让「删除文件后基线残留」这类漂移无人发现）；
2. **灵敏度**——守卫必须真的能报错（防「永远返回空 → 永远绿」的假绿，
   同 `tests/core/test_core_layer_boundary.py` 的反向验证思路）。

守卫逻辑按路径加载复用，不重复实现（判定规则只有一份）。
"""

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'check_view_thickness.py'


def _load_guard():
    spec = importlib.util.spec_from_file_location('check_view_thickness', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_guard_passes_on_current_repo(capsys):
    """仓库当前状态必须通过（基线取自 #1606 下沉后的实测值）。"""
    guard = _load_guard()
    assert guard.main([]) == 0


def test_baseline_covers_every_views_file():
    """每个 `domains/*/views.py` 都要有基线条目（防「新增视图文件漏登记」）。"""
    guard = _load_guard()
    actual = {guard._rel(p) for p in guard._iter_views()}
    assert actual, '未扫描到任何视图文件，守卫的 glob 可能失效'
    assert actual == set(guard.BASELINE), (
        f'基线缺条目：{sorted(actual - set(guard.BASELINE))}；基线多余条目：{sorted(set(guard.BASELINE) - actual)}'
    )


def test_metrics_count_db_calls_and_longest_function(tmp_path):
    """指标口径：`db.query` / `commit` 计数 + 最长函数行数（用合成样本钉死）。"""
    guard = _load_guard()
    sample = tmp_path / 'views.py'
    body = '\n'.join(f'    x{i} = {i}' for i in range(80))
    sample.write_text(f'def thick(db):\n{body}\n    db.query(1)\n    db.query(2)\n    db.commit()\n', encoding='utf-8')

    metrics = guard.collect_metrics(sample)
    assert metrics['orm_queries'] == 2
    assert metrics['commits'] == 1
    assert metrics['max_func'] >= 80  # 函数体 80+ 行


def test_guard_flags_regression_against_baseline(tmp_path, monkeypatch, capsys):
    """灵敏度：文件比基线更厚必须报错（防「永远绿」的假守卫）。"""
    guard = _load_guard()
    thick = tmp_path / 'views.py'
    thick.write_text(
        'def thick(db):\n' + '\n'.join(f'    x{i} = db.query({i})' for i in range(20)) + '\n',
        encoding='utf-8',
    )

    monkeypatch.setattr(guard, '_iter_views', lambda: [thick])
    monkeypatch.setattr(guard, '_rel', lambda path: 'backend/app/domains/x/views.py')
    monkeypatch.setattr(
        guard,
        'BASELINE',
        {'backend/app/domains/x/views.py': {'lines': 5, 'orm_queries': 1, 'commits': 0, 'max_func': 5}},
    )

    assert guard.main([]) == 1
    captured = capsys.readouterr()
    assert 'orm_queries' in captured.err
    assert '基线冻结（只减不增）' in captured.err


def test_guard_flags_new_file_over_limits(tmp_path, monkeypatch, capsys):
    """灵敏度：基线外的新视图文件超上限必须报错（含「新增上限」提示）。"""
    guard = _load_guard()
    fresh = tmp_path / 'views.py'
    fresh.write_text(
        'def thick(db):\n' + '\n'.join(f'    x{i} = db.query({i})' for i in range(20)) + '\n',
        encoding='utf-8',
    )

    monkeypatch.setattr(guard, '_iter_views', lambda: [fresh])
    monkeypatch.setattr(guard, '_rel', lambda path: 'backend/app/domains/new/views.py')
    monkeypatch.setattr(guard, 'BASELINE', {})

    assert guard.main([]) == 1
    captured = capsys.readouterr()
    assert '新增上限' in captured.err
