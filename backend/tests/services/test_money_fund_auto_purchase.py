# -*- coding: utf-8 -*-
# File : test_money_fund_auto_purchase.py
"""#1137 卖出回款自动申购账户绑定的类现金产品（「余额宝」）测试。

设计见 docs/working-notes/ledger-cash-like-product-binding-2026-08-29.md：
- 仅当账户开启 `auto_purchase_money_fund` 且绑定了有效货基时才申购；
- 申购生成孤儿流水（asset_type='money_fund'、entry_status='orphan'），
  货基不建持仓，与导入器 / money_fund_income 口径一致；
- 货基 / 逆回购自身的卖出不触发，避免「赎回 → 自动申购」死循环。
"""

from datetime import date

from app.core.money import Money
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService

TRADE_DATE = date(2026, 8, 1)


def _make_ledger(
    db,
    fund_code='000198',
    fund_name='天弘余额宝货币',
    bind=True,
    auto=True,
):
    """构造「证券账户 + 可选绑定的类现金产品」。"""
    fund = Fund(fund_code=fund_code, name=fund_name)
    db.add(fund)
    db.flush()
    ledger = Ledger(
        name='华泰证券',
        ledger_type='stock',
        linked_money_fund_id=fund.id if bind else None,
        auto_purchase_money_fund=auto,
    )
    db.add(ledger)
    db.commit()
    return ledger, fund


def _sell(db, position_id, quantity=50, price=12.0, fee=5.0, asset_type='stock'):
    """执行一次卖出，返回回款净额（分）。"""
    PositionService.process_sell_or_withdraw(
        db,
        {
            'position_id': position_id,
            'quantity': quantity,
            'avg_price': price,
            'op_type': 'sell',
            'fee': fee,
            'trade_date': TRADE_DATE,
            'confirm_date': TRADE_DATE,
            'family_id': 1,
            'asset_type': asset_type,
        },
        skip_lot_check=True,
    )
    db.commit()
    gross = Money.multiply_price_quantity(Money.yuan_to_price_units(price), Money.shares_to_min_unit(quantity))
    return gross - Money.yuan_to_cents(fee)


def _money_fund_flows(db, ledger_id):
    """该账户的货基**申购**流水（txn_type='buy'）；赎回 / 卖出流水不计入。"""
    return db.query(Transaction).filter_by(ledger_id=ledger_id, asset_type='money_fund', txn_type='buy').all()


class TestAutoPurchaseMoneyFund:
    def test_sell_creates_purchase_flow_when_enabled(self, db, make_position):
        """开启开关且绑定货基：卖出生成一笔货基申购孤儿流水，金额 = 成交额 - 手续费"""
        ledger, fund = _make_ledger(db)
        pos = make_position(
            symbol='SH600519',
            name='贵州茅台',
            ledger_id=ledger.id,
            account_name='华泰证券',
            quantity=100,
            avg_price=10.0,
            current_price=10.0,
        )
        expected_net = _sell(db, pos.id)

        flows = _money_fund_flows(db, ledger.id)
        assert len(flows) == 1
        flow = flows[0]
        assert flow.txn_type == 'buy'
        assert flow.symbol == fund.fund_code
        assert flow.position_name == fund.name
        assert flow.amount == expected_net
        # 货基不建持仓：孤儿流水口径
        assert flow.position_id is None
        assert flow.entry_status == 'orphan'

    def test_no_purchase_when_switch_off(self, db, make_position):
        """开关关闭（默认）：卖出不生成任何申购流水——用户不操作系统不代劳"""
        ledger, _fund = _make_ledger(db, auto=False)
        pos = make_position(
            symbol='SH600519',
            name='贵州茅台',
            ledger_id=ledger.id,
            account_name='华泰证券',
            quantity=100,
            avg_price=10.0,
            current_price=10.0,
        )
        _sell(db, pos.id)
        assert _money_fund_flows(db, ledger.id) == []

    def test_no_purchase_without_binding(self, db, make_position):
        """未绑定类现金产品：即使开关为开也不申购"""
        ledger, _fund = _make_ledger(db, bind=False, auto=True)
        pos = make_position(
            symbol='SH600519',
            name='贵州茅台',
            ledger_id=ledger.id,
            account_name='华泰证券',
            quantity=100,
            avg_price=10.0,
            current_price=10.0,
        )
        _sell(db, pos.id)
        assert _money_fund_flows(db, ledger.id) == []

    def test_money_fund_sell_does_not_trigger_purchase(self, db, make_position):
        """货基自身卖出不触发自动申购（避免赎回 → 自动申购死循环）"""
        ledger, fund = _make_ledger(db)
        pos = make_position(
            symbol=fund.fund_code,
            name=fund.name,
            ledger_id=ledger.id,
            account_name='华泰证券',
            quantity=100,
            avg_price=1.0,
            current_price=1.0,
            asset_type='money_fund',
        )
        _sell(db, pos.id, quantity=50, price=1.0, fee=0.0, asset_type='money_fund')
        # 赎回本身正常落库（否则用例可能假阳性：卖出压根没执行）
        sells = db.query(Transaction).filter_by(ledger_id=ledger.id, asset_type='money_fund', txn_type='sell').all()
        assert len(sells) == 1
        # 但不得自动申购回来
        assert _money_fund_flows(db, ledger.id) == []

    def test_multiple_sells_create_multiple_flows(self, db, make_position):
        """多次卖出各自生成一笔申购流水"""
        ledger, _fund = _make_ledger(db)
        pos = make_position(
            symbol='SH600519',
            name='贵州茅台',
            ledger_id=ledger.id,
            account_name='华泰证券',
            quantity=300,
            avg_price=10.0,
            current_price=10.0,
        )
        _sell(db, pos.id, quantity=50)
        _sell(db, pos.id, quantity=50)
        assert len(_money_fund_flows(db, ledger.id)) == 2
