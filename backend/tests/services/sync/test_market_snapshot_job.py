# -*- coding: utf-8 -*-
"""探市快照落库 job 单测（#1460 方案 B）。

不依赖真实网络：用假 akshare 替换 `market_service.get_akshare`。

覆盖的验收点（见 docs/working-notes/market-snapshot-persist-plan-2026-09-13.md §6）：
1. 14 个可取数资产 + 1 条债券收益率轨 = 15 行落库；**6 个结构性软占位不入库**；
2. 同日重复跑幂等（唯一键 upsert，不产生重复行）；
3. 单资产取数失败 → 该行 `stale=True`，job 仍报 success 但把失败写进 `stats.errors`；
4. 全部失败 → job 报 failed（关键 job 要能被告警抓到）；
5. 交易日滞后守卫：`trade_date` 落后同批次最大值 >14 天 → `stale=True`
   （这是 F6「汇率卡展示 2023 年数据」那类事故的兜底）。
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from app.core.time_utils import now_shanghai
from app.domains.temperature.models import MarketMultiItem
from app.services import market_service
from app.services.sync.jobs.market_snapshot_job import MarketSnapshotSyncJob

# 结构性软占位（ASSET_CONFIG 里 available=False）：不该出现在库内
_SOFT_PLACEHOLDER_CODES = {'sh932000', '.N225', '.FTSE', '.GDAXI', '.FCHI', 'BTC'}

_EXPECTED_ASSET_ROWS = 14
_EXPECTED_TOTAL_ROWS = _EXPECTED_ASSET_ROWS + 1  # + 债券收益率轨


def _df(base: float, end: str | None = None, periods: int = 520) -> pd.DataFrame:
    """构造 (date, close) 假 DataFrame；`end` 用于伪造「数据陈旧」场景。"""
    if end:
        dates = pd.date_range(end=end, periods=periods, freq='D')
    else:
        dates = pd.date_range('2024-01-01', periods=periods, freq='D')
    return pd.DataFrame({'date': dates.strftime('%Y-%m-%d'), 'close': [base + i * 0.1 for i in range(periods)]})


def _currency_df(base: float = 6.8, end: str | None = None) -> pd.DataFrame:
    """汇率口径：中行折算价列（列名与真实 akshare 一致）。"""
    if end:
        dates = pd.date_range(end=end, periods=400, freq='D')
    else:
        dates = pd.date_range('2024-01-01', periods=520, freq='D')
    return pd.DataFrame({'日期': dates.strftime('%Y-%m-%d'), '中行折算价': [base + i * 0.0001 for i in range(len(dates))]})


def _bond_df() -> pd.DataFrame:
    dates = pd.date_range('2024-01-01', periods=520, freq='D').strftime('%Y-%m-%d')
    return pd.DataFrame(
        {
            '日期': dates,
            '中国国债收益率10年': [1.85 + 0.001 * i for i in range(520)],
            '美国国债收益率10年': [4.12 - 0.0008 * i for i in range(520)],
        }
    )


class FakeAk:
    """假 akshare：所有已用 source 返回合理假数据。"""

    def stock_zh_index_daily(self, *a, **kw):
        return _df(3000.0)

    def stock_hk_index_daily_sina(self, *a, **kw):
        return _df(18000.0)

    def index_us_stock_sina(self, *a, **kw):
        return _df(4500.0)

    def fund_etf_hist_sina(self, *a, **kw):
        return _df(110.0)

    def futures_main_sina(self, *a, **kw):
        return _df(400.0)

    def stock_us_daily(self, *a, **kw):
        return _df(95.0)

    def currency_boc_sina(self, *a, **kw):
        return _currency_df()

    def bond_zh_us_rate(self, *a, **kw):
        return _bond_df()


class FakeAkBrokenCurrency(FakeAk):
    """汇率源抛异常：验证单资产失败落 stale 且不影响其余资产。"""

    def currency_boc_sina(self, *a, **kw):
        raise ConnectionError('模拟汇率源不可达')


class FakeAkAllBroken(FakeAk):
    """所有 source 都抛异常：验证「全部失败 → failed」。"""

    def _boom(self, *a, **kw):
        raise ConnectionError('模拟全源不可达')

    stock_zh_index_daily = _boom
    stock_hk_index_daily_sina = _boom
    index_us_stock_sina = _boom
    fund_etf_hist_sina = _boom
    futures_main_sina = _boom
    stock_us_daily = _boom
    currency_boc_sina = _boom

    def bond_zh_us_rate(self, *a, **kw):
        raise ConnectionError('模拟债券源不可达')


class FakeAkStaleCurrency(FakeAk):
    """汇率源返回停在 2023-11-10 的旧窗口 —— 复现 F6 现象。

    用于验证「交易日滞后守卫」：即使源没报错，落后同批次最大值过多的行也会被标 stale。
    """

    def currency_boc_sina(self, *a, **kw):
        return _currency_df(end='2023-11-10')


@pytest.fixture
def fake_ak(monkeypatch):
    """默认假 akshare（全部源健康）；传入自定义 fake 可切换失败场景。"""

    def _use(fake=None):
        monkeypatch.setattr(market_service, 'get_akshare', lambda: fake or FakeAk())

    _use()
    return _use


def _rows(db, source='market_snapshot'):
    db.expire_all()
    return db.query(MarketMultiItem).filter(MarketMultiItem.source == source).all()


def _by_code(db):
    return {r.item_code: r for r in _rows(db)}


class TestMarketSnapshotJobWrites:
    def test_writes_14_assets_plus_bond_and_excludes_placeholders(self, db, fake_ak):
        result = MarketSnapshotSyncJob(db).run()

        assert result['status'] == 'success'
        rows = _rows(db)
        assert len(rows) == _EXPECTED_TOTAL_ROWS, f'应落 {_EXPECTED_TOTAL_ROWS} 行，实际 {len(rows)}'

        codes = {r.item_code for r in rows}
        # 6 个结构性软占位（无源）绝不入库——它们由代码常量提供，落库等于每天写常量
        assert not (codes & _SOFT_PLACEHOLDER_CODES), f'软占位不该入库: {codes & _SOFT_PLACEHOLDER_CODES}'
        # 债券收益率轨单独一行
        assert 'cn_us_10y' in codes

        sh = next(r for r in rows if r.item_code == 'sh000001')
        assert sh.item_type == 'asset'
        assert sh.item_name == '上证指数'
        assert sh.stale is False
        assert sh.data['change_pct'] is not None
        assert sh.data['position']['window'] == 500
        assert sh.data['data_asof']

    def test_soft_placeholders_count_matches_config(self, db, fake_ak):
        """落库行数 = ASSET_CONFIG 中 available=True 的资产数 + 1，防止配置与落库口径漂移。"""
        available = sum(1 for a in market_service.ASSET_CONFIG if a.get('available', True))
        assert available == _EXPECTED_ASSET_ROWS, 'ASSET_CONFIG 的可取数资产数变了，请同步本测试的期望值'

        MarketSnapshotSyncJob(db).run()
        assert len(_rows(db)) == available + 1

    def test_idempotent_on_same_day(self, db, fake_ak):
        """同日重复跑只 upsert 同批行（唯一键），不产生重复。"""
        MarketSnapshotSyncJob(db).run()
        first = len(_rows(db))
        MarketSnapshotSyncJob(db).run()
        assert len(_rows(db)) == first


class TestMarketSnapshotJobFailureHandling:
    def test_partial_failure_marks_stale_but_reports_success(self, db, fake_ak):
        """单资产失败 → 该行 stale=True；job 仍 success，但失败明细可查。"""
        fake_ak(FakeAkBrokenCurrency())
        result = MarketSnapshotSyncJob(db).run()

        assert result['status'] == 'success'
        assert result['stats']['failed'] == 2  # 美元指数 + 离岸人民币
        assert len(result['stats']['errors']) == 2

        by = _by_code(db)
        for code in ('USD_INDEX', 'USDCNH'):
            assert by[code].stale is True, f'{code} 应标 stale'
            assert 'error' in by[code].data
        # 其余资产不受影响
        assert by['sh000001'].stale is False

    def test_all_failed_reports_failed(self, db, fake_ak):
        """全部取数失败 → failed（关键 job，要能被 D9 的告警口径抓到）。"""
        fake_ak(FakeAkAllBroken())
        result = MarketSnapshotSyncJob(db).run()
        assert result['status'] == 'failed'

    def test_trade_lag_guard_flags_stale(self, db, fake_ak):
        """交易日滞后守卫：源没报错但数据停在 2023-11-10 → stale=True（F6 兜底）。"""
        fake_ak(FakeAkStaleCurrency())
        MarketSnapshotSyncJob(db).run()

        by = _by_code(db)
        for code in ('USD_INDEX', 'USDCNH'):
            assert by[code].stale is True, f'{code} 数据滞后却未标 stale'
            assert '滞后' in by[code].data['error']
        # 新鲜资产不受牵连
        assert by['sh000001'].stale is False


class TestTradeLagHelpers:
    def test_parse_trade_date_tolerates_garbage(self):
        assert MarketSnapshotSyncJob._parse_trade_date(None) is None
        assert MarketSnapshotSyncJob._parse_trade_date('') is None
        assert MarketSnapshotSyncJob._parse_trade_date('不是日期') is None
        assert MarketSnapshotSyncJob._parse_trade_date('2026-09-11') == date(2026, 9, 11)
        # 带时间戳的字符串取前 10 位
        assert MarketSnapshotSyncJob._parse_trade_date('2026-09-11 15:00:11') == date(2026, 9, 11)

    def test_max_trade_date_picks_latest(self):
        items = [{'trade_date': '2026-09-10'}, {'trade_date': '2026-09-11'}, {'trade_date': None}]
        assert MarketSnapshotSyncJob._max_trade_date(items) == date(2026, 9, 11)

    def test_max_trade_date_all_unparsable_is_none(self):
        assert MarketSnapshotSyncJob._max_trade_date([{'trade_date': 'x'}]) is None

    def test_trade_lag_days_returns_none_when_uncomparable(self):
        ref = date(2026, 9, 11)
        assert MarketSnapshotSyncJob._trade_lag_days(None, ref) is None
        assert MarketSnapshotSyncJob._trade_lag_days('2026-09-01', None) is None
        assert MarketSnapshotSyncJob._trade_lag_days('2026-09-01', ref) == 10


class TestCollectedAt:
    def test_collected_at_is_shanghai_today(self, db, fake_ak):
        """collected_at 取 job 开始时刻的上海日期（幂等键的一半）。"""
        MarketSnapshotSyncJob(db).run()
        today = now_shanghai().date()
        assert {r.collected_at for r in _rows(db)} == {today}

    def test_collected_at_within_lookback_window(self, db, fake_ak):
        """落库日必须在读路径的回看窗口内，否则读库会取不到。"""
        MarketSnapshotSyncJob(db).run()
        cutoff = now_shanghai().date() - timedelta(days=market_service._DB_LOOKBACK_DAYS)
        assert all(r.collected_at >= cutoff for r in _rows(db))
