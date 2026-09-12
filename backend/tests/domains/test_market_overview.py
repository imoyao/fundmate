# -*- coding: utf-8 -*-
"""探市·大类资产观察 service 单测（#1436 / #1444 收口实现）。

不依赖真实网络 / akshare：用假 akshare 模块替换 app.core.akshare_lazy.get_akshare，
验证：
1. 可取数资产能算出 change_pct 与相对位置分位；
2. 任一取数失败 → 该资产降级为软占位（available=false + reason），整体不崩；
3. 离岸人民币 USDCNH 走 currency_boc_sina 在岸替代口径（available + caliber 标注）；
4. 整体返回 20 资产、6 个软占位、债券收益率轨 best-effort 解析。
"""

import pandas as pd
import pytest

from app.services import market_service
from app.services.market_service import MarketOverviewService


def _make_series_df(n: int = 520, base: float = 3000.0, kind: str = 'stock'):
    """构造 (date, close) 的假 DataFrame。"""
    import numpy as np

    dates = pd.date_range('2024-01-01', periods=n, freq='D').strftime('%Y-%m-%d')
    # 用正弦 + 趋势，保证分位可计算且非平凡
    xs = np.linspace(0, 6 * np.pi, n)
    closes = base + 50 * np.sin(xs) + np.linspace(0, 150, n)
    if kind == 'currency':
        # 汇率口径：中行折算价列
        return pd.DataFrame({'日期': dates, '中行折算价': closes / 400.0})
    return pd.DataFrame({'date': dates, 'close': closes})


class FakeAk:
    """假 akshare：所有已用 source 返回合理假 DataFrame。"""

    def stock_zh_index_daily(self, *args):
        return _make_series_df()

    def stock_hk_index_daily_sina(self, *args):
        return _make_series_df(base=18000.0)

    def index_us_stock_sina(self, *args):
        return _make_series_df(base=4500.0)

    def fund_etf_hist_sina(self, *args):
        return _make_series_df(base=110.0)

    def futures_main_sina(self, *args):
        return _make_series_df(base=400.0)

    def stock_us_daily(self, *args):
        return _make_series_df(base=95.0)

    def currency_boc_sina(self, *args):
        return _make_series_df(kind='currency')

    def bond_zh_us_rate(self, *args, **kwargs):
        # 真实 akshare 签名支持 start_date；服务层传它以避免「不传则翻 19 页拉全历史」（#1461）。
        # 故假实现必须接受关键字参数，否则会 FakeAk.bond_zh_us_rate() 报 unexpected kwarg。
        dates = pd.date_range('2024-01-01', periods=520, freq='D').strftime('%Y-%m-%d')
        return pd.DataFrame(
            {
                '日期': dates,
                '中国国债收益率10年': [1.85 + 0.001 * i for i in range(520)],
                '美国国债收益率10年': [4.12 - 0.0008 * i for i in range(520)],
            }
        )


class FakeAkRaiseOnCurrency(FakeAk):
    """currency_boc_sina 抛异常，验证汇率类资产降级。"""

    def currency_boc_sina(self, *args):
        raise ConnectionError('东财通道不可达（模拟）')


@pytest.fixture
def patch_akshare(monkeypatch):
    monkeypatch.setattr(market_service, 'get_akshare', lambda: FakeAk())


def _find(overview, name):
    for g in overview['groups']:
        for a in g['assets']:
            if a['name'] == name:
                return a
    return None


def test_overview_structure_and_available(patch_akshare):
    ov = MarketOverviewService.get_overview(force_refresh=True)
    # 20 资产
    total = sum(len(g['assets']) for g in ov['groups'])
    assert total == 20, f'应有 20 资产，实际 {total}'
    # 6 个软占位（建账配置的 available=False）
    assert ov['unavailable_count'] == 6, ov['unavailable_count']
    # 分组顺序与数量
    cats = [g['category'] for g in ov['groups']]
    assert cats == ['A股', '港股', '海外', '债券', '商品', '汇率']

    # 可取数资产：上证指数
    sh = _find(ov, '上证指数')
    assert sh['available'] is True
    assert sh['change_pct'] is not None
    assert sh['position'] is not None
    assert 0 <= sh['position']['percentile'] <= 100
    assert sh['position']['basis'] == '价格分位'


def test_cnh_onshore_substitute(patch_akshare):
    ov = MarketOverviewService.get_overview(force_refresh=True)
    cnh = _find(ov, '离岸人民币')
    assert cnh['available'] is True
    assert cnh['caliber'] and '在岸' in cnh['caliber']
    assert cnh['change_pct'] is not None


def test_bitcoin_placeholder(patch_akshare):
    ov = MarketOverviewService.get_overview(force_refresh=True)
    btc = _find(ov, '比特币')
    assert btc['available'] is False
    assert btc['reason']


def test_fetch_failure_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(market_service, 'get_akshare', lambda: FakeAkRaiseOnCurrency())
    ov = MarketOverviewService.get_overview(force_refresh=True)
    # 汇率类（美元指数 + 离岸人民币）应降级为软占位，但整体仍返回 20 项
    usd = _find(ov, '美元指数')
    cnh = _find(ov, '离岸人民币')
    assert usd['available'] is False and usd['reason']
    assert cnh['available'] is False and cnh['reason']
    total = sum(len(g['assets']) for g in ov['groups'])
    assert total == 20  # 不丢资产，仅降级


def test_bond_yield_parsed(patch_akshare):
    ov = MarketOverviewService.get_overview(force_refresh=True)
    by = ov['bond_yield']
    assert by is not None
    assert by['cn_10y'] is not None
    assert by['us_10y'] is not None
    # 中债 10Y 末值 = 1.85 + 0.001*519 = 2.369
    assert abs(by['cn_10y'] - 2.369) < 0.01


def test_bond_yield_passes_start_date(monkeypatch):
    """#1461：`bond_zh_us_rate` 必须带 `start_date`。

    不传时 akshare 会翻 19 页拉全历史（≈9500 行 / ~29s），是 `/api/market/overview`
    首屏超时的主因。此断言锁住该修复，避免回退成全量翻页。
    """
    fake = FakeAk()
    captured: dict = {}

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return fake.bond_zh_us_rate(*args, **kwargs)

    monkeypatch.setattr(fake, 'bond_zh_us_rate', spy)
    monkeypatch.setattr(market_service, 'get_akshare', lambda: fake)

    MarketOverviewService.get_overview(force_refresh=True)

    assert captured.get('start_date'), '未给 bond_zh_us_rate 传 start_date：会退化为全量翻页（~29s），首屏仍会超时'
