# -*- coding: utf-8 -*-
"""#2141 pnl_calendar 当日预估回退测试。

锁定三件事：
1. 当日无官方净值 + 有估值行 → 当日行 estimated=True，盈亏按估值计算；
2. 当日有官方净值 → 官方优先，无 estimated 标记；
3. 历史日期（非今日）的估值行不参与回退——严格 date==today。
"""

import datetime as dt
from unittest.mock import patch

import pytest

from app.domains.funds.models import DailyWorth, FundValuationDaily
from app.services.pnl_calendar import build_daily_pnl_series

# 固定"今天"为 2026-10-14（周三），确保是交易日
TODAY = dt.date(2026, 10, 14)
TODAY_DT = dt.datetime(2026, 10, 14, 15, 0, 0)


def _seed_position(db, make_position, make_transaction, symbol='000001'):
    """建仓：d1 买入 1000 份 @1.0"""
    d1 = dt.date(2026, 10, 12)  # 周一
    pos = make_position(
        symbol=symbol,
        name='测试基金',
        quantity=1000,
        avg_price=1.0,
        asset_type='fund',
        account_name='测试账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol=symbol,
    )
    return pos


def _seed_nav(db, code, day, nav):
    db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav))
    db.commit()


def _seed_estimate(db, code, day, nav='1.0500'):
    db.add(
        FundValuationDaily(
            fund_code=code,
            est_date=day,
            estimated_nav=nav,
            change_pct='5.00',
            source='tiantian_gsz',
            source_time=f'{day.isoformat()} 15:00',
            status='estimated',
        )
    )
    db.commit()


def _row_of(result, day_str):
    return next((d for d in result['days'] if d['date'] == day_str), None)


class TestEstimateFallback:
    def test_today_no_official_nav_uses_estimate(self, db, make_position, make_transaction):
        """当日无官方净值 + 有估值行 → estimated=True，盈亏按估值算"""
        _seed_position(db, make_position, make_transaction)
        _seed_nav(db, '000001', dt.date(2026, 10, 12), 1.0)
        _seed_estimate(db, '000001', TODAY, nav='1.0500')

        with patch('app.services.pnl_calendar.now_shanghai', return_value=TODAY_DT):
            result = build_daily_pnl_series(
                db,
                family_id=1,
                start_date='2026-10-12',
                end_date=TODAY.isoformat(),
            )

        row = _row_of(result, TODAY.isoformat())
        assert row is not None, '今日行应存在'
        assert row.get('estimated') is True, f'应带 estimated 标记，实际 {row}'
        # 盈亏 = (1.05 - 1.0) × 1000 = 50 元（估算）
        assert row['daily_pnl'] == pytest.approx(50.0, abs=0.01), f'盈亏应≈50，实际 {row["daily_pnl"]}'

    def test_today_official_nav_wins(self, db, make_position, make_transaction):
        """当日有官方净值 → 官方优先，无 estimated 标记"""
        _seed_position(db, make_position, make_transaction)
        _seed_nav(db, '000001', dt.date(2026, 10, 12), 1.0)
        _seed_nav(db, '000001', TODAY, 1.03)
        _seed_estimate(db, '000001', TODAY, nav='1.0500')

        with patch('app.services.pnl_calendar.now_shanghai', return_value=TODAY_DT):
            result = build_daily_pnl_series(
                db,
                family_id=1,
                start_date='2026-10-12',
                end_date=TODAY.isoformat(),
            )

        row = _row_of(result, TODAY.isoformat())
        assert row is not None
        assert not row.get('estimated'), f'官方净值存在时不应有 estimated，实际 {row}'
        # 盈亏 = (1.03 - 1.0) × 1000 = 30 元（官方）
        assert row['daily_pnl'] == pytest.approx(30.0, abs=0.01), f'应按官方净值算，实际 {row["daily_pnl"]}'

    def test_historical_estimate_not_used(self, db, make_position, make_transaction):
        """历史日期（非今日）的估值行不参与回退——严格 date==today"""
        hist_day = dt.date(2026, 10, 13)  # 周二（昨天）
        _seed_position(db, make_position, make_transaction)
        _seed_nav(db, '000001', dt.date(2026, 10, 12), 1.0)
        _seed_estimate(db, '000001', hist_day, nav='1.1000')

        with patch('app.services.pnl_calendar.now_shanghai', return_value=TODAY_DT):
            result = build_daily_pnl_series(
                db,
                family_id=1,
                start_date='2026-10-12',
                end_date=TODAY.isoformat(),
            )

        hist_row = _row_of(result, hist_day.isoformat())
        if hist_row is not None:
            assert not hist_row.get('estimated'), f'历史日不应有 estimated，实际 {hist_row}'
        today_row = _row_of(result, TODAY.isoformat())
        if today_row is not None:
            assert not today_row.get('estimated'), f'今日无估值行时不应有 estimated，实际 {today_row}'

    def test_historical_range_no_estimate_query(self, db, make_position, make_transaction):
        """区间不含今日（end < today）→ 不发估值查询，不产生 estimated"""
        _seed_position(db, make_position, make_transaction)
        _seed_nav(db, '000001', dt.date(2026, 10, 12), 1.0)
        _seed_nav(db, '000001', dt.date(2026, 10, 13), 1.02)
        _seed_estimate(db, '000001', TODAY, nav='1.0500')

        with patch('app.services.pnl_calendar.now_shanghai', return_value=TODAY_DT):
            result = build_daily_pnl_series(
                db,
                family_id=1,
                start_date='2026-10-12',
                end_date='2026-10-13',
            )

        for row in result['days']:
            assert not row.get('estimated'), f'区间不含今日时不应有 estimated，实际 {row}'
