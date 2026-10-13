# -*- coding: utf-8 -*-
"""#2120 P0-1 回归测试：货基七日年化的口径与重算。

三条最要紧的回归点（都是实测踩出来的，不是防御性测试）：

1. **量级**：万份收益 0.23 元/万份/日 → 七日年化必须落在 **0.84%** 附近。
   实现里漏掉「÷10000」（元 → 日收益率小数）会算出 8000% 量级的荒谬值，
   本组断言把量级钉死。
2. **窗口按自然日、不按「最近 7 条观测」**：实测热点货基 000379 在窗口
   `[10-05, 10-11]` 内只有 6 条观测——7 天国庆缺口让「最近 7 条观测」一路跨到
   13 个自然日前。收益率突变时（窗口外 0.60 / 窗口内 0.20）两种口径差 28%
   （0.73% vs 0.94%）；收益率恒定时几乎无差。
3. **幂等**：`recompute_annual_return_7d` 重跑一次，`changed` 必须为 0。
"""

from datetime import date, timedelta

import pytest

from app.domains.funds.models import Fund, MoneyFundDailyWorth
from app.services.money_fund_yield import (
    annual_return_7d_at,
    compute_annual_return_7d_series,
    compute_series_from_records,
    recompute_annual_return_7d,
)

# 实测锚点（invest.db 2026-10-13）：000379 余额宝类货基，万份收益约 0.2314 元/日
_REAL_DAILY_YIELD = 0.2314


def _points(start: date, values, step_days: int = 1):
    """把「每日万份收益」列表按步长展开成 (日期, 万份收益) 升序序列。"""
    return [(start + timedelta(days=i * step_days), v) for i, v in enumerate(values)]


class TestAnnualizeScale:
    """量级：别把 % 算成 8000%"""

    def test_constant_yield_matches_hand_calculation(self):
        """连续 7 天万份收益恒为 0.2314 → 日均 0.2314/10000 → ×365×100。"""
        pts = _points(date(2026, 10, 5), [0.2314] * 7)
        # 0.2314 / 10000 * 365 * 100 = 0.8446...
        expected = round(0.2314 / 10000 * 365 * 100, 4)
        assert annual_return_7d_at(pts, date(2026, 10, 11)) == expected
        assert annual_return_7d_at(pts, date(2026, 10, 11)) == pytest.approx(0.8446, abs=1e-4)

    def test_realistic_money_fund_level(self):
        """余额宝量级：0.2314 元/万份/日 → 七日年化约 0.84%，落在货基真实区间。"""
        pts = _points(date(2026, 10, 5), [_REAL_DAILY_YIELD] * 7)
        value = annual_return_7d_at(pts, date(2026, 10, 11))
        assert 0.5 < value < 2.0, '货基七日年化应在 0.5%~2% 量级，疑似漏了 ÷10000'


class TestCalendarWindow:
    """窗口必须按自然日走，不能按「最近 7 条观测」"""

    def test_holiday_gap_does_not_inflate(self):
        """000379 实测形态：7 天国庆缺口使「最近 7 条观测」一路跨到 13 个自然日前。

        构造收益率突变场景来让两种口径真正分出高下：窗口内 6 条都是 0.20，
        窗口外（09-29）那条是高收益 0.60。
        - 自然日窗口（正确）：只取 10-06~10-11 → 0.73%
        - 观测窗口（错误）：把 0.60 拉进来平均 → 0.94%，虚高 28%
        """
        pts = [
            (date(2026, 9, 29), 0.6000),
            (date(2026, 10, 6), 0.2000),
            (date(2026, 10, 7), 0.2000),
            (date(2026, 10, 8), 0.2000),
            (date(2026, 10, 9), 0.2000),
            (date(2026, 10, 10), 0.2000),
            (date(2026, 10, 11), 0.2000),
        ]
        as_of = date(2026, 10, 11)
        got = annual_return_7d_at(pts, as_of)
        # 正确口径：6 条窗口内观测求日均 0.20 → 0.20/10000*365*100 = 0.73%
        assert got == pytest.approx(0.73, abs=1e-3)
        # 反证：若误按「最近 7 条观测」求平均，会把窗口外的 0.60 拉进来
        wrong = round(((0.6000 + 0.2000 * 6) / 7) / 10000 * 365 * 100, 4)
        assert wrong == pytest.approx(0.9386, abs=1e-3)
        assert got < wrong

    def test_constant_yield_two_calendars_agree(self):
        """收益率恒定时两种口径几乎无差——说明差别来自窗口漂移而非分母本身。"""
        pts = [
            (date(2026, 9, 29), 0.2316),
            (date(2026, 10, 6), 0.2314),
            (date(2026, 10, 7), 0.2314),
            (date(2026, 10, 8), 0.2315),
            (date(2026, 10, 9), 0.2299),
            (date(2026, 10, 10), 0.2301),
            (date(2026, 10, 11), 0.2301),
        ]
        as_of = date(2026, 10, 11)
        got = annual_return_7d_at(pts, as_of)
        by_obs = round((sum(v for _d, v in pts) / 7) / 10000 * 365 * 100, 4)
        assert got == pytest.approx(by_obs, abs=1e-3)

    def test_outside_window_excluded(self):
        """窗口外的观测不得进入计算。"""
        pts = _points(date(2026, 9, 1), [99.0] * 20 + [0.2] * 7)
        value = annual_return_7d_at(pts, date(2026, 9, 28))
        assert value == pytest.approx(round(0.2 / 10000 * 365 * 100, 4), abs=1e-6)


class TestMinSamplesAndNulls:
    """样本不足与空值：宁缺勿滥，不补 0、不补均值"""

    def test_single_sample_is_none(self):
        """单点不构成「平均」。"""
        pts = _points(date(2026, 10, 11), [0.23])
        assert annual_return_7d_at(pts, date(2026, 10, 11)) is None

    def test_null_nav_not_counted_as_zero(self):
        """万份收益为空的日子不计入样本数（否则会把分母灌水拉低结果）。"""
        pts = [
            (date(2026, 10, 9), 0.23),
            (date(2026, 10, 10), None),
            (date(2026, 10, 11), 0.23),
        ]
        # 只有 2 个有效样本 → 照常出值，且等于两日均值
        assert annual_return_7d_at(pts, date(2026, 10, 11)) == pytest.approx(
            round((0.23 / 10000) * 365 * 100, 4), abs=1e-6
        )

    def test_all_null_is_none(self):
        pts = [(date(2026, 10, 10), None), (date(2026, 10, 11), None)]
        assert annual_return_7d_at(pts, date(2026, 10, 11)) is None


class TestSeries:
    """序列版：逐位对齐 + 内存直算"""

    def test_series_aligned_with_input(self):
        pts = _points(date(2026, 10, 5), [0.2] * 10)
        out = compute_annual_return_7d_series(pts)
        assert len(out) == len(pts)
        # 只有第 1 个点样本不足（门槛 n>=2）
        assert out[0] is None
        assert all(v is not None for v in out[1:])

    def test_series_matches_point_query(self):
        pts = _points(date(2026, 10, 1), [0.21, 0.22, 0.23, 0.24, 0.25, 0.26, 0.27, 0.28])
        out = compute_annual_return_7d_series(pts)
        for (day, _v), series_val in zip(pts, out):
            assert series_val == annual_return_7d_at(pts, day)

    def test_compute_series_from_records_sorts_and_pairs(self):
        records = [
            {'date': date(2026, 10, 11), 'nav_per_10k': 0.23},
            {'date': date(2026, 10, 9), 'nav_per_10k': 0.21},
            {'date': date(2026, 10, 10), 'nav_per_10k': 0.22},
        ]
        out = compute_series_from_records(records)
        assert [r[0] for r in out] == [date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 11)]
        assert out[0][2] is None
        assert out[2][2] is not None


class TestRecomputeDb:
    """落库重算：dry-run 默认 + 幂等"""

    @pytest.fixture
    def seeded(self, db):
        if not db.query(Fund).filter_by(fund_code='900001').first():
            db.add(Fund(fund_code='900001', name='七日年化测试货基'))
            db.flush()
        start = date(2026, 10, 1)
        for i in range(10):
            db.add(
                MoneyFundDailyWorth(
                    fund_code='900001',
                    date=start + timedelta(days=i),
                    nav_per_10k=0.2314,
                )
            )
        db.commit()
        yield '900001'
        db.query(MoneyFundDailyWorth).filter_by(fund_code='900001').delete()
        db.commit()

    def test_dry_run_does_not_write(self, db, seeded):
        before = db.query(MoneyFundDailyWorth).filter_by(fund_code=seeded).count()
        stats = recompute_annual_return_7d(db, fund_codes=[seeded], apply=False)
        assert stats['funds'] == 1
        assert stats['scanned'] == before
        assert stats['changed'] > 0, 'dry-run 也应报告将要变动的行数'
        # 未落库
        assert all(
            row.annual_return_7d is None for row in db.query(MoneyFundDailyWorth).filter_by(fund_code=seeded).all()
        )

    def test_apply_then_idempotent(self, db, seeded):
        first = recompute_annual_return_7d(db, fund_codes=[seeded], apply=True)
        assert first['changed'] > 0

        rows = db.query(MoneyFundDailyWorth).filter_by(fund_code=seeded).order_by(MoneyFundDailyWorth.date).all()
        assert rows[0].annual_return_7d is None, '首行样本不足应保持 None'
        assert rows[-1].annual_return_7d == pytest.approx(0.8446, abs=1e-3)

        second = recompute_annual_return_7d(db, fund_codes=[seeded], apply=True)
        assert second['changed'] == 0, '重跑必须幂等：值没变就不该再写'


class TestReadPathCaliberMetadata:
    """#2121 验收项：读侧必须交代口径（as_of / 样本天数 / 7 自然日还是 7 交易日）。"""

    def _seed_fund(self, db):
        """造一只**货基**：`_is_money_fund` 靠 `fund.fund_type.name` 含「货币」判定。"""
        from app.domains.funds.models import Fund, FundType

        ft = db.query(FundType).filter_by(name='货币型').first()
        if ft is None:
            ft = FundType(name='货币型')
            db.add(ft)
            db.flush()
        if not db.query(Fund).filter_by(fund_code='900009').first():
            db.add(Fund(fund_code='900009', name='口径元数据测试货基', fund_type_id=ft.id))
            db.flush()

    def _seed_rows(self, db, dates):
        from app.domains.funds.models import MoneyFundDailyWorth

        for d in dates:
            db.add(MoneyFundDailyWorth(fund_code='900009', date=d, nav_per_10k=0.23))
        db.commit()

    def test_exposes_window_samples_and_note(self, db):
        """窗口 7 自然日 + 样本数 + 口径说明三件套都要返回（端到端：算→落→读）。"""
        from app.services.fund_performance import build_fund_performance
        from app.services.money_fund_yield import recompute_annual_return_7d

        self._seed_fund(db)
        self._seed_rows(db, [date(2026, 10, 5) + timedelta(days=i) for i in range(7)])
        # 读路径读的是**落库值**，所以先重算把 annual_return_7d 填上
        recompute_annual_return_7d(db, fund_codes=['900009'], apply=True)
        perf = build_fund_performance(db, '900009')
        assert perf['fund_kind'] == 'money'
        assert perf['window_days'] == 7
        assert perf['samples'] == 7
        assert perf['annual_return_7d'] == pytest.approx(0.84, abs=1e-3)
        assert '自然日' in perf['caliber_note'] and '365' in perf['caliber_note']

    def test_samples_counts_only_published_days(self, db):
        """节假日缺口：窗口仍 7 自然日，但样本数须如实为 6。"""
        from app.services.fund_performance import build_fund_performance
        from app.services.money_fund_yield import recompute_annual_return_7d

        self._seed_fund(db)
        self._seed_rows(db, [date(2026, 10, 6) + timedelta(days=i) for i in range(6)])
        recompute_annual_return_7d(db, fund_codes=['900009'], apply=True)
        perf = build_fund_performance(db, '900009')
        assert perf['as_of'] == '2026-10-11'
        assert perf['window_days'] == 7, '窗口是 7 个自然日，不是 7 个观测'
        assert perf['samples'] == 6, '样本数必须如实反映节假日缺口'
        assert perf['annual_return_7d'] is not None

    def test_reads_stored_value_not_recomputed(self, db):
        """读路径读落库值：没算过的行 annual_return_7d 为 None，但元数据仍在。"""
        from app.services.fund_performance import build_fund_performance

        self._seed_fund(db)
        self._seed_rows(db, [date(2026, 10, 5) + timedelta(days=i) for i in range(7)])
        perf = build_fund_performance(db, '900009')
        assert perf['samples'] == 7, '元数据与数值解耦：样本数照实给'
        assert perf['annual_return_7d'] is None, '未回填的行不编造数值'

    def test_no_rows_returns_zero_samples(self, db):
        from app.services.fund_performance import build_fund_performance

        self._seed_fund(db)
        perf = build_fund_performance(db, '900009')
        assert perf['basis'] == 'insufficient'
        assert perf['window_days'] == 7
        assert perf['samples'] == 0
        assert perf['annual_return_7d'] is None

    def test_window_days_matches_compute_module(self):
        """读侧与计算侧窗口常量必须同源，否则口径会在两处漂移。"""
        from app.services import money_fund_yield

        assert money_fund_yield.WINDOW_DAYS == 7
        assert '自然日' in money_fund_yield.CALIBER_NOTE
