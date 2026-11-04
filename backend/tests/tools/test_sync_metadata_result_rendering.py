# -*- coding: utf-8 -*-
"""`pdm run sync` 的结果渲染（2026-10-22 实测回归）。

案发形态：`pdm run sync --job bias` 把 37 个品种**全部算完、落库 37 条**，
最后一行却是 `AttributeError: 'dict' object has no attribute 'success'`，exit 1。
根因不在 job，而在渲染：调用点按对象属性读 `result.success` / `result.message` /
`result.duration_ms`，而 `run_job` 返回的是 dict。`--all` 路径更早一步错——
`run_all_jobs` 返回 `{job_name: result}` 字典，旧代码却按列表遍历。

为什么这类 bug 值得单独钉：它**只在任务成功之后**才炸，所以「任务白跑了」与
「任务跑成功但命令报失败」在观感上完全一样；而 `sync_logs` 里是 success，
两边不一致时，人只会相信自己看到的那个红叉。

本文件两层判据：
- 纯函数层：`render_job_result` 对「成功 / 失败 / 缺可选键」的输出；
- 调用点层：真的走一遍 `main()`（外部依赖全替掉），确保**渲染真的接到了这两条路径上**
  ——只测纯函数挡不住「调用点改回属性访问」。
"""

import sys
from unittest.mock import MagicMock

import pytest

from app.tools import sync_metadata

SUCCESS_RESULT = {
    'job_name': 'bias',
    'status': 'success',
    'stats': {'total': 37, 'success': 37, 'skipped': 0, 'failed': 0, 'errors': []},
    'retry_count': 0,
    'duration': 108.3,
}

FAILED_RESULT = {
    'job_name': 'bias',
    'status': 'failed',
    'stats': {'total': 37, 'success': 0, 'skipped': 0, 'failed': 37, 'errors': [{'item_code': '801010'}]},
    'retry_count': 3,
    'duration': 210.0,
}

ALL_FAILED_RESULT = {
    'job_name': 'temperature',
    'status': 'error',
    'error': '上游接口 500',
    'stats': {},
}


@pytest.fixture
def install_orchestrator(monkeypatch):
    """把 `main()` 的外部依赖全部替掉，只留「解析参数 → 渲染结果」这段被测逻辑。"""
    db_cm = MagicMock()
    db_cm.__enter__.return_value = MagicMock(name='session')
    db_cm.__exit__.return_value = False

    monkeypatch.setattr(sync_metadata, 'init_db', lambda *a, **k: None)
    monkeypatch.setattr(sync_metadata, 'ensure_fund_sync_fields', lambda db: None)
    monkeypatch.setattr(sync_metadata, 'get_db', lambda: db_cm)
    monkeypatch.setattr(sync_metadata, 'app_db_startup_check', lambda strict=False: None)
    monkeypatch.setattr(sync_metadata, 'resolve_app_db', lambda env: ('sqlite:///./test.db', 'test'))

    def install(orch):
        monkeypatch.setattr(sync_metadata, 'DataSyncOrchestrator', lambda db: orch)
        return orch

    return install


class TestRenderJobResult:
    def test_success_renders_check_and_counts(self):
        mark, detail, ok = sync_metadata.render_job_result(SUCCESS_RESULT)

        assert ok is True
        assert mark == '✅'
        assert 'total=37' in detail
        assert 'success=37' in detail
        # 失败数为 0 时不啰嗦（否则每行都挂一个 failed=0，噪声）
        assert 'failed=' not in detail
        assert detail.endswith('108.3s')

    def test_failed_renders_cross_and_failed_count(self):
        mark, detail, ok = sync_metadata.render_job_result(FAILED_RESULT)

        assert ok is False
        assert mark == '❌'
        assert 'failed=37' in detail

    def test_minimal_dict_does_not_raise(self):
        """缺 stats / duration / job_name 的降级行（审计二次失败时只写最小字段）也要能渲染。"""
        mark, detail, ok = sync_metadata.render_job_result(ALL_FAILED_RESULT)

        assert ok is False
        assert 'error=上游接口 500' in detail
        # 没有 duration 就不编一个出来
        assert not detail.endswith('s')


class TestCliSingleJobRendering:
    def test_success_exits_zero(self, install_orchestrator, monkeypatch, capsys):
        """判据本体：任务成功 ⇒ 命令必须以 exit 0 收尾（旧代码在这里 exit 1）。"""
        orch = MagicMock()
        orch.run_job.return_value = dict(SUCCESS_RESULT)
        install_orchestrator(orch)
        monkeypatch.setattr(sys, 'argv', ['sync', '--job', 'bias'])

        result = sync_metadata.main()

        assert result is None  # 正常返回，模块级 `raise SystemExit(main() or 0)` ⇒ 0
        out = capsys.readouterr().out
        assert '✅ bias' in out
        assert 'total=37' in out

    def test_failed_exits_one(self, install_orchestrator, monkeypatch, capsys):
        orch = MagicMock()
        orch.run_job.return_value = dict(FAILED_RESULT)
        install_orchestrator(orch)
        monkeypatch.setattr(sys, 'argv', ['sync', '--job', 'bias'])

        with pytest.raises(SystemExit) as excinfo:
            sync_metadata.main()

        assert excinfo.value.code == 1
        assert '❌ bias' in capsys.readouterr().out


class TestCliAllJobsRendering:
    def test_all_iterates_result_dict(self, install_orchestrator, monkeypatch, capsys):
        """`run_all_jobs` 返回 `{job_name: result}` 字典；按列表遍历会拿到字符串键。"""
        orch = MagicMock()
        orch.run_all_jobs.return_value = {
            'bias': dict(SUCCESS_RESULT),
            'temperature': dict(ALL_FAILED_RESULT),
        }
        install_orchestrator(orch)
        monkeypatch.setattr(sys, 'argv', ['sync', '--all'])

        with pytest.raises(SystemExit) as excinfo:
            sync_metadata.main()

        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert '✅ bias' in out
        assert '❌ temperature' in out

    def test_all_success_exits_zero(self, install_orchestrator, monkeypatch):
        orch = MagicMock()
        orch.run_all_jobs.return_value = {
            'bias': dict(SUCCESS_RESULT),
            'temperature': dict(SUCCESS_RESULT, job_name='temperature'),
        }
        install_orchestrator(orch)
        monkeypatch.setattr(sys, 'argv', ['sync', '--all'])

        assert sync_metadata.main() is None
