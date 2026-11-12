# -*- coding: utf-8 -*-
"""逆回购到期回款的服务层判据（#3087 / D114）。

背景：逆回购不建持仓、按孤儿流水记账，导入只带来「买入」——真库 4 笔全是 `buy`，
202,000.84 元永远在途，类现金只增不减、总资产把它连同回到现金账户的那笔钱算两遍。

这里的每条判据都对应一种「回款写错了钱就错了」的形态：
- 本金算错（把收益桶当本金）⇒ 回款金额大于实际出借；
- 没有幂等 ⇒ 重复点两下凭空多出一笔回款；
- 跨标的混算 ⇒ 结清 A 却把 B 的在途额也冲掉；
- 利息不独立成行 ⇒ 累计收益少算这笔钱。
"""

from datetime import datetime

import pytest

from app.domains.ledgers.models import Ledger
from app.domains.transactions.models import Transaction
from app.services import cash_like_settle as svc
from app.services.summary_service import orphan_cash_like_breakdown

SETTLE_DAY = datetime(2026, 11, 12)


def _ledger(db) -> Ledger:
    ledger = Ledger(name='券商', ledger_type='stock', family_id=1)
    db.add(ledger)
    db.flush()
    return ledger


def _buy(db, ledger, symbol='SH204001', name='GC001', amount=2100002) -> Transaction:
    txn = Transaction(
        family_id=1,
        ledger_id=ledger.id,
        txn_type='buy',
        asset_type='reverse_repo',
        symbol=symbol,
        position_name=name,
        amount=amount,
        status='success',
    )
    db.add(txn)
    db.flush()
    return txn


class TestOutstanding:
    def test_counts_only_principal_bucket(self, db):
        """收益行不算在途本金——否则回款会把收益一起「还」回去。"""
        ledger = _ledger(db)
        _buy(db, ledger)
        db.add(
            Transaction(
                family_id=1,
                ledger_id=ledger.id,
                txn_type='dividend',
                asset_type='reverse_repo',
                symbol='SH204001',
                position_name='GC001',
                amount=12300,
                is_income=True,
                status='success',
            )
        )
        db.flush()

        assert svc.outstanding_cents(db, 1, ledger.id, 'SH204001') == 2100002

    def test_ignores_other_symbols(self, db):
        ledger = _ledger(db)
        _buy(db, ledger, symbol='SH204001', amount=2100002)
        _buy(db, ledger, symbol='SH204007', name='GC007', amount=6000030)

        assert svc.outstanding_cents(db, 1, ledger.id, 'SH204001') == 2100002

    def test_position_linked_flows_not_counted(self, db):
        """已归到持仓上的流水不是孤儿流水，不进类现金口径。"""
        ledger = _ledger(db)
        txn = _buy(db, ledger)
        txn.position_id = 999
        db.flush()

        assert svc.outstanding_cents(db, 1, ledger.id, 'SH204001') == 0


class TestSettle:
    def test_settle_offsets_principal_and_books_interest(self, db):
        ledger = _ledger(db)
        _buy(db, ledger)

        result = svc.settle_reverse_repo(
            db, family_id=1, ledger_id=ledger.id, symbol='SH204001', settle_date=SETTLE_DAY, interest_cents=12300
        )

        assert result['settled_amount'] == 21000.02
        assert result['interest_amount'] == 123.0
        assert svc.outstanding_cents(db, 1, ledger.id, 'SH204001') == 0

        rows = db.query(Transaction).filter(Transaction.notes.like('逆回购到期回款%')).all()
        assert {row.txn_type for row in rows} == {'sell', 'dividend'}
        sell = next(row for row in rows if row.txn_type == 'sell')
        assert sell.amount == 2100002
        assert sell.position_id is None, '回款行仍是孤儿流水（不建持仓）'
        assert sell.source == 'manual'
        interest = next(row for row in rows if row.txn_type == 'dividend')
        assert interest.is_income is True, '利息是收益行，不能混进本金桶'

    def test_breakdown_shows_zero_principal_after_settle(self, db):
        """账户页读的是 `orphan_cash_like_breakdown`——回款后本金必须归零，收益保留。"""
        ledger = _ledger(db)
        _buy(db, ledger)

        svc.settle_reverse_repo(
            db, family_id=1, ledger_id=ledger.id, symbol='SH204001', settle_date=SETTLE_DAY, interest_cents=12300
        )
        items, net_cents, income_cents = orphan_cash_like_breakdown(db, 1, ledger.id)

        assert net_cents == 0
        assert income_cents == 12300
        assert items[0]['net_amount'] == 0

    def test_second_settle_is_rejected(self, db):
        """幂等靠净额归零：重复结清必须被拒，而不是凭空再写一笔回款。"""
        ledger = _ledger(db)
        _buy(db, ledger)
        svc.settle_reverse_repo(db, family_id=1, ledger_id=ledger.id, symbol='SH204001', settle_date=SETTLE_DAY)

        with pytest.raises(svc.SettleError) as err:
            svc.settle_reverse_repo(db, family_id=1, ledger_id=ledger.id, symbol='SH204001', settle_date=SETTLE_DAY)

        assert '没有在途本金' in err.value.message
        assert db.query(Transaction).filter(Transaction.notes.like('逆回购到期回款%')).count() == 1

    def test_settle_without_flows_is_rejected(self, db):
        ledger = _ledger(db)

        with pytest.raises(svc.SettleError):
            svc.settle_reverse_repo(db, family_id=1, ledger_id=ledger.id, symbol='SH204001', settle_date=SETTLE_DAY)

    def test_negative_interest_is_rejected(self, db):
        ledger = _ledger(db)
        _buy(db, ledger)

        with pytest.raises(svc.SettleError) as err:
            svc.settle_reverse_repo(
                db, family_id=1, ledger_id=ledger.id, symbol='SH204001', settle_date=SETTLE_DAY, interest_cents=-1
            )

        assert '利息不能为负' in err.value.message

    def test_settle_does_not_touch_trade_date_of_history(self, db):
        """**禁止批量回填 `trade_date`**：历史行一个字都不改（补它等于替用户猜交易日）。"""
        ledger = _ledger(db)
        buy = _buy(db, ledger)
        assert buy.trade_date is None

        svc.settle_reverse_repo(db, family_id=1, ledger_id=ledger.id, symbol='SH204001', settle_date=SETTLE_DAY)

        db.refresh(buy)
        assert buy.trade_date is None, '历史流水不得被回填'
