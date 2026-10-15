# -*- coding: utf-8 -*-
"""净值缺失先记账（nav_pending）+ nav_backfill 回填 —— 服务层端到端。

锁定十件事：
1. 净值缺失创建 → 无历史净值时占位 1.0、份额按金额暂算、entry_status='pending_nav'；
2. 库内有 ≤nav_date 历史净值 → 用最近净值占位；未来净值不得泄漏为占位价；
3. 竞态：库内已有 nav_date 当日官方净值 → 直接用官方值、不标 pending；
4. 手动份额 + 净值缺失 → 保留手动份额、只用占位价、extra.shares_manual=True；
5. 回填命中（自动型）→ 份额=金额/官方净值、价格=官方净值、金额=价格×份额、
   清标记、持仓份额/均价/现价同步；
6. 回填命中（手动型）→ 份额不动、只校正净值与金额；
7. 未命中官方净值 → 保持 pending 等下一轮；
8. 手动编辑份额 → 清 pending（手动优先），此后回填不再覆盖；持仓份额同步；
9. 货基 nav_pending → 净值恒 1.0 直接定值、不标 pending；
10. 幂等/空跑：无 pending 空跑 success；已回填流水重跑零副作用。
"""

import json
from datetime import date

import pytest

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services import ledger_write_service
from app.services.position_service import PositionService
from app.services.sync.jobs.nav_backfill_job import NavBackfillJob

LEDGER_NAME = '净值测试基金账户'
TRADE_DAY = date(2026, 10, 14)


def _make_ledger(db):
    ledger = db.query(Ledger).filter_by(name=LEDGER_NAME, family_id=1).first()
    if ledger is None:
        ledger = Ledger(name=LEDGER_NAME, ledger_type='fund', family_id=1)
        db.add(ledger)
        db.flush()
    return ledger


def _seed_nav(db, code, day, nav):
    db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav))
    db.commit()


def _buy_pending(db, ledger, **overrides):
    data = {
        'symbol': '000001',
        'name': '华夏成长混合',
        'asset_type': 'fund',
        'ledger_id': ledger.id,
        'account_name': LEDGER_NAME,
        'family_id': 1,
        'op_type': 'buy',
        'amount': 10000,
        'trade_date': TRADE_DAY,
        'confirm_date': TRADE_DAY,
        'nav_pending': True,
        'nav_date': '2026-10-14',
    }
    data.update(overrides)
    return PositionService.process_buy_or_deposit(db, data)


def _txn_of(db, pos):
    return db.query(Transaction).filter_by(position_id=pos.id).one()


class TestNavPendingCreation:
    def test_no_history_placeholder_1(self, db):
        """无任何历史净值 → 占位 1.0、份额=金额、标 pending_nav。"""
        ledger = _make_ledger(db)
        pos = _buy_pending(db, ledger)
        txn = _txn_of(db, pos)

        assert txn.entry_status == 'pending_nav'
        assert json.loads(txn.extra) == {
            'nav_pending': True,
            'nav_date': '2026-10-14',
            'shares_manual': False,
        }
        # 占位价 1.0：份额 = 10000 / 1.0 = 10000 份
        assert float(Money.price_units_to_yuan(txn.price)) == pytest.approx(1.0)
        assert float(Money.min_unit_to_shares(txn.quantity)) == pytest.approx(10000.0)
        assert txn.amount == Money.yuan_to_cents(10000)
        # 持仓与流水同步（占位口径）
        assert pos.quantity == Money.shares_to_min_unit(10000)
        assert pos.avg_price == Money.yuan_to_price_units(1.0)

    def test_recent_history_used_as_placeholder(self, db):
        """≤nav_date 的最近历史净值做占位（非 1.0）。"""
        ledger = _make_ledger(db)
        _seed_nav(db, '000001', date(2026, 10, 10), '2.000000')

        pos = _buy_pending(db, ledger)
        txn = _txn_of(db, pos)

        assert txn.entry_status == 'pending_nav'
        # 占位价 2.0：份额 = 10000 / 2.0 = 5000 份
        assert float(Money.price_units_to_yuan(txn.price)) == pytest.approx(2.0)
        assert float(Money.min_unit_to_shares(txn.quantity)) == pytest.approx(5000.0)

    def test_future_nav_not_leaked(self, db):
        """晚于 nav_date 的净值不得泄漏为占位价（只能取 ≤nav_date）。"""
        ledger = _make_ledger(db)
        _seed_nav(db, '000001', date(2026, 10, 15), '9.900000')

        pos = _buy_pending(db, ledger)
        txn = _txn_of(db, pos)

        assert txn.entry_status == 'pending_nav'
        assert float(Money.price_units_to_yuan(txn.price)) == pytest.approx(1.0)

    def test_exact_official_resolves_immediately(self, db):
        """竞态：提交时官方净值已落库 → 直接用官方值，一次到位不标 pending。"""
        ledger = _make_ledger(db)
        _seed_nav(db, '000001', TRADE_DAY, '3.000000')

        pos = _buy_pending(db, ledger)
        txn = _txn_of(db, pos)

        assert txn.entry_status is None
        assert txn.extra is None
        assert float(Money.price_units_to_yuan(txn.price)) == pytest.approx(3.0)
        # 份额 = round(10000 / 3, 4) = 3333.3333 份
        assert float(Money.min_unit_to_shares(txn.quantity)) == pytest.approx(3333.3333)

    def test_manual_shares_kept_with_placeholder(self, db):
        """手动份额是权威值：占位只补价格，份额不动、标 shares_manual=True。"""
        ledger = _make_ledger(db)
        _seed_nav(db, '000001', date(2026, 10, 10), '2.000000')

        pos = _buy_pending(db, ledger, quantity=400, shares_manual=True)
        txn = _txn_of(db, pos)

        assert txn.entry_status == 'pending_nav'
        assert json.loads(txn.extra)['shares_manual'] is True
        assert float(Money.price_units_to_yuan(txn.price)) == pytest.approx(2.0)
        assert float(Money.min_unit_to_shares(txn.quantity)) == pytest.approx(400.0)

    def test_money_fund_resolves_at_once(self, db):
        """货基净值恒为 1.0（#1233）：nav_pending 直接定值，不标 pending。"""
        ledger = _make_ledger(db)
        pos = PositionService.process_buy_or_deposit(
            db,
            {
                'symbol': '000198',
                'name': '天弘余额宝',
                'asset_type': 'money_fund',
                'ledger_id': ledger.id,
                'account_name': LEDGER_NAME,
                'family_id': 1,
                'op_type': 'buy',
                'amount': 5000,
                'trade_date': TRADE_DAY,
                'confirm_date': TRADE_DAY,
                'nav_pending': True,
                'nav_date': '2026-10-14',
            },
            force_create_position=True,
        )
        txn = _txn_of(db, pos)

        assert txn.entry_status is None
        assert float(Money.price_units_to_yuan(txn.price)) == pytest.approx(1.0)
        assert float(Money.min_unit_to_shares(txn.quantity)) == pytest.approx(5000.0)


class TestNavBackfillJob:
    @pytest.fixture
    def job(self, db):
        return NavBackfillJob(db)

    def test_backfill_auto_shares(self, job, db):
        """自动型：官方到位 → 份额=金额/官方净值、价格/金额/持仓同步、清标记。"""
        ledger = _make_ledger(db)
        pos = _buy_pending(db, ledger)
        txn = _txn_of(db, pos)
        _seed_nav(db, '000001', TRADE_DAY, '2.500000')

        result = job.run(full_sync=False, targets=None)
        assert result['status'] == 'success'
        assert result['stats'].get('success', 0) == 1

        txn = _txn_of(db, pos)
        assert txn.entry_status is None
        assert float(Money.price_units_to_yuan(txn.price)) == pytest.approx(2.5)
        # 份额 = 10000 / 2.5 = 4000 份；金额 = 2.5 × 4000 = 10000 元（净投入守恒）
        assert float(Money.min_unit_to_shares(txn.quantity)) == pytest.approx(4000.0)
        assert txn.amount == Money.yuan_to_cents(10000)

        extra = json.loads(txn.extra)
        assert extra['nav_pending'] is False
        assert extra.get('backfilled_at')

        pos = db.query(Position).filter_by(id=pos.id).one()
        assert pos.quantity == Money.shares_to_min_unit(4000)
        assert pos.avg_price == Money.yuan_to_price_units(2.5)
        assert pos.current_price == Money.yuan_to_price_units(2.5)

    def test_backfill_manual_shares_untouched(self, job, db):
        """手动型：份额保持用户录入值，只校正净值与金额。"""
        ledger = _make_ledger(db)
        pos = _buy_pending(db, ledger, quantity=400, shares_manual=True)
        _seed_nav(db, '000001', TRADE_DAY, '2.500000')

        job.run(full_sync=False, targets=None)

        txn = _txn_of(db, pos)
        assert txn.entry_status is None
        assert float(Money.min_unit_to_shares(txn.quantity)) == pytest.approx(400.0), '手动份额不得被回填覆盖'
        assert float(Money.price_units_to_yuan(txn.price)) == pytest.approx(2.5)
        # 金额 = 2.5 × 400 = 1000 元
        assert txn.amount == Money.yuan_to_cents(1000)

    def test_missed_official_stays_pending(self, job, db):
        """未命中官方净值 → 保持 pending，等下一轮。"""
        ledger = _make_ledger(db)
        pos = _buy_pending(db, ledger)
        txn_before = _txn_of(db, pos)

        result = job.run(full_sync=False, targets=None)
        assert result['status'] == 'success'
        assert result['stats'].get('success', 0) == 0

        txn = _txn_of(db, pos)
        assert txn.entry_status == 'pending_nav'
        assert txn.quantity == txn_before.quantity

    def test_job_idempotent_after_backfill(self, job, db):
        """已回填流水不再是 pending，重跑零副作用。"""
        ledger = _make_ledger(db)
        pos = _buy_pending(db, ledger)
        _seed_nav(db, '000001', TRADE_DAY, '2.500000')
        job.run(full_sync=False, targets=None)
        first = _txn_of(db, pos)

        job.run(full_sync=False, targets=None)
        second = _txn_of(db, pos)
        assert second.quantity == first.quantity
        assert second.price == first.price
        assert second.amount == first.amount
        assert second.entry_status is None

    def test_empty_run_success(self, job, db):
        result = job.run(full_sync=False, targets=None)
        assert result['status'] == 'success'
        assert result['stats'].get('success', 0) == 0


class TestManualEditPriority:
    def test_quantity_edit_clears_pending(self, db):
        """手动编辑份额 → 清 pending、记 shares_manual；持仓份额同步。"""
        ledger = _make_ledger(db)
        pos = _buy_pending(db, ledger)
        txn = _txn_of(db, pos)

        ledger_write_service.update_ledger_transaction(db, ledger, txn, {'quantity': 410})

        assert txn.entry_status is None
        extra = json.loads(txn.extra)
        assert extra['nav_pending'] is False
        assert extra['shares_manual'] is True
        pos = db.query(Position).filter_by(id=pos.id).one()
        assert pos.quantity == Money.shares_to_min_unit(410), '份额微调必须同步进持仓'

    def test_backfill_respects_manual_edit(self, db):
        """清标后官方净值到位，回填不得覆盖手动结果。"""
        ledger = _make_ledger(db)
        pos = _buy_pending(db, ledger)
        txn = _txn_of(db, pos)
        ledger_write_service.update_ledger_transaction(db, ledger, txn, {'quantity': 410})
        price_before = txn.price
        db.commit()

        _seed_nav(db, '000001', TRADE_DAY, '2.500000')
        NavBackfillJob(db).run(full_sync=False, targets=None)

        txn = _txn_of(db, pos)
        assert float(Money.min_unit_to_shares(txn.quantity)) == pytest.approx(410.0)
        assert txn.price == price_before
