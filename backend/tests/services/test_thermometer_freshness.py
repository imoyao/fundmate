# -*- coding: utf-8 -*-
"""温度新鲜度守卫的**交易日口径**回归（#1720）。

背景（#1720 的现象与修订验收）：

  - 本机每日调度默认关闭（`SCHEDULER_ENABLED`），温度数据可能停在上一交易日；
    修好「可见性」后，探市页会按 `freshness.stale` 提示数据陈旧。
  - 但原判定是「距今自然日 > 阈值」——**周末与法定假期必然误报**「数据陈旧 / 调度未运行」，
    而这期间数据停留上一交易日本属正常。修订后口径为：
      · 今天非交易日（周末 / 法定休市）→ `stale` 必须为 False，不提示调度故障；
      · 今天是交易日 → 以「上一交易日」为界，数据早于它才算陈旧（已跨交易日未更新）。

本文件把这两条钉死。守门价值在于它多为**反面断言**：一旦有人把判定改回自然日口径
（或把休市日也判成 stale），周末每天都会刷出假告警，用户会开始无视该提示，
提示也就等于不存在了。

日期取值依赖 `tests/core/test_trading_calendar.py` 已钉的日历事实
（2026-10-01 国庆休市、2026-10-10 是周六）；下面用例会先断言该前提，
一旦日历口径变化就先在这里暴露，而不是让断言莫名通过或失败。
"""

from datetime import date

from app.core.trading_calendar import is_trading_day
from app.domains.temperature.models import MarketSingleValue
from app.services.thermometer import service as thermometer_service
from app.services.thermometer.service import TemperatureService

# 交易日（周五）；节后首个交易日；休市日（周六）
TRADING_DAY = date(2026, 10, 9)
PREV_TRADING_DAY = date(2026, 10, 8)
CLOSED_DAY = date(2026, 10, 10)


def _freeze_today(monkeypatch, day: date) -> None:
    """把 service 里的「今天」钉到指定日期。

    两个必须照原样的细节（都不是随意写的）：
      1. patch 目标是**模块属性**——service.py 顶部是
         `from app.core.time_utils import today_shanghai`（早绑定），patch 原模块无效；
      2. 返回类型必须是 **date**——`today_shanghai()` 的签名是 `-> date`
         （`now_shanghai().date()`），而 freshness 里算的是 `today_shanghai() - collected_at`
         且 `collected_at` 是 `Column(Date)`。若这里返回 datetime，会得到
         `TypeError: unsupported operand type(s) for -: 'datetime.datetime' and 'datetime.date'`，
         测试变成测「我造错了类型」而非测被测行为。
    """
    monkeypatch.setattr(thermometer_service, 'today_shanghai', lambda: day)


def _freshness_with_data(db, monkeypatch, today: date, collected_at: date) -> dict:
    """造一条温度数据并返回该日期视角下的 freshness。"""
    assert is_trading_day(today) is (today != CLOSED_DAY), f'测试前提失效：{today} 的交易日判定变了'
    db.add(
        MarketSingleValue(
            source='qieman',
            name='市场温度',
            value=50.0,
            collected_at=collected_at,
        )
    )
    db.commit()
    _freeze_today(monkeypatch, today)
    return TemperatureService.get_overview()['freshness']


def test_calendar_premise_is_trading_day():
    """前提：2026-10-09 是交易日、10-10 是休市日（下面全部用例依赖它）。"""
    assert is_trading_day(TRADING_DAY) is True
    assert is_trading_day(PREV_TRADING_DAY) is True
    assert is_trading_day(CLOSED_DAY) is False


def test_trading_day_data_at_prev_trading_day_is_fresh(db, monkeypatch):
    """交易日+ 数据正好停在上一交易日 → 不陈旧（刚更新过）。"""
    freshness = _freshness_with_data(db, monkeypatch, TRADING_DAY, PREV_TRADING_DAY)
    assert freshness['stale'] is False
    assert str(freshness['latest'])[:10] == str(PREV_TRADING_DAY)


def test_trading_day_data_older_than_prev_trading_day_is_stale(db, monkeypatch):
    """交易日 + 数据早于上一交易日 → 陈旧（已跨交易日未更新，调度大概率没跑）。"""
    freshness = _freshness_with_data(db, monkeypatch, TRADING_DAY, date(2026, 10, 7))
    assert freshness['stale'] is True


def test_closed_day_never_reports_stale(db, monkeypatch):
    """休市日的数据一律不算陈旧——**这条是防周末假告警的核心**。

    数据停在上一交易日（正常）与停在更早（假期没抓）都不应提示「调度未运行」。
    """
    for collected in (PREV_TRADING_DAY, date(2026, 10, 7), date(2026, 9, 30)):
        db.query(MarketSingleValue).delete()
        db.commit()
        freshness = _freshness_with_data(db, monkeypatch, CLOSED_DAY, collected)
        assert freshness['stale'] is False, f'休市日 {CLOSED_DAY} + 数据 {collected} 不该报 stale'


def test_no_data_at_all_is_not_stale(db, monkeypatch):
    """一张数据都没有时不报 stale（陈旧提示只针对「有数据但没更新」，空态另有口径）。"""
    _freeze_today(monkeypatch, TRADING_DAY)
    freshness = TemperatureService.get_overview()['freshness']
    assert freshness['latest'] is None
    assert freshness['stale'] is False
