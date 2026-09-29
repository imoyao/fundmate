# -*- coding: utf-8 -*-
"""分红与股息统计口径回归（#872）。

覆盖的判据（都被文档化为口径，改实现前先看 `services/dividend_service.py` 的模块 docstring）：

1. 事件分类：现金分红 / 红利再投（同 `link_group_id` 有 buy 流水）/ 红利税 / 送股；
2. 债券兑付**不入**分红统计（还本付息不是股息收入）；
3. 窗口口径：TTM 只算窗口内的，累计口径算全量；
4. 股息率分母是**当前成本**（成本均价 × 份额），分子是「现金 + 再投 − 红利税」；
5. 在管 vs 全量：已清仓 / 孤儿分红进 `totals`，不进 `portfolio`/`holdings`；
6. 红利再投浮盈按当前价反推，人工录市值的持仓不可算（返回 None）；
7. 股息目标达成度。
"""

from datetime import date

import pytest

from app.core.money import Money
from app.services.dividend_service import (
    KIND_CASH,
    KIND_REINVEST,
    KIND_SPLIT,
    KIND_TAX,
    build_dividend_summary,
    clear_target,
    load_dividend_events,
    read_target,
    upsert_target,
)

TODAY = date(2026, 9, 29)


@pytest.fixture
def holding(make_position):
    """一只股票：1000 份 @ 成本 10 元（成本基数 10000 元 = 1,000,000 分），现价 12 元。"""
    return make_position(
        symbol='600519',
        name='测试股票',
        asset_type='stock',
        account_name='测试账户',
        quantity=1000,
        avg_price=10.0,
        current_price=12.0,
    )


def _summary(db, **kwargs):
    kwargs.setdefault('today', TODAY)
    return build_dividend_summary(db, 1, **kwargs)


class TestEventClassification:
    """流水 → 分红事件的分类判据。"""

    def test_cash_dividend_without_pair_is_cash(self, db, holding, make_transaction):
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=500.0,
            confirm_date=date(2026, 6, 20),
            symbol=holding.symbol,
        )
        events = load_dividend_events(db, 1)
        assert len(events) == 1
        assert events[0].kind == KIND_CASH
        assert events[0].amount_cents == 50000

    def test_dividend_with_paired_buy_is_reinvest(self, db, holding, make_transaction):
        """红利再投的判据是「同 link_group_id 有 buy 流水」，不是「link_group_id 非空」。"""
        group = 'group-1'
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=200.0,
            confirm_date=date(2026, 6, 20),
            link_group_id=group,
            symbol=holding.symbol,
        )
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='buy',
            quantity=100,
            price=2.0,
            amount=200.0,
            confirm_date=date(2026, 6, 20),
            link_group_id=group,
            symbol=holding.symbol,
        )
        events = load_dividend_events(db, 1)
        assert [e.kind for e in events] == [KIND_REINVEST]

    def test_dividend_with_lone_link_group_is_still_cash(self, db, holding, make_transaction):
        """只有配对列、没有配对申购 → 仍是现金分红（防把通用配对列误判成再投）。"""
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=300.0,
            confirm_date=date(2026, 6, 20),
            link_group_id='lone-group',
            symbol=holding.symbol,
        )
        assert [e.kind for e in load_dividend_events(db, 1)] == [KIND_CASH]

    def test_tax_and_split_are_classified(self, db, holding, make_transaction):
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend_tax',
            quantity=0,
            price=0,
            amount=-30.0,
            confirm_date=date(2026, 6, 20),
            symbol=holding.symbol,
        )
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='split',
            quantity=100,
            price=0,
            amount=0.0,
            confirm_date=date(2026, 6, 21),
            symbol=holding.symbol,
        )
        kinds = {e.kind for e in load_dividend_events(db, 1)}
        assert kinds == {KIND_TAX, KIND_SPLIT}

    def test_bond_redeem_is_excluded(self, db, holding, make_transaction):
        """债券兑付是还本付息，计入会把本金回收算成股息收入。"""
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='bond_redeem',
            quantity=0,
            price=0,
            amount=1000.0,
            confirm_date=date(2026, 6, 20),
            symbol=holding.symbol,
        )
        assert load_dividend_events(db, 1) == []


class TestSummaryTotals:
    """累计口径与窗口口径。"""

    def test_empty_family_is_all_zero(self, db):
        summary = _summary(db)
        assert summary['totals']['all_time']['net_cents'] == 0
        assert summary['totals']['ttm']['net_cents'] == 0
        assert summary['totals']['first_date'] is None
        assert summary['holdings'] == []
        assert summary['portfolio']['yield_on_cost_pct'] is None
        assert summary['target']['configured'] is False

    def test_cash_dividend_yield_on_cost(self, db, holding, make_transaction):
        """500 元现金分红 / 10000 元成本 = 5%；市值口径 500/12000 = 4.17%。"""
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=500.0,
            confirm_date=date(2026, 6, 20),
            symbol=holding.symbol,
        )
        summary = _summary(db)
        row = summary['holdings'][0]
        assert row['cost_cents'] == 1_000_000
        assert row['market_value_cents'] == 1_200_000
        assert row['net_cents'] == 50000
        assert row['yield_on_cost_pct'] == 5.0
        assert row['cash_yield_on_cost_pct'] == 5.0
        assert row['yield_on_value_pct'] == 4.17
        assert row['last_dividend_date'] == '2026-06-20'
        # 组合口径与单一持仓一致
        assert summary['portfolio']['yield_on_cost_pct'] == 5.0
        assert summary['portfolio']['paying_count'] == 1

    def test_tax_reduces_net_but_not_cash(self, db, holding, make_transaction):
        """红利税在流水里是负数，展示为正数并从净分红中扣除。"""
        common = {
            'position_id': holding.id,
            'ledger_id': holding.ledger_id,
            'quantity': 0,
            'price': 0,
            'confirm_date': date(2026, 6, 20),
            'symbol': holding.symbol,
        }
        make_transaction(txn_type='dividend', amount=500.0, **common)
        make_transaction(txn_type='dividend_tax', amount=-30.0, **common)
        totals = _summary(db)['totals']['all_time']
        assert totals['cash_cents'] == 50000
        assert totals['tax_cents'] == 3000
        assert totals['net_cents'] == 47000
        assert _summary(db)['holdings'][0]['yield_on_cost_pct'] == 4.7

    def test_split_counts_event_but_adds_no_amount(self, db, holding, make_transaction):
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='split',
            quantity=100,
            price=0,
            amount=0.0,
            confirm_date=date(2026, 6, 21),
            symbol=holding.symbol,
        )
        totals = _summary(db)['totals']['all_time']
        assert totals['split_count'] == 1
        assert totals['net_cents'] == 0
        assert totals['event_count'] == 1

    def test_ttm_window_excludes_older_events(self, db, holding, make_transaction):
        """窗口外（2024-08）的分红只进累计，不进 TTM，也不进股息率分子。"""
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=100.0,
            confirm_date=date(2024, 8, 1),
            symbol=holding.symbol,
        )
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=400.0,
            confirm_date=date(2026, 3, 1),
            symbol=holding.symbol,
        )
        summary = _summary(db)
        assert summary['period'] == {'months': 12, 'start': '2025-09-29', 'end': '2026-09-29'}
        assert summary['totals']['ttm']['cash_cents'] == 40000
        assert summary['totals']['all_time']['cash_cents'] == 50000
        assert summary['holdings'][0]['all_time_cash_cents'] == 50000
        assert summary['holdings'][0]['cash_yield_on_cost_pct'] == 4.0

    def test_months_param_widens_window(self, db, holding, make_transaction):
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=100.0,
            confirm_date=date(2024, 8, 1),
            symbol=holding.symbol,
        )
        assert _summary(db, months=12)['totals']['ttm']['cash_cents'] == 0
        assert _summary(db, months=36)['totals']['ttm']['cash_cents'] == 10000

    def test_by_year_is_descending_and_capped(self, db, holding, make_transaction):
        for day, amount in ((date(2023, 5, 1), 100.0), (date(2025, 5, 1), 200.0), (date(2026, 5, 1), 300.0)):
            make_transaction(
                position_id=holding.id,
                ledger_id=holding.ledger_id,
                txn_type='dividend',
                quantity=0,
                price=0,
                amount=amount,
                confirm_date=day,
                symbol=holding.symbol,
            )
        years = _summary(db, years=5)['by_year']
        assert [y['year'] for y in years] == [2026, 2025, 2023]
        assert years[0]['cash_cents'] == 30000
        # years=2 → 只回溯 2025/2026
        assert [y['year'] for y in _summary(db, years=2)['by_year']] == [2026, 2025]

    def test_orphan_dividend_in_totals_but_not_portfolio(self, db, holding, make_transaction):
        """孤儿分红（无持仓，含已清仓后的结转）只进累计口径，不污染在管股息率。"""
        make_transaction(
            position_id=None,
            ledger_id=None,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=800.0,
            confirm_date=date(2026, 5, 1),
            symbol='510300',
        )
        summary = _summary(db)
        assert summary['totals']['ttm']['cash_cents'] == 80000
        assert summary['portfolio']['net_cents'] == 0
        assert summary['portfolio']['yield_on_cost_pct'] == 0.0
        # 在管持仓仍在列表里（只是没分红）
        assert len(summary['holdings']) == 1
        assert summary['holdings'][0]['net_cents'] == 0

    def test_inactive_position_excluded_from_holdings(self, db, holding, make_transaction):
        """已清仓持仓（ownership_status != active）的分红留在累计口径。"""
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=600.0,
            confirm_date=date(2026, 6, 1),
            symbol=holding.symbol,
        )
        holding.ownership_status = 'cleared'
        db.flush()
        summary = _summary(db)
        assert summary['holdings'] == []
        assert summary['totals']['ttm']['cash_cents'] == 60000
        assert summary['portfolio']['yield_on_cost_pct'] is None


class TestReinvest:
    """红利再投：双流水识别 + 再投浮盈。"""

    def _make_reinvest(
        self, holding, make_transaction, *, dividend=200.0, shares=100.0, nav=2.0, day=date(2026, 6, 20)
    ):
        group = f'group-{holding.id}-{day.isoformat()}'
        common = {
            'position_id': holding.id,
            'ledger_id': holding.ledger_id,
            'confirm_date': day,
            'symbol': holding.symbol,
            'link_group_id': group,
        }
        make_transaction(txn_type='dividend', quantity=0, price=0, amount=dividend, **common)
        make_transaction(txn_type='buy', quantity=shares, price=nav, amount=dividend, **common)

    def test_reinvest_counts_into_yield(self, db, holding, make_transaction):
        self._make_reinvest(holding, make_transaction)
        row = _summary(db)['holdings'][0]
        assert row['cash_cents'] == 0
        assert row['reinvest_cents'] == 20000
        assert row['net_cents'] == 20000
        assert row['yield_on_cost_pct'] == 2.0

    def test_reinvest_gain_uses_current_price(self, db, holding, make_transaction):
        """再投 100 份、成本价 2 元、现价 12 元 → 浮盈 100 × (12 − 2) = 1000 元。"""
        self._make_reinvest(holding, make_transaction)
        assert _summary(db)['holdings'][0]['reinvest_gain_cents'] == 100_000

    def test_reinvest_gain_is_none_when_market_value_is_manual(self, db, holding, make_transaction):
        """人工录市值的持仓没有可信当前价 → 再投收益返回 None（前端显示 --），不瞎报 0。"""
        self._make_reinvest(holding, make_transaction)
        holding.market_value_override = 999_999
        db.flush()
        row = _summary(db)['holdings'][0]
        assert row['reinvest_gain_cents'] is None
        assert _summary(db)['portfolio']['reinvest_gain_cents'] is None

    def test_lone_dividend_row_without_buy_is_cash(self, db, holding, make_transaction):
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=200.0,
            confirm_date=date(2026, 6, 20),
            symbol=holding.symbol,
        )
        row = _summary(db)['holdings'][0]
        assert row['cash_cents'] == 20000
        assert row['reinvest_gain_cents'] == 0


class TestTarget:
    """股息目标：读写 + 达成度。"""

    def test_read_write_clear(self, db):
        assert read_target(db, 1) == {'configured': False, 'target_yield_pct': None, 'notes': None}
        upsert_target(db, 1, target_yield_pct=4.0, notes='退休现金流')
        assert read_target(db, 1) == {'configured': True, 'target_yield_pct': 4.0, 'notes': '退休现金流'}
        # 再写一次是更新而不是新增（一家庭一条）
        upsert_target(db, 1, target_yield_pct=5.0, notes=None)
        assert read_target(db, 1)['target_yield_pct'] == 5.0
        assert clear_target(db, 1) is True
        assert clear_target(db, 1) is False
        assert read_target(db, 1)['configured'] is False

    def test_target_progress_and_gap(self, db, holding, make_transaction):
        """实际 5% vs 目标 4% → 达成度 125%，超出 1 个百分点。"""
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=500.0,
            confirm_date=date(2026, 6, 20),
            symbol=holding.symbol,
        )
        upsert_target(db, 1, target_yield_pct=4.0, notes=None)
        target = _summary(db)['target']
        assert target['configured'] is True
        assert target['progress_pct'] == 125.0
        assert target['gap_pct'] == 1.0
        assert target['met'] is True

    def test_target_not_met(self, db, holding, make_transaction):
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=100.0,
            confirm_date=date(2026, 6, 20),
            symbol=holding.symbol,
        )
        upsert_target(db, 1, target_yield_pct=4.0, notes=None)
        target = _summary(db)['target']
        assert target['met'] is False
        assert target['gap_pct'] == -3.0

    def test_target_progress_is_none_without_cost(self, db):
        """没有持仓（成本为 0）时达成度不可算 → None，而不是 0%。"""
        upsert_target(db, 1, target_yield_pct=4.0, notes=None)
        target = _summary(db)['target']
        assert target['configured'] is True
        assert target['progress_pct'] is None
        assert target['met'] is None


class TestMoneyConversion:
    """金额单位契约：一律整数分。"""

    def test_amounts_are_integer_cents(self, db, holding, make_transaction):
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=123.45,
            confirm_date=date(2026, 6, 20),
            symbol=holding.symbol,
        )
        summary = _summary(db)
        assert summary['totals']['ttm']['cash_cents'] == Money.yuan_to_cents(123.45)
        for key in ('cost_cents', 'market_value_cents', 'net_cents'):
            assert isinstance(summary['holdings'][0][key], int)
