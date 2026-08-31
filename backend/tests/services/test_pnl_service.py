# -*- coding: utf-8 -*-
"""盈亏口径拆分单测（#1183）。

覆盖 issue 验收要求的三个场景：部分卖出、清仓、分红，
外加「已实现盈亏不随后续均价变动漂移」与 balance 模式成本基数两条口径断言。
"""

from datetime import date

from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.pnl_service import (
    compute_sell_realized_cents,
    family_realized_pnl_cents,
    net_invested_by_position,
    position_pnl_cents,
    realized_pnl_by_position,
)
from app.services.position_service import PositionService
from app.services.summary_service import get_summary_data

TRADE_DATE = date(2026, 8, 30)


def _buy(db, make_position, quantity=1000.0, price=1.0, current_price=None, **extra):
    pos = make_position(
        symbol='000001',
        asset_type='fund',
        market='CN_A',
        quantity=quantity,
        avg_price=price,
        current_price=current_price if current_price is not None else price,
        account_name='测试账户',
        **extra,
    )
    # 买入流水：净投入按成交金额计（balance 模式的成本基数来源）
    db.add(
        Transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            family_id=1,
            txn_type='buy',
            symbol=pos.symbol,
            quantity=Money.shares_to_min_unit(quantity),
            price=Money.yuan_to_price_units(price),
            amount=Money.yuan_to_cents(quantity * price),
            trade_date=TRADE_DATE,
            confirm_date=TRADE_DATE,
            status='success',
        )
    )
    db.commit()
    return pos


def _sell(db, position_id, quantity, price, fee=0.0):
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
            'asset_type': 'fund',
        },
        skip_lot_check=True,
    )
    db.commit()


class TestComputeSellRealized:
    def test_profit_minus_fee(self):
        # (1.5 − 1.0) × 500份 = 250元，扣 5 元手续费 → 245元 = 24500 分
        assert (
            compute_sell_realized_cents(
                price_units=Money.yuan_to_price_units(1.5),
                avg_price_units=Money.yuan_to_price_units(1.0),
                qty_units=Money.shares_to_min_unit(500),
                fee_cents=Money.yuan_to_cents(5),
            )
            == 24500
        )

    def test_loss_is_negative(self):
        # (0.8 − 1.0) × 500份 = −100元 = −10000 分
        assert (
            compute_sell_realized_cents(
                price_units=Money.yuan_to_price_units(0.8),
                avg_price_units=Money.yuan_to_price_units(1.0),
                qty_units=Money.shares_to_min_unit(500),
            )
            == -10000
        )

    def test_at_cost_is_zero(self):
        assert (
            compute_sell_realized_cents(
                price_units=Money.yuan_to_price_units(1.0),
                avg_price_units=Money.yuan_to_price_units(1.0),
                qty_units=Money.shares_to_min_unit(500),
            )
            == 0
        )


class TestPartialSell:
    def test_partial_sell_splits_realized_and_unrealized(self, db, make_position):
        """部分卖出：卖掉的一半落袋为已实现，剩下的一半仍是浮动。"""
        pos = _buy(db, make_position, quantity=1000.0, price=1.0, current_price=1.5)
        _sell(db, pos.id, quantity=500.0, price=1.5)

        txn = db.query(Transaction).filter_by(position_id=pos.id, txn_type='sell').one()
        # 已实现 = (1.5 − 1.0) × 500 = 250元
        assert txn.realized_pnl == 25000

        db.refresh(pos)
        realized_map = realized_pnl_by_position(db, 1)
        invested_map = net_invested_by_position(db, 1)
        detail = position_pnl_cents(
            pos,
            rate=1.0,
            realized_cents=realized_map.get(pos.id, 0),
            net_invested=invested_map.get(pos.id, 0),
        )

        assert Money.min_unit_to_shares(pos.quantity) == 500.0  # 份额减半
        assert detail['market_value_cents'] == 75000  # 500份 × 1.5元
        assert detail['cost_basis_cents'] == 50000  # 500份 × 1.0元（移动加权：卖出不改均价）
        assert detail['realized_pnl_cents'] == 25000
        assert detail['unrealized_pnl_cents'] == 25000
        assert detail['total_pnl_cents'] == 50000  # 已实现 + 未实现

    def test_realized_does_not_drift_when_avg_price_changes(self, db, make_position):
        """已实现盈亏结转后，不得随后续均价变动而漂移（验收第 2 条）。"""
        pos = _buy(db, make_position, quantity=1000.0, price=1.0, current_price=1.5)
        _sell(db, pos.id, quantity=500.0, price=1.5)
        assert family_realized_pnl_cents(db, 1) == 25000

        # 后续以 2.0 元加仓，移动加权均价被抬高到 1.5，已实现盈亏必须仍是 250元
        db.refresh(pos)
        pos.avg_price = Money.yuan_to_price_units(1.5)
        pos.current_price = Money.yuan_to_price_units(2.0)
        db.commit()

        assert family_realized_pnl_cents(db, 1) == 25000


class TestClearPosition:
    def test_cleared_position_keeps_realized_pnl(self, db, make_position):
        """清仓会删除持仓行，但已实现盈亏记在流水上，必须仍然查得到。"""
        pos = _buy(db, make_position, quantity=1000.0, price=1.0, current_price=1.5)
        _sell(db, pos.id, quantity=1000.0, price=1.5)

        assert db.query(Position).filter_by(id=pos.id).first() is None  # 持仓已删除
        assert family_realized_pnl_cents(db, 1) == 50000  # (1.5−1.0)×1000 = 500元

        summary = get_summary_data(db, 1)
        assert summary['realized_pnl_cny'] == 500.0
        assert summary['unrealized_pnl_cny'] == 0.0  # 无在库持仓，浮动为 0
        assert summary['total_pnl_cny'] == 500.0


class TestDividend:
    def test_cash_dividend_counts_as_realized(self, db, make_position):
        """现金分红全额计入已实现盈亏，与 XIRR 的 dividend_cash 正现金流同口径。"""
        pos = _buy(db, make_position, quantity=1000.0, price=1.0, current_price=1.0)
        PositionService.process_dividend(
            db,
            {
                'position_id': pos.id,
                'dividend_amount': 100,
                'symbol': pos.symbol,
                'asset_type': 'fund',
                'trade_date': TRADE_DATE,
                'confirm_date': TRADE_DATE,
                'family_id': 1,
            },
        )
        db.commit()

        txn = db.query(Transaction).filter_by(position_id=pos.id, txn_type='dividend').one()
        assert txn.realized_pnl == 10000  # 100元

        db.refresh(pos)
        detail = position_pnl_cents(pos, rate=1.0, realized_cents=family_realized_pnl_cents(db, 1))
        assert detail['unrealized_pnl_cents'] == 0  # 分红不改动份额与成本
        assert detail['realized_pnl_cents'] == 10000
        assert detail['total_pnl_cents'] == 10000

    def test_dividend_reinvest_is_total_neutral(self, db, make_position):
        """红利再投资：分红入账记已实现 +D，申购抬高成本基数 +D，对总盈亏净额为 0。"""
        pos = _buy(db, make_position, quantity=1000.0, price=1.0, current_price=1.0)
        PositionService.process_dividend_reinvest(
            db,
            {
                'position_id': pos.id,
                'dividend_amount': 100,
                'nav': 1.0,
                'quantity': 100,
                'symbol': pos.symbol,
                'asset_type': 'fund',
                'trade_date': TRADE_DATE,
                'confirm_date': TRADE_DATE,
                'family_id': 1,
            },
        )
        db.commit()
        db.refresh(pos)

        invested_map = net_invested_by_position(db, 1)
        detail = position_pnl_cents(
            pos,
            rate=1.0,
            realized_cents=family_realized_pnl_cents(db, 1),
            net_invested=invested_map.get(pos.id, 0),
        )
        assert Money.min_unit_to_shares(pos.quantity) == 1100.0  # 份额增加 100
        assert detail['realized_pnl_cents'] == 10000  # 分红 100元 已落袋
        assert detail['cost_basis_cents'] == 110000  # 原 1000元 + 再投 100元
        assert detail['unrealized_pnl_cents'] == 0  # 市值 1100元 − 成本 1100元
        assert detail['total_pnl_cents'] == 10000  # 总盈亏即那笔分红


class TestBalanceModeCostBasis:
    def test_balance_mode_uses_net_invested_as_cost(self, db, make_position):
        """balance 模式无份额可乘，成本基数取现金流净投入。"""
        pos = make_position(
            symbol='LC001',
            asset_type='other',
            market='CN_A',
            quantity=0,
            avg_price=0,
            current_price=0,
            valuation_mode='balance',
            market_value_override=12000,  # 人工录入市值 120元
            account_name='测试账户',
        )
        db.add(
            Transaction(
                position_id=pos.id,
                ledger_id=pos.ledger_id,
                family_id=1,
                txn_type='buy',
                symbol=pos.symbol,
                quantity=0,
                price=0,
                amount=Money.yuan_to_cents(100),  # 投入 100元
                trade_date=TRADE_DATE,
                confirm_date=TRADE_DATE,
                status='success',
            )
        )
        db.commit()

        invested_map = net_invested_by_position(db, 1)
        assert invested_map[pos.id] == 10000

        detail = position_pnl_cents(pos, rate=1.0, net_invested=invested_map.get(pos.id, 0))
        assert detail['market_value_cents'] == 12000  # override 优先
        assert detail['cost_basis_cents'] == 10000  # 净投入
        assert detail['unrealized_pnl_cents'] == 2000  # 浮盈 20元

    def test_balance_mode_withdraw_reduces_cost_basis(self, db, make_position):
        """取出回款冲减成本基数（不是收益）。"""
        pos = make_position(
            symbol='LC002',
            asset_type='other',
            market='CN_A',
            quantity=0,
            avg_price=0,
            current_price=0,
            valuation_mode='balance',
            market_value_override=6000,
            account_name='测试账户',
        )
        for txn_type, amount in (('buy', 100), ('sell', 40)):
            db.add(
                Transaction(
                    position_id=pos.id,
                    ledger_id=pos.ledger_id,
                    family_id=1,
                    txn_type=txn_type,
                    symbol=pos.symbol,
                    quantity=0,
                    price=0,
                    amount=Money.yuan_to_cents(amount),
                    trade_date=TRADE_DATE,
                    confirm_date=TRADE_DATE,
                    status='success',
                )
            )
        db.commit()

        invested_map = net_invested_by_position(db, 1)
        assert invested_map[pos.id] == 6000  # 100 − 40 = 60元

        detail = position_pnl_cents(pos, rate=1.0, net_invested=invested_map.get(pos.id, 0))
        assert detail['unrealized_pnl_cents'] == 0  # 市值 60元 − 净投入 60元


class TestSummaryPnlSplit:
    def test_summary_returns_three_pnl_figures(self, db, make_position):
        """汇总接口分别返回已实现 / 未实现 / 总盈亏，且 total = realized + unrealized。"""
        pos = _buy(db, make_position, quantity=1000.0, price=1.0, current_price=1.5)
        _sell(db, pos.id, quantity=500.0, price=1.5)

        summary = get_summary_data(db, 1)
        assert set(['realized_pnl_cny', 'unrealized_pnl_cny', 'total_pnl_cny']).issubset(summary)
        assert summary['realized_pnl_cny'] == 250.0
        assert summary['unrealized_pnl_cny'] == 250.0
        assert summary['total_pnl_cny'] == 500.0

    def test_total_equals_realized_plus_unrealized(self, db, make_position):
        _buy(db, make_position, quantity=1000.0, price=1.0, current_price=1.2)
        summary = get_summary_data(db, 1)
        assert round(summary['realized_pnl_cny'] + summary['unrealized_pnl_cny'], 2) == summary['total_pnl_cny']
        assert summary['total_pnl_cny'] == 200.0  # 1000份 × (1.2−1.0)
