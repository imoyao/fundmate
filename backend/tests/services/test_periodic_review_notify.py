# -*- coding: utf-8 -*-
"""定期复盘报告的站内通知发射单测（#875）。

钉死：category=report / source_type=periodic_report、客观陈述（无指令措辞）、
周期级 dedup（同期间幂等、跨期间是新提醒）、收益率不可算时正文只陈述「已生成」、
期间键 → 中文名换算。
"""

import datetime as dt

from app.services import notification_service as ns
from app.services.periodic_review_notify import (
    CATEGORY_REPORT,
    SOURCE_TYPE_PERIODIC_REPORT,
    emit_periodic_report_notice,
)


class TestEmitPeriodicReportNotice:
    def test_emits_one_report_notification(self, db):
        """报告生成 → 一条 category=report / source_type=periodic_report 通知。"""
        created = emit_periodic_report_notice(db, 1, 'month', '2026-11')
        assert created == 1
        row = ns.list_notifications(db, 1)[0]
        assert row.category == CATEGORY_REPORT
        assert row.source_type == SOURCE_TYPE_PERIODIC_REPORT
        assert '月报' in row.title
        assert row.source_key == '2026-11'

    def test_idempotent_within_same_period(self, db):
        """同期间重复 emit → 只留一条（周期级 dedup，不含日期）。"""
        assert emit_periodic_report_notice(db, 1, 'week', '2026-W48') == 1
        assert emit_periodic_report_notice(db, 1, 'week', '2026-W48') == 0
        assert ns.total_count(db, 1) == 1

    def test_cross_period_is_new_notification(self, db):
        """跨周期 → 新提醒（去重键含 kind+key，不含日期）。"""
        assert emit_periodic_report_notice(db, 1, 'week', '2026-W48') == 1
        assert emit_periodic_report_notice(db, 1, 'week', '2026-W49') == 1
        assert emit_periodic_report_notice(db, 1, 'month', '2026-11') == 1
        assert ns.total_count(db, 1) == 3

    def test_body_contains_rate_when_computable(self, db):
        """收益率可算 → 正文含带符号百分比（客观数字，无指令措辞）。"""
        payload = {'excess': {'range_rate': 10.0}}
        created = emit_periodic_report_notice(db, 1, 'month', '2026-11', payload=payload)
        assert created == 1
        row = ns.list_notifications(db, 1)[0]
        assert '+10.00%' in row.body
        # 无指令措辞
        for banned in ('建议', '买入', '卖出', '赎回', '加仓', '减仓'):
            assert banned not in row.title
            assert banned not in row.body

    def test_body_falls_back_when_rate_missing(self, db):
        """收益率不可算（无持仓/无基准）→ 正文只陈述「已生成」，不写 0%。"""
        created = emit_periodic_report_notice(db, 1, 'month', '2026-11', payload={'excess': {'range_rate': None}})
        assert created == 1
        row = ns.list_notifications(db, 1)[0]
        assert '已生成' in row.body
        assert '%' not in row.body


class TestPeriodDisplayName:
    def test_all_kinds_display_name(self, db):
        """四种粒度的中文名与标题正确（周/月/季/年，均含粒度词）。"""
        emit_periodic_report_notice(db, 1, 'week', '2026-W48')
        emit_periodic_report_notice(db, 1, 'month', '2026-11')
        emit_periodic_report_notice(db, 1, 'quarter', '2026-Q4')
        emit_periodic_report_notice(db, 1, 'year', '2026')
        titles = [r.title for r in ns.list_notifications(db, 1)]
        assert any('第48周周报' in t for t in titles)
        assert any('11月月报' in t for t in titles)
        assert any('第4季度季报' in t for t in titles)
        assert any('2026年年报' in t for t in titles)


class TestDedupKey:
    def test_dedup_key_scoped_by_family(self, db):
        """去重键含 family——不同家庭同期间互不影响。"""
        emit_periodic_report_notice(db, 1, 'year', '2026')
        emit_periodic_report_notice(db, 2, 'year', '2026')
        assert ns.total_count(db, 1) == 1
        assert ns.total_count(db, 2) == 1


class TestJobEmitIntegration:
    """job `_generate_one` 生成成功后 → 落一条 category=report 通知（接线回归）。

    monkeypatch 掉真实日历与净值就绪判定，让测试不依赖「今天是不是某周期最后交易日」，
    只验证「生成 → 通知落库」这一段接线。
    """

    def test_generate_one_emits_notice(self, db, make_position, make_transaction, monkeypatch):
        """造一份真实持仓 + 净值，`_generate_one` 生成后通知表多一条 report 通知。"""
        from app.domains.funds.models import DailyWorth
        from app.services.sync.jobs import periodic_review_job as job_mod

        # 买入日提前到周期前，让区间首日有基线（range_rate 可算）。
        d0 = dt.date(2026, 11, 20)
        pos = make_position(
            symbol='000031',
            name='通知测试基金',
            quantity=1000,
            avg_price=1.0,
            asset_type='fund',
            account_name='通知账户',
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
        for d, nav in [(d0, 1.0), (dt.date(2026, 11, 23), 1.0), (dt.date(2026, 11, 27), 1.1)]:
            db.add(DailyWorth(fund_code='000031', date=d, unit_nav=nav))
        db.commit()

        # 固定日历与净值就绪判定，隔离真实日期/交易日依赖。
        monkeypatch.setattr(job_mod, 'is_trading_day', lambda _d: True)
        job = job_mod.PeriodicReviewJob(db)
        monkeypatch.setattr(job, '_nav_ready', lambda _d: True)

        job._generate_one(1, 'week', '2026-W48')

        assert ns.total_count(db, 1) == 1
        row = ns.list_notifications(db, 1)[0]
        assert row.category == CATEGORY_REPORT
        assert row.source_type == SOURCE_TYPE_PERIODIC_REPORT
        assert '第48周周报' in row.title
        assert '%' in row.body  # 收益率可算，正文含百分比
