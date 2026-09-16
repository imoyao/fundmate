# -*- coding: utf-8 -*-
"""#1431：baostock 辅助函数的离线用例（不打网络）。

覆盖两件事：
1. `_is_index_code` 的指数 / 个股判定（回补时用于过滤无 pbMRQ 的指数）；
2. `bao_industry_map` / `bao_backfill_pb` 的迭代方式已修正为
   `while rs.next(): rs.get_row_data()` —— baostock 的 `next()` 返回 **bool**，
   原实现会把 bool 当行数据（必抛 `TypeError`，该路径因此从未成功执行）。
"""

import pytest

from app.services.thermometer import industry_crowding as ic


class TestIsIndexCode:
    @pytest.mark.parametrize('code', ['sh.000001', 'sh.000300', 'sh.950001', 'sh.880001', 'sz.399001'])
    def test_index_codes(self, code):
        assert ic._is_index_code(code) is True

    @pytest.mark.parametrize('code', ['sh.600000', 'sz.000001', 'sz.300750', 'bj.430047'])
    def test_stock_codes(self, code):
        assert ic._is_index_code(code) is False

    def test_malformed_is_treated_as_index(self):
        assert ic._is_index_code('600000') is True


class _FakeRS:
    """模拟 baostock 结果集：`next()` 返回 bool，行数据用 `get_row_data()` 取。"""

    def __init__(self, rows):
        self._rows = list(rows)
        self._index = -1

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


@pytest.fixture
def _baostock_offline(tmp_path, monkeypatch):
    """把 baostock 登录/登出替换成空操作，缓存目录指向用例私有目录（不打网络、不落真实缓存）。

    #1539：缓存目录由模块级常量改为**调用期**解析 env `CACHE_FILE_DIR`
    （`ic.baostock_cache_dir()` → `<CACHE_FILE_DIR>/baostock_pb`），故这里只设 env。
    """
    monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
    monkeypatch.setattr(ic.bs, 'login', lambda *a, **k: None)
    monkeypatch.setattr(ic.bs, 'logout', lambda *a, **k: None)


class TestBaostockIteration:
    def test_industry_map_reads_row_data(self, _baostock_offline, monkeypatch):
        """列序 updateDate/code/code_name/industry/industryClassification：取 row[1] 与 row[3]。"""
        rows = [
            ['2026-09-14', 'sh.600000', '浦发银行', 'J66', ''],
            ['2026-09-14', 'sh.600036', '招商银行', 'J66', ''],
            ['2026-09-14', 'sh.600001', '', '', ''],
        ]
        monkeypatch.setattr(ic.bs, 'query_stock_industry', lambda *a, **k: _FakeRS(rows))
        mapping = ic.bao_industry_map()
        assert mapping == {'sh.600000': 'J66', 'sh.600036': 'J66'}

    def test_industry_map_reads_cache_second_call(self, _baostock_offline, monkeypatch):
        calls = {'n': 0}

        def _query(*a, **k):
            calls['n'] += 1
            return _FakeRS([['2026-09-14', 'sh.600000', '', 'J66', '']])

        monkeypatch.setattr(ic.bs, 'query_stock_industry', _query)
        first = ic.bao_industry_map()
        second = ic.bao_industry_map()
        assert first == second == {'sh.600000': 'J66'}
        assert calls['n'] == 1  # 第二次命中 json 缓存

    def test_backfill_filters_index_codes(self, _baostock_offline, monkeypatch):
        all_stock = [
            ['sh.000001', '1', '上证指数'],
            ['sh.600000', '1', '浦发银行'],
            ['sz.399001', '1', '深证成指'],
        ]
        queried = []

        def _fake_k(code, fields, **kwargs):
            queried.append(code)
            return _FakeRS([['2026-09-11', '0.5']])

        monkeypatch.setattr(ic.bs, 'query_all_stock', lambda *a, **k: _FakeRS(all_stock))
        monkeypatch.setattr(ic.bs, 'query_history_k_data_plus', _fake_k)
        # 环境可能无 parquet 引擎（pyarrow / fastparquet）：落盘替身，聚焦"迭代与过滤"这一修复点
        monkeypatch.setattr(ic.pd.DataFrame, 'to_parquet', lambda self, path, **kw: None)
        monkeypatch.setattr(ic.pd.DataFrame, 'to_csv', lambda self, path, **kw: None)
        ic.bao_backfill_pb(start='2026-01-01', end='2026-09-11')
        assert queried == ['sh.600000']  # 两个指数被过滤，仅回补个股

    def test_backfill_skips_existing_cache(self, _baostock_offline, monkeypatch):
        from pathlib import Path

        cache_dir = Path(ic.baostock_cache_dir())
        cache_dir.mkdir(parents=True, exist_ok=True)
        f = cache_dir / 'sh_600000.parquet'
        f.write_bytes(b'dummy')
        queried = []

        def _fake_k(code, fields, **kwargs):
            queried.append(code)
            return _FakeRS([['2026-09-11', '0.5']])

        monkeypatch.setattr(ic.bs, 'query_all_stock', lambda *a, **k: _FakeRS([['sh.600000', '1', '浦发银行']]))
        monkeypatch.setattr(ic.bs, 'query_history_k_data_plus', _fake_k)
        ic.bao_backfill_pb(start='2026-01-01', end='2026-09-11')
        assert queried == []  # 已有缓存 → 跳过请求（增量友好）
