# -*- coding: utf-8 -*-
"""探市·大类资产观察 service 单测（#1436 / #1444 收口实现）。

不依赖真实网络 / akshare：用假 akshare 模块替换 app.core.akshare_lazy.get_akshare，
验证：
1. 可取数资产能算出 change_pct 与相对位置分位；
2. 任一取数失败 → 该资产降级为软占位（available=false + reason），整体不崩；
3. 离岸人民币 USDCNH 走 currency_boc_sina 在岸替代口径（available + caliber 标注）；
4. 整体返回 20 资产、6 个软占位、债券收益率轨 best-effort 解析。
"""

from datetime import timedelta

import pandas as pd
import pytest

from app.core.time_utils import now_shanghai
from app.domains.temperature.models import MarketMultiItem
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

    def currency_boc_sina(self, *args, **kwargs):
        # 服务层必须显式传 start_date/end_date（#1460 F6：akshare 该函数的默认区间被
        # 上游硬编码为 20230304~20231110，不传就永远拿到 2023 年那 180 行）。
        # 故假实现必须接受关键字参数，否则会 unexpected kwarg 报错。
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

    def currency_boc_sina(self, *args, **kwargs):
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


def test_currency_boc_sina_passes_explicit_date_range(monkeypatch):
    """#1460 F6 / #1481：`currency_boc_sina` 必须显式传 `start_date` / `end_date`。

    akshare 该函数的默认区间被上游**硬编码为 `20230304`~`20231110`**，只传品种名会
    永远拿到 2023 年那 180 行——页面上「美元指数」「离岸人民币」两张卡会一直展示
    2023 年的「当日涨跌」（2026-09-13 实测发现的现网缺陷）。此断言锁住修复。
    """
    fake = FakeAk()
    captured: dict = {}

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return fake.currency_boc_sina(*args, **kwargs)

    monkeypatch.setattr(fake, 'currency_boc_sina', spy)
    monkeypatch.setattr(market_service, 'get_akshare', lambda: fake)

    MarketOverviewService.get_overview(force_refresh=True)

    assert captured.get('start_date'), '未给 currency_boc_sina 传 start_date：会拿到 akshare 硬编码的 2023 年窗口'
    assert captured.get('end_date'), '未给 currency_boc_sina 传 end_date'
    assert captured['start_date'] < captured['end_date']
    # akshare 硬编码的窗口是 `20230304`~`20231110`；显式传入的值必须不是它。
    # 注意：不能用「不以 2023 开头」判定——近 3 年窗口的起点本就可能落在 2023 年。
    assert captured['start_date'] != '20230304', 'start_date 仍是 akshare 硬编码的 20230304'
    assert captured['end_date'] != '20231110', 'end_date 仍是 akshare 硬编码的 20231110'
    # 近 3 年（≥500 交易日），满足 500 日分位与 250 日 σ 两个窗口
    assert captured['start_date'][:4] <= str(now_shanghai().year - 2)


class TestOverviewSourceSwitch:
    """#1460 方案 B：`live` / `db` 开关、非法值兜底、库空回退。"""

    def test_default_is_live(self, monkeypatch):
        """默认必须是 live —— 保证合并后线上行为与引入落库前完全一致。"""
        monkeypatch.delenv('MARKET_OVERVIEW_SOURCE', raising=False)
        assert MarketOverviewService._source() == 'live'

    def test_invalid_value_falls_back_to_live(self, monkeypatch):
        """配置笔误不该让页面变成静默读陈旧数据的页面。"""
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'mysql')
        assert MarketOverviewService._source() == 'live'

    def test_db_value_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'DB')
        assert MarketOverviewService._source() == 'db'

    def test_empty_db_falls_back_to_live(self, db, monkeypatch, patch_akshare):
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'db')
        ov = MarketOverviewService.get_overview()
        assert ov['data_source'] == 'live'
        assert sum(len(g['assets']) for g in ov['groups']) == 20

    def test_force_refresh_bypasses_db(self, db, monkeypatch, patch_akshare):
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'db')
        ov = MarketOverviewService.get_overview(force_refresh=True)
        assert ov['data_source'] == 'live'

    def test_live_path_reports_live_source(self, patch_akshare):
        ov = MarketOverviewService.get_overview(force_refresh=True)
        assert ov['data_source'] == 'live'
        # 新增的 stale 字段在实时路径下恒为 False
        assert all(a['stale'] is False for g in ov['groups'] for a in g['assets'])


def _add_snapshot(db, *, code, name, collected_at, stale=False, data=None):
    db.add(
        MarketMultiItem(
            source=market_service.SNAPSHOT_SOURCE,
            item_type=market_service.SNAPSHOT_ITEM_TYPE,
            item_code=code,
            item_name=name,
            data=data if data is not None else {'error': 'boom'},
            collected_at=collected_at,
            stale=stale,
        )
    )


def _good_payload(change=1.23, asof='2026-09-13 08:02:11'):
    return {
        'change_pct': change,
        'trade_date': '2026-09-11',
        'data_asof': asof,
        'position': {'percentile': 41.2, 'label': '适中', 'basis': '价格分位', 'window': 500},
        'anomaly': None,
        'caliber': None,
    }


class TestOverviewFromDb:
    """#1460 方案 B：读库路径。"""

    def test_serves_snapshot_and_reports_db_source(self, db, monkeypatch, patch_akshare):
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'db')
        today = now_shanghai().date()
        _add_snapshot(db, code='sh000001', name='上证指数', collected_at=today, data=_good_payload())
        db.commit()

        ov = MarketOverviewService.get_overview()

        assert ov['data_source'] == 'db'
        sh = _find(ov, '上证指数')
        assert sh['available'] is True
        assert sh['change_pct'] == 1.23
        assert sh['stale'] is False
        # 「更新于」显示的是**数据**的取数时刻，不是本次组装时刻（否则谎报新鲜度）
        assert ov['updated_at'] == '2026-09-13 08:02:11'
        # 库里没有的资产 → 软占位，而不是回退实时（避免读库路径静默变慢）
        assert _find(ov, '沪深300')['available'] is False

    def test_stale_row_falls_back_to_last_good(self, db, monkeypatch, patch_akshare):
        """当日行 stale → 回退最近一次成功值，并标 stale 让「今天失败」可见。"""
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'db')
        today = now_shanghai().date()
        _add_snapshot(
            db,
            code='sh000001',
            name='上证指数',
            collected_at=today - timedelta(days=1),
            data=_good_payload(0.5, '2026-09-12 08:02:00'),
        )
        _add_snapshot(db, code='sh000001', name='上证指数', collected_at=today, stale=True)
        db.commit()

        ov = MarketOverviewService.get_overview()
        sh = _find(ov, '上证指数')

        assert sh['stale'] is True
        assert sh['change_pct'] == 0.5, '应回退到上次成功值'
        assert '上次成功值' in (sh['reason'] or '')

    def test_stale_row_without_history_becomes_placeholder(self, db, monkeypatch, patch_akshare):
        """当日失败且库内无历史成功值 → 软占位，不编造数值。"""
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'db')
        _add_snapshot(db, code='sh000001', name='上证指数', collected_at=now_shanghai().date(), stale=True)
        db.commit()

        sh = _find(MarketOverviewService.get_overview(), '上证指数')
        assert sh['available'] is False
        assert sh['change_pct'] is None

    def test_soft_placeholder_stays_placeholder_in_db_mode(self, db, monkeypatch, patch_akshare):
        """结构性软占位（无源资产）在读库路径下仍是软占位。"""
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'db')
        _add_snapshot(db, code='sh000001', name='上证指数', collected_at=now_shanghai().date(), data=_good_payload())
        db.commit()

        ov = MarketOverviewService.get_overview()
        assert _find(ov, '比特币')['available'] is False
        assert ov['unavailable_count'] >= 6

    def test_bond_track_read_from_db(self, db, monkeypatch, patch_akshare):
        """债券收益率轨从库内读取（stale 行只有 error、无数值时跳过它）。"""
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'db')
        today = now_shanghai().date()
        db.add(
            MarketMultiItem(
                source=market_service.SNAPSHOT_SOURCE,
                item_type=market_service.SNAPSHOT_BOND_ITEM_TYPE,
                item_code=market_service.SNAPSHOT_BOND_ITEM_CODE,
                item_name='中美国债10Y收益率',
                data={'cn_10y': 1.85, 'cn_10y_change_bp': -2.3, 'us_10y': 4.12, 'us_10y_change_bp': 1.1},
                collected_at=today,
                stale=False,
            )
        )
        _add_snapshot(db, code='sh000001', name='上证指数', collected_at=today, data=_good_payload())
        db.commit()

        by = MarketOverviewService.get_overview()['bond_yield']
        assert by is not None
        assert by['cn_10y'] == 1.85
        assert by['us_10y'] == 4.12

    def test_db_read_failure_degrades_to_live(self, db, monkeypatch, patch_akshare):
        """读库抛异常时回退实时取数，端点永不 500。"""
        monkeypatch.setenv('MARKET_OVERVIEW_SOURCE', 'db')

        def _boom():
            raise RuntimeError('模拟读库失败')

        monkeypatch.setattr(MarketOverviewService, '_get_overview_from_db', classmethod(lambda cls: _boom()))
        ov = MarketOverviewService.get_overview()
        assert ov['data_source'] == 'live'


# ── 并发度：预热失败必须退回串行 ────────────────────────────────────────
# V8 守卫本身的单测在 tests/core/test_v8_guard.py；这里只钉 market_service 侧的
# 并发度决策——预热失败时若仍开 6 线程，可能让整个进程被 V8 abort 掉。
# （背景：akshare 新浪系源每次调用新建 V8 isolate，并发首次创建会 C++ abort，抓不住。）


class TestFetchConcurrencyGuard:
    @staticmethod
    def _spy_workers(monkeypatch):
        """记录 ThreadPoolExecutor 实际拿到的 max_workers。"""
        seen = {}
        real_pool = market_service.ThreadPoolExecutor

        def _spy(max_workers=None, **kw):
            seen['workers'] = max_workers
            return real_pool(max_workers=max_workers, **kw)

        monkeypatch.setattr(market_service, 'ThreadPoolExecutor', _spy)
        return seen

    def test_workers_downgrade_to_serial_when_prewarm_fails(self, monkeypatch, patch_akshare):
        monkeypatch.setattr(market_service, '_prewarm_js_engine', lambda: False)
        seen = self._spy_workers(monkeypatch)

        market_service.MarketOverviewService.fetch_snapshot(force_refresh=True)

        assert seen['workers'] == 1, '预热失败必须退回串行——串行只是慢，并发 abort 是没进程'

    def test_workers_use_configured_value_when_prewarm_ok(self, monkeypatch, patch_akshare):
        monkeypatch.setattr(market_service, '_prewarm_js_engine', lambda: True)
        seen = self._spy_workers(monkeypatch)

        market_service.MarketOverviewService.fetch_snapshot(force_refresh=True)

        assert seen['workers'] == market_service._FETCH_WORKERS
