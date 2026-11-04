# -*- coding: utf-8 -*-
"""探市大类资产长历史落库 / 按需回填单测（#1460 P2）。

不依赖网络：历史落库只测读写层，回填编排用假的 fetch_asset_series 替换取数。

覆盖：
1. 新表登记在 market 域（写读同库的前提）；
2. 保存只写缺失日期（重复回填幂等），不可解析日期被丢弃；
3. 读序列返回升序尾部 N 条；
4. 库空 → 首次查看触发一次回填并落库；
5. 库内落后 → 只补缺失日期（不重复写旧行）；
6. 库内已到「应已收盘的最近交易日」→ 不再向源取数；
7. 取数失败但库里有历史 → 返回库内数据并标 stale，不让页面空白；
8. 取数失败且库空 → 503（不吞错、不返回半份数据）；
9. 未知 / 无源资产 → 404；
10. 「应已收盘的最近交易日」的周末回退与美股日期偏移判据。
"""

from datetime import date, datetime, timedelta

import pytest

from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_MARKET
from app.core.exceptions import SBException
from app.services import market_history_service, market_history_store
from app.services.market_history_service import expected_latest_date, resolve_asset_history
from app.services.market_service import ASSET_CONFIG

#: 2026-10-28 是周三；20:00 已过 A 股 / 港股收盘 ⇒ 当日日线应已可取
NOW_AFTER_CLOSE = datetime(2026, 10, 28, 20, 0)


def _weekday_series(end: date, n: int, base: float = 100.0):
    """构造以 end 结尾（含）的 n 个工作日序列，升序。"""
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return [x.strftime('%Y-%m-%d') for x in days], [base + i for i in range(n)]


def _asset(key: str) -> dict:
    return next(a for a in ASSET_CONFIG if a['key'] == key)


def test_history_table_registered_as_market():
    """新表必须归 market 域：否则写进应用库、market_session 读不到（启动校验也会拦）。"""
    assert DATA_DOMAIN_REGISTRY.get('market_asset_history') == DOMAIN_MARKET


def test_save_series_only_writes_missing_dates(db):
    dates, closes = _weekday_series(date(2026, 10, 28), 3)

    assert market_history_store.save_series(db, 'sh000300', dates, closes) == 3
    # 重复回填同一批：一行不写
    assert market_history_store.save_series(db, 'sh000300', dates, closes) == 0

    more_dates, more_closes = _weekday_series(date(2026, 10, 28), 4)
    assert market_history_store.save_series(db, 'sh000300', more_dates, more_closes) == 1

    count, last = market_history_store.coverage(db, 'sh000300')
    assert count == 4
    assert last == date(2026, 10, 28)


def test_save_series_drops_unparseable_dates(db):
    added = market_history_store.save_series(db, 'HSI', ['not-a-date', '2026-10-27'], [1.0, 2.0])
    assert added == 1
    assert market_history_store.load_series(db, 'HSI') == (['2026-10-27'], [2.0])


def test_load_series_returns_ascending_tail(db):
    dates, closes = _weekday_series(date(2026, 10, 28), 5)
    market_history_store.save_series(db, '.INX', dates, closes)

    tail_dates, tail_closes = market_history_store.load_series(db, '.INX', limit=2)
    assert tail_dates == dates[-2:]
    assert tail_closes == closes[-2:]


def test_resolve_backfills_on_first_view(db, monkeypatch):
    dates, closes = _weekday_series(date(2026, 10, 28), 3)
    monkeypatch.setattr(market_history_service, 'fetch_asset_series', lambda asset: (dates, closes))

    result = resolve_asset_history('sh000300', days=500, now=NOW_AFTER_CLOSE, db=db)

    assert result['fetched'] is True
    assert result['added'] == 3
    assert result['stale'] is False
    assert result['last_date'] == '2026-10-28'
    assert [p['date'] for p in result['points']] == dates
    assert result['count'] == 3
    assert market_history_store.coverage(db, 'sh000300')[0] == 3


def test_resolve_appends_only_missing_dates(db, monkeypatch):
    old_dates, old_closes = _weekday_series(date(2026, 10, 27), 2)
    market_history_store.save_series(db, 'sh000300', old_dates, old_closes)

    # 源返回全量：已落库的两天 + 新增的 10-28
    dates, closes = _weekday_series(date(2026, 10, 28), 3)
    monkeypatch.setattr(market_history_service, 'fetch_asset_series', lambda asset: (dates, closes))

    result = resolve_asset_history('sh000300', now=NOW_AFTER_CLOSE, db=db)

    assert result['fetched'] is True
    assert result['added'] == 1, '只应补 10-28 一天，旧日期不重写'
    assert result['total_rows'] == 3
    assert result['last_date'] == '2026-10-28'


def test_resolve_skips_fetch_when_db_is_fresh(db, monkeypatch):
    dates, closes = _weekday_series(date(2026, 10, 28), 3)
    market_history_store.save_series(db, 'sh000300', dates, closes)

    def _boom(asset):
        raise AssertionError('库内已到应已收盘的最近交易日，不应再向源取数')

    monkeypatch.setattr(market_history_service, 'fetch_asset_series', _boom)

    result = resolve_asset_history('sh000300', now=NOW_AFTER_CLOSE, db=db)
    assert result['fetched'] is False
    assert result['added'] == 0
    assert result['count'] == 3


def test_resolve_falls_back_to_db_when_fetch_fails(db, monkeypatch):
    old_dates, old_closes = _weekday_series(date(2026, 10, 27), 2)
    market_history_store.save_series(db, 'sh000300', old_dates, old_closes)

    def _fail(asset):
        raise ConnectionError('源端限流（模拟）')

    monkeypatch.setattr(market_history_service, 'fetch_asset_series', _fail)

    result = resolve_asset_history('sh000300', now=NOW_AFTER_CLOSE, db=db)
    assert result['stale'] is True
    assert result['reason']
    assert result['count'] == 2, '库内历史必须照常返回，不能让页面空白'
    assert result['last_date'] == '2026-10-27'


def test_resolve_raises_503_when_no_history_and_fetch_fails(db, monkeypatch):
    def _fail(asset):
        raise ConnectionError('源端不可达（模拟）')

    monkeypatch.setattr(market_history_service, 'fetch_asset_series', _fail)

    with pytest.raises(SBException) as exc:
        resolve_asset_history('sh000300', now=NOW_AFTER_CLOSE, db=db)
    assert exc.value.status_code == 503


def test_resolve_rejects_unknown_asset(db):
    with pytest.raises(SBException) as exc:
        resolve_asset_history('no_such_asset', db=db)
    assert exc.value.status_code == 404


def test_resolve_rejects_unavailable_asset(db):
    """软占位资产（无可靠数据源）没有历史可取，直接 404 + 卡面同一句人话原因。"""
    unavailable = next(a for a in ASSET_CONFIG if not a.get('available', True))
    with pytest.raises(SBException) as exc:
        resolve_asset_history(unavailable['key'], db=db)
    assert exc.value.status_code == 404
    assert exc.value.message == unavailable['reason']


def test_expected_latest_date_rolls_back_to_friday_on_weekend():
    """周一早上（当日未收盘）⇒ 库里最高只该到上周五。"""
    asset = _asset('sh000300')
    assert expected_latest_date(asset, datetime(2026, 10, 26, 10, 0)) == date(2026, 10, 23)


def test_expected_latest_date_for_us_market_offsets_beijing_open():
    """美股日线取美东日期：北京 05:00 后才出现「昨天」那根，05:00 前只到「前天」。"""
    asset = _asset('.INX')
    assert expected_latest_date(asset, datetime(2026, 10, 28, 6, 0)) == date(2026, 10, 27)
    assert expected_latest_date(asset, datetime(2026, 10, 28, 3, 0)) == date(2026, 10, 26)
