# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/14
# File : test_summary_money_fund.py
"""孤儿货基/逆回购流水净额并入总资产 / 账户汇总的聚合测试。

背景：position_service 对 money_fund / reverse_repo 只建孤立流水
（position_id=None、entry_status='orphan'、amount=净额分），不建 positions。
本测试验证四处聚合（get_summary_data / get_sankey_data / get_account_groups /
get_overview_stats）把孤儿流水净额正确并入，且与 positions/assets 并存不重复计数。
"""

from app.domains.ledgers.models import Ledger
from app.services.ledger_service import LedgerService
from app.services.summary_service import get_account_groups, get_sankey_data, get_summary_data


def _make_orphan_txn(make_transaction, ledger_id, txn_type, amount_yuan):
    """创建一条孤儿货基流水（position_id=None、entry_status='orphan'、asset_type='money_fund'）。

    amount_yuan 为元，make_transaction fixture 会自动转分落库。
    """
    return make_transaction(
        None,
        ledger_id,
        txn_type=txn_type,
        amount=amount_yuan,
        asset_type='money_fund',
        entry_status='orphan',
    )


def _make_bank_ledger(db, name='招商银行'):
    ledger = Ledger(name=name, ledger_type='bank')
    db.add(ledger)
    db.commit()
    return ledger


class TestSummaryDataOrphanNet:
    """get_summary_data：孤儿净额并入总资产"""

    def test_positive_net_included_in_total_assets(self, db, make_transaction):
        """正净额（买入/存入）孤儿流水并入总资产"""
        _make_orphan_txn(make_transaction, None, 'buy', 100)  # 100 元
        _make_orphan_txn(make_transaction, None, 'buy', 50)  # 50 元
        data = get_summary_data(db, 1)
        assert data['total_assets_cny'] == 150.0
        assert data['net_assets_cny'] == 150.0
        assert data['total_liabilities_cny'] == 0.0

    def test_negative_net_reduces_assets(self, db, make_transaction):
        """卖出/取现负净额按负数处理（归入资产负值，不特殊处理）"""
        _make_orphan_txn(make_transaction, None, 'buy', 100)  # 买入 100 元
        _make_orphan_txn(make_transaction, None, 'sell', 300)  # 卖出 300 元
        data = get_summary_data(db, 1)
        assert data['total_assets_cny'] == -200.0
        assert data['net_assets_cny'] == -200.0

    def test_withdraw_negative(self, db, make_transaction):
        """取现类型同样按负向计入"""
        _make_orphan_txn(make_transaction, None, 'deposit', 100)
        _make_orphan_txn(make_transaction, None, 'withdraw', 40)
        data = get_summary_data(db, 1)
        assert data['total_assets_cny'] == 60.0

    def test_orphan_net_combined_with_positions_and_assets(self, db, make_position, make_asset, make_transaction):
        """与 positions/assets 并存，孤儿净额只计一次，不重复计数"""
        make_position(symbol='S1', name='股1', quantity=100, avg_price=10.0, current_price=12.0)
        make_asset(major_category='cash', name='活期', amount=500)
        _make_orphan_txn(make_transaction, None, 'buy', 100)
        data = get_summary_data(db, 1)
        # 持仓 1200 + 资产 500 + 孤儿净额 100 = 1800
        assert data['total_assets_cny'] == 1800.0

    def test_non_orphan_money_fund_position_not_double_counted(self, db, make_transaction, make_position):
        """有持仓的货基（positions 表）不走孤儿口径，只按持仓市值计一次"""
        make_position(
            symbol='MF001', name='货基', quantity=1000, avg_price=1.0, current_price=1.0, asset_type='money_fund'
        )
        _make_orphan_txn(make_transaction, None, 'buy', 100)
        data = get_summary_data(db, 1)
        # 持仓市值 1000 + 孤儿净额 100 = 1100
        assert data['total_assets_cny'] == 1100.0


class TestAccountGroupsOrphanNet:
    """get_account_groups：孤儿净额按 ledger_id 归组"""

    def test_grouped_by_ledger_name(self, db, make_transaction):
        """有 ledger 的孤儿净额归入对应账户名分组"""
        ledger = _make_bank_ledger(db)
        _make_orphan_txn(make_transaction, ledger.id, 'buy', 100)
        _make_orphan_txn(make_transaction, ledger.id, 'buy', 50)
        groups = get_account_groups(db, 1)
        assert len(groups) == 1
        assert groups[0]['name'] == '招商银行'
        assert groups[0]['total'] == 150.0
        assert groups[0]['count'] == 1  # 同一 ledger 聚合成一组

    def test_no_ledger_goes_to_orphan_group(self, db, make_transaction):
        """无 ledger 的孤儿净额归「游离」分组"""
        _make_orphan_txn(make_transaction, None, 'buy', 100)
        groups = get_account_groups(db, 1)
        assert len(groups) == 1
        assert groups[0]['name'] == '游离'
        assert groups[0]['total'] == 100.0

    def test_merged_with_positions_and_assets_same_ledger(self, db, make_position, make_asset, make_transaction):
        """同一账户下 positions/assets/孤儿净额合并，不重复计数"""
        ledger = _make_bank_ledger(db)
        make_position(
            symbol='S1',
            name='股1',
            ledger_id=ledger.id,
            account_name='招商银行',
            quantity=100,
            avg_price=10.0,
            current_price=12.0,
        )
        make_asset(major_category='cash', name='活期', amount=500, ledger_id=ledger.id, account_name='招商银行')
        _make_orphan_txn(make_transaction, ledger.id, 'buy', 100)
        groups = get_account_groups(db, 1)
        assert len(groups) == 1
        assert groups[0]['name'] == '招商银行'
        assert groups[0]['total'] == 1200.0 + 500.0 + 100.0
        assert groups[0]['count'] == 3


class TestSankeyOrphanNet:
    """get_sankey_data：孤儿净额归入「流动资金/cash」大类"""

    def test_orphan_net_in_cash_category(self, db, make_transaction):
        """正净额孤儿流水 → 流动资金节点 → 总资产"""
        _make_orphan_txn(make_transaction, None, 'buy', 100)
        data = get_sankey_data(db, 1)
        node_names = {n['name'] for n in data['nodes']}
        assert '流动资金' in node_names
        link = next(lnk for lnk in data['links'] if lnk['source'] == '流动资金')
        assert link['target'] == '总资产'
        assert link['value'] == 100.0

    def test_negative_net_not_shown_as_positive_link(self, db, make_transaction):
        """负净额不产生正向流动资金连线（按负数处理，不特殊生成负债）"""
        _make_orphan_txn(make_transaction, None, 'buy', 100)
        _make_orphan_txn(make_transaction, None, 'sell', 300)
        data = get_sankey_data(db, 1)
        # 总资产为负，无任何正向连线（符合既有负资产行为，不特殊处理）
        assert all(lnk['value'] > 0 for lnk in data['links'])

    def test_orphan_merged_with_assets_cash_category(self, db, make_asset, make_transaction):
        """孤儿净额与通用现金资产合并进同一「流动资金」大类，不重复计数"""
        make_asset(major_category='cash', name='活期', amount=500)
        _make_orphan_txn(make_transaction, None, 'buy', 100)
        data = get_sankey_data(db, 1)
        link = next(lnk for lnk in data['links'] if lnk['source'] == '流动资金')
        assert link['value'] == 500.0 + 100.0


class TestOverviewStatsOrphanNet:
    """LedgerService.get_overview_stats：孤儿净额按 ledger_id 归组"""

    def test_grouped_into_ledger_type(self, db, make_transaction):
        """有 ledger 的孤儿净额并入对应账户类型分组"""
        ledger = _make_bank_ledger(db)
        _make_orphan_txn(make_transaction, ledger.id, 'buy', 100)
        stats = LedgerService.get_overview_stats(db, 1)
        bank_group = next(g for g in stats['groups'] if g['type'] == 'bank')
        assert bank_group['total'] == 100.0
        assert stats['net_worth'] == 100.0

    def test_no_ledger_goes_to_deleted_group(self, db, make_transaction):
        """无 ledger 的孤儿净额与游离数据统一归入 deleted 分组"""
        _make_orphan_txn(make_transaction, None, 'buy', 100)
        stats = LedgerService.get_overview_stats(db, 1)
        deleted = next(g for g in stats['groups'] if g['type'] == 'deleted')
        assert deleted['total'] == 100.0
        assert deleted['count'] == 1
        assert stats['net_worth'] == 100.0

    def test_negative_net(self, db, make_transaction):
        """卖出/取现负净额按负数计入账户分组"""
        ledger = _make_bank_ledger(db)
        _make_orphan_txn(make_transaction, ledger.id, 'buy', 100)
        _make_orphan_txn(make_transaction, ledger.id, 'sell', 300)
        stats = LedgerService.get_overview_stats(db, 1)
        bank_group = next(g for g in stats['groups'] if g['type'] == 'bank')
        assert bank_group['total'] == -200.0
        assert stats['net_worth'] == -200.0

    def test_merged_with_orphan_positions_no_double_count(self, db, make_position, make_transaction):
        """游离持仓 + 无 ledger 孤儿净额合并进 deleted，不重复计数"""
        make_position(symbol='S1', name='股1', quantity=100, avg_price=10.0, current_price=12.0)  # ledger_id=None
        _make_orphan_txn(make_transaction, None, 'buy', 100)
        stats = LedgerService.get_overview_stats(db, 1)
        deleted = next(g for g in stats['groups'] if g['type'] == 'deleted')
        assert deleted['total'] == 1200.0 + 100.0
        assert deleted['count'] == 1  # 0 键只有一个（游离合并）
        assert stats['net_worth'] == 1300.0
