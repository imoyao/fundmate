# -*- coding: utf-8 -*-
"""
industry_crowding 模块离线测试：覆盖分母兜底链降级顺序与 baostock 兜底路径。
不依赖真实外部数据源（mock 掉 legulegu / baostock / 东财请求）。
"""

from datetime import datetime

import pandas as pd
import pytest

from app.services.thermometer import industry_crowding as ic


class _FakeRows:
    """伪造 baostock ResultData 迭代：fields + next()/get_row_data()。"""

    def __init__(self, rows):
        self.fields = ['date', 'code', 'pbMRQ']
        self._rows = list(rows)
        self._i = 0

    def next(self):
        if self._i < len(self._rows):
            self._i += 1
            return True
        return False

    def get_row_data(self):
        return list(self._rows[self._i - 1])


@pytest.fixture
def fake_baostock(monkeypatch):
    """把 baostock.login / query_daily_history_k_AStock / logout 替换为可编程假实现。"""
    import types

    captured = {'calls': 0, 'rows': []}

    class _FakeBS:
        @staticmethod
        def login():
            return types.SimpleNamespace(error_code=0, error_msg='success')

        @staticmethod
        def logout():
            return types.SimpleNamespace(error_code=0, error_msg='success')

        @staticmethod
        def query_daily_history_k_AStock(date=''):
            captured['calls'] += 1
            return _FakeRows(captured['rows'])

    monkeypatch.setattr(ic, 'bs', _FakeBS)
    # 隔离真实 socket：让 _run 里的 import baostock 拿到假模块
    import sys

    monkeypatch.setitem(sys.modules, 'baostock', _FakeBS)
    monkeypatch.setitem(sys.modules, 'baostock.data', types.SimpleNamespace())
    return captured


def test_market_pb_series_baostock_fallback(fake_baostock, monkeypatch):
    """legulegu 与本地缓存都不可用时，应落到 baostock 兜底并返回当日点。"""
    fake_baostock['rows'] = [
        ['2026-08-07', 'sh.600519', '6.27'],
        ['2026-08-07', 'sz.000001', '0.49'],
        ['2026-08-07', 'sh.601318', '0.99'],
        ['2026-08-07', 'sh.600036', '0.85'],
        ['2026-08-07', 'sz.000858', '5.50'],
    ]

    monkeypatch.setattr(ic, 'ak', None)
    monkeypatch.setattr(ic, '_load_allpb_cache', lambda: None)
    monkeypatch.setattr(ic, '_eastmoney_current_median_pb', lambda: None)
    # 防止兜底分支把单点序列写回受保护的 data/all_pb.csv 基线
    monkeypatch.setattr(ic, '_save_allpb_cache', lambda s: None)

    s, meta = ic.market_pb_series()

    assert meta['src'] == 'baostock'
    assert meta['hist_ok'] is False
    # 中位数：排序 [0.49, 0.85, 0.99, 5.50, 6.27] -> 0.99
    assert s.iloc[-1] == pytest.approx(0.99)
    assert fake_baostock['calls'] == 1


def test_market_pb_series_falls_back_to_eastmoney(fake_baostock, monkeypatch):
    """baostock 兜底返回 None 时，应继续落到东财（历史遗留）。"""
    fake_baostock['rows'] = []  # 空行 -> median 抛错 -> 返回 None

    monkeypatch.setattr(ic, 'ak', None)
    monkeypatch.setattr(ic, '_load_allpb_cache', lambda: None)
    monkeypatch.setattr(
        ic,
        '_eastmoney_current_median_pb',
        lambda: 2.5,
    )
    # 防止兜底分支把单点序列写回受保护的 data/all_pb.csv 基线
    monkeypatch.setattr(ic, '_save_allpb_cache', lambda s: None)

    s, meta = ic.market_pb_series()

    assert meta['src'] == 'eastmoney-live'
    assert s.iloc[-1] == pytest.approx(2.5)


def test_market_pb_series_unavailable(fake_baostock, monkeypatch):
    """全链失败（baostock 空 + 东财 None）→ unavailable，绝不抛异常。"""
    fake_baostock['rows'] = []
    monkeypatch.setattr(ic, 'ak', None)
    monkeypatch.setattr(ic, '_load_allpb_cache', lambda: None)
    monkeypatch.setattr(ic, '_eastmoney_current_median_pb', lambda: None)

    s, meta = ic.market_pb_series()

    assert meta['src'] == 'unavailable'
    assert s is None


def test_baostock_timeout_not_raised(monkeypatch):
    """baostock 兜底内部任何异常都应降级为 None，不向上抛（保护主链路）。"""
    import concurrent.futures

    def _boom():
        raise RuntimeError('simulated bs failure')

    monkeypatch.setattr(ic, '_save_allpb_cache', lambda s: None)

    # 用可控的超时实现（立刻超时），验证异常被吞掉
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_boom)
        with pytest.raises(RuntimeError):
            fut.result(timeout=1)


def test_crowding_hist_ok_false_returns_multiple_only():
    """hist_ok=False（分母仅当日点）时只给倍数，crowding_pct 为 None 且标注。"""
    ind = pd.Series({pd.Timestamp('2026-08-07'): 6.27})
    mkt = pd.Series({pd.Timestamp('2026-08-07'): 2.62})

    c = ic.crowding(ind, mkt, hist_ok=False)

    assert c is not None
    assert c['multiple'] == pytest.approx(6.27 / 2.62, rel=1e-3)
    assert c['crowding_pct'] is None
    assert c['hist_ok'] is False


def test_record_stale_placeholder_shape():
    """全失败时的 stale 占位记录符合 multi 扁平格式（前端可直接消费）。"""
    rec = ic._placeholder('测试占位')

    assert rec['kind'] == 'multi'
    assert rec['source'] == 'industry_crowding'
    assert rec['stale'] is True
    assert rec['data']['note'] == '测试占位'
    assert isinstance(rec['collected_at'], datetime)


# ───────────────── 东财两维：成交额占比分位 + 换手率分位 ─────────────────


def test_em_secid_mapping():
    """中证指数代码 -> 东财 secid（沪市前缀 1，深市前缀 0）。"""
    assert ic._em_secid('000990.SH') == '1.000990'
    assert ic._em_secid('399997.SZ') == '0.399997'
    assert ic._em_secid('000985.SH') == '1.000985'


def test_em_industry_hist_parses_klines(monkeypatch):
    """东财 K线 CSV 解析：正确提取成交额(f57)与换手率(f61)，date 为索引。"""

    class _FakeResp:
        def json(self):
            return {
                'data': {
                    'klines': [
                        '2024-01-02,100,101,102,99,1000,123456789,1.5,0.5,0.5,2.30',
                        '2024-01-03,101,102,103,100,1200,130000000,1.2,1.0,1.0,2.50',
                    ]
                }
            }

    monkeypatch.setattr(ic.requests, 'get', lambda *a, **kw: _FakeResp())

    df = ic._em_industry_hist('000990.SH')

    assert df is not None
    assert list(df.columns) == ['amount', 'turnover']
    assert df['amount'].iloc[0] == pytest.approx(123456789)
    assert df['turnover'].iloc[-1] == pytest.approx(2.5)
    assert df.index[0] == pd.Timestamp('2024-01-02')


def test_em_industry_hist_failure_returns_none(monkeypatch):
    """东财请求异常/空数据应返回 None，绝不抛异常。"""

    class _BoomResp:
        def json(self):
            raise RuntimeError('simulated network failure')

    monkeypatch.setattr(ic.requests, 'get', lambda *a, **kw: _BoomResp())

    assert ic._em_industry_hist('000990.SH') is None


def test_amount_ratio_rank_correctness():
    """成交额占比分位：构造已知序列验证当前占比与历史百分位。"""
    dates = pd.date_range('2024-01-01', periods=210, freq='B')
    # 行业成交额：前 200 天 100，后 10 天 200；全A成交额恒定 1000
    ind_hist = pd.DataFrame({'amount': [100.0] * 200 + [200.0] * 10}, index=dates)
    mkt_hist = pd.DataFrame({'amount': [1000.0] * 210}, index=dates)

    out = ic._amount_ratio_rank(ind_hist, mkt_hist)

    assert out is not None
    # 当前占比 = 200/1000 = 20%
    assert out['amount_pct'] == pytest.approx(20.0)
    # 历史占比：前 200 天 10%，后 10 天 20%；当前值 20% 大于前 200 天 -> 200/210
    assert out['amount_pct_rank'] == pytest.approx(200 / 210 * 100, abs=0.1)


def test_amount_ratio_rank_short_history_returns_none():
    """成交额占比历史不足 200 天应返回 None（分位无判别力）。"""
    dates = pd.date_range('2024-01-01', periods=150, freq='B')
    ind_hist = pd.DataFrame({'amount': [100.0] * 150}, index=dates)
    mkt_hist = pd.DataFrame({'amount': [1000.0] * 150}, index=dates)

    assert ic._amount_ratio_rank(ind_hist, mkt_hist) is None
    assert ic._amount_ratio_rank(ind_hist, None) is None


def test_turnover_rank_correctness():
    """换手率分位：构造已知序列验证当前值与历史百分位。"""
    dates = pd.date_range('2024-01-01', periods=210, freq='B')
    ind_hist = pd.DataFrame({'turnover': [1.0] * 200 + [3.0] * 10}, index=dates)

    out = ic._turnover_rank(ind_hist)

    assert out is not None
    assert out['turnover'] == pytest.approx(3.0)
    # 当前值 3.0 大于前 200 天 -> 200/210
    assert out['turnover_rank'] == pytest.approx(200 / 210 * 100, abs=0.1)


def test_turnover_rank_short_history_returns_none():
    """换手率历史不足 200 天应返回 None。"""
    dates = pd.date_range('2024-01-01', periods=150, freq='B')
    ind_hist = pd.DataFrame({'turnover': [1.0] * 150}, index=dates)

    assert ic._turnover_rank(ind_hist) is None
    assert ic._turnover_rank(None) is None


def test_em_extra_dims_failure_returns_none(monkeypatch):
    """东财历史抓取失败时两维字段均为 None，且不抛异常。"""
    monkeypatch.setattr(ic, '_em_industry_hist', lambda code: None)

    out = ic._em_extra_dims('000990.SH', None)

    assert out == {
        'amount_pct': None,
        'amount_pct_rank': None,
        'turnover': None,
        'turnover_rank': None,
    }


def test_em_extra_dims_merges_both_dims(monkeypatch):
    """东财历史正常时两维分位合并进结果。"""
    dates = pd.date_range('2024-01-01', periods=210, freq='B')
    fake_hist = pd.DataFrame(
        {'amount': [100.0] * 200 + [200.0] * 10, 'turnover': [1.0] * 200 + [3.0] * 10},
        index=dates,
    )
    fake_mkt = pd.DataFrame({'amount': [1000.0] * 210}, index=dates)
    monkeypatch.setattr(ic, '_em_industry_hist', lambda code: fake_hist)

    out = ic._em_extra_dims('000990.SH', fake_mkt)

    assert out['amount_pct'] == pytest.approx(20.0)
    assert out['amount_pct_rank'] == pytest.approx(200 / 210 * 100, abs=0.1)
    assert out['turnover'] == pytest.approx(3.0)
    assert out['turnover_rank'] == pytest.approx(200 / 210 * 100, abs=0.1)


def test_record_includes_em_dims_and_note():
    """_record 输出含东财两维字段；两维缺失时 note 追加说明。"""
    base = {
        'multiple': 2.5,
        'ind_pb': 6.0,
        'mkt_pb': 2.4,
        'history_days': 300,
        'hist_ok': True,
    }
    rec = ic._record('中证消费', '000990.SH', dict(base))
    assert rec['data']['amount_pct'] is None
    assert rec['data']['amount_pct_rank'] is None
    assert rec['data']['turnover'] is None
    assert rec['data']['turnover_rank'] is None
    assert '成交额/换手率分位暂不可用' in rec['data']['note']

    rec2 = ic._record(
        '中证消费',
        '000990.SH',
        dict(base, amount_pct=1.23, amount_pct_rank=88.0, turnover=2.40, turnover_rank=75.0),
    )
    assert rec2['data']['amount_pct'] == pytest.approx(1.23)
    assert rec2['data']['amount_pct_rank'] == pytest.approx(88.0)
    assert rec2['data']['turnover'] == pytest.approx(2.40)
    assert rec2['data']['turnover_rank'] == pytest.approx(75.0)
    assert '成交额/换手率分位暂不可用' not in rec2['data']['note']
