# -*- coding: utf-8 -*-
"""#2142 预估→正式对照 job 测试。

锁定七件事：
1. 官方到位 → 翻 confirmed + 三列数值正确（含 Decimal quantize）；
2. 官方缺失 → 保持 estimated、三列 NULL；
3. unit_nav NULL → 不翻；
4. 幂等 → confirmed 行重跑不改 updated_at；
5. 货基（仅 money_fund_daily_worth，无 daily_worth）→ 保持 estimated；
6. 无 estimated 行 → 空跑 success；
7. 多日期混合 → 只翻有官方的那天。
"""

from datetime import date

import pytest

from app.domains.funds.models import DailyWorth, FundValuationDaily
from app.services.sync.jobs.fund_valuation_reconcile_job import FundValuationReconcileJob


def _seed_estimate(db, code, day, nav='1.234567', status='estimated'):
    row = FundValuationDaily(
        fund_code=code,
        est_date=day,
        estimated_nav=nav,
        change_pct='0.56',
        source='tiantian_gsz',
        source_time=f'{day.isoformat()} 15:00',
        status=status,
    )
    db.add(row)
    db.commit()
    return row.id


def _seed_nav(db, code, day, nav='1.230000'):
    db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav))
    db.commit()


class TestFundValuationReconcile:
    @pytest.fixture
    def job(self, db):
        return FundValuationReconcileJob(db)

    def _row(self, db, code, day):
        return (
            db.query(FundValuationDaily)
            .filter(FundValuationDaily.fund_code == code, FundValuationDaily.est_date == day)
            .one()
        )

    # ── 1. 官方到位翻 confirmed ──

    def test_official_present_flips_confirmed(self, job, db):
        day = date(2026, 10, 13)
        _seed_estimate(db, '000001', day, nav='1.234567')
        _seed_nav(db, '000001', day, nav='1.230000')

        result = job.run(full_sync=False, targets=None)
        assert result['status'] == 'success'

        row = self._row(db, '000001', day)
        assert row.status == 'confirmed'
        assert float(row.official_nav) == 1.230000
        # deviation = 1.234567 - 1.230000 = 0.004567
        assert float(row.deviation) == pytest.approx(0.004567, abs=1e-9)
        # deviation_pct = 0.004567 / 1.230000 * 100 ≈ 0.3713%
        assert float(row.deviation_pct) == pytest.approx(0.3713, abs=1e-3)

    # ── 2. 官方缺失保持 estimated ──

    def test_official_missing_stays_estimated(self, job, db):
        day = date(2026, 10, 13)
        _seed_estimate(db, '000001', day)

        job.run(full_sync=False, targets=None)

        row = self._row(db, '000001', day)
        assert row.status == 'estimated'
        assert row.official_nav is None
        assert row.deviation is None
        assert row.deviation_pct is None

    # ── 3. unit_nav NULL 不翻 ──

    def test_null_unit_nav_not_flipped(self, job, db):
        day = date(2026, 10, 13)
        _seed_estimate(db, '000001', day)
        _seed_nav(db, '000001', day, nav=None)

        job.run(full_sync=False, targets=None)

        row = self._row(db, '000001', day)
        assert row.status == 'estimated', 'unit_nav NULL 时不应翻 confirmed'

    # ── 4. 幂等：confirmed 行重跑不动 ──

    def test_idempotent_confirmed_untouched(self, job, db):
        day = date(2026, 10, 13)
        _seed_estimate(db, '000001', day, nav='1.234567')
        _seed_nav(db, '000001', day, nav='1.230000')

        job.run(full_sync=False, targets=None)
        first_updated = self._row(db, '000001', day).updated_at

        # 第二次运行：行已是 confirmed，_fetch_data 不再捞它 → updated_at 不变
        job.run(full_sync=False, targets=None)
        second = self._row(db, '000001', day)
        assert second.status == 'confirmed'
        assert second.updated_at == first_updated, 'confirmed 行重跑不应改 updated_at'

    # ── 5. 货基（无 daily_worth 行）保持 estimated ──

    def test_money_fund_no_daily_worth_stays_estimated(self, job, db):
        # 货基净值在 money_fund_daily_worth，daily_worth 无行 → 无匹配，保持 estimated
        day = date(2026, 10, 13)
        _seed_estimate(db, '511880', day, nav='1.0000')

        job.run(full_sync=False, targets=None)

        row = self._row(db, '511880', day)
        assert row.status == 'estimated', '货基无 daily_worth 匹配，不应翻 confirmed'

    # ── 6. 无 estimated 行空跑 ──

    def test_empty_estimated_runs_success(self, job, db):
        result = job.run(full_sync=False, targets=None)
        assert result['status'] == 'success'
        assert result['stats'].get('success', 0) == 0

    # ── 7. 多日期混合只翻有官方的 ──

    def test_mixed_dates_only_flips_with_official(self, job, db):
        d1, d2 = date(2026, 10, 12), date(2026, 10, 13)
        _seed_estimate(db, '000001', d1)
        _seed_estimate(db, '000001', d2)
        # 只有 d1 有官方净值
        _seed_nav(db, '000001', d1, nav='1.100000')

        job.run(full_sync=False, targets=None)

        assert self._row(db, '000001', d1).status == 'confirmed'
        assert self._row(db, '000001', d2).status == 'estimated'
