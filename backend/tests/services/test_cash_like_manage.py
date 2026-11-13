# -*- coding: utf-8 -*-
"""账外类现金流水管理（补录 / 到期回款 / 增删改 / 归置）测试。

验收项来自「A 方案 + 把 C 的『数据可核对』并进来、砍掉批量回填 trade_date」：
- 口径不动：净额仍由 `summary_service.orphan_flow_delta` 单点判定；
- 补录「到期回款」能让逆回购的只增不减净额真正减下去；
- 归置能表达「这批流水已由某持仓体现」，且只改 `position_id`；
- 禁止批量回填 `trade_date` / 重算 `import_hash`。
"""

import json
import uuid
from datetime import date, datetime

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services import cash_like_manage as svc
from app.services import summary_service
from app.services.trading import TransactionService

FAMILY = 1


def _ledger(db, name='同花顺（银河证券）'):
    ledger = Ledger(name=name, ledger_type='stock')
    db.add(ledger)
    db.commit()
    return ledger


def _position(db, ledger, *, name='银河水星现金添利货币市场基金', symbol='026029'):
    pos = Position(
        name=name,
        symbol=symbol,
        ledger_id=ledger.id,
        account_name=ledger.name,
        asset_type='fund',
        quantity=Money.shares_to_min_unit(22757.85),
        family_id=FAMILY,
    )
    db.add(pos)
    db.commit()
    return pos


def _orphan(
    db,
    ledger,
    *,
    asset_type='reverse_repo',
    txn_type='buy',
    yuan=1000.0,
    symbol=None,
    confirm_date=date(2025, 9, 29),
):
    txn = TransactionService.create(
        db,
        ledger_id=ledger.id,
        account_name=ledger.name,
        family_id=FAMILY,
        asset_type=asset_type,
        txn_type=txn_type,
        amount=Money.yuan_to_cents(yuan),
        quantity=0,
        price=0,
        fee=0,
        status='success',
        entry_status='orphan',
        position_id=None,
        position_name='GC001',
        symbol=symbol,
        confirm_date=confirm_date,
        import_hash=f'legacy|{uuid.uuid4().hex}',
    )
    db.commit()
    return txn


def _net_cents(db, ledger):
    net_map, _ = summary_service.orphan_money_fund_totals_by_ledger(db, FAMILY)
    return net_map.get(ledger.id, 0)


def _payload(ledger, **overrides):
    data = {
        'ledger_id': ledger.id,
        'asset_type': 'reverse_repo',
        'confirm_date': '2025-10-08',
        'position_name': 'GC001',
        'amount': 1000.0,
        'client_token': uuid.uuid4().hex,
    }
    data.update(overrides)
    return data


class TestCaliberParity:
    def test_asset_types_match_summary_service(self):
        """两份类型常量漂移 ⇒ 管理入口与净额桶会各自筛掉对方的行。"""
        assert svc.CASH_LIKE_ASSET_TYPES == summary_service._ORPHAN_FLOW_ASSET_TYPES


class TestListFlows:
    def test_only_orphan_cash_like_rows(self, db):
        ledger = _ledger(db)
        orphan = _orphan(db, ledger)
        attached = _orphan(db, ledger, asset_type='money_fund')
        attached.position_id = 999
        db.commit()

        result = svc.list_flows(db, FAMILY, q='GC001')
        assert result['total'] == 1
        assert result['items'][0]['id'] == orphan.id
        assert result['items'][0]['asset_type'] == 'reverse_repo'

    def test_reconciled_rows_visible_when_asked(self, db):
        ledger = _ledger(db)
        target = _position(db, ledger)
        orphan = _orphan(db, ledger)
        svc.reconcile_flows(
            db, FAMILY,
            {'action': 'attach', 'transaction_ids': [orphan.id], 'target_position_id': target.id},
        )
        assert svc.list_flows(db, FAMILY)['total'] == 0
        listed = svc.list_flows(db, FAMILY, include_reconciled=True)
        assert listed['total'] == 1
        assert listed['items'][0]['reconciled']['position_id'] == target.id


class TestCreateFlows:
    def test_repayment_reduces_net_and_is_idempotent(self, db):
        """逆回购只有 buy 时净额恒为正在途；补回款后必须真的减下去。"""
        ledger = _ledger(db)
        _orphan(db, ledger, yuan=202000.84, confirm_date=date(2025, 9, 29))
        assert _net_cents(db, ledger) == Money.yuan_to_cents(202000.84)

        token = uuid.uuid4().hex
        payload = _payload(ledger, kind='repayment', amount=202000.84, interest=12.34, client_token=token)
        first = svc.create_flows(db, FAMILY, payload)
        assert first['created'] == 2
        assert _net_cents(db, ledger) == 0

        second = svc.create_flows(db, FAMILY, payload)
        assert second['created'] == 0 and second['reused'] == 2
        assert _net_cents(db, ledger) == 0

        income_map = summary_service.orphan_money_fund_totals_by_ledger(db, FAMILY)[1]
        assert income_map.get(ledger.id, 0) == Money.yuan_to_cents(12.34)

    def test_new_row_has_no_derived_legacy_date_and_keeps_import_hash_namespace(self, db):
        """新行的 trade_date 沿用唯一写入口径；不重算、不占用既有哈希空间。"""
        ledger = _ledger(db)
        old = _orphan(db, ledger, confirm_date=date(2023, 2, 28))
        old.trade_date = None  # 模拟真库 162 笔「无交易日」的存量行
        old_hash = old.import_hash
        db.commit()

        svc.create_flows(db, FAMILY, _payload(ledger, kind='sell'))
        db.refresh(old)
        assert old.trade_date is None
        assert old.import_hash == old_hash

        rows = svc.list_flows(db, FAMILY)['items']
        new_row = next(r for r in rows if r['is_manual'])
        assert new_row['confirm_date'] == '2025-10-08'
        assert new_row['trade_date'] == '2025-10-08'  # prepare_write_kwargs 的既有兜底，不是回填
        assert new_row['bucket'] == 'net'

    def test_symbol_inference_is_marked(self, db):
        ledger = _ledger(db)
        svc.create_flows(db, FAMILY, _payload(ledger, symbol='026029', symbol_inferred=True))
        row = svc.list_flows(db, FAMILY)['items'][0]
        assert row['symbol'] == '026029'
        assert row['symbol_inferred'] is True


class TestUpdateAndDelete:
    def test_update_never_touches_import_hash_or_trade_date_when_blank(self, db):
        ledger = _ledger(db)
        txn = _orphan(db, ledger)
        txn.trade_date = None
        old_hash = txn.import_hash
        db.commit()

        row = svc.update_flow(
            db, FAMILY, txn.id,
            {'amount': 500.0, 'symbol': 'SH204001', 'notes': '核对后修正', 'trade_date': ''},
        )
        assert row['amount'] == 500.0
        assert row['symbol'] == 'SH204001'
        assert row['trade_date'] is None
        db.refresh(txn)
        assert txn.import_hash == old_hash
        assert txn.trade_date is None

    def test_user_can_explicitly_fill_trade_date_single_row(self, db):
        """D99 允许「用户显式补录自己知道的历史」，但只限单笔。"""
        ledger = _ledger(db)
        txn = _orphan(db, ledger)
        txn.trade_date = None
        db.commit()
        row = svc.update_flow(db, FAMILY, txn.id, {'trade_date': '2023-02-27'})
        assert row['trade_date'] == '2023-02-27'
        assert isinstance(txn.trade_date, datetime)

    def test_forbidden_fields_rejected(self, db):
        ledger = _ledger(db)
        txn = _orphan(db, ledger)
        with pytest.raises(ValueError, match='不可修改'):
            svc.update_flow(db, FAMILY, txn.id, {'import_hash': 'x'})
        with pytest.raises(ValueError, match='不可修改'):
            svc.update_flow(db, FAMILY, txn.id, {'trade_date': '2023-01-01', 'asset_type': 'stock'})

    def test_delete_orphan_row(self, db):
        ledger = _ledger(db)
        txn = _orphan(db, ledger)
        svc.delete_flow(db, FAMILY, txn.id)
        assert svc.list_flows(db, FAMILY)['total'] == 0
        assert _net_cents(db, ledger) == 0


class TestReconcile:
    def test_attach_only_changes_position_id_and_removes_double_count(self, db):
        """归置＝表达「这批流水已由某持仓体现」；金额 / 日期 / 代码 / 哈希一个都不动。"""
        ledger = _ledger(db)
        target = _position(db, ledger)
        txn = _orphan(db, ledger)
        txn.symbol = None
        txn.trade_date = None
        old_hash = txn.import_hash
        db.commit()
        assert _net_cents(db, ledger) == Money.yuan_to_cents(1000.0)

        result = svc.reconcile_flows(
            db, FAMILY,
            {'action': 'attach', 'transaction_ids': [txn.id], 'target_position_id': target.id},
        )
        assert result['changed'] == 1
        assert _net_cents(db, ledger) == 0

        db.refresh(txn)
        assert txn.position_id == target.id
        assert txn.amount == Money.yuan_to_cents(1000.0)
        assert txn.trade_date is None
        assert txn.symbol is None
        assert txn.import_hash == old_hash
        extra = json.loads(txn.extra)
        assert extra[svc.RECONCILED_KEY]['position_id'] == target.id

    def test_detach_returns_to_orphan_bucket(self, db):
        ledger = _ledger(db)
        target = _position(db, ledger)
        txn = _orphan(db, ledger)
        svc.reconcile_flows(
            db, FAMILY,
            {'action': 'attach', 'transaction_ids': [txn.id], 'target_position_id': target.id},
        )
        assert _net_cents(db, ledger) == 0
        svc.reconcile_flows(db, FAMILY, {'action': 'detach', 'transaction_ids': [txn.id]})
        assert _net_cents(db, ledger) == Money.yuan_to_cents(1000.0)
        db.refresh(txn)
        assert txn.position_id is None
        assert svc.RECONCILED_KEY not in json.loads(txn.extra or '{}')

    def test_reconciled_row_cannot_be_edited_or_deleted(self, db):
        ledger = _ledger(db)
        target = _position(db, ledger)
        txn = _orphan(db, ledger)
        svc.reconcile_flows(
            db, FAMILY,
            {'action': 'attach', 'transaction_ids': [txn.id], 'target_position_id': target.id},
        )
        with pytest.raises(ValueError, match='请先撤销归置'):
            svc.update_flow(db, FAMILY, txn.id, {'amount': 1.0})
        with pytest.raises(ValueError, match='请先撤销归置'):
            svc.delete_flow(db, FAMILY, txn.id)

    def test_targets_are_family_scoped_and_searchable(self, db):
        ledger = _ledger(db)
        target = _position(db, ledger)
        rows = svc.list_targets(db, FAMILY, q='水星')
        assert [r['id'] for r in rows] == [target.id]
        assert svc.list_targets(db, 999, q='水星') == []

    def test_rejects_cross_family_or_unknown_ids(self, db):
        ledger = _ledger(db)
        txn = _orphan(db, ledger)
        with pytest.raises(ValueError, match='目标持仓不存在'):
            svc.reconcile_flows(
                db, FAMILY,
                {'action': 'attach', 'transaction_ids': [txn.id], 'target_position_id': 999999},
            )
        with pytest.raises(ValueError, match='部分流水不存在'):
            svc.reconcile_flows(
                db, FAMILY,
                {'action': 'attach', 'transaction_ids': [txn.id, 999999], 'target_position_id': 1},
            )
