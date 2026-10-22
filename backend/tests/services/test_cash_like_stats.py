# -*- coding: utf-8 -*-
# File : test_cash_like_stats.py
"""#1137 类现金统计（货基 + 逆回购 + 账户现金）测试。

口径与 XIRR 的 EXCLUDED_ASSET_TYPES = ('money_fund','reverse_repo','cash') 一致：
- 货基持仓市值（positions）
- 孤儿货基 / 逆回购流水净额（不建持仓，按流水净额并入）
- 账户内现金（Asset.major_category='cash'）

债券基金不计入（有净值波动、XIRR 未排除，属中低风险投资而非现金）。

金额期望值一律用 Money 换算推导，不在测试里硬编码单位倍数。
"""

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.services.ledger_service import LedgerService


def _make_ledger(db, name='华泰证券', ledger_type='fund'):
    ledger = Ledger(name=name, ledger_type=ledger_type)
    db.add(ledger)
    db.commit()
    return ledger


def _market_value_yuan(shares: float, price_yuan: float) -> float:
    """按 Money 换算推导市值（元），与服务端计算同源。"""
    return Money.cents_to_yuan(
        Money.multiply_price_quantity(Money.yuan_to_price_units(price_yuan), Money.shares_to_min_unit(shares))
    )


def _make_position(db, ledger, symbol, name, shares, price_yuan, asset_type='fund', code=None):
    if code:
        fund = Fund(fund_code=code, name=name)
        db.add(fund)
        db.flush()
    pos = Position(
        symbol=symbol,
        name=name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        asset_type=asset_type,
        quantity=Money.shares_to_min_unit(shares),
        avg_price=Money.yuan_to_price_units(price_yuan),
        current_price=Money.yuan_to_price_units(price_yuan),
    )
    db.add(pos)
    db.commit()
    return pos


class TestCashLikeStats:
    def test_money_fund_position_counted(self, db):
        """货基持仓市值计入类现金"""
        ledger = _make_ledger(db)
        _make_position(
            db,
            ledger,
            symbol='000198',
            name='天弘余额宝货币',
            shares=10.0,
            price_yuan=1.0,
            asset_type='money_fund',
            code='000198',
        )
        expected = round(_market_value_yuan(10.0, 1.0), 2)
        stats = LedgerService.get_cash_like_stats(db, ledger.id, 1)
        assert stats['money_fund_amount'] == expected
        assert stats['cash_like_amount'] == expected

    def test_cash_asset_counted(self, db):
        """账户内现金（cash 类资产）计入类现金"""
        ledger = _make_ledger(db)
        # Asset.amount 单位为分：30000 分 = 300 元
        db.add(
            Asset(
                name='账户余额',
                amount=30000,
                major_category='cash',
                ledger_id=ledger.id,
                family_id=1,
            )
        )
        db.commit()
        stats = LedgerService.get_cash_like_stats(db, ledger.id, 1)
        assert stats['cash_amount'] == 300.0
        assert stats['cash_like_amount'] == 300.0

    def test_orphan_reverse_repo_counted(self, db, make_transaction):
        """孤儿逆回购流水净额计入类现金（逆回购不建持仓，只走流水）"""
        ledger = _make_ledger(db)
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=1000,
            asset_type='reverse_repo',
            entry_status='orphan',
        )
        stats = LedgerService.get_cash_like_stats(db, ledger.id, 1)
        # 持仓货基 0 + 现金 0 + 孤儿逆回购 1000 元
        assert stats['cash_like_amount'] == 1000.0

    def test_bond_fund_not_counted_as_cash_like(self, db):
        """债券基金不计入类现金：它是中低风险**投资**，不是现金"""
        ledger = _make_ledger(db)
        _make_position(
            db,
            ledger,
            symbol='110020',
            name='中银纯债',
            shares=10.0,
            price_yuan=1.0,
            asset_type='fund',
        )
        stats = LedgerService.get_cash_like_stats(db, ledger.id, 1)
        assert stats['cash_like_amount'] == 0.0

    def test_summary_exposes_cash_like_and_investment(self, client, db):
        """账户概览接口返回 cash_like_amount 与 investment_amount（总市值 - 类现金）"""
        ledger = _make_ledger(db, name='蚂蚁基金', ledger_type='fund')
        # 货基 10 份 × 1 元
        _make_position(
            db,
            ledger,
            symbol='000198',
            name='天弘余额宝货币',
            shares=10.0,
            price_yuan=1.0,
            asset_type='money_fund',
            code='000198',
        )
        # 普通基金 10 份 × 100 元
        _make_position(
            db,
            ledger,
            symbol='110011',
            name='易方达优质精选',
            shares=10.0,
            price_yuan=100.0,
            asset_type='fund',
        )

        mf_mv = round(_market_value_yuan(10.0, 1.0), 2)
        fund_mv = round(_market_value_yuan(10.0, 100.0), 2)

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_market_value'] == round(mf_mv + fund_mv, 2)
        assert data['cash_like_amount'] == mf_mv
        # 中高风险 = 总市值 - 类现金（只剩普通基金）
        assert data['investment_amount'] == fund_mv

    def test_investment_amount_never_negative_when_cash_like_exceeds_mv(self, client, db, make_transaction):
        """账外类现金 > 持仓总市值时，「投资资产」不得为负（真机 #bug 回归）。

        真机形态（账户「同花顺——银河」id=12，stock）：
        - 持仓总市值 296,042 元
        - 孤儿货基/逆回购流水净额 476,951 元（**不建持仓，不进总市值**）
        旧式 `investment_amount = 总市值 - cash_like_amount` 算出 **-180,909 元**，
        前端环形图因此显示「投资资产 -63.2% / 现金类资产 163.2%」：
        占比为负、且超过 100%，圆环被渲染成一整圈绿。

        根因是口径错配：cash_like 里的「账外」部分（孤儿流水净额 + 账户现金）
        从来不在 total_market_value 里，从总市值中扣掉等于减了两遍。
        """
        ledger = _make_ledger(db, name='同花顺——银河', ledger_type='stock')
        _make_position(
            db,
            ledger,
            symbol='600519',
            name='贵州茅台',
            shares=10.0,
            price_yuan=1.0,  # 市值 10 元
            asset_type='stock',
        )
        # 孤儿货基流水净额 1000 元 >> 持仓市值 10 元
        # （`make_transaction` 的 amount 入参单位是**元**，与 Asset.amount 的分不同，别混）
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=1000,
            asset_type='money_fund',
            entry_status='orphan',
        )
        db.commit()

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']

        total_mv = data['total_market_value']
        assert total_mv == 10.0
        # 账外类现金照旧独立暴露（它仍是真实存在的类现金，只是不进持仓市值）
        assert data['cash_like_amount'] == 1000.0
        # 关键断言：投资资产非负，且两片合计 == 总市值（左侧「总资产」）
        assert data['investment_amount'] >= 0
        assert data['investment_amount'] == 10.0
        assert data['cash_like_in_positions_amount'] == 0.0
        assert (
            round(
                data['investment_amount'] + data['cash_like_in_positions_amount'],
                2,
            )
            == total_mv
        )

    def test_composition_slices_partition_total_market_value(self, client, db):
        """正常形态：投资 + 持仓内类现金 == 总市值（构成图两片合计恒为 100%）。

        货基 10 元 + 普通基金 1000 元：现金片 10 元、投资片 1000 元，合计 1010。
        """
        ledger = _make_ledger(db, name='蚂蚁基金', ledger_type='fund')
        _make_position(
            db,
            ledger,
            symbol='000198',
            name='天弘余额宝货币',
            shares=10.0,
            price_yuan=1.0,
            asset_type='money_fund',
            code='000198',
        )
        _make_position(
            db,
            ledger,
            symbol='110011',
            name='易方达优质精选',
            shares=10.0,
            price_yuan=100.0,
            asset_type='fund',
        )

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']

        mf_mv = _market_value_yuan(10.0, 1.0)
        fund_mv = _market_value_yuan(10.0, 100.0)
        total_mv = round(mf_mv + fund_mv, 2)

        assert data['total_market_value'] == total_mv
        assert round(data['cash_like_in_positions_amount'], 2) == round(mf_mv, 2)
        assert round(data['investment_amount'], 2) == round(fund_mv, 2)
        assert (
            round(
                data['investment_amount'] + data['cash_like_in_positions_amount'],
                2,
            )
            == total_mv
        )


class TestCashLikeBreakdown:
    """#2155：账外类现金的**分项出口**与逐产品明细。

    背景：`get_cash_like_stats` 原先只给一个 `cash_like_amount` 合计，账户详情页
    没有任何 UI 出口，用户看到「总资产 296,042 / 账外类现金 476,951」时无法知道
    这笔钱是什么、为什么不在持仓里（真机账户 id=12）。

    口径纪律：本次**只增加分项出口，不改合计口径**。故此处第一要务是钉住
    「分项相加 == 合计」，而不是钉住某个具体数字。
    """

    def test_split_fields_sum_to_cash_like_amount(self, client, db, make_transaction):
        """分项相加必须等于 cash_like_amount（三条来源各出一个数）。"""
        ledger = _make_ledger(db, name='蚂蚁基金', ledger_type='fund')
        # 持仓内：货基 10 份 × 1 元 = 10 元
        _make_position(
            db,
            ledger,
            symbol='000198',
            name='天弘余额宝货币',
            shares=10.0,
            price_yuan=1.0,
            asset_type='money_fund',
            code='000198',
        )
        # 账户内现金：500 元
        db.add(
            Asset(
                name='账户余额',
                amount=50000,
                major_category='cash',
                ledger_id=ledger.id,
                family_id=1,
            )
        )
        # 账外孤儿货基本金净额：buy 1000 − sell 400 = 600 元
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=1000,
            asset_type='money_fund',
            entry_status='orphan',
        )
        make_transaction(
            None,
            ledger.id,
            txn_type='sell',
            amount=400,
            asset_type='money_fund',
            entry_status='orphan',
        )
        db.commit()

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']

        assert data['cash_like_in_positions_amount'] == 10.0
        assert data['orphan_amount'] == 600.0
        assert data['account_cash_amount'] == 500.0
        # 合计口径未变（#1137 原样）
        assert data['cash_like_amount'] == 1110.0
        assert (
            round(
                data['cash_like_in_positions_amount'] + data['orphan_amount'] + data['account_cash_amount'],
                2,
            )
            == data['cash_like_amount']
        )

    def test_in_positions_field_is_subset_of_total_market_value(self, client, db, make_transaction):
        """`cash_like_in_positions_amount` 必须是 total_market_value 的子集（≤），
        且环形图两片之和恒等于总市值——这正是 #1606 修好的性质，分项出口不得破坏它。"""
        ledger = _make_ledger(db, name='同花顺——银河', ledger_type='stock')
        _make_position(
            db,
            ledger,
            symbol='600519',
            name='贵州茅台',
            shares=10.0,
            price_yuan=1.0,
            asset_type='stock',
        )
        _make_position(
            db,
            ledger,
            symbol='511990',
            name='华宝添益',
            shares=3.0,
            price_yuan=1.0,
            asset_type='money_fund',
        )
        # 账外孤儿净额远大于持仓市值（真机形态）
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=1000,
            asset_type='money_fund',
            entry_status='orphan',
        )
        db.commit()

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        data = resp.get_json()['data']

        assert data['cash_like_in_positions_amount'] <= data['total_market_value']
        assert data['investment_amount'] + data['cash_like_in_positions_amount'] == data['total_market_value']

    def test_breakdown_grouped_by_product(self, client, db, make_transaction):
        """逐产品明细：按产品归组、金额正确、净额降序、含笔数。

        这是卡面验收第 2 条（「它是什么、为什么不在持仓里」）的载体：
        只给汇总数字不构成解释。
        """
        ledger = _make_ledger(db, name='同花顺——银河', ledger_type='stock')
        # 产品 A：买入 1000、卖出 400 → 净 600（2 笔）
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=1000,
            symbol='000198',
            position_name='天弘余额宝货币',
            asset_type='money_fund',
            entry_status='orphan',
        )
        make_transaction(
            None,
            ledger.id,
            txn_type='sell',
            amount=400,
            symbol='000198',
            position_name='天弘余额宝货币',
            asset_type='money_fund',
            entry_status='orphan',
        )
        # 产品 B：逆回购存入 5000 → 净 5000（1 笔）
        make_transaction(
            None,
            ledger.id,
            txn_type='deposit',
            amount=5000,
            symbol='GC001',
            position_name='国债逆回购1天',
            asset_type='reverse_repo',
            entry_status='orphan',
        )
        db.commit()

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        data = resp.get_json()['data']

        assert data['orphan_amount'] == 5600.0
        items = data['cash_like_breakdown']
        assert len(items) == 2, items
        # 绝对值降序：逆回购 5000 在前
        assert items[0]['symbol'] == 'GC001'
        assert items[0]['total_amount'] == 5000.0
        assert items[0]['txn_count'] == 1
        assert items[0]['asset_type_label'] == '逆回购'
        assert items[1]['symbol'] == '000198'
        assert items[1]['net_amount'] == 600.0
        assert items[1]['txn_count'] == 2
        # 明细合计必须等于出口的汇总数（否则「汇总与明细对不上」比不给明细更糟）
        assert round(sum(i['total_amount'] for i in items), 2) == data['orphan_amount']

    def test_income_bucket_listed_separately_and_not_in_cash_like_total(self, client, db, make_transaction):
        """渠道收益桶（is_income=True）单列，且**不混进** cash_like_amount 本金口径。

        #863 D1：收益只进总资产、不膨胀本金。故它必须能在明细里看到，
        但不能改变 `cash_like_amount`（合计口径维持 #1137）。
        """
        ledger = _make_ledger(db, name='理财通', ledger_type='stock')
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=1000,
            symbol='000198',
            position_name='天弘余额宝货币',
            asset_type='money_fund',
            entry_status='orphan',
        )
        make_transaction(
            None,
            ledger.id,
            txn_type='deposit',
            amount=88,
            symbol='000198',
            position_name='天弘余额宝货币',
            asset_type='money_fund',
            entry_status='orphan',
            is_income=True,
        )
        db.commit()

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        data = resp.get_json()['data']

        # 本金桶 1000，收益桶 88 —— 合计口径只含本金
        assert data['orphan_amount'] == 1000.0
        assert data['orphan_income_amount'] == 88.0
        assert data['cash_like_amount'] == 1000.0
        # 明细里两者在同一个产品下分列（用户要看得见那 88 元）
        item = data['cash_like_breakdown'][0]
        assert item['net_amount'] == 1000.0
        assert item['income_amount'] == 88.0
        assert item['total_amount'] == 1088.0

    def test_breakdown_empty_when_no_orphan_flow(self, client, db):
        """无孤儿流水时明细为空数组（不是 None），且分项全为 0。

        空数组而非 None：前端用 `v-if="items.length"` 判断，返回 None 会炸。
        """
        ledger = _make_ledger(db, name='蚂蚁基金', ledger_type='fund')
        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        data = resp.get_json()['data']

        assert data['cash_like_breakdown'] == []
        assert data['orphan_amount'] == 0.0
        assert data['orphan_income_amount'] == 0.0
        assert data['cash_like_in_positions_amount'] == 0.0
        assert data['account_cash_amount'] == 0.0

    def test_position_linked_flow_excluded_from_breakdown(self, client, db, make_transaction):
        """**有持仓**的货基流水不得进入账外明细（position_id 非 NULL 即已在持仓内）。

        这是明细与汇总的分离点：`position_id IS NULL` 是「账外」的唯一判据。
        若漏掉这个过滤，持仓内货基的每一笔买卖都会同时出现在「持仓内」与
        「账外」两处 —— 用户会看到同一笔钱被算两遍（比不给明细更糟）。
        """
        ledger = _make_ledger(db, name='蚂蚁基金', ledger_type='fund')
        pos = _make_position(
            db,
            ledger,
            symbol='000198',
            name='天弘余额宝货币',
            shares=10.0,
            price_yuan=1.0,
            asset_type='money_fund',
            code='000198',
        )
        # 挂在持仓上的流水（position_id 非空）——它不是账外的
        make_transaction(
            pos.id,
            ledger.id,
            txn_type='buy',
            amount=777,
            symbol='000198',
            position_name='天弘余额宝货币',
            asset_type='money_fund',
        )
        # 真正的孤儿流水
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=100,
            symbol='000198',
            position_name='天弘余额宝货币',
            asset_type='money_fund',
            entry_status='orphan',
        )
        db.commit()

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        data = resp.get_json()['data']

        # 777 属于持仓内，不得出现在账外口径里
        assert data['orphan_amount'] == 100.0
        assert len(data['cash_like_breakdown']) == 1
        assert data['cash_like_breakdown'][0]['txn_count'] == 1
        assert data['cash_like_breakdown'][0]['total_amount'] == 100.0

    def test_same_asset_type_products_are_separate_rows(self, client, db, make_transaction):
        """同一 `asset_type` 下的**不同产品**必须各成一行（分组键不能只看 asset_type）。

        真机形态：一个券商账户里同时躺着一只场内货基和一只场外货基，
        两者 asset_type 都是 money_fund —— 合并成一行等于把「去买哪只」这个
        用户唯一能执行的信息抹掉，明细就白给了。
        """
        ledger = _make_ledger(db, name='同花顺——银河', ledger_type='stock')
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=3000,
            symbol='511990',
            position_name='华宝添益',
            asset_type='money_fund',
            entry_status='orphan',
        )
        make_transaction(
            None,
            ledger.id,
            txn_type='buy',
            amount=1000,
            symbol='000198',
            position_name='天弘余额宝货币',
            asset_type='money_fund',
            entry_status='orphan',
        )
        db.commit()

        resp = client.get(f'/api/ledgers/{ledger.id}/summary/')
        data = resp.get_json()['data']

        items = data['cash_like_breakdown']
        assert len(items) == 2, items
        assert {i['symbol'] for i in items} == {'511990', '000198'}
        assert items[0]['symbol'] == '511990'  # 金额降序
        assert round(sum(i['total_amount'] for i in items), 2) == data['orphan_amount'] == 4000.0
