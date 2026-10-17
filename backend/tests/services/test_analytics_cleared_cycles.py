# -*- coding: utf-8 -*-
"""清仓周期统计（analytics/cleared_cycles.py · #2131）测试。

两层覆盖：

- **纯函数层**（``compute_cleared_cycles`` / ``summarize_cycles``）：合成流水
  （SimpleNamespace）精确控制每个字段，覆盖口径矩阵——单周期、同标的多轮周期、
  未完结不产出、部分配对降级、先卖后买不归集、分红单列、is_income 排除、
  symbol 写法变体合并、汇总胜率/盈亏比；
- **db 层**（``build_cleared_cycles``）：复用 conftest 的 ``make_position`` /
  ``make_transaction``（amount 自动元→分转换），含类现金资产排除。

金额约定：出参一律元；流水侧 amount 为分。
"""

from datetime import date
from types import SimpleNamespace

from app.services.analytics.cleared_cycles import build_cleared_cycles, compute_cleared_cycles, summarize_cycles


def _txn(
    txn_type,
    quantity=0,
    amount=0,
    confirm_date=None,
    is_income=None,
    symbol='000001',
    position_name=None,
    trade_date=None,
    asset_type='stock',
):
    """合成一条流水（字段形态对齐 Transaction；金额已是分）。

    `asset_type` 默认 'stock'：分组键走 `symbol_identity(symbol, asset_type)`
    （#1662），与真实写入一致（流水快照带 asset_type）。
    """
    return SimpleNamespace(
        txn_type=txn_type,
        quantity=quantity,
        amount=amount,
        confirm_date=confirm_date,
        trade_date=trade_date,
        is_income=is_income,
        symbol=symbol,
        position_name=position_name,
        asset_type=asset_type,
    )


def _closed_cycle(symbol='000001', qty=10000, buy_amt=100000, sell_amt=105000, buy_d=None, sell_d=None, name=None):
    """一轮完整周期：买入 → 卖出（默认 1000 元买、1050 元卖 → 盈 50 元）。"""
    return [
        _txn(
            'buy',
            quantity=qty,
            amount=buy_amt,
            confirm_date=buy_d or date(2026, 1, 1),
            symbol=symbol,
            position_name=name,
        ),
        _txn(
            'sell',
            quantity=qty,
            amount=sell_amt,
            confirm_date=sell_d or date(2026, 2, 1),
            symbol=symbol,
            position_name=name,
        ),
    ]


class TestSingleCycle:
    def test_basic_cycle_fields(self):
        """单周期：字段逐项核对（pnl=回款−成本、持有期=确认日差、交易次数=2）。"""
        cycles = compute_cleared_cycles(_closed_cycle(buy_d=date(2026, 1, 1), sell_d=date(2026, 2, 1), name='华夏成长'))
        assert len(cycles) == 1
        c = cycles[0]
        assert c['symbol'] == '000001'
        assert c['name'] == '华夏成长'
        assert c['cycle_number'] == 1
        assert c['first_buy_date'] == '2026-01-01'
        assert c['last_sell_date'] == '2026-02-01'
        assert c['trade_count'] == 2
        assert c['buy_count'] == 1
        assert c['sell_count'] == 1
        assert c['total_buy_amount'] == 1000.0
        assert c['total_sell_amount'] == 1050.0
        assert c['realized_pnl'] == 50.0
        assert c['pnl_pct'] == 5.0
        assert c['avg_holding_days'] == 31.0
        assert c['pnl_known'] is True
        assert c['dividend_total'] is None

    def test_realized_pnl_field_is_ignored(self):
        """口径与 behavior v2 同：不读流水 realized_pnl 列（存量库全 0）。"""
        txns = _closed_cycle()
        for t in txns:
            t.realized_pnl = 0
        cycles = compute_cleared_cycles(txns)
        assert cycles[0]['realized_pnl'] == 50.0

    def test_open_cycle_not_emitted(self):
        """数据末尾仍持有（队列非空）：未完结，不产出。"""
        txns = [_txn('buy', quantity=10000, amount=100000, confirm_date=date(2026, 1, 1))]
        assert compute_cleared_cycles(txns) == []

    def test_partial_sell_keeps_cycle_open(self):
        """部分卖出：队列未空 → 周期继续，不提前关闭。"""
        txns = [
            _txn('buy', quantity=10000, amount=100000, confirm_date=date(2026, 1, 1)),
            _txn('sell', quantity=5000, amount=52500, confirm_date=date(2026, 2, 1)),
        ]
        assert compute_cleared_cycles(txns) == []


class TestMultiCycleAndSymbols:
    def test_second_cycle_numbered(self):
        """同标的多轮周期：cycle_number 递增、各自独立结算。"""
        txns = _closed_cycle(buy_d=date(2026, 1, 1), sell_d=date(2026, 2, 1)) + _closed_cycle(
            buy_d=date(2026, 3, 1), sell_d=date(2026, 4, 1), buy_amt=200000, sell_amt=190000
        )
        cycles = compute_cleared_cycles(txns)
        assert len(cycles) == 2
        by_no = {c['cycle_number']: c for c in cycles}
        assert by_no[1]['realized_pnl'] == 50.0
        assert by_no[2]['realized_pnl'] == -100.0
        assert by_no[2]['last_sell_date'] == '2026-04-01'

    def test_symbol_variants_merged(self):
        """写法变体（SZ000001 / 000001）：按归一身份键合并为一个标的的周期。

        端到端实测形态：买入写 HK00700、卖出写 00700.HK（asset_type 快照相同），
        身份键一致才不至把一轮周期劈成两半。
        """
        txns = [
            _txn('buy', quantity=10000, amount=100000, confirm_date=date(2026, 1, 1), symbol='SZ000001'),
            _txn('sell', quantity=10000, amount=105000, confirm_date=date(2026, 2, 1), symbol='000001'),
        ]
        cycles = compute_cleared_cycles(txns)
        assert len(cycles) == 1
        assert cycles[0]['realized_pnl'] == 50.0
        # 展示名取周期内最近一次写字面量
        assert cycles[0]['symbol'] == '000001'

    def test_hk_symbol_variants_merged(self):
        """港股写法变体（HK00700 / 00700.HK）：身份键合并（剥前缀搞不定 HK 形态）。"""
        txns = [
            _txn('buy', quantity=10000, amount=100000, confirm_date=date(2026, 1, 1), symbol='HK00700'),
            _txn('sell', quantity=10000, amount=105000, confirm_date=date(2026, 2, 1), symbol='00700.HK'),
        ]
        cycles = compute_cleared_cycles(txns)
        assert len(cycles) == 1
        assert cycles[0]['realized_pnl'] == 50.0

    def test_multi_symbol_independent(self):
        """多 symbol 各自成周期，互不污染。"""
        txns = _closed_cycle(symbol='A', buy_d=date(2026, 1, 1), sell_d=date(2026, 2, 1)) + _closed_cycle(
            symbol='B', buy_d=date(2026, 1, 1), sell_d=date(2026, 2, 1), sell_amt=98000
        )
        cycles = compute_cleared_cycles(txns)
        assert len(cycles) == 2
        pnls = sorted(c['realized_pnl'] for c in cycles)
        assert pnls == [-20.0, 50.0]

    def test_cycles_sorted_by_last_sell_desc(self):
        """输出按末卖日降序（最近清仓在前）。"""
        txns = _closed_cycle(symbol='A', buy_d=date(2026, 1, 1), sell_d=date(2026, 2, 1)) + _closed_cycle(
            symbol='B', buy_d=date(2026, 3, 1), sell_d=date(2026, 4, 1)
        )
        cycles = compute_cleared_cycles(txns)
        assert [c['last_sell_date'] for c in cycles] == ['2026-04-01', '2026-02-01']


class TestDegradation:
    def test_sell_before_buy_not_collected(self):
        """先卖后买（存量迁移）：卖出无进行中周期 → 不归集、不编造。"""
        txns = [
            _txn('sell', quantity=10000, amount=100000, confirm_date=date(2026, 1, 5)),
            _txn('buy', quantity=20000, amount=200000, confirm_date=date(2026, 2, 1)),
        ]
        assert compute_cleared_cycles(txns) == []

    def test_partial_match_cycle_pnl_none(self):
        """卖出份额 > 可配份额：周期关闭但 pnl_known=False、盈亏不编造。"""
        txns = [
            _txn('buy', quantity=5000, amount=50000, confirm_date=date(2026, 1, 1)),
            _txn('sell', quantity=10000, amount=105000, confirm_date=date(2026, 2, 1)),
        ]
        cycles = compute_cleared_cycles(txns)
        assert len(cycles) == 1
        assert cycles[0]['realized_pnl'] is None
        assert cycles[0]['pnl_pct'] is None
        assert cycles[0]['pnl_known'] is False
        # 已配对部分仍计持有期
        assert cycles[0]['avg_holding_days'] == 31.0

    def test_lot_without_amount_pnl_none(self):
        """买入批次 amount 缺失（0）：可算周期但盈亏不可算。"""
        txns = [
            _txn('buy', quantity=10000, amount=0, confirm_date=date(2026, 1, 1)),
            _txn('sell', quantity=10000, amount=105000, confirm_date=date(2026, 2, 1)),
        ]
        cycles = compute_cleared_cycles(txns)
        assert len(cycles) == 1
        assert cycles[0]['pnl_known'] is False

    def test_zero_qty_sell_does_not_close(self):
        """quantity=0 的卖出（场外转出等）：不关周期，仅标记 partial。"""
        txns = [
            _txn('buy', quantity=10000, amount=100000, confirm_date=date(2026, 1, 1)),
            _txn('sell', quantity=0, amount=1000, confirm_date=date(2026, 1, 20)),
            _txn('sell', quantity=10000, amount=105000, confirm_date=date(2026, 2, 1)),
        ]
        cycles = compute_cleared_cycles(txns)
        assert len(cycles) == 1
        # 无份额卖出不消耗批次、不污染盈亏样本
        assert cycles[0]['pnl_known'] is True
        assert cycles[0]['realized_pnl'] == 50.0

    def test_dividend_single_out_not_in_sample(self):
        """现金分红（新码 dividend_cash 与历史码 dividend）单列，不进盈亏样本。"""
        txns = _closed_cycle() + [
            _txn('dividend_cash', amount=8000, confirm_date=date(2026, 1, 15)),
            _txn('dividend', amount=2000, confirm_date=date(2026, 1, 20)),
        ]
        cycles = compute_cleared_cycles(txns)
        assert cycles[0]['realized_pnl'] == 50.0
        assert cycles[0]['dividend_total'] == 100.0

    def test_income_rows_excluded(self):
        """#863 收益发放行不是交易决策：整行排除。"""
        txns = _closed_cycle() + [
            _txn('dividend_cash', amount=5000, is_income=True),
            _txn('buy', quantity=1000, amount=10000, is_income=True, confirm_date=date(2026, 1, 10)),
        ]
        cycles = compute_cleared_cycles(txns)
        assert len(cycles) == 1
        assert cycles[0]['dividend_total'] is None
        assert cycles[0]['buy_count'] == 1
        assert cycles[0]['realized_pnl'] == 50.0

    def test_withdraw_ignored(self):
        """withdraw 是现金类取出：不进配对、不关周期（与 behavior 同口径）。"""
        txns = [
            _txn('buy', quantity=10000, amount=100000, confirm_date=date(2026, 1, 1)),
            _txn('withdraw', quantity=10000, amount=52000, confirm_date=date(2026, 3, 1)),
        ]
        assert compute_cleared_cycles(txns) == []

    def test_out_of_order_input(self):
        """乱序输入：内部按交易日重排，配对不受调用方顺序影响。"""
        cycles = compute_cleared_cycles(list(reversed(_closed_cycle())))
        assert len(cycles) == 1
        assert cycles[0]['realized_pnl'] == 50.0

    def test_empty_input(self):
        assert compute_cleared_cycles([]) == []


class TestSummarize:
    def _summary(self, cycles):
        return summarize_cycles(cycles)

    def test_mixed_win_loss(self):
        """混合盈亏：胜率/盈亏比/均值逐位核对。"""
        txns = (
            _closed_cycle(symbol='A', buy_d=date(2026, 1, 1), sell_d=date(2026, 2, 1))  # +50
            + _closed_cycle(symbol='B', buy_d=date(2026, 2, 1), sell_d=date(2026, 3, 1), sell_amt=98000)  # -20
            + _closed_cycle(symbol='C', buy_d=date(2026, 3, 1), sell_d=date(2026, 4, 1), sell_amt=103000)  # +30
        )
        s = self._summary(compute_cleared_cycles(txns))
        assert s['cycle_count'] == 3
        assert s['sample_count'] == 3
        assert s['win_count'] == 2
        assert s['loss_count'] == 1
        assert s['win_rate'] == 66.67
        assert s['profit_loss_ratio'] == 2.0  # (50+30)/2 ÷ 20
        assert s['realized_pnl_total'] == 60.0
        assert s['total_trade_count'] == 6
        # 持有期：1→2 月 31 天、2→3 月 28 天（2026 非闰年）、3→4 月 31 天 → 均值 30.0
        assert s['avg_holding_days'] == 30.0

    def test_all_wins_ratio_none(self):
        """全胜（无亏损周期）：盈亏比除零 → None，不输出 Infinity。"""
        txns = _closed_cycle(symbol='A') + _closed_cycle(symbol='B', sell_amt=102000)
        s = self._summary(compute_cleared_cycles(txns))
        assert s['win_rate'] == 100.0
        assert s['profit_loss_ratio'] is None

    def test_partial_cycles_excluded_from_sample(self):
        """部分配对周期：展示但不进样本（胜率分母只算可算周期）。"""
        txns = (
            _closed_cycle(symbol='A')
            # B：部分配对 → pnl_known=False
            + [
                _txn('buy', quantity=5000, amount=50000, confirm_date=date(2026, 1, 1), symbol='B'),
                _txn('sell', quantity=10000, amount=105000, confirm_date=date(2026, 2, 1), symbol='B'),
            ]
        )
        s = self._summary(compute_cleared_cycles(txns))
        assert s['cycle_count'] == 2
        assert s['sample_count'] == 1
        assert s['win_rate'] == 100.0

    def test_empty_summary_shape(self):
        s = self._summary([])
        assert s['cycle_count'] == 0
        assert s['win_rate'] is None
        assert s['realized_pnl_total'] is None
        assert s['avg_holding_days'] is None


class TestBuildClearedCycles:
    def test_db_roundtrip(self, db, make_position, make_transaction):
        """db 层：真实 Transaction 走通（make_transaction 自动元→分）。"""
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
            confirm_date=date(2026, 1, 1),
            symbol='110022',
        )
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='sell',
            quantity=1000,
            price=1.05,
            amount=1050.0,
            confirm_date=date(2026, 2, 1),
            symbol='110022',
        )
        data = build_cleared_cycles(db, family_id=1)
        assert len(data['cycles']) == 1
        c = data['cycles'][0]
        assert c['symbol'] == '110022'
        assert c['realized_pnl'] == 50.0
        assert c['avg_holding_days'] == 31.0
        assert data['summary']['win_rate'] == 100.0

    def test_cash_equivalents_excluded_by_default(self, db, make_position, make_transaction):
        """类现金资产（货基）默认排除；include_cash_equivalents=True 才纳入。

        过滤判据是**流水快照的 asset_type**（与 behavior/XIRR 同口径），故两条
        流水都显式带 asset_type='money_fund'。
        """
        pos = make_position(
            symbol='000198',
            name='余额宝',
            account_name='账户A',
            asset_type='money_fund',
            quantity=1000,
            current_price=1.0,
        )
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='buy',
            quantity=1000,
            price=1.0,
            amount=1000.0,
            confirm_date=date(2026, 1, 1),
            symbol='000198',
            asset_type='money_fund',
        )
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='sell',
            quantity=1000,
            price=1.01,
            amount=1010.0,
            confirm_date=date(2026, 2, 1),
            symbol='000198',
            asset_type='money_fund',
        )
        assert build_cleared_cycles(db, family_id=1)['cycles'] == []
        data = build_cleared_cycles(db, family_id=1, include_cash_equivalents=True)
        assert len(data['cycles']) == 1

    def test_symbol_filter(self, db, make_position, make_transaction):
        """symbol 过滤：字面量与带前缀写法都命中（两账户同标的合并为一轮周期）。"""
        # 两个写法变体放不同账户：positions 唯一约束是 (ledger_id, symbol_norm)，
        # 同账户下 '600519' 与 'SH600519' 归一到同一 symbol_norm 会冲突。
        for account, symbol in (('账户A', '600519'), ('账户B', 'SH600519')):
            pos = make_position(
                symbol=symbol,
                name='贵州茅台',
                account_name=account,
                asset_type='stock',
                quantity=100,
                current_price=1500.0,
            )
            make_transaction(
                pos.id,
                pos.ledger_id,
                txn_type='buy',
                quantity=100,
                price=1400.0,
                amount=140000.0,
                confirm_date=date(2026, 1, 1),
                symbol=symbol,
                asset_type='stock',
            )
            make_transaction(
                pos.id,
                pos.ledger_id,
                txn_type='sell',
                quantity=100,
                price=1500.0,
                amount=150000.0,
                confirm_date=date(2026, 2, 1),
                symbol=symbol,
                asset_type='stock',
            )
        # 不过滤：两只写法变体按身份键合并为一个标的（产品级口径）
        all_data = build_cleared_cycles(db, family_id=1)
        assert len(all_data['cycles']) == 1
        assert all_data['cycles'][0]['realized_pnl'] == 20000.0
        assert all_data['cycles'][0]['trade_count'] == 4
        # 过滤：字面量与带前缀写法都能命中同一标的
        for q in ('600519', 'SH600519'):
            data = build_cleared_cycles(db, family_id=1, symbol=q)
            assert len(data['cycles']) == 1
            assert data['cycles'][0]['realized_pnl'] == 20000.0

    def test_ledger_filter(self, db, make_position, make_transaction):
        """ledger_id 过滤：只统计该账户的流水（两账户同标的合并仍一轮周期）。"""
        positions = []
        for account in ('账户A', '账户B'):
            # make_position 按 account_name 自动建档（不同名 → 不同 ledger_id）
            positions.append(
                make_position(
                    symbol='000001',
                    name='标的',
                    account_name=account,
                    asset_type='open_fund',
                    quantity=100,
                    current_price=1.0,
                )
            )
        for pos in positions:
            make_transaction(
                pos.id,
                pos.ledger_id,
                txn_type='buy',
                quantity=100,
                price=1.0,
                amount=100.0,
                confirm_date=date(2026, 1, 1),
                symbol='000001',
            )
            make_transaction(
                pos.id,
                pos.ledger_id,
                txn_type='sell',
                quantity=100,
                price=1.2,
                amount=120.0,
                confirm_date=date(2026, 2, 1),
                symbol='000001',
            )
        data = build_cleared_cycles(db, family_id=1, ledger_id=positions[0].ledger_id)
        assert len(data['cycles']) == 1
        assert data['cycles'][0]['realized_pnl'] == 20.0
        # 不传 ledger_id：两账户合并（产品级口径）仍是一个标的的一轮周期
        merged = build_cleared_cycles(db, family_id=1)
        assert len(merged['cycles']) == 1
        assert merged['cycles'][0]['realized_pnl'] == 40.0
        assert merged['cycles'][0]['trade_count'] == 4
