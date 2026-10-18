# -*- coding: utf-8 -*-
"""交易行为画像（analytics/behavior.py · 口径 v2）测试。

两层覆盖：

- **纯函数层**（``compute_behavior_stats``）：合成流水（SimpleNamespace）精确控制
  每个字段，覆盖口径矩阵——FIFO 配对盈亏、全额/部分配对门控、分红单列、
  is_income 排除、无买入流水（存量迁移）诚实降级、乱序输入；
- **db 层**（``build_symbol_behavior``）：复用 conftest 的 ``make_transaction`` /
  ``make_position``（amount 自动元→分转换）。

金额约定：出参一律元；流水侧 amount 为分。
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.services.analytics.behavior import build_symbol_behavior, compute_behavior_stats


def _txn(
    txn_type,
    quantity=0,
    amount=0,
    confirm_date=None,
    is_income=None,
    symbol='000001',
    trade_date=None,
):
    """合成一条流水（字段形态对齐 Transaction；金额已是分）。"""
    return SimpleNamespace(
        txn_type=txn_type,
        quantity=quantity,
        amount=amount,
        confirm_date=confirm_date,
        trade_date=trade_date,
        is_income=is_income,
        symbol=symbol,
    )


def _closed_trade(symbol='000001', qty=10000, buy_amt=100000, sell_amt=105000, buy_d=None, sell_d=None):
    """一笔完整闭环（买入 → 卖出）。

    默认：qty=10000（0.0001 份单位）= 1.0 份；买入 100000 分 = 1000 元；
    卖出 105000 分 = 1050 元 → **盈 50 元**。
    """
    return [
        _txn('buy', quantity=qty, amount=buy_amt, confirm_date=buy_d or date(2026, 1, 1), symbol=symbol),
        _txn('sell', quantity=qty, amount=sell_amt, confirm_date=sell_d or date(2026, 2, 1), symbol=symbol),
    ]


class TestPairedPnl:
    def test_mixed_wins_and_losses(self):
        """混合盈亏：胜率/盈亏比/均值逐位核对（配对自算：回款 − 成本）。"""
        txns = (
            _closed_trade(buy_amt=100000, sell_amt=105000, buy_d=date(2026, 1, 1), sell_d=date(2026, 2, 1))  # +50 元
            + _closed_trade(buy_amt=100000, sell_amt=98000, buy_d=date(2026, 2, 1), sell_d=date(2026, 3, 1))  # −20 元
            + _closed_trade(buy_amt=100000, sell_amt=103000, buy_d=date(2026, 3, 1), sell_d=date(2026, 4, 1))  # +30 元
        )
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 3
        assert r['win_rate'] == 66.67  # 2/3
        assert r['avg_win'] == 40.0  # (50+30)/2 元
        assert r['avg_loss'] == -20.0
        assert r['profit_loss_ratio'] == 2.0
        assert r['realized_pnl_total'] == 60.0

    def test_all_wins_ratio_is_none(self):
        """全胜（无亏损笔）：盈亏比除零 → None，不输出 Infinity。"""
        txns = _closed_trade(sell_amt=101000, buy_d=date(2026, 1, 1)) + _closed_trade(
            sell_amt=102000, buy_d=date(2026, 2, 1), sell_d=date(2026, 3, 1)
        )
        r = compute_behavior_stats(txns)
        assert r['win_rate'] == 100.0
        assert r['profit_loss_ratio'] is None

    def test_ignores_realized_pnl_field_entirely(self):
        """口径 v2 的核心：realized_pnl 恒 0（存量库实测）不影响结果——根本不读它。"""
        txns = _closed_trade()
        for t in txns:
            t.realized_pnl = 0
        r = compute_behavior_stats(txns)
        assert r['win_rate'] == 100.0
        assert r['realized_pnl_total'] == 50.0

    def test_sell_before_any_buy_excluded(self):
        """卖出早于所有买入（存量迁移形态）：无批次可配，不进盈亏样本、不编造成本。"""
        txns = [
            _txn('sell', quantity=10000, amount=100000, confirm_date=date(2026, 1, 5)),
            _txn('buy', quantity=20000, amount=200000, confirm_date=date(2026, 2, 1)),  # 买入在卖出之后
        ]
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 0
        assert r['win_rate'] is None
        assert r['realized_pnl_total'] is None
        assert r['unmatched_sell_count'] == 1
        assert r['unmatched_sell_shares'] == 10000

    def test_partial_match_sell_excluded_from_pnl(self):
        """部分配对（卖 10000 配到 2000）：不进盈亏样本（未配对部分成本未知）。"""
        txns = [
            _txn('buy', quantity=2000, amount=20000, confirm_date=date(2026, 1, 1)),
            _txn('sell', quantity=10000, amount=105000, confirm_date=date(2026, 2, 1)),
        ]
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 0
        assert r['unmatched_sell_count'] == 1
        assert r['unmatched_sell_shares'] == 8000
        assert r['avg_holding_days'] == 31.0  # 已配对部分仍计周期

    def test_zero_qty_sell_excluded(self):
        """quantity=0 的卖出（场外转出等，主仓库 SZ001937 实测形态）：不可配对，排除。"""
        txns = [_txn('sell', quantity=0, amount=1000, confirm_date=date(2026, 1, 5))]
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 0
        assert r['unmatched_sell_count'] == 1
        assert r['avg_holding_days'] is None

    def test_out_of_order_input(self):
        """乱序输入：内部按交易日重排，FIFO 不受调用方顺序影响。"""
        txns = list(reversed(_closed_trade()))
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 1
        assert r['realized_pnl_total'] == 50.0

    def test_empty_input(self):
        r = compute_behavior_stats([])
        assert r['closed_count'] == 0
        assert r['buy_count'] == 0


class TestDividendAndIncomeRows:
    def test_dividend_cash_single_out_not_in_sample(self):
        """现金分红单列，不进胜率样本（分红不是平仓决策）。"""
        txns = _closed_trade() + [_txn('dividend_cash', amount=8000)]
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 1
        assert r['win_rate'] == 100.0
        assert r['realized_pnl_total'] == 50.0
        assert r['cash_dividend_total'] == 80.0

    def test_income_rows_excluded(self):
        """#863 收益发放行不是交易决策：不进配对队列、不进分红合计、不进样本。"""
        txns = _closed_trade() + [
            _txn('dividend_cash', amount=5000, is_income=True),
            _txn('buy', quantity=1000, amount=10000, is_income=True),
        ]
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 1
        assert r['buy_count'] == 1  # is_income 的 buy 未计
        assert r['cash_dividend_total'] is None


class TestFifoHoldingPeriod:
    def test_fifo_weighted_average_days(self):
        """FIFO 配对：一笔买入分两次卖完，持有期与盈亏按配对份额分摊。"""
        txns = [
            _txn('buy', quantity=10000, amount=1000000, confirm_date=date(2025, 1, 1)),  # 1 元/份
            _txn('sell', quantity=5000, amount=525000, confirm_date=date(2025, 12, 31)),  # +250 分
            _txn('sell', quantity=5000, amount=550000, confirm_date=date(2026, 12, 31)),  # +500 分
        ]
        r = compute_behavior_stats(txns)
        # 加权：(5000×364 + 5000×729) / 10000 = 546.5 天（2025-01-01→12-31 实为 364 天差）
        assert r['avg_holding_days'] == 546.5
        assert r['closed_count'] == 2
        assert r['win_rate'] == 100.0
        # 盈亏：525000 − 500000 = 250 元 + 550000 − 500000 = 500 元（摊销后剩余成本必须同步扣减）
        assert r['realized_pnl_total'] == 750.0

    def test_reinvest_enters_queue(self):
        """红利再投资等价一笔买入（增加份额），参与 FIFO 配对。"""
        txns = [
            _txn('buy', quantity=5000, amount=50000, confirm_date=date(2025, 6, 1)),  # 1 元/份
            _txn('dividend_reinvest', quantity=2500, amount=22500, confirm_date=date(2025, 12, 1)),  # 0.9 元/份
            _txn('sell', quantity=7500, amount=82500, confirm_date=date(2026, 6, 1)),  # 回款 825 元
        ]
        r = compute_behavior_stats(txns)
        # 持有：(5000×365 + 2500×182) / 7500 = 304.0 天
        assert r['avg_holding_days'] == 304.0
        # 盈亏：825 − (500×1.0 + 250×0.9) = 825 − 725 = 100 元
        assert r['realized_pnl_total'] == 100.0

    def test_multi_symbol_queues_are_independent(self):
        """多 symbol 各自 FIFO（纯函数不假设单 symbol，键隔离）。"""
        txns = _closed_trade(symbol='A', buy_d=date(2025, 1, 1), sell_d=date(2025, 12, 31)) + [
            _txn('sell', quantity=5000, amount=50000, confirm_date=date(2026, 1, 1), symbol='B')
        ]
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 1
        assert r['avg_holding_days'] == 364.0  # B 的卖出无配对批次，不拉低均值
        assert r['unmatched_sell_shares'] == 5000

    def test_withdraw_never_matched(self):
        """withdraw 是现金类取出：不参与份额配对、不进盈亏样本。"""
        txns = [
            _txn('buy', quantity=5000, amount=50000, confirm_date=date(2026, 1, 1)),
            _txn('withdraw', quantity=5000, amount=52000, confirm_date=date(2026, 3, 1)),
        ]
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 0
        assert r['win_rate'] is None
        assert r['unmatched_sell_count'] == 0
        assert r['unmatched_sell_shares'] == 0

    def test_lot_without_amount_cost_fallback(self):
        """买入批次 amount 缺失（0）：可算周期但盈亏不可算 → 该笔卖出不进盈亏样本。"""
        txns = [
            _txn('buy', quantity=10000, amount=0, confirm_date=date(2026, 1, 1)),
            _txn('sell', quantity=10000, amount=105000, confirm_date=date(2026, 2, 1)),
        ]
        r = compute_behavior_stats(txns)
        assert r['closed_count'] == 0
        assert r['avg_holding_days'] == 31.0
        assert r['unmatched_sell_count'] == 1


class TestBuildSymbolBehavior:
    def test_db_roundtrip_with_real_transaction(self, db, make_position, make_transaction):
        """db 层：真实 Transaction 模型走通（make_transaction 自动元→分）。"""
        pos = make_position(
            symbol='110022',
            name='易方达消费行业',
            account_name='账户A',
            asset_type='bond',
            quantity=1000,
            current_price=1.2,
        )
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            quantity=1000,
            price=1.0,
            amount=1000.0,
            confirm_date=date.today() - timedelta(days=400),
            symbol='110022',
        )
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='sell',
            quantity=1000,
            price=1.095,
            amount=1095.0,
            confirm_date=date.today() - timedelta(days=35),
            symbol='110022',
        )
        r = build_symbol_behavior(db, '110022', family_id=1)
        assert r['buy_count'] == 1
        assert r['sell_count'] == 1
        assert r['closed_count'] == 1
        assert r['win_rate'] == 100.0
        assert r['realized_pnl_total'] == 95.0
        # 持有期 ≈ 400−35=365 天（confirm_date 差）
        assert r['avg_holding_days'] == 365.0

    def test_no_transactions_returns_empty_shape(self, db, make_position):
        """无成交：空形态（与 XIRR 空结构同风格），不抛异常。"""
        make_position(
            symbol='000001',
            name='无流水标的',
            account_name='账户A',
            asset_type='bond',
            quantity=100,
            current_price=1.0,
        )
        r = build_symbol_behavior(db, '000001', family_id=1)
        assert r['closed_count'] == 0
        assert r['win_rate'] is None

    def test_symbol_scope_isolation(self, db, make_position, make_transaction):
        """symbol 隔离：别的标的的结转笔不污染本标的画像。"""
        pos_a = make_position(
            symbol='000001', name='A', account_name='账户A', asset_type='bond', quantity=100, current_price=1.0
        )
        pos_b = make_position(
            symbol='000002', name='B', account_name='账户A', asset_type='bond', quantity=100, current_price=1.0
        )
        make_transaction(
            pos_a.id,
            pos_a.ledger_id,
            txn_type='buy',
            quantity=100,
            price=1.0,
            amount=100.0,
            confirm_date=date(2026, 1, 1),
            symbol='000001',
        )
        make_transaction(
            pos_a.id,
            pos_a.ledger_id,
            txn_type='sell',
            quantity=100,
            price=1.2,
            amount=120.0,
            confirm_date=date(2026, 1, 5),
            symbol='000001',
        )
        make_transaction(
            pos_b.id,
            pos_b.ledger_id,
            txn_type='sell',
            quantity=100,
            price=1.0,
            amount=50.0,
            confirm_date=date(2026, 1, 6),
            symbol='000002',
        )
        r = build_symbol_behavior(db, '000001', family_id=1)
        assert r['closed_count'] == 1
        assert r['win_rate'] == 100.0
        assert r['realized_pnl_total'] == 20.0

    def test_trade_date_fallback_when_confirm_missing(self):
        """confirm_date 缺失回退 trade_date（datetime → date）。"""
        buy = _txn('buy', quantity=10000, amount=100000, symbol='A')
        sell = _txn('sell', quantity=10000, amount=105000, symbol='A')
        buy.trade_date = datetime(2025, 1, 1, 9, 30)
        sell.trade_date = datetime(2025, 4, 1, 15, 0)
        r = compute_behavior_stats([buy, sell])
        assert r['avg_holding_days'] == 90.0
        assert r['closed_count'] == 1
