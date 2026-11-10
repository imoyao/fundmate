# -*- coding: utf-8 -*-
"""账户级「累计盈亏」三段口径（2026-11-10）。

被测的是三件事，任何一件错了账面上都会对不上：

1. `realized_pnl_by_ledger` / `buy_fee_by_ledger` **扫流水**而不是扫持仓——
   清仓后持仓行还在（`ownership_status='cleared'`）却不进 `_load_user_assets`，
   按持仓汇总会把那笔已实现盈亏整个丢掉。这是本卡要修的原始 bug。
2. `get_ledger_pnl` 的 `total = realized + unrealized − buy_fee` 逐分成立；
3. `/api/ledgers/` 与 `/api/ledgers/<id>/summary/` 只在投资类账户上下发
   `realized_pnl` / `buy_fee` / `total_pnl`，bank / property **不出现这三个键**——
   写 0 会让用户以为真的不赚不亏，比不显示更误导。
"""

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.ledger_cumulative_pnl import buy_fee_by_ledger, realized_pnl_by_ledger
from app.services.summary_service import get_ledger_pnl


def _ledger(db, name, ledger_type='stock'):
    ledger = Ledger(name=name, ledger_type=ledger_type)
    db.add(ledger)
    db.commit()
    return ledger


def _txn(db, *, ledger_id, position_id=None, txn_type='buy', realized_pnl=0, fee=0):
    txn = Transaction(
        family_id=1,
        ledger_id=ledger_id,
        position_id=position_id,
        symbol='T1',
        symbol_norm='OTC:T1',
        txn_type=txn_type,
        realized_pnl=realized_pnl,
        fee=fee,
    )
    db.add(txn)
    db.commit()
    return txn


class TestByLedgerAggregators:
    def test_realized_grouped_by_ledger(self, db):
        a = _ledger(db, 'A')
        b = _ledger(db, 'B')
        _txn(db, ledger_id=a.id, txn_type='sell', realized_pnl=12345)
        _txn(db, ledger_id=a.id, txn_type='sell', realized_pnl=-2345)
        _txn(db, ledger_id=b.id, txn_type='sell', realized_pnl=100)

        assert realized_pnl_by_ledger(db, 1)[a.id] == 10000
        assert realized_pnl_by_ledger(db, 1)[b.id] == 100

    def test_null_ledger_falls_into_sentinel_zero(self, db):
        s = _ledger(db, 'S')
        _txn(db, ledger_id=s.id, txn_type='sell', realized_pnl=7)
        _txn(db, ledger_id=None, txn_type='sell', realized_pnl=11)

        result = realized_pnl_by_ledger(db, 1)
        assert result[0] == 11
        assert result[s.id] == 7

    def test_ledger_ids_slice_semantics(self, db):
        a = _ledger(db, 'A')
        b = _ledger(db, 'B')
        _txn(db, ledger_id=a.id, txn_type='sell', realized_pnl=5)
        _txn(db, ledger_id=b.id, txn_type='sell', realized_pnl=9)

        assert realized_pnl_by_ledger(db, 1, [a.id]) == {a.id: 5}
        # 空集合 = 该成员无账户 ⇒ 空表（调用方据此得 0，而不是全家庭）
        assert realized_pnl_by_ledger(db, 1, []) == {}

    def test_buy_fee_only_counts_buy_side(self, db):
        a = _ledger(db, 'A')
        _txn(db, ledger_id=a.id, txn_type='buy', fee=500)
        _txn(db, ledger_id=a.id, txn_type='deposit', fee=200)
        # 卖出费已在 realized_pnl 里扣过，这里再收就是双扣
        _txn(db, ledger_id=a.id, txn_type='sell', fee=900)

        assert buy_fee_by_ledger(db, 1)[a.id] == 700


class TestGetLedgerPnlIncludesClearedPositions:
    """本卡的核心回归：已清仓持仓的已实现盈亏不能从账户上消失。"""

    def test_realized_of_cleared_position_is_kept(self, db, make_position):
        ledger = _ledger(db, '银河')
        # 仍在持有的标的
        alive = make_position(
            symbol='A1',
            name='持有中',
            ledger_id=ledger.id,
            quantity=200,
            avg_price=5.0,
            current_price=6.0,
        )
        # 已清仓的标的：持仓行还在，但 ownership_status 不是 active ⇒ 不进 _load_user_assets
        cleared = Position(
            family_id=1,
            ledger_id=ledger.id,
            symbol='B1',
            name='已清仓',
            quantity=0,
            avg_price=Money.yuan_to_price_units(10.0),
            current_price=Money.yuan_to_price_units(0.0),
            ownership_status='cleared',
        )
        db.add(cleared)
        db.commit()
        db.refresh(cleared)

        # 已实现只留在流水上：买 1000 元付 5 元佣金，卖光亏 300 元（费已扣在 realized 里）
        _txn(db, ledger_id=ledger.id, position_id=cleared.id, txn_type='buy', fee=500)
        _txn(db, ledger_id=ledger.id, position_id=cleared.id, txn_type='sell', realized_pnl=-30000)
        # 持有中的那笔顺带有一笔买入费
        _txn(db, ledger_id=ledger.id, position_id=alive.id, txn_type='buy', fee=100)

        totals = get_ledger_pnl(db, 1)[ledger.id]

        # 若 realized 走 position 级求和，这里会是 0——清仓那笔的 -300 被丢掉
        assert totals['realized_pnl_cents'] == -30000
        assert totals['buy_fee_cents'] == 600
        assert totals['unrealized_pnl_cents'] == 20000  # (6 − 5) × 200
        assert totals['total_pnl_cents'] == -30000 + 20000 - 600

    def test_ledger_with_only_cleared_positions_still_appears(self, db):
        ledger = _ledger(db, '全清了')
        _txn(db, ledger_id=ledger.id, txn_type='sell', realized_pnl=-5000)

        totals = get_ledger_pnl(db, 1)
        assert ledger.id in totals
        assert totals[ledger.id]['realized_pnl_cents'] == -5000
        assert totals[ledger.id]['unrealized_pnl_cents'] == 0


class TestApiExposesCumulativePnl:
    def _seed(self, client, db):
        ledger = _ledger(db, '测试证券')
        make = Position(
            family_id=1,
            ledger_id=ledger.id,
            symbol='A1',
            name='持有中',
            quantity=Money.shares_to_min_unit(200),
            avg_price=Money.yuan_to_price_units(5.0),
            current_price=Money.yuan_to_price_units(6.0),
        )
        db.add(make)
        db.commit()
        _txn(db, ledger_id=ledger.id, position_id=make.id, txn_type='buy', fee=500)
        _txn(db, ledger_id=ledger.id, txn_type='sell', realized_pnl=-30000)
        return ledger

    def test_list_ledgers_adds_three_fields_and_adds_up(self, client, db):
        ledger = self._seed(client, db)

        resp = client.get('/api/ledgers/')
        assert resp.status_code == 200
        target = next(x for x in resp.get_json()['data'] if x['id'] == ledger.id)

        assert target['pnl'] == 200.0  # 持仓盈亏：(6−5)×200
        assert target['realized_pnl'] == -300.0
        assert target['buy_fee'] == 5.0
        # 三个数字必须能和卡片上已有的持仓盈亏相加：200 + (−300) − 5
        assert target['total_pnl'] == -105.0
        assert target['total_pnl'] == round(target['pnl'] + target['realized_pnl'] - target['buy_fee'], 2)

    def test_ledger_summary_adds_three_fields_and_adds_up(self, client, db):
        ledger = self._seed(client, db)

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']

        assert data['position_pnl'] == 200.0
        assert data['realized_pnl'] == -300.0
        assert data['buy_fee'] == 5.0
        assert data['total_pnl'] == -105.0
        # 既有字段不得被本卡改动（cumulative_return 仍按原口径下发）
        assert 'cumulative_return' in data

    def test_bank_ledger_has_no_cumulative_fields(self, client, db):
        ledger = _ledger(db, '某银行', ledger_type='bank')

        listed = next(x for x in client.get('/api/ledgers/').get_json()['data'] if x['id'] == ledger.id)
        for key in ('realized_pnl', 'buy_fee', 'total_pnl'):
            assert key not in listed, f'bank 账户不应下发 {key}（写 0 会被读成「不赚不亏」）'

        detail = client.get(f'/api/ledgers/{ledger.id}/summary/').get_json()['data']
        for key in ('realized_pnl', 'buy_fee', 'total_pnl'):
            assert key not in detail

    def test_property_ledger_has_no_cumulative_fields(self, client, db):
        ledger = _ledger(db, '某套房', ledger_type='property')

        listed = next(x for x in client.get('/api/ledgers/').get_json()['data'] if x['id'] == ledger.id)
        for key in ('realized_pnl', 'buy_fee', 'total_pnl'):
            assert key not in listed

        detail = client.get(f'/api/ledgers/{ledger.id}/summary/').get_json()['data']
        for key in ('realized_pnl', 'buy_fee', 'total_pnl'):
            assert key not in detail
