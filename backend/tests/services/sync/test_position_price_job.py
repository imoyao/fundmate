# -*- coding: utf-8 -*-
"""测试 PositionPriceSyncJob：持仓现价回写（场外＝确认净值，场内＝最近交易日收盘价，#1104）。

覆盖三类**红线**：

1. 单位与精度——写的是 0.0001 元（走 `Money.yuan_to_price_units`），不是裸 float；
2. 新鲜度闸门——过期净值（> MAX_STALENESS_DAYS）/ 过期收盘价
   （> MAX_INTRADAY_STALENESS_DAYS）**不写**，宁可保持原值；
3. 口径边界——货基按面值、场内取 `price_history` 收盘价、balance 模式跳过、
   无显式类型跳过，且**全程不联网**（`allow_remote=False`）。
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.money import Money
from app.core.time_utils import today_shanghai
from app.domains.funds.models import DailyWorth
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.sync.jobs.position_price_job import (
    MAX_INTRADAY_STALENESS_DAYS,
    MAX_STALENESS_DAYS,
    MONEY_FUND_FACE_VALUE,
    SKIP_BALANCE_MODE,
    SKIP_NO_CLOSE,
    SKIP_NO_NAV,
    SKIP_STALE_CLOSE,
    SKIP_STALE_NAV,
    SKIP_UNKNOWN_TYPE,
    PositionPriceSyncJob,
)


@pytest.fixture
def job(db):
    return PositionPriceSyncJob(db)


def _add_nav(db, code: str, nav: float, days_ago: int = 1) -> None:
    day = today_shanghai() - timedelta(days=days_ago)
    db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav, acc_nav=nav))
    db.commit()


def _add_close(db, symbol: str, close: float, days_ago: int = 0) -> None:
    """写一根场内日线（price_history.security_id 非空，故先建证券记录）。"""
    sec = db.query(Security).filter(Security.symbol == symbol).first()
    if sec is None:
        sec = Security(symbol=symbol, name=symbol, market='CN_A', type='stock')
        db.add(sec)
        db.flush()
    db.add(
        PriceHistory(
            security_id=sec.id,
            symbol=symbol,
            trade_date=today_shanghai() - timedelta(days=days_ago),
            close=close,
        )
    )
    db.commit()


# ── 1. 基本链路：确认净值 → current_price ──────────────────────────────


def test_writes_confirmed_nav_in_price_units(job, db, make_position):
    """导入时 avg_price == current_price（盈亏恒 0）→ 回写后两者分离。"""
    pos = make_position(
        symbol='023887', name='测试基金', asset_type='fund', quantity=1000, avg_price=0.83, current_price=0.83
    )
    _add_nav(db, '023887', 0.8567, days_ago=1)

    result = job.run()

    assert result['status'] == 'success'
    assert result['stats']['success'] == 1
    db.refresh(pos)
    # 0.8567 元 → 8567（0.0001 元），4 位精度不丢
    assert pos.current_price == 8567
    assert Money.price_units_to_yuan(pos.current_price) == pytest.approx(0.8567)
    # 盈亏不再恒为 0
    assert pos.current_price != pos.avg_price


def test_unchanged_price_is_not_rewritten(job, db, make_position):
    """同价不写：避免每次调度都把 updated_at 刷成今天，让「何时真正更新过」失真。

    #2007 补充：「没变」要连同 `prev_close` / `price_date` 一起算——只比 `current_price`
    不够（见下一条用例）。故这里先让三者都处在「跑完会得到的样子」：库里只有一根净值，
    所以没有上一根、日期就是那一根。此时 job 才是真正无事可做。
    """
    pos = make_position(symbol='023887', asset_type='fund', quantity=1000, avg_price=1.0, current_price=1.2345)
    pos.prev_close = None
    pos.price_date = today_shanghai() - timedelta(days=1)
    db.commit()
    _add_nav(db, '023887', 1.2345, days_ago=1)

    result = job.run()

    assert result['stats']['success'] == 0
    assert result['stats']['unchanged'] == 1
    # 有价无基准：这一笔算不出当日盈亏，计数要如实（前端会降级「—」）
    assert result['stats']['prev_close_missing'] == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(1.2345)


def test_prev_close_and_price_date_are_written_with_price(job, db, make_position):
    """#2007：current_price / prev_close / price_date **同批**落库，三个值同源。

    有上一根净值时，prev_close 必须是**相邻的那一根**（不是随便一个更早的数）——
    上层要拿 (current_price − prev_close) 当当日涨跌用。
    """
    pos = make_position(symbol='023887', asset_type='fund', quantity=1000, avg_price=1.0, current_price=1.0)
    _add_nav(db, '023887', 1.2000, days_ago=2)  # 上一根
    _add_nav(db, '023887', 1.2345, days_ago=1)  # 最新一根

    result = job.run()

    assert result['stats']['success'] == 1
    assert result['stats']['prev_close_missing'] == 0
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(1.2345)
    assert pos.prev_close == Money.yuan_to_price_units(1.2000)
    assert pos.price_date == today_shanghai() - timedelta(days=1)


def test_same_price_new_day_still_updates_baseline(job, db, make_position):
    """「同价不写」的边界（#2007）：价格没变但**交易日推进**时仍须写。

    连续两天收在同一个价（一字板 / 净值持平）是常见的。若只比 current_price 就跳过，
    prev_close 与 price_date 会永远停在昨天，用户看到的是「今天的涨跌」写着一个昨天的差。
    """
    pos = make_position(symbol='023887', asset_type='fund', quantity=1000, avg_price=1.0, current_price=1.5)
    _add_nav(db, '023887', 1.5, days_ago=2)
    _add_nav(db, '023887', 1.5, days_ago=1)

    result = job.run()

    assert result['stats']['success'] == 1, '同价但基准推进了，必须写'
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(1.5)
    assert pos.prev_close == Money.yuan_to_price_units(1.5)
    assert pos.price_date == today_shanghai() - timedelta(days=1)


def test_money_fund_leaves_baseline_null(job, db, make_position):
    """货基按面值计价，没有「上一日价差」→ 基准留 NULL，不写 0（#2007）。"""
    pos = make_position(symbol='000009', asset_type='money_fund', quantity=10000, avg_price=1.0, current_price=0.9)
    _add_nav(db, '000009', 2.0, days_ago=1)  # 即便库里有净值，货基也不读

    result = job.run()

    assert result['stats']['success'] == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(MONEY_FUND_FACE_VALUE)
    assert pos.prev_close is None
    assert pos.price_date is None


def test_multiple_families_are_all_updated(job, db, make_position):
    """现价回写是数据任务（非请求路径），不应被 family 过滤挡掉。"""
    a = make_position(symbol='000001', asset_type='fund', quantity=100, avg_price=1.0, current_price=1.0, family_id=1)
    b = make_position(symbol='000001', asset_type='fund', quantity=200, avg_price=1.0, current_price=1.0, family_id=2)
    _add_nav(db, '000001', 1.5, days_ago=1)

    result = job.run()

    assert result['stats']['success'] == 2
    db.refresh(a)
    db.refresh(b)
    assert a.current_price == b.current_price == Money.yuan_to_price_units(1.5)


# ── 2. 新鲜度闸门 ─────────────────────────────────────────────────────


def test_stale_nav_is_not_written(job, db, make_position):
    """同步链路断掉时，宁可保持原值，也不写入更旧的数据（假新鲜）。"""
    pos = make_position(symbol='023887', asset_type='fund', quantity=1000, avg_price=1.0, current_price=1.11)
    _add_nav(db, '023887', 0.8567, days_ago=MAX_STALENESS_DAYS + 1)

    result = job.run()

    assert result['stats']['success'] == 0
    assert result['stats']['skip_reasons'].get(SKIP_STALE_NAV) == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(1.11)  # 原值未被覆盖


def test_nav_at_threshold_boundary_is_written(job, db, make_position):
    """边界：正好 MAX_STALENESS_DAYS 天前仍算新鲜（闸门是「大于」才拦）。"""
    pos = make_position(symbol='023887', asset_type='fund', quantity=1000, avg_price=1.0, current_price=1.0)
    _add_nav(db, '023887', 1.23, days_ago=MAX_STALENESS_DAYS)

    result = job.run()

    assert result['stats']['success'] == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(1.23)


# ── 3. 口径边界 ───────────────────────────────────────────────────────


def test_money_fund_uses_face_value_not_daily_worth(job, db, make_position):
    """货基按面值 1.0000 元写；**即便 daily_worth 有错表残留也不采信**（#1554）。"""
    pos = make_position(symbol='000509', asset_type='money_fund', quantity=10000, avg_price=1.0, current_price=0)
    # 错表残留形态：货基被写进 daily_worth，unit_nav 是「每万份收益」被当净值
    _add_nav(db, '000509', 1.2345, days_ago=1)

    result = job.run()

    assert result['stats']['success'] == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(MONEY_FUND_FACE_VALUE) == 10000


def test_intraday_assets_use_latest_close(job, db, make_position):
    """场内（ETF / 股票 / 可转债）现价 ← price_history 最近交易日**未复权**收盘价（#1104）。"""
    etf = make_position(symbol='SZ159857', asset_type='etf', quantity=1000, avg_price=0.85, current_price=1.094)
    stock = make_position(symbol='SH601012', asset_type='stock', quantity=100, avg_price=17.25, current_price=23.4)
    _add_close(db, 'SZ159857', 0.701, days_ago=1)
    _add_close(db, 'SH601012', 11.38, days_ago=0)

    result = job.run()

    assert result['status'] == 'success'
    assert result['stats']['success'] == 2
    db.refresh(etf)
    db.refresh(stock)
    assert etf.current_price == Money.yuan_to_price_units(Decimal('0.701'))
    assert stock.current_price == Money.yuan_to_price_units(Decimal('11.38'))
    # 盈亏不再恒为 0（导入时 avg_price == current_price 的老问题）
    assert stock.current_price != stock.avg_price


def test_intraday_prefers_newest_close(job, db, make_position):
    """多条日线时取**最近**一根，而不是最早一根（回补后历史成片写入）。"""
    pos = make_position(symbol='SH601012', asset_type='stock', quantity=100, avg_price=17.25, current_price=23.4)
    _add_close(db, 'SH601012', 11.0, days_ago=5)
    _add_close(db, 'SH601012', 11.38, days_ago=0)

    result = job.run()

    assert result['stats']['success'] == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(Decimal('11.38'))


def test_stale_close_is_not_written(job, db, make_position):
    """收盘价过期（停牌 / 行情链路断）→ 保持原值，不写入更旧的数据。"""
    pos = make_position(symbol='SZ159857', asset_type='etf', quantity=1000, avg_price=0.85, current_price=1.094)
    _add_close(db, 'SZ159857', 0.5, days_ago=MAX_INTRADAY_STALENESS_DAYS + 1)

    result = job.run()

    assert result['stats']['success'] == 0
    assert result['stats']['skip_reasons'].get(SKIP_STALE_CLOSE) == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(Decimal('1.094'))


def test_intraday_without_close_does_not_use_nav(job, db, make_position):
    """库内无近期收盘价 → 计数跳过；**不得**用 daily_worth 的净值冒充场内价。"""
    pos = make_position(symbol='SZ159857', asset_type='etf', quantity=1000, avg_price=0.85, current_price=1.094)
    _add_nav(db, 'SZ159857', 0.9, days_ago=1)

    result = job.run()

    assert result['stats']['success'] == 0
    assert result['stats']['skip_reasons'].get(SKIP_NO_CLOSE) == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(Decimal('1.094'))


def test_balance_mode_is_skipped(job, db, make_position):
    """balance 模式没有份额可乘，市值靠人工录入 market_value_override。"""
    pos = make_position(
        symbol='023887',
        asset_type='fund',
        quantity=1000,
        avg_price=1.0,
        current_price=1.0,
        valuation_mode='balance',
    )
    _add_nav(db, '023887', 1.23, days_ago=1)

    result = job.run()

    assert result['stats']['skip_reasons'].get(SKIP_BALANCE_MODE) == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(1.0)


def test_unknown_asset_type_is_skipped(job, db, make_position):
    """6 位数字代码在场外基金与场内 ETF 上重叠（如 510300），无显式类型时不许猜。"""
    pos = make_position(symbol='510300', asset_type=None, quantity=1000, avg_price=4.0, current_price=4.0)
    _add_nav(db, '510300', 4.5, days_ago=1)

    result = job.run()

    assert result['stats']['skip_reasons'].get(SKIP_UNKNOWN_TYPE) == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(4.0)


def test_position_without_nav_in_db_is_counted(job, db, make_position):
    pos = make_position(symbol='999999', asset_type='fund', quantity=1000, avg_price=1.0, current_price=1.0)

    result = job.run()

    assert result['stats']['skip_reasons'].get(SKIP_NO_NAV) == 1
    db.refresh(pos)
    assert pos.current_price == Money.yuan_to_price_units(1.0)


def test_zero_quantity_position_is_not_a_candidate(job, db, make_position):
    """清仓后的零数量持仓不参与（避免把已了结的仓位价格改来改去）。"""
    make_position(symbol='023887', asset_type='fund', quantity=0, avg_price=1.0, current_price=0.5)
    _add_nav(db, '023887', 1.23, days_ago=1)

    result = job.run()

    assert result['stats']['total'] == 0
    assert result['stats']['success'] == 0


def test_empty_portfolio_is_success(job, db):
    result = job.run()
    assert result['status'] == 'success'
    assert result['stats']['total'] == 0


# ── 4. 不联网（数据策略红线） ──────────────────────────────────────────


def test_never_triggers_remote_fetch(job, db, make_position):
    """本 job 只读库内已有净值：绝不因为「库里没有」就替用户逐只抓取。"""
    make_position(symbol='023887', asset_type='fund', quantity=1000, avg_price=1.0, current_price=1.0)

    with patch(
        'app.services.nav_service.NavService._fetch_remote_batch',
        side_effect=AssertionError('position_price job 不得联网'),
    ):
        result = job.run()

    assert result['status'] == 'success'
    assert result['stats']['skip_reasons'].get(SKIP_NO_NAV) == 1
