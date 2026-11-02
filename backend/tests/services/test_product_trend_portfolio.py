# -*- coding: utf-8 -*-
"""测试投顾组合的走势分支（``fetch_product_trend`` 的 ``portfolio`` 路径）。

这条路径此前**根本不存在**：``_NO_SERIES_TYPES`` 把 ``portfolio`` 与 ``manager``
一起判成「无序列数据源」，于是详情页整块走势卡不渲染。事实是且慢 MCP 有全历史净值
（实测 ZH012926 = 2250 行），缺的只是落库链路——本文件钉的是「接上之后」的契约：

1. 命中库内序列 ⇒ ``kind='nav'`` + **空 ohlc**（前端据此画净值线而非 K 线）；
2. 无序列 ⇒ 返回 ``None``（调用方降级为空态），**不画假曲线**；
3. ``source`` 是站点名（「且慢」）而不是内部码（``qieman``）；
4. 基金经理仍返回 ``None``（它才是真的没有数据源）——收窄 ``_NO_SERIES_TYPES``
   时不能顺手把它也放出来。
"""

from datetime import date, timedelta

import pytest

from app.domains.funds.models import AdvisorPortfolio
from app.services import advisor_nav
from app.services.product_trend import fetch_product_trend


@pytest.fixture
def portfolio(db):
    """一个库内已建档的且慢组合（远足，实测代码 ZH012926）。"""
    row = AdvisorPortfolio(platform='QIEMAN', code='ZH012926', name='远足')
    db.add(row)
    db.commit()
    return row


def _seed_series(db, portfolio_id: int, days_back: int = 20) -> None:
    """写一串「到今天为止」的净值，避开按需补拉（``FRESH_DAYS`` 内视为够新）。"""
    today = date.today()
    rows = [
        {'nav_date': (today - timedelta(days=offset)).isoformat(), 'nav': 1.0 + offset * 0.001}
        for offset in range(days_back, -1, -1)
    ]
    advisor_nav.save_nav_rows(db, portfolio_id, rows, 'qieman')


def test_portfolio_trend_returns_nav_series(db, portfolio):
    """库内有序列 ⇒ kind=nav、ohlc 为空、source 是站点名。"""
    _seed_series(db, portfolio.id)

    result = fetch_product_trend(db, 'ZH012926', 'portfolio', '1M')

    assert result is not None
    assert result['kind'] == 'nav'
    # 组合没有 OHLCV：前端据此走净值线渲染分支，而不是画一根根蜡烛
    assert result['ohlc'] == []
    assert result['source'] == '且慢'
    assert '组合单位净值' in result['basis']
    assert len(result['dates']) == len(result['values']) > 0
    # 日期升序、与 values 一一对应（前端按 index 取轴标签）
    assert result['dates'] == sorted(result['dates'])
    assert result['available_days'] >= 0


def test_portfolio_trend_respects_range_window(db, portfolio):
    """区间档位生效：1M 只取 30 天内，长历史不该被整段塞回来。"""
    _seed_series(db, portfolio.id, days_back=200)

    short = fetch_product_trend(db, 'ZH012926', 'portfolio', '1M')
    long = fetch_product_trend(db, 'ZH012926', 'portfolio', '1Y')

    assert short is not None and long is not None
    assert len(short['dates']) < len(long['dates'])
    # 档位回看 30 天，序列起点不得早于 today-31
    assert short['dates'][0] >= (date.today() - timedelta(days=31)).isoformat()


def test_portfolio_trend_without_series_returns_none(db, portfolio, monkeypatch):
    """库内无序列且补拉无果 ⇒ None（诚实降级，不返回空壳冒充成功）。"""
    called = {}

    def _noop_ensure(db_, portfolio_, **kwargs):
        called['hit'] = portfolio_.code

    monkeypatch.setattr(advisor_nav, 'ensure_series', _noop_ensure)

    assert fetch_product_trend(db, 'ZH012926', 'portfolio', '3M') is None
    # 读路径必须先尝试按需补拉（首次查看不在目标池内的组合），而不是直接认输
    assert called['hit'] == 'ZH012926'


def test_portfolio_trend_unknown_code_returns_none(db):
    """未建档的组合 ⇒ None，且**不去调上游**（连它是谁都不知道，无权打 MCP）。"""
    assert fetch_product_trend(db, 'ZH000000', 'portfolio', '3M') is None


def test_portfolio_trend_survives_backfill_failure(db, portfolio, monkeypatch):
    """按需补拉抛错不得让请求 500：降级为库内数据（有就画，没有就 None）+ 留日志。"""

    def _boom(*args, **kwargs):
        raise RuntimeError('MCP 抖了一下')

    monkeypatch.setattr(advisor_nav, 'ensure_series', _boom)

    assert fetch_product_trend(db, 'ZH012926', 'portfolio', '3M') is None

    # 库里原本就有数据时：补拉失败也必须照旧画出来（降级而非丢弃）
    _seed_series(db, portfolio.id, days_back=10)
    result = fetch_product_trend(db, 'ZH012926', 'portfolio', '1M')
    assert result is not None
    assert len(result['values']) > 0


def test_manager_still_has_no_series(db):
    """基金经理**仍然**没有序列数据源：收窄 `_NO_SERIES_TYPES` 不得把它一起放出来。"""
    assert fetch_product_trend(db, 'MGR_000001', 'manager', '3M') is None


def test_portfolio_code_is_normalized(db, portfolio):
    """入参可能带场地前缀 / 小写（自选与持仓里的形态），读路径要能对上。"""
    _seed_series(db, portfolio.id, days_back=5)

    result = fetch_product_trend(db, 'NO_VENUE:zh012926', 'portfolio', '1M')

    assert result is not None
    assert result['symbol'] == 'NO_VENUE:ZH012926'  # symbol 原样回显，便于前端对齐请求
    assert len(result['values']) > 0
