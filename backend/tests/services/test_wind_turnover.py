# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/25
# File : test_wind_turnover.py
"""申万一级行业换手率 · Wind EDB 源（#1502 步骤 1）。

本文件钉住四条契约（对应触达的四种失败形态）：

1. **未配置**（``is_available()`` 假）是「可选组件缺失」，不是故障——不请求上游、
   有缓存就回缓存、没缓存回 ``None``，绝不抛异常阻塞温度计主链路；
2. **增量**：已有缓存但过期时，只从「缓存最后一天 +1」拉到今天（不重拉全历史）；
3. **上游故障**回**已有的（可能 stale）缓存**——宁可分位旧一点，也不让整块温度计
   因为一条支路失败而缺数据；
4. **分位口径**与 ``industry_crowding._turnover_rank`` 一致（同公式、同 200 天下限），
   且指标名走精确口径 ``换手率:申万行业指数:{name}``（含糊问题会混口径，见
   ``adapters/wind_edb.py`` 模块头）。

缓存落盘目录由 conftest 的 autouse 隔离夹具（``CACHE_FILE_DIR``）重定向到用例私有
目录，故这些用例不打网络、不污染真实缓存。
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.thermometer import wind_turnover as wt

_CODE = '801010'
_NAME = '农林牧渔'
_INDICATOR = '换手率:申万行业指数:农林牧渔'


def _series(days: int, *, end: date | None = None, value: float = 1.0) -> dict:
    """构造 ``{date: turnover}`` 形态的 EDB 返回（升序，不含周末无关紧要）。"""
    last = end or date.today()
    return {last - timedelta(days=days - 1 - i): value for i in range(days)}


def _seed_cache(days: int, *, end: date, last_value: float = 1.0) -> pd.DataFrame:
    """预置一份缓存文件（模拟「上一轮跑过、已经过期」的现场）。"""
    df = pd.DataFrame(
        {'turnover': [last_value] * days},
        index=pd.to_datetime([end - timedelta(days=days - 1 - i) for i in range(days)]),
    )
    df.index.name = 'date'
    wt._save_cache(_CODE, df)
    return df


class TestUnavailablePath:
    def test_unconfigured_returns_none_without_calling_upstream(self, monkeypatch):
        """未配置：不请求上游、无缓存回 None（可选组件缺失不该刷 warning）。"""
        calls: list = []
        monkeypatch.setattr(wt, 'is_available', lambda: False)
        monkeypatch.setattr(wt, 'fetch_edb_series', lambda *a, **k: calls.append(a) or {})

        assert wt.wind_turnover_hist(_CODE, _NAME) is None
        assert calls == [], '未配置时不应发起任何取数请求'

    def test_unconfigured_still_returns_existing_cache(self, monkeypatch, tmp_path):
        """未配置但有历史缓存：回缓存（数据仍有价值，不必因缺配置而丢）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        seeded = _seed_cache(210, end=date.today() - timedelta(days=30))
        monkeypatch.setattr(wt, 'is_available', lambda: False)

        out = wt.wind_turnover_hist(_CODE, _NAME)

        assert out is not None
        assert len(out) == len(seeded)


class TestIncrementalFetch:
    def test_incremental_fetch_starts_after_cached_date(self, monkeypatch, tmp_path):
        """过期缓存只拉增量：begin = 缓存最后一天 + 1（不重拉全历史）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        last = date.today() - timedelta(days=10)
        _seed_cache(210, end=last)
        seen: list = []

        def _fake(indicator: str, begin: date, end: date) -> dict:
            seen.append((indicator, begin, end))
            return _series(5)

        monkeypatch.setattr(wt, 'is_available', lambda: True)
        monkeypatch.setattr(wt, 'fetch_edb_series', _fake)

        wt.wind_turnover_hist(_CODE, _NAME)

        assert len(seen) == 1
        indicator, begin, _ = seen[0]
        assert indicator == _INDICATOR, '必须走精确指标名，含糊问题会混口径'
        assert begin == last + timedelta(days=1)

    def test_first_run_pulls_full_history_and_writes_cache(self, monkeypatch, tmp_path):
        """首次：从全历史起点拉一次，并落盘（下次直接复用）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        begin_seen: list = []

        def _fake(indicator: str, begin: date, end: date) -> dict:
            begin_seen.append(begin)
            return _series(250)

        monkeypatch.setattr(wt, 'is_available', lambda: True)
        monkeypatch.setattr(wt, 'fetch_edb_series', _fake)

        out = wt.wind_turnover_hist(_CODE, _NAME)

        assert out is not None and len(out) == 250
        assert begin_seen == [wt._FULL_SYNC_BEGIN]
        assert wt._load_cache(_CODE) is not None, '取到数据必须落盘，否则每天重拉全历史'

    def test_fresh_cache_skips_upstream_entirely(self, monkeypatch, tmp_path):
        """缓存新鲜（含今天）：0 次请求。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        _seed_cache(210, end=date.today())
        calls: list = []
        monkeypatch.setattr(wt, 'is_available', lambda: True)
        monkeypatch.setattr(wt, 'fetch_edb_series', lambda *a, **k: calls.append(a) or {})

        wt.wind_turnover_hist(_CODE, _NAME)

        assert calls == []


class TestUpstreamFailure:
    def test_failure_falls_back_to_stale_cache(self, monkeypatch, tmp_path):
        """上游抛异常：回已有缓存，异常不外抛（不阻塞温度计主链路）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        seeded = _seed_cache(210, end=date.today() - timedelta(days=20))

        def _boom(*_a, **_k):
            raise RuntimeError('wind down')

        monkeypatch.setattr(wt, 'is_available', lambda: True)
        monkeypatch.setattr(wt, 'fetch_edb_series', _boom)

        out = wt.wind_turnover_hist(_CODE, _NAME)

        assert out is not None
        assert len(out) == len(seeded)

    def test_empty_series_keeps_cache(self, monkeypatch, tmp_path):
        """上游回空（未取到数据）：保留缓存，不用空结果覆盖。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        seeded = _seed_cache(210, end=date.today() - timedelta(days=20))
        monkeypatch.setattr(wt, 'is_available', lambda: True)
        monkeypatch.setattr(wt, 'fetch_edb_series', lambda *a, **k: {})

        out = wt.wind_turnover_hist(_CODE, _NAME)

        assert out is not None
        assert len(out) == len(seeded)


class TestRank:
    def test_short_history_returns_none(self, monkeypatch, tmp_path):
        """历史不足 200 天：不给分位（与东财路径同下限）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        monkeypatch.setattr(wt, 'is_available', lambda: True)
        monkeypatch.setattr(wt, 'fetch_edb_series', lambda *a, **k: _series(150))

        assert wt.wind_turnover_rank(_CODE, _NAME) is None

    def test_rank_matches_percentile_formula(self, monkeypatch, tmp_path):
        """分位 = 历史中严格小于当前值的占比（当前最高值 ⇒ 100）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        series = _series(200, value=1.0)
        series[max(series)] = 3.0  # 最后一天（最大值）作为当前值
        monkeypatch.setattr(wt, 'is_available', lambda: True)
        monkeypatch.setattr(wt, 'fetch_edb_series', lambda *a, **k: series)

        out = wt.wind_turnover_rank(_CODE, _NAME)

        assert out == {'turnover': 3.0, 'turnover_rank': pytest.approx(199 / 200 * 100, abs=0.1)}

    def test_no_data_returns_none(self, monkeypatch):
        """无任何数据（未配置且无缓存）：None，不抛异常。"""
        monkeypatch.setattr(wt, 'is_available', lambda: False)

        assert wt.wind_turnover_rank(_CODE, _NAME) is None
