# -*- coding: utf-8 -*-
"""视图层厚度守卫的回归网（#1606）。

`scripts/check_view_thickness.py` 是「视图层只做 HTTP 编排」这条判据的执行者
（`decisions.md` 2026-09-19），它有两个容易静默失效的点，本文件各钉一条：

1. **基线必须与真实文件集一致**——新增 `domains/*/views.py` 若漏登记，守卫会静默
   放行（没有基线也不在新增上限内就什么都不查？不：新文件走上限校验，但基线虚胖
   会让「删除文件后基线残留」这类漂移无人发现）；
2. **灵敏度**——守卫必须真的能报错（防「永远返回空 → 永远绿」的假绿，
   同 `tests/core/test_core_layer_boundary.py` 的反向验证思路）；
3. **基线虚胖**——基线宽于实测时，该维度的「只减不增」拦截会静默失效（实测 #1606 落地后
   `commits` 维度空转了 41/44：41 处 `commit()` 已随 #1609 batch 2/3/4 改为 `flush()`，
   基线却仍写着旧数字，于是「把 `flush` 改回 `commit`」不会被拦）。

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
    """BASELINE 必须恰好等于冻结的 legacy 集（防漏登记 / 防给新文件塞 fat 基线 gaming），
    且每个真实视图要么是 legacy（在 BASELINE 中），要么作为新文件压在 NEW_FILE_LIMITS 内。"""
    guard = _load_guard()
    views = guard._iter_views()
    assert views, '未扫描到任何视图文件，守卫的 glob 可能失效'
    actual = {guard._rel(p) for p in views}
    # 冻结集是分水岭：BASELINE 的键必须恰好等于 legacy 集——多一条=疑似 gaming，少一条=漏守卫
    assert set(guard.BASELINE) == set(guard.LEGACY_VIEWS), (
        f'BASELINE 与冻结 legacy 集不一致：缺 {sorted(set(guard.LEGACY_VIEWS) - set(guard.BASELINE))}；'
        f'多 {sorted(set(guard.BASELINE) - set(guard.LEGACY_VIEWS))}'
    )
    for path in views:
        rel = guard._rel(path)
        if rel in guard.LEGACY_VIEWS:
            continue
        # 新文件：不得有 BASELINE 条目（否则会被 gaming 成 fat 基线），且必须压在新增上限内
        assert rel not in guard.BASELINE, f'新文件 {rel} 不应有 BASELINE 条目，应走 NEW_FILE_LIMITS'
        m = guard.collect_metrics(path)
        for metric, limit in guard.NEW_FILE_LIMITS.items():
            assert m[metric] <= limit, f'新文件 {rel} 的 {metric} = {m[metric]} 超过新增上限 {limit}'


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
    monkeypatch.setattr(guard, 'LEGACY_VIEWS', {'backend/app/domains/x/views.py'})

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


def test_guard_hints_loose_baseline(tmp_path, monkeypatch, capsys):
    """防基线虚胖：实测低于基线时必须提示回写，但**不报错**（正常收敛不该红掉校验）。"""
    guard = _load_guard()
    thin = tmp_path / 'views.py'
    thin.write_text('def thin(db):\n    db.commit()\n', encoding='utf-8')

    monkeypatch.setattr(guard, '_iter_views', lambda: [thin])
    monkeypatch.setattr(guard, '_rel', lambda path: 'backend/app/domains/x/views.py')
    monkeypatch.setattr(
        guard,
        'BASELINE',
        {'backend/app/domains/x/views.py': {'lines': 50, 'orm_queries': 5, 'commits': 9, 'max_func': 60}},
    )
    monkeypatch.setattr(guard, 'LEGACY_VIEWS', {'backend/app/domains/x/views.py'})

    assert guard.main([]) == 0
    captured = capsys.readouterr()
    assert '收紧 BASELINE' in captured.out
    assert 'commits = 1' in captured.out
    assert captured.err == ''


def test_baseline_matches_current_metrics():
    """基线与实测必须**贴合**（不是「不超过」）：`commits` 维度已在 #1609 batch 2/3/4 收敛
    （44 → 3），基线若不回写，「只减不增」在这一维度就是空转（#1606 复核发现：把 `flush`
    改回 `commit` 不会被拦）。收敛后请在同 PR 内 `python scripts/check_view_thickness.py
    --report` 回写 BASELINE——基线**调大**仍会由本用例拦下（守卫生效的唯一方式）。"""
    guard = _load_guard()
    measured = {guard._rel(p): guard.collect_metrics(p) for p in guard._iter_views()}
    for rel, m in measured.items():
        if rel not in guard.BASELINE:
            continue  # 新文件不在基线内，已由 NEW_FILE_LIMITS 覆盖
        for metric, budget in guard.BASELINE[rel].items():
            assert m[metric] <= budget, f'{rel} 的 {metric} = {m[metric]} 超过基线 {budget}（变厚）'
            assert m[metric] == budget, f'{rel} 的 {metric} = {m[metric]} 低于基线 {budget}，请用 --report 收紧基线'


def test_guard_blocks_new_file_with_fat_baseline_entry(tmp_path, monkeypatch, capsys):
    """灵敏度（防 gaming / 反例）：新文件即便在 BASELINE 塞了 fat 条目（如 500 行），
    也必须被 NEW_FILE_LIMITS 拦下——证明「给新文件开后门」这条路被堵死。"""
    guard = _load_guard()
    fat = tmp_path / 'views.py'
    fat.write_text(
        'def thick(db):\n' + '\n'.join(f'    x{i} = db.query({i})' for i in range(20)) + '\n',
        encoding='utf-8',
    )

    monkeypatch.setattr(guard, '_iter_views', lambda: [fat])
    monkeypatch.setattr(guard, '_rel', lambda path: 'backend/app/domains/brandnew/views.py')
    monkeypatch.setattr(guard, 'LEGACY_VIEWS', frozenset())  # 不在冻结集 → 视为新文件
    monkeypatch.setattr(
        guard,
        'BASELINE',
        {'backend/app/domains/brandnew/views.py': {'lines': 500, 'orm_queries': 20, 'commits': 0, 'max_func': 200}},
    )

    assert guard.main([]) == 1
    captured = capsys.readouterr()
    assert '新增上限' in captured.err  # 被 NEW_FILE_LIMITS 拦，而非被（fat）基线放过
    assert '500' not in captured.err  # fat 基线条目未生效


def test_guard_allows_new_file_under_limits(tmp_path, monkeypatch, capsys):
    """灵敏度（防过度抑制 / 正例）：压在 NEW_FILE_LIMITS 内的新文件必须放行。"""
    guard = _load_guard()
    ok = tmp_path / 'views.py'
    ok.write_text('def thin(db):\n    return db.query(1)\n', encoding='utf-8')

    monkeypatch.setattr(guard, '_iter_views', lambda: [ok])
    monkeypatch.setattr(guard, '_rel', lambda path: 'backend/app/domains/brandnew/views.py')
    monkeypatch.setattr(guard, 'LEGACY_VIEWS', frozenset())
    monkeypatch.setattr(guard, 'BASELINE', {})

    assert guard.main([]) == 0
    captured = capsys.readouterr()
    assert captured.err == ''
