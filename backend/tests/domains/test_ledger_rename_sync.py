# -*- coding: utf-8 -*-
"""#1354：账户改名必须级联刷新下游 account_name 冗余快照。

account_name 是 ledgers.name 的冗余列，散落在 assets / positions / transactions
三张表。历史实现只改 ledgers.name，导致「账本改名了，明细里还是旧名字」。
"""

from app.domains.assets.models import Asset
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction


class TestLedgerRenameSyncsAccountName:
    def test_rename_syncs_all_three_tables(self, client, db, make_position, make_asset, make_transaction):
        """改名后三张表的快照都要跟着变（含资产 / 持仓 / 流水）"""
        pos = make_position(account_name='旧账本', name='测试持仓', symbol='000001', asset_type='fund')
        asset = make_asset(account_name='旧账本', name='定期存款', major_category='investment', amount=1000)
        txn = make_transaction(position_id=pos.id, ledger_id=pos.ledger_id, account_name='旧账本')
        # make_transaction 只 flush 不 commit，此处补提交，保证 API 侧会话可见
        db.commit()

        resp = client.patch(f'/api/ledgers/{pos.ledger_id}/', json={'name': '新账本'})
        assert resp.status_code == 200

        db.expire_all()
        assert db.get(Position, pos.id).account_name == '新账本'
        assert db.get(Asset, asset.id).account_name == '新账本'
        assert db.get(Transaction, txn.id).account_name == '新账本'

    def test_rename_does_not_touch_other_ledgers(self, client, db, make_position, make_asset, make_transaction):
        """改名只影响本账户下游，不能误伤同名 / 其他账户的数据（三张表都要隔离）"""
        pos_a = make_position(account_name='账户A', name='持仓A', symbol='000001', asset_type='fund')
        pos_b = make_position(account_name='账户B', name='持仓B', symbol='000002', asset_type='fund')
        asset_a = make_asset(
            account_name='账户A', name='资产A', major_category='cash', amount=100, ledger_id=pos_a.ledger_id
        )
        asset_b = make_asset(
            account_name='账户B', name='资产B', major_category='cash', amount=100, ledger_id=pos_b.ledger_id
        )
        txn_a = make_transaction(position_id=pos_a.id, ledger_id=pos_a.ledger_id, account_name='账户A')
        txn_b = make_transaction(position_id=pos_b.id, ledger_id=pos_b.ledger_id, account_name='账户B')
        db.commit()

        resp = client.patch(f'/api/ledgers/{pos_a.ledger_id}/', json={'name': '账户A改名'})
        assert resp.status_code == 200

        db.expire_all()
        assert db.get(Position, pos_a.id).account_name == '账户A改名'
        assert db.get(Asset, asset_a.id).account_name == '账户A改名'
        assert db.get(Transaction, txn_a.id).account_name == '账户A改名'
        # 其他账户的三张表快照保持原值，未被误改
        assert db.get(Position, pos_b.id).account_name == '账户B'
        assert db.get(Asset, asset_b.id).account_name == '账户B'
        assert db.get(Transaction, txn_b.id).account_name == '账户B'

    def test_rename_without_name_change_keeps_snapshot(self, client, db, make_position):
        """只改备注不改名时，不触发快照刷新（避免无谓的全表 UPDATE）"""
        pos = make_position(account_name='账本X', name='持仓X', symbol='000001', asset_type='fund')

        resp = client.patch(f'/api/ledgers/{pos.ledger_id}/', json={'notes': '仅改备注'})
        assert resp.status_code == 200

        db.expire_all()
        assert db.get(Position, pos.id).account_name == '账本X'

    def test_rename_orphan_rows_untouched(self, client, db, make_position):
        """ledger_id 为空的孤儿数据不参与级联（本就没有账户可对齐）"""
        pos = make_position(account_name='账本Y', name='持仓Y', symbol='000001', asset_type='fund')
        orphan = make_position(
            name='孤儿持仓',
            symbol='000003',
            asset_type='fund',
            ledger_id=None,
            account_name='孤儿账户名',
        )

        resp = client.patch(f'/api/ledgers/{pos.ledger_id}/', json={'name': '账本Y改名'})
        assert resp.status_code == 200

        db.expire_all()
        # 受影响的正常行必须被级联更新（否则级联逻辑完全未生效，本测试也会通过 → 假绿）
        assert db.get(Position, pos.id).account_name == '账本Y改名'
        # ledger_id 为空的孤儿数据不参与级联（本就没有账户可对齐）
        assert db.get(Position, orphan.id).account_name == '孤儿账户名'
