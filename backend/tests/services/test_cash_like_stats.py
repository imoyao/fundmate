# -*- coding: utf-8 -*-
# File : test_cash_like_stats.py
"""#1137 类现金统计（货基 + 逆回购 + 账户现金）测试。

口径与 XIRR 的 EXCLUDED_ASSET_TYPES = ('money_fund','reverse_repo','cash') 一致：
- 货基持仓市值（positions）
- 孤儿货基 / 逆回购流水净额（不建持仓，按流水净额并入）
- 账户内现金（Asset.major_category='current'）

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
        """账户内现金（current 类资产）计入类现金"""
        ledger = _make_ledger(db)
        # Asset.amount 单位为分：30000 分 = 300 元
        db.add(
            Asset(
                name='账户余额',
                amount=30000,
                major_category='current',
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
