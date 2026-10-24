# -*- coding: utf-8 -*-
"""TWR（时间加权收益率）单测 —— #2133。

锁三件事：
1. **连乘口径**：日因子 = 1 + pnl / |前一日净资产|，与 pnl_calendar 的 `daily_pnl`
   同源（该字段已剔除当日资金流，故入金不改变因子）；
2. **缺失不洗成 0**：缺数据的天整日跳过并计入 `days_skipped`，但差分基准照常推进；
3. **无数据返回 None**：`twr=None` 而不是 0（0 表示「持平」，是另一个事实）。
"""

import pytest

from app.services.performance.twr import chain_twr


def _day(date: str, pnl, net_worth):
    return {'date': date, 'daily_pnl': pnl, 'net_worth': net_worth, 'rate': None, 'state': 'updown'}


def _series(days):
    return {'scope': 'family', 'ledger_id': None, 'days': days}


def test_单日收益按前一日净资产连乘():
    # 1000 → 1100（涨 100）⇒ 因子 1.1，区间 TWR = 10%
    result = chain_twr(
        _series(
            [
                _day('2026-01-05', 0.0, 1000.0),
                _day('2026-01-06', 100.0, 1100.0),
            ]
        )
    )
    assert result['twr'] == pytest.approx(0.1)
    assert result['days_used'] == 1
    assert result['start_date'] == '2026-01-06'
    assert result['end_date'] == '2026-01-06'
    # 单日无法谈年化
    assert result['twr_annualized'] is None


def test_多日因子连乘而非简单相加():
    # 1000 → 1100 → 1210，两天各 +10% ⇒ 1.1*1.1 = 1.21（不是 20% 之和的 20%？
    # 这里两天都是 10%，相加也恰好 20%，故再乘一天 -50% 让两者分道扬镳）
    days = [
        _day('2026-01-05', 0.0, 1000.0),
        _day('2026-01-06', 100.0, 1100.0),
        _day('2026-01-07', 110.0, 1210.0),
        _day('2026-01-08', -605.0, 605.0),
    ]
    result = chain_twr(_series(days))
    # 1.1 * 1.1 * 0.5 = 0.605 ⇒ -39.5%；若错写成算术相加则是 10+10-50 = -30%
    assert result['twr'] == pytest.approx(-0.395, abs=1e-6)
    assert result['days_used'] == 3


def test_入金日不产生收益因子():
    # 净资产翻倍但当日盈亏为 0（钱是当天转进来的）⇒ 因子必须是 1，TWR 仍为 0
    days = [
        _day('2026-01-05', 0.0, 1000.0),
        _day('2026-01-06', 0.0, 2000.0),
    ]
    result = chain_twr(_series(days))
    assert result['twr'] == pytest.approx(0.0, abs=1e-9)
    assert result['days_used'] == 1


def test_缺数据的天跳过但基准继续推进():
    # 1-06 缺盈亏（None）：不参与连乘，但 1-07 的分母必须是 1-06 的净资产 1200
    days = [
        _day('2026-01-05', 0.0, 1000.0),
        _day('2026-01-06', None, 1200.0),
        _day('2026-01-07', 120.0, 1320.0),
    ]
    result = chain_twr(_series(days))
    # 1-06 跳过；1-07 因子 = 1 + 120/1200 = 1.1
    assert result['twr'] == pytest.approx(0.1)
    assert result['days_skipped'] == 2  # 首日无前值 + 1-06 缺盈亏
    assert result['days_used'] == 1


def test_无数据返回None而不是0():
    result = chain_twr(_series([]))
    assert result['twr'] is None
    assert result['twr_annualized'] is None
    assert result['days_used'] == 0


def test_净资产为0的天不算因子():
    # 分母塌陷：1-05 净资产 0 ⇒ 1-06 没有可用的前值，两天都不产生因子
    days = [
        _day('2026-01-05', 0.0, 0.0),
        _day('2026-01-06', 10.0, 1000.0),
    ]
    result = chain_twr(_series(days))
    assert result['days_used'] == 0
    assert result['twr'] is None


def test_年化按首个到末个有效日的日历天数():
    # 2026-01-06 → 2026-01-07，两天，因子 1.1 ⇒ 年化 = 1.1 ** (365/2) - 1
    days = [
        _day('2026-01-05', 0.0, 1000.0),
        _day('2026-01-06', 100.0, 1100.0),
        _day('2026-01-07', 110.0, 1210.0),
    ]
    result = chain_twr(_series(days))
    expected_factor = 1.1 * 1.1
    assert result['twr'] == pytest.approx(expected_factor - 1, abs=1e-6)
    # 两天 21% 年化后是天文数字（~1.28e15），故用相对误差而不是绝对误差
    assert result['twr_annualized'] == pytest.approx(round(expected_factor ** (365 / 2) - 1, 6), rel=1e-9)


def test_接口返回契约信封(client):
    resp = client.get('/api/performance/twr/?start_date=2026-01-05&end_date=2026-01-07')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert 'data' in payload and 'message' in payload
    data = payload['data']
    for key in ('twr', 'twr_annualized', 'days_used', 'days_skipped', 'method', 'scope'):
        assert key in data
    assert data['method'] == 'daily_chained'
    assert data['scope'] == 'family'
