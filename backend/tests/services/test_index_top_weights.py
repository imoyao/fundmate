# -*- coding: utf-8 -*-
"""指数十大权重（#2278 · 详情页指数区块）。

重点覆盖四件事：
1. **降序取前 N**：源侧返回**不是**权重降序（实测首行 1.266 而最大 9.218 在后），
   必须自行排序——排序错会让「十大权重」展示成「前十行」；
2. **口径**：as_of 取源侧日期列（月频滞后数据）、top_sum 前 N 合计、total_count 全成分数；
3. **缓存纪律**：成功进 12h TTL 缓存；空结果/源异常**不进缓存**（下次重试）；
4. **脏数据不编数**：权重非数值的行丢弃，全部坏行 → None。

akshare 入口在本文件打桩——单测不联网（真机 931151 → 50 行 / 000300 → 300 行
的实测见模块 docstring 与 #2278 卡面）。
"""

import pandas as pd
import pytest

from app.services import index_top_weights as itw
from app.services.index_top_weights import _pick_rows, fetch_top_weights


def _fake_df(rows, columns=None):
    """按源侧实测列构造 DataFrame（日期 / 指数代码 / 指数名称 / 成分券代码 / 成分券名称 / 交易所 / 权重）。"""
    cols = columns or ['日期', '指数代码', '指数名称', '成分券代码', '成分券名称', '交易所', '权重']
    return pd.DataFrame(rows, columns=cols)


def _row(code, name, weight, day='2026-09-30'):
    return [day, '931151', '中证A500', code, name, '上交所', weight]


# ── _pick_rows（纯转换）───────────────────────────────────────────────
def test_pick_rows_sorts_desc_takes_top_n():
    """源侧乱序 → 按权重降序取前 N（锁定「排序」这个最容易漏的动作）。"""
    # 故意把最大权重放最后（复刻真机实测形态）
    df = _fake_df(
        [
            _row('600089', '特变电工', 1.266),
            _row('600519', '贵州茅台', 9.218),
            _row('601318', '中国平安', 1.32),
            _row('600036', '招商银行', 3.84),
        ]
    )
    out = _pick_rows(df, top_n=3)

    assert out['as_of'] == '2026-09-30'
    assert [r['symbol'] for r in out['rows']] == ['600519', '600036', '601318']
    assert out['rows'][0] == {'symbol': '600519', 'name': '贵州茅台', 'weight': 9.218}
    assert out['top_sum'] == pytest.approx(9.218 + 3.84 + 1.32, abs=1e-9)
    assert out['total_count'] == 4  # 全成分数，不是前 N 数


def test_pick_rows_keeps_all_when_fewer_than_n():
    df = _fake_df([_row('600519', '贵州茅台', 9.2), _row('600036', '招商银行', 3.8)])
    out = _pick_rows(df, top_n=10)

    assert len(out['rows']) == 2
    assert out['total_count'] == 2
    assert out['top_sum'] == pytest.approx(13.0, abs=1e-9)


def test_pick_rows_skips_non_numeric_weight():
    """坏行丢弃不编数；好行照常。"""
    df = _fake_df(
        [
            _row('600519', '贵州茅台', 9.2),
            _row('600000', '坏行', 'n/a'),
            _row('600036', '招商银行', 3.8),
        ]
    )
    out = _pick_rows(df, top_n=10)

    assert [r['symbol'] for r in out['rows']] == ['600519', '600036']
    assert out['total_count'] == 2


def test_pick_rows_missing_columns_empty():
    """列名对不上（源侧改版）→ 空 dict，上层降级 None。"""
    df = pd.DataFrame({'日期': ['2026-09-30'], '权重': [1.0]})
    assert _pick_rows(df, top_n=10) == {}


def test_pick_rows_empty_df_empty():
    assert _pick_rows(_fake_df([]), top_n=10) == {}


# ── fetch_top_weights（缓存 + 降级，打桩 akshare）─────────────────────
class _FakeAK:
    def __init__(self, df=None, exc=None):
        self._df = df
        self._exc = exc
        self.calls = []

    def index_stock_cons_weight_csindex(self, symbol):
        self.calls.append(symbol)
        if self._exc:
            raise self._exc
        return self._df


@pytest.fixture(autouse=True)
def _clear_weights_cache():
    itw._weights_cache.clear()
    yield
    itw._weights_cache.clear()


def test_fetch_success_and_cache(monkeypatch):
    ak = _FakeAK(df=_fake_df([_row('600519', '贵州茅台', 9.2), _row('600036', '招商银行', 3.8)]))
    monkeypatch.setattr(itw, 'get_akshare', lambda: ak)

    r1 = fetch_top_weights('931151')
    r2 = fetch_top_weights('SH931151')  # 带前缀形态归一到同一缓存键

    assert r1 is not None
    assert r1['as_of'] == '2026-09-30'
    assert len(r1['rows']) == 2
    assert r2 == r1
    assert ak.calls == ['931151']  # 第二次命中缓存（且归一成裸码调源）


def test_fetch_exception_not_cached(monkeypatch):
    """源异常 → None 且不进缓存（下次重试）。"""
    ak = _FakeAK(exc=RuntimeError('rate limited'))
    monkeypatch.setattr(itw, 'get_akshare', lambda: ak)

    assert fetch_top_weights('931151') is None
    assert '931151' not in itw._weights_cache
    assert fetch_top_weights('931151') is None
    assert len(ak.calls) == 2  # 真的重试了


def test_fetch_empty_result_not_cached(monkeypatch):
    ak = _FakeAK(df=_fake_df([]))
    monkeypatch.setattr(itw, 'get_akshare', lambda: ak)

    assert fetch_top_weights('399006') is None
    assert '399006' not in itw._weights_cache


def test_fetch_blank_symbol_none():
    assert fetch_top_weights('') is None
    assert fetch_top_weights('中证A500') is None
