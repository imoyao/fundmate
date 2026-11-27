# -*- coding: utf-8 -*-
"""定期复盘报告落库服务单测（#875）。

钉死：幂等 upsert（同作用域同期间只覆盖不新增）、口径版本号（不符则现算重算）、
payload 单列 JSON 序列化往返、期间非法值抛错。
"""

import datetime as dt

import pytest

from app.domains.funds.models import DailyWorth
from app.domains.summary.models import PeriodicReviewReport
from app.services import periodic_review_service as svc


class TestGenerateAndStoreEndToEnd:
    """真实链路：复用 build_scope_excess + compute_range_attribution 产出并落库。"""

    def test_generate_produces_excess_and_attribution(self, db, make_position, make_transaction):
        """造一笔真实持仓+净值，确认报告 payload 同时含区间绩效与品种归因。"""
        d0 = dt.date(2026, 11, 20)  # 买入日（周期前，让 11-23 区间首日有基线）
        d3 = dt.date(2026, 11, 27)  # 区间末日
        pos = make_position(
            symbol='000031',
            name='报告测试基金',
            quantity=1000,
            avg_price=1.0,
            asset_type='fund',
            account_name='报告账户',
        )
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=1000,
            price=1.0,
            confirm_date=d0,
            symbol='000031',
        )
        for d, nav in [(d0, 1.0), (dt.date(2026, 11, 23), 1.0), (d3, 1.1)]:  # 涨 10%
            db.add(DailyWorth(fund_code='000031', date=d, unit_nav=nav))
        db.commit()

        row = svc.generate_and_store(db, 1, 'week', '2026-W48')
        db.commit()

        payload = svc._deserialize(row.payload)
        # 区间绩效：range_rate 约 +10%（区间首日净值 1.0 → 末日 1.1）
        assert payload['excess']['range_rate'] == pytest.approx(10.0, abs=1.0)
        # 品种归因：有一个品种，pnl > 0
        positions = payload['attribution']['positions']
        assert len(positions) == 1
        assert positions[0]['symbol'] == '000031'
        assert positions[0]['pnl'] > 0

        # 落库元信息正确
        assert row.period_kind == 'week'
        assert row.period_key == '2026-W48'
        assert row.start_date == dt.date(2026, 11, 23)
        assert row.end_date == dt.date(2026, 11, 29)


class TestWriteReportIdempotency:
    def test_upsert_overwrites_not_duplicates(self, db):
        """同 (family_id, ledger_id, kind, key) 重复写 → 只覆盖不新增。"""
        payload = {'excess': {'range_rate': 1.0}, 'attribution': {'total_pnl': 2.0}}
        svc.write_report(db, 1, 'week', '2026-W48', dt.date(2026, 11, 23), dt.date(2026, 11, 29), payload)
        db.commit()

        payload2 = {'excess': {'range_rate': 3.0}, 'attribution': {'total_pnl': 4.0}}
        svc.write_report(db, 1, 'week', '2026-W48', dt.date(2026, 11, 23), dt.date(2026, 11, 29), payload2)
        db.commit()

        rows = db.query(PeriodicReviewReport).all()
        assert len(rows) == 1
        assert rows[0].caliber_version == svc.CALIBER_VERSION
        assert svc._deserialize(rows[0].payload)['excess']['range_rate'] == 3.0  # 被覆盖

    def test_scope_isolation(self, db):
        """不同 (kind, key) 或不同 ledger_id 是不同行。"""
        svc.write_report(db, 1, 'week', '2026-W48', dt.date(2026, 11, 23), dt.date(2026, 11, 29), {'a': 1})
        svc.write_report(db, 1, 'month', '2026-11', dt.date(2026, 11, 1), dt.date(2026, 11, 30), {'a': 2})
        svc.write_report(db, 1, 'week', '2026-W48', dt.date(2026, 11, 23), dt.date(2026, 11, 29), {'a': 3}, ledger_id=5)
        db.commit()
        assert db.query(PeriodicReviewReport).count() == 3


class TestReadReport:
    def test_read_hit_snapshot(self, db):
        svc.write_report(db, 1, 'year', '2026', dt.date(2026, 1, 1), dt.date(2026, 12, 31), {'x': 'y'})
        db.commit()
        assert svc.read_report(db, 1, 'year', '2026') == {'x': 'y'}

    def test_read_missing_recomputes(self, db, monkeypatch):
        """缺快照 → 现算兜底（monkeypatch 掉重计算，避免依赖真实净值数据）。"""
        monkeypatch.setattr(svc, '_build_payload', lambda *a, **k: {'computed': True})
        result = svc.read_report(db, 1, 'year', '2026')
        assert result == {'computed': True}
        # 现算结果应回写快照
        db.commit()
        assert db.query(PeriodicReviewReport).count() == 1

    def test_read_stale_caliber_recomputes(self, db, monkeypatch):
        """口径版本不符 → 现算重算（#1926 三道失效机制同源）。"""
        svc.write_report(db, 1, 'year', '2026', dt.date(2026, 1, 1), dt.date(2026, 12, 31), {'old': 1})
        # 人为把口径版本改旧
        row = db.query(PeriodicReviewReport).first()
        row.caliber_version = svc.CALIBER_VERSION - 1
        db.commit()

        monkeypatch.setattr(svc, '_build_payload', lambda *a, **k: {'fresh': True})
        assert svc.read_report(db, 1, 'year', '2026') == {'fresh': True}
        db.commit()
        row = db.query(PeriodicReviewReport).first()
        assert row.caliber_version == svc.CALIBER_VERSION  # 重算后版本更新


class TestResolvePeriod:
    def test_valid(self):
        assert svc.resolve_period('week', '2026-W48') == (dt.date(2026, 11, 23), dt.date(2026, 11, 29))

    def test_invalid_kind(self):
        with pytest.raises(ValueError):
            svc.resolve_period('hour', '2026-W48')

    def test_invalid_key(self):
        with pytest.raises(ValueError):
            svc.resolve_period('month', '2026-13')
