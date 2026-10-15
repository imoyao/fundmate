# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/15
# File : test_summary_total_assets_contract.py
"""总资产契约测试：多个后端出口必须给出**同一个数**（#2154）。

背景：「总资产」长期有多个出口、各写一份累加逻辑，修一处漏一处：
- #1174 把市值收口到 `position_valuation.market_value_cents`，只改了
  `get_summary_data` / `get_distributions`；
- `get_account_groups` / `get_sankey_data` 漏改，仍在裸算「份额 × 快照价」，
  balance 模式（无份额无价格、市值靠 `market_value_override`）的持仓
  在 `/api/summary/` 算得出、在 `account_groups` 里恒为 0。

本文件是**契约网**：不验证某个具体数字，只验证「多出口必须相等」——
以后再有人新增出口或改口径，这里会直接红，而不是等用户发现两个页面数字不一样。

三处出口：
1. `get_summary_data` → `total_assets_cny`
2. `get_distributions` → `total_assets`
3. `get_account_groups` → `sum(g['total'])`
"""

from app.core.money import Money
from app.services.summary_service import (
    family_totals,
    get_account_groups,
    get_distributions,
    get_sankey_data,
    get_summary_data,
)


def _assert_all_exits_equal(db, *, assets_yuan=0.0, note=''):
    """「总资产」的三个出口必须相等；不等则打印全部数值便于定位。

    ⚠️ 口径说明：`get_account_groups` 的 `total` 是**账户净额**（负债取负，
    见其 docstring「负债金额为负数」），所以它的合计 = 总资产 − 总负债。
    本断言把负债加回去，比的是同一个「总资产」概念，不要求它改变既有契约。
    """
    s = get_summary_data(db, 1)['total_assets_cny']
    d = get_distributions(db, 1)['total_assets']
    t = family_totals(db, 1)['total_assets']
    liab = get_summary_data(db, 1)['total_liabilities_cny']
    g = round(sum(x['total'] for x in get_account_groups(db, 1)) + liab, 2)
    ctx = f' [{note}]' if note else ''
    assert s == d == g == t, (
        f'总资产出口分叉{ctx}: summary={s} distributions={d} account_groups(+负债)={g} family_totals={t}'
    )
    assert s == round(assets_yuan, 2), f'总资产数值不符{ctx}: {s} != {assets_yuan}'
    return s


class TestTotalAssetsSingleExit:
    """多出口数值一致性（#2154 契约）"""

    def test_balance_mode_position_all_exits_equal(self, db, make_position):
        """balance 模式持仓（无份额无价格、市值靠 override）→ 三出口必须相等。

        这是 #2154 的原始症状：`get_account_groups` 曾裸算「份额 × 快照价」恒得 0。
        """
        make_position(
            symbol='BAL001',
            name='投顾产品',
            account_name='投顾账户',
            asset_type='fund',
            valuation_mode='balance',
            market_value_override=Money.yuan_to_cents(123456.78),
            quantity=0,
            current_price=0,
            market='场外',
            allocation='longterm',
        )
        _assert_all_exits_equal(db, assets_yuan=123456.78, note='balance 模式')

    def test_nav_mode_position_all_exits_equal(self, db, make_position):
        """nav 模式持仓（份额 × 价格）→ 三出口必须相等（回归保护）"""
        make_position(
            symbol='NAV001',
            name='普通基金',
            account_name='基金账户',
            asset_type='fund',
            valuation_mode='nav',
            quantity=100,
            current_price=10.5,
            market='场外',
            allocation='longterm',
        )
        _assert_all_exits_equal(db, assets_yuan=1050.0, note='nav 模式')

    def test_override_beats_nav_all_exits_equal(self, db, make_position):
        """override 优先于 nav（有份额价格但录了 override）→ 三出口相等"""
        make_position(
            symbol='OVR001',
            name='有 override 的持仓',
            account_name='场外账户',
            asset_type='fund',
            valuation_mode='nav',
            quantity=100,
            current_price=10.0,
            market_value_override=Money.yuan_to_cents(9999.99),
            market='场外',
            allocation='longterm',
        )
        _assert_all_exits_equal(db, assets_yuan=9999.99, note='override 优先')

    def test_assets_and_liabilities_all_exits_equal(self, db, make_asset):
        """通用资产 + 负债：资产出口相等，负债也相等"""
        make_asset(account_name='银行', major_category='cash', name='活期', amount=50000)
        make_asset(account_name='银行', major_category='liability', name='信用卡', amount=8000)

        s = get_summary_data(db, 1)
        d = get_distributions(db, 1)
        t = family_totals(db, 1)
        assert s['total_assets_cny'] == d['total_assets'] == t['total_assets'] == 50000.0
        assert s['total_liabilities_cny'] == d['total_liabilities'] == t['total_liabilities'] == 8000.0
        assert s['net_assets_cny'] == d['net_worth'] == t['net_worth'] == 42000.0

    def test_orphan_cash_flow_all_exits_equal(self, db, make_transaction):
        """账外类现金（孤儿货基流水）计入总资产 → 三出口相等"""
        make_transaction(
            None,
            None,
            txn_type='buy',
            amount=30000,
            asset_type='money_fund',
            entry_status='orphan',
        )
        _assert_all_exits_equal(db, assets_yuan=30000.0, note='孤儿货基流水')

    def test_mixed_portfolio_all_exits_equal(self, db, make_position, make_asset, make_transaction):
        """混合场景：balance 持仓 + nav 持仓 + 资产 + 负债 + 孤儿流水，一次对齐"""
        make_position(
            symbol='MIX001',
            name='投顾产品',
            account_name='投顾账户',
            asset_type='fund',
            valuation_mode='balance',
            market_value_override=Money.yuan_to_cents(80000),
            quantity=0,
            current_price=0,
            market='场外',
            allocation='longterm',
        )
        make_position(
            symbol='MIX002',
            name='股票',
            account_name='券商',
            asset_type='stock',
            valuation_mode='nav',
            quantity=200,
            current_price=50.0,
            market='沪市',
            allocation='speculative',
        )
        make_asset(account_name='银行', major_category='cash', name='活期', amount=10000)
        make_asset(account_name='银行', major_category='liability', name='信用卡', amount=5000)
        make_transaction(None, None, txn_type='buy', amount=2000, asset_type='reverse_repo', entry_status='orphan')

        # 80000 + 10000 + 10000 + 2000 = 102000
        _assert_all_exits_equal(db, assets_yuan=102000.0, note='混合场景')

    def test_empty_portfolio_all_zero(self, db):
        """空家庭：三出口都为 0，且不抛异常"""
        assert get_summary_data(db, 1)['total_assets_cny'] == 0.0
        assert get_distributions(db, 1)['total_assets'] == 0.0
        assert get_account_groups(db, 1) == []
        assert family_totals(db, 1)['total_assets'] == 0.0

    def test_shadow_position_excluded_from_all_exits(self, db, make_position):
        """shadow（E账户影子记录）不进任何出口（§12.3 口径，回归保护）"""
        make_position(
            symbol='SHD001',
            name='影子记录',
            account_name='E账户',
            asset_type='stock',
            valuation_mode='nav',
            quantity=100,
            current_price=10.0,
            market='深市',
            allocation='longterm',
            ownership_status='shadow',
        )
        assert get_summary_data(db, 1)['total_assets_cny'] == 0.0
        assert get_distributions(db, 1)['total_assets'] == 0.0
        assert sum(x['total'] for x in get_account_groups(db, 1)) == 0.0
        assert family_totals(db, 1)['total_assets'] == 0.0
        # shadow 也不该出现在账户分组里（否则等于给用户看一条假账户）
        assert all(x['name'] != 'E账户' for x in get_account_groups(db, 1))

    def test_sankey_center_agrees_with_summary(self, db, make_position, make_asset):
        """桑基图「总资产 → 净资产」链路金额与 dashboard 总资产一致（#2154 附带修复）"""
        make_position(
            symbol='SK001',
            name='投顾产品',
            account_name='投顾账户',
            asset_type='fund',
            valuation_mode='balance',
            market_value_override=Money.yuan_to_cents(50000),
            quantity=0,
            current_price=0,
            market='场外',
            allocation='longterm',
        )
        maken = make_asset(account_name='银行', major_category='liability', name='信用卡', amount=1000)
        maken  # 确保负债存在但不影响净资产链路断言

        links = get_sankey_data(db, 1)['links']
        total_to_net = [x for x in links if x['source'] == '总资产' and x['target'] == '净资产']
        assert len(total_to_net) == 1, f'桑基图缺少 总资产→净资产 链路: {links}'
        # 总资产 50000 − 负债 1000 = 49000
        assert total_to_net[0]['value'] == 49000.0

    def test_sankey_category_node_uses_unique_valuation(self, db, make_position):
        """桑基图的「投资理财」大类节点也必须走唯一市值口径（#2154）。

        桑基图自身不累加总资产，但它的**分类节点**是独立算的：旧版这里同样裸算
        「份额 × 快照价」，balance 模式持仓在图上就是缺的（总资产节点有、来源片没有）。
        """
        make_position(
            symbol='SK002',
            name='投顾产品',
            account_name='投顾账户',
            asset_type='fund',
            valuation_mode='balance',
            market_value_override=Money.yuan_to_cents(50000),
            quantity=0,
            current_price=0,
            market='场外',
            allocation='longterm',
        )
        links = get_sankey_data(db, 1)['links']
        investment_links = [x for x in links if x['target'] == '总资产' and x['source'] == '投资理财']
        assert len(investment_links) == 1, f'桑基图「投资理财」大类缺失（balance 持仓未计）: {links}'
        assert investment_links[0]['value'] == 50000.0


class TestFamilyTotalsHelper:
    """`family_totals` 是唯一聚合出口本身的行为"""

    def test_reuses_passed_collections(self, db, make_position):
        """传入已加载的 positions/assets 时不重复查库（同值）"""
        make_position(
            symbol='R001',
            name='基金',
            account_name='场外账户',
            asset_type='fund',
            valuation_mode='nav',
            quantity=10,
            current_price=100.0,
            market='场外',
            allocation='longterm',
        )
        from app.services.summary_service import _load_user_assets

        positions, assets = _load_user_assets(db, 1)
        a = family_totals(db, 1, positions=positions, assets=assets)
        b = family_totals(db, 1)
        assert a == b == {'total_assets': 1000.0, 'total_liabilities': 0.0, 'net_worth': 1000.0}
