# -*- coding: utf-8 -*-
"""#863 2-A：账户「确认中」货基申购预估端点测试（UI 标注过渡，非账本口径）。"""

import datetime as dt

from app.core.money import Money
from app.core.time_utils import today_shanghai
from app.domains.ledgers.models import Ledger
from app.domains.transactions.models import Transaction
from app.services.ledger_service import LedgerService


def _make_ledger(db, name='货基账户', family_id=1):
    ledger = Ledger(name=name, ledger_type='fund', family_id=family_id)
    db.add(ledger)
    db.flush()
    return ledger


def _pending_txn(db, ledger, amount_yuan, confirm_date, family_id=1):
    db.add(
        Transaction(
            ledger_id=ledger.id,
            family_id=family_id,
            asset_type='money_fund',
            txn_type='buy',
            amount=Money.yuan_to_cents(amount_yuan),
            trade_date=dt.datetime.combine(confirm_date - dt.timedelta(days=1), dt.time(10, 0)),
            confirm_date=confirm_date,
            status='success',
            position_id=None,
        )
    )
    db.flush()


class TestPendingMoneyFundEstimate:
    def test_future_confirm_flows_are_estimated(self, db):
        ledger = _make_ledger(db)
        _pending_txn(db, ledger, 500.0, today_shanghai() + dt.timedelta(days=1))  # 明日确认
        _pending_txn(db, ledger, 300.0, today_shanghai() + dt.timedelta(days=2))  # 后日确认
        db.commit()

        data = LedgerService.get_pending_money_fund_estimate(db, ledger.id, ledger.family_id)
        assert data['pending_amount_cents'] == Money.yuan_to_cents(800)
        assert data['estimated_confirm_date'] == (today_shanghai() + dt.timedelta(days=1)).isoformat()

    def test_confirmed_flows_not_counted(self, db):
        ledger = _make_ledger(db)
        _pending_txn(db, ledger, 500.0, today_shanghai() - dt.timedelta(days=1))  # 昨日已确认
        db.commit()

        data = LedgerService.get_pending_money_fund_estimate(db, ledger.id, ledger.family_id)
        assert data['pending_amount_cents'] == 0
        assert data['estimated_confirm_date'] is None

    def test_family_isolation(self, db):
        ledger_a = _make_ledger(db, family_id=1)
        _pending_txn(db, ledger_a, 500.0, today_shanghai() + dt.timedelta(days=1), family_id=1)
        ledger_b = _make_ledger(db, family_id=2)
        _pending_txn(db, ledger_b, 999.0, today_shanghai() + dt.timedelta(days=1), family_id=2)
        db.commit()

        data = LedgerService.get_pending_money_fund_estimate(db, ledger_a.id, ledger_a.family_id)
        assert data['pending_amount_cents'] == Money.yuan_to_cents(500)


class TestPendingEstimateEndpoint:
    def test_endpoint_returns_estimate(self, client, db):
        ledger = _make_ledger(db)
        _pending_txn(db, ledger, 500.0, today_shanghai() + dt.timedelta(days=1))
        db.commit()

        resp = client.get(f'/api/ledgers/{ledger.id}/pending-estimate/')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['message'] == 'ok'
        assert body['data']['pending_amount_cents'] == Money.yuan_to_cents(500)
        assert 'note' in body['data']

    def test_endpoint_unknown_ledger_404(self, client, db):
        resp = client.get('/api/ledgers/999999/pending-estimate/')
        assert resp.status_code == 404
