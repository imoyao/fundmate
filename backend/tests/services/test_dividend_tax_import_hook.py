# -*- coding: utf-8 -*-
"""导入完成后立刻复核红利税（#541）——**接线级**用例。

为什么单独一个文件钉这件事：扫描判据全绿，也可能一条提醒都没写出去
（AGENTS.md 那类「宿主没把 isDirty 接进守卫」的漏点）。用户的原话是
「不能漏提醒」——而漏提醒最可能的形态，就是这条链路根本没接上。

两条硬要求：

1. 本批导入里**有现金分红、没有扣税行** ⇒ 立刻有一条站内提醒（不等第二天定时）；
2. 本批自己就带了扣税行 ⇒ **一条都不许发**（刚记完就说「你没记」比不提醒更伤人）。
"""

from datetime import date

import pytest

from app.domains.notification.models import Notification
from app.services.importer.mappings import BusinessType
from app.services.importer.orchestrator import ImportOrchestrator


class _Record:
    """`StandardTransactionRecord` 的最小替身：钩子只读 symbol / business_type。"""

    def __init__(self, symbol: str, business_type: str):
        self.symbol = symbol
        self.business_type = business_type


class _FakeDb:
    """钩子测试只关心「有没有被调用、发了什么」，不需要真会话。"""

    def __init__(self):
        self.emitted = 0


@pytest.fixture
def orchestrator(db, make_position):
    make_position(
        symbol='600519',
        name='贵州茅台',
        asset_type='stock',
        account_name='测试账户',
        quantity=1000,
        avg_price=10.0,
        current_price=12.0,
    )
    return ImportOrchestrator(db, family_id=1)


def _seed_dividend(db, make_transaction, make_position):
    """库里已有一笔没配到税的现金分红（模拟「分红先到、税还没记」）。"""
    return make_transaction(
        position_id=None,
        ledger_id=None,
        txn_type='dividend',
        quantity=0,
        price=0,
        amount=500.0,
        confirm_date=date(2026, 6, 20),
        symbol='600519',
        notes='红利入账',
        asset_type='stock',
    )


class TestImportHook:
    def test_dividend_import_triggers_reminder(self, db, orchestrator, make_transaction):
        """本批导入了现金分红、没有扣税 ⇒ 立刻写一条提醒。"""
        _seed_dividend(db, make_transaction, None)
        orchestrator._refresh_dividend_tax_reminders([_Record('600519', BusinessType.DIVIDEND_CASH.code)])
        db.commit()
        rows = db.query(Notification).all()
        assert len(rows) == 1
        assert rows[0].source_type == 'dividend_tax_pending'

    def test_batch_with_its_own_tax_stays_silent(self, db, orchestrator, make_transaction):
        """同一批里带着扣税行 ⇒ 不复核（用户刚记的正是那笔税）。"""
        _seed_dividend(db, make_transaction, None)
        orchestrator._refresh_dividend_tax_reminders(
            [
                _Record('600519', BusinessType.DIVIDEND_CASH.code),
                _Record('600519', BusinessType.TAX.code),
            ]
        )
        db.commit()
        assert db.query(Notification).count() == 0

    def test_reinvest_only_import_stays_silent(self, db, orchestrator, make_transaction):
        """这一批只有红利再投 ⇒ 不发提醒（再投不产生现金，也就没有现金税）。"""
        orchestrator._refresh_dividend_tax_reminders([_Record('600519', BusinessType.DIVIDEND_REINVEST.code)])
        db.commit()
        assert db.query(Notification).count() == 0

    def test_buy_only_import_stays_silent(self, db, orchestrator, make_transaction):
        """买入批次不触发复核——导入路径不该做全库派生。"""
        _seed_dividend(db, make_transaction, None)
        orchestrator._refresh_dividend_tax_reminders([_Record('600519', BusinessType.BUY.code)])
        db.commit()
        assert db.query(Notification).count() == 0

    def test_other_symbol_dividend_does_not_leak_into_batch(self, db, orchestrator, make_transaction):
        """只复核本批涉及的标的：别的股票的旧分红不该借这次导入冒出来。"""
        make_transaction(
            position_id=None,
            ledger_id=None,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=900.0,
            confirm_date=date(2026, 6, 20),
            symbol='000001',
            notes='红利入账',
            asset_type='stock',
        )
        orchestrator._refresh_dividend_tax_reminders([_Record('600519', BusinessType.DIVIDEND_CASH.code)])
        db.commit()
        assert db.query(Notification).count() == 0
