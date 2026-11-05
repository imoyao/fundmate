import datetime as dt

from app.services.importer.mappings import BusinessType
from app.services.performance.xirr_engine import (
    _exclude_internal_transfers,
    calculate_xirr,
    generate_cashflows,
)


class MockTransaction:
    def __init__(self, confirm_date, txn_type, amount, trade_date=None, asset_type=None, fee=None):
        self.confirm_date = confirm_date
        self.trade_date = trade_date
        self.txn_type = txn_type
        self.amount = amount
        # 货基 / 逆回购 / 现金需被 XIRR 排除（决策文档 §2.1-4），故需可指定资产类型
        self.asset_type = asset_type
        # 手续费（分）。默认 None 而不是 0：真实库里这一列可为 NULL，
        # 聚合侧必须容忍「没有这一列/值为空」的桩，不能 AttributeError。
        self.fee = fee


def _npv(rate: float, cashflows: list[tuple[dt.date, float]]) -> float:
    """
    按 Excel XIRR 的定义（ACT/365）计算净现值。

    Excel 的 XIRR 就是使该 NPV 为 0 的 rate，因此断言 NPV≈0 等价于
    「与 Excel 一致」，比硬编码手算结果更可靠（不会因手算失误引入假绿灯）。
    """
    d0 = cashflows[0][0]
    return sum(amount / (1 + rate) ** ((d - d0).days / 365.0) for d, amount in cashflows)


def assert_solves_xirr(rate: float, cashflows: list[tuple[dt.date, float]], tol: float = 1e-8) -> None:
    """
    断言 rate 确实是该现金流的 XIRR 解。

    用**相对**残差（NPV / 现金流总规模）而非绝对值：现金流越大绝对残差越大，
    绝对容差会随金额量级误报。
    """
    scale = sum(abs(a) for _, a in cashflows) or 1.0
    residual = abs(_npv(rate, cashflows)) / scale
    assert residual < tol, f'XIRR={rate} 未解出零 NPV，相对残差={residual:.3e}'


class TestGenerateCashflows:
    def test_basic_buy_sell(self):
        txn = [
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000),  # 1000元 -> 100000分
            MockTransaction(dt.date(2025, 6, 1), BusinessType.SELL.code, 120000),  # 1200元 -> 120000分
        ]
        cf = generate_cashflows(txn, current_value=0)
        assert len(cf) == 2
        # 引擎会转回元，所以断言值仍是 -1000.0 / 1200.0
        assert cf[0] == (dt.date(2025, 1, 1), -1000.0)
        assert cf[1] == (dt.date(2025, 6, 1), 1200.0)

    def test_with_virtual_sale(self):
        txn = [MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000)]
        cf = generate_cashflows(txn, current_value=1100.0)  # current_value 仍是元
        assert len(cf) == 2
        assert cf[1] == (dt.date.today(), 1100.0)

    def test_skip_none_date(self):
        txn = [MockTransaction(None, BusinessType.BUY.code, 50000)]  # 500元 -> 50000分
        cf = generate_cashflows(txn, current_value=0)
        assert len(cf) == 0

    def test_mixed_types(self):
        txn = [
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000),
            MockTransaction(dt.date(2025, 2, 1), 'dividend_cash', 5000),
            MockTransaction(dt.date(2025, 3, 1), 'dividend_reinvest', 2000),
            MockTransaction(dt.date(2025, 4, 1), BusinessType.SELL.code, 50000),
        ]
        cf = generate_cashflows(txn, current_value=0)
        assert cf == [
            (dt.date(2025, 1, 1), -1000.0),
            (dt.date(2025, 2, 1), 50.0),
            (dt.date(2025, 3, 1), -20.0),
            (dt.date(2025, 4, 1), 500.0),
        ]


class TestXirr:
    def test_simple_xirr(self):
        cf = [
            (dt.date(2024, 1, 1), -1000.0),
            (dt.date(2025, 1, 1), 1100.0),
        ]
        result = calculate_xirr(cf)
        assert abs(result - 0.1) < 0.01

    def test_empty_cashflows(self):
        assert calculate_xirr([]) == 0.0

    def test_all_positive(self):
        cf = [
            (dt.date(2024, 1, 1), 1000.0),
            (dt.date(2024, 2, 1), 1000.0),
        ]
        assert calculate_xirr(cf) == 0.0

    def test_all_negative(self):
        cf = [
            (dt.date(2024, 1, 1), -1000.0),
            (dt.date(2024, 2, 1), -1000.0),
        ]
        assert calculate_xirr(cf) == 0.0

    def test_zero_amount_filtered(self):
        cf = [
            (dt.date(2024, 1, 1), -1000.0),
            (dt.date(2024, 6, 1), 0.0),
            (dt.date(2025, 1, 1), 1100.0),
        ]
        result = calculate_xirr(cf)
        assert abs(result - 0.1) < 0.01

    def test_excel_comparison(self):
        cf = [
            (dt.date(2020, 1, 1), -10000),
            (dt.date(2020, 6, 1), -2000),
            (dt.date(2021, 1, 1), 3000),
            (dt.date(2021, 6, 1), 5000),
            (dt.date(2022, 1, 1), 7000),
        ]
        result = calculate_xirr(cf)
        assert result > 0 and result < 1.0
        # 与 Excel 一致 = 令 NPV(ACT/365) 归零
        assert_solves_xirr(result, cf)


class TestSpec83Cases:
    """
    补齐 issue #796 决策文档 §8.3「单元测试用例清单」中此前未覆盖的用例。

    清单共 11 条，此前已覆盖：1（空记录）、4（买入后全部卖出）、7（现金分红）、8（红利再投资）。
    本类覆盖剩余：2、3、5、6、9、10、11。
    """

    # --- 用例 2：只有一笔买入 → 返回 0 ---
    def test_case2_only_one_buy_returns_zero(self):
        txn = [MockTransaction(dt.date(2024, 1, 1), BusinessType.BUY.code, 100000)]
        cf = generate_cashflows(txn, current_value=0)
        assert len(cf) == 1  # 只有一笔流出，无法求解
        assert calculate_xirr(cf) == 0.0

    # --- 用例 3：只有一笔卖出 → 返回 0 ---
    def test_case3_only_one_sell_returns_zero(self):
        txn = [MockTransaction(dt.date(2024, 6, 1), BusinessType.SELL.code, 120000)]
        cf = generate_cashflows(txn, current_value=0)
        assert len(cf) == 1
        assert calculate_xirr(cf) == 0.0

    # --- 用例 5：定投多笔后全部卖出 → 与 Excel 一致 ---
    def test_case5_dca_then_full_redeem(self):
        txn = [
            MockTransaction(dt.date(2023, 1, 1), BusinessType.BUY.code, 100000),  # 1000 元
            MockTransaction(dt.date(2023, 2, 1), BusinessType.BUY.code, 100000),
            MockTransaction(dt.date(2023, 3, 1), BusinessType.BUY.code, 100000),
            MockTransaction(dt.date(2024, 1, 1), BusinessType.SELL.code, 330000),  # 3300 元
        ]
        cf = generate_cashflows(txn, current_value=0)
        assert len(cf) == 4
        assert cf[-1] == (dt.date(2024, 1, 1), 3300.0)

        result = calculate_xirr(cf)
        # 总投入 3000 收回 3300，持有不足一年 → 年化应高于 10%
        assert result > 0.10
        assert_solves_xirr(result, cf)

    # --- 用例 6：部分卖出后继续持有 → 与 Excel 一致 ---
    def test_case6_partial_sell_and_hold(self):
        txn = [
            MockTransaction(dt.date(2023, 1, 1), BusinessType.BUY.code, 100000),  # 买入 1000
            MockTransaction(dt.date(2023, 7, 1), BusinessType.SELL.code, 60000),  # 卖出 600
        ]
        # 剩余持仓按最新净值虚拟卖出 700 元（决策：虚拟卖出合并为一笔）
        cf = generate_cashflows(txn, current_value=700.0, end_date=dt.date(2024, 1, 1))
        assert cf == [
            (dt.date(2023, 1, 1), -1000.0),
            (dt.date(2023, 7, 1), 600.0),
            (dt.date(2024, 1, 1), 700.0),
        ]

        result = calculate_xirr(cf)
        assert result > 0
        assert_solves_xirr(result, cf)

    # --- 用例 9：包含资金转入转出 ---
    def test_case9_deposit_withdraw_not_in_cashflows(self):
        """转入/转出不是投资行为，不得进入现金流（否则年化被资金搬运稀释）。"""
        txn = [
            MockTransaction(dt.date(2023, 1, 1), BusinessType.DEPOSIT.code, 500000),
            MockTransaction(dt.date(2023, 1, 2), BusinessType.BUY.code, 100000),
            MockTransaction(dt.date(2024, 1, 2), BusinessType.SELL.code, 110000),
            MockTransaction(dt.date(2024, 1, 3), BusinessType.WITHDRAW.code, 500000),
        ]
        cf = generate_cashflows(txn, current_value=0)
        assert cf == [
            (dt.date(2023, 1, 2), -1000.0),
            (dt.date(2024, 1, 2), 1100.0),
        ]
        assert abs(calculate_xirr(cf) - 0.1) < 0.01

    def test_case9_internal_transfer_pair_excluded(self):
        """组合内两账户之间同日等额对敲，应被识别为内部划转并成对剔除（按 ledger_id）。"""
        candidates = [
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.WITHDRAW.code,
                'ledger_id': 1,
            },
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.DEPOSIT.code,
                'ledger_id': 2,
            },
        ]
        excluded = _exclude_internal_transfers(candidates, {1, 2})
        assert excluded == {0, 1}

    def test_case9_external_transfer_not_excluded(self):
        """对手方不在本组合内（ledger_id 不在集合），不得当成内部划转剔除。"""
        candidates = [
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.WITHDRAW.code,
                'ledger_id': 1,
            },
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.DEPOSIT.code,
                'ledger_id': 3,  # 不属于本组合账户
            },
        ]
        excluded = _exclude_internal_transfers(candidates, {1, 2})
        assert excluded == set()

    def test_case9_transfer_amount_mismatch_not_excluded(self):
        """金额不等不构成划转配对。"""
        candidates = [
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.WITHDRAW.code,
                'ledger_id': 1,
            },
            {
                'date': dt.date(2024, 3, 1),
                'amount': 4000.0,
                'amount_cents': 400000,
                'txn_type': BusinessType.DEPOSIT.code,
                'ledger_id': 2,
            },
        ]
        excluded = _exclude_internal_transfers(candidates, {1, 2})
        assert excluded == set()

    def test_case9_same_name_different_ledger_still_paired(self):
        """回归：两账户同名（不同 ledger_id）但都属于本组合 → 仍正确配对剔除。"""
        candidates = [
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.WITHDRAW.code,
                'ledger_id': 1,  # 账户 A（与 B 同名）
            },
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.DEPOSIT.code,
                'ledger_id': 2,  # 账户 B（与 A 同名，ID 不同）
            },
        ]
        excluded = _exclude_internal_transfers(candidates, {1, 2})
        assert excluded == {0, 1}

    def test_case9_same_name_one_outside_not_excluded(self):
        """回归（account_name 同名 bug 修复）：同名账户之一 ledger_id 不在本组合，不得剔除。"""
        candidates = [
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.WITHDRAW.code,
                'ledger_id': 1,  # 账户 A（本组合）
            },
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.DEPOSIT.code,
                'ledger_id': 99,  # 账户 C 同名但不在本组合
            },
        ]
        excluded = _exclude_internal_transfers(candidates, {1, 2})
        assert excluded == set()

    # --- 用例 10：极端收益率 ---
    def test_case10_extreme_high_return(self):
        """一年 3 倍（+200%）：在 [-1, 10] 区间内，应如实返回而非截断。"""
        cf = [
            (dt.date(2023, 1, 1), -1000.0),
            (dt.date(2024, 1, 1), 3000.0),  # 恰好 365 天
        ]
        result = calculate_xirr(cf)
        assert abs(result - 2.0) < 0.005
        assert_solves_xirr(result, cf)

    def test_case10_extreme_loss(self):
        """一年亏 70%（<-50%）：应如实返回负值。"""
        cf = [
            (dt.date(2023, 1, 1), -1000.0),
            (dt.date(2024, 1, 1), 300.0),
        ]
        result = calculate_xirr(cf)
        assert abs(result - (-0.7)) < 0.005
        assert_solves_xirr(result, cf)

    def test_case10_out_of_range_returns_zero(self):
        """超出 [-1, 10] 的异常值按决策文档归零，避免前端展示 99999%。"""
        cf = [
            (dt.date(2023, 1, 1), -1.0),
            (dt.date(2024, 1, 1), 10000.0),  # 年化约 9999 倍
        ]
        assert calculate_xirr(cf) == 0.0

    # --- 用例 11：包含货币基金交易 → 自动排除 ---
    def test_case11_money_fund_excluded(self):
        txn = [
            MockTransaction(dt.date(2023, 1, 1), BusinessType.BUY.code, 100000, asset_type='fund'),
            MockTransaction(dt.date(2023, 2, 1), BusinessType.BUY.code, 900000, asset_type='money_fund'),
            MockTransaction(dt.date(2023, 6, 1), BusinessType.SELL.code, 900000, asset_type='money_fund'),
            MockTransaction(dt.date(2024, 1, 1), BusinessType.SELL.code, 110000, asset_type='fund'),
        ]
        cf = generate_cashflows(txn, current_value=0)
        # 货基两笔被剔除，只剩普通基金买卖
        assert cf == [
            (dt.date(2023, 1, 1), -1000.0),
            (dt.date(2024, 1, 1), 1100.0),
        ]
        assert abs(calculate_xirr(cf) - 0.1) < 0.01

    def test_case11_reverse_repo_and_cash_excluded(self):
        """逆回购与现金同属活钱管理，一并排除。"""
        txn = [
            MockTransaction(dt.date(2023, 1, 1), BusinessType.BUY.code, 100000, asset_type='reverse_repo'),
            MockTransaction(dt.date(2023, 2, 1), BusinessType.SELL.code, 100500, asset_type='reverse_repo'),
            MockTransaction(dt.date(2023, 3, 1), BusinessType.BUY.code, 200000, asset_type='cash'),
        ]
        assert generate_cashflows(txn, current_value=0) == []


class TestIncludeCashEquivalents:
    """#1354：年化收益是否纳入现金等价物（货币基金/逆回购/现金）的可切换口径。"""

    def test_default_excludes_cash_like(self):
        """默认口径（剔除现金等价物）：货币基金买卖不进现金流。"""
        txn = [
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000, asset_type='money_fund'),
            MockTransaction(dt.date(2025, 6, 1), BusinessType.SELL.code, 102000, asset_type='money_fund'),
        ]
        assert generate_cashflows(txn, current_value=0) == []

    def test_flag_true_keeps_cash_like(self):
        """include_cash_equivalents=True：货币基金买卖并入现金流，得到账户总收益口径。"""
        txn = [
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000, asset_type='money_fund'),
            MockTransaction(dt.date(2025, 6, 1), BusinessType.SELL.code, 102000, asset_type='money_fund'),
        ]
        cf = generate_cashflows(txn, current_value=0, include_cash_equivalents=True)
        assert cf == [
            (dt.date(2025, 1, 1), -1000.0),
            (dt.date(2025, 6, 1), 1020.0),
        ]

    def test_blended_return_lower_than_investment_only(self):
        """含现金等价物会拉低年化（货基 ~2% 拖拽主动投资 ~10%）。"""
        inv = [
            MockTransaction(dt.date(2024, 1, 1), BusinessType.BUY.code, 100000, asset_type='fund'),
            MockTransaction(dt.date(2025, 1, 1), BusinessType.SELL.code, 110000, asset_type='fund'),
        ]
        cash = [
            MockTransaction(dt.date(2024, 1, 1), BusinessType.BUY.code, 100000, asset_type='money_fund'),
            MockTransaction(dt.date(2025, 1, 1), BusinessType.SELL.code, 102000, asset_type='money_fund'),
        ]
        excl = generate_cashflows(inv, current_value=0)
        incl = generate_cashflows(inv + cash, current_value=0, include_cash_equivalents=True)
        from app.services.performance.xirr_engine import calculate_xirr

        xirr_excl = calculate_xirr(excl)
        xirr_incl = calculate_xirr(incl)
        assert xirr_excl > xirr_incl  # 10% > 6%


class TestFeesSink:
    """`fees_sink`：把同一 scope 的手续费合计带出去，且费用**并入现金流**。

    两件事都要钉：
    - 并入（改算）：买入流出 `+(费)`、卖出流入 `−(费)`，否则总收益虚高；
    - 带出去（可见）：同一笔费用还要能单独展示，用户才答得出「花了多少手续费」。

    ⚠️ 2026-11-05 决策：C 阶段这里曾断言「费用不并入现金流」。B 阶段按用户
    拍板改为并入（`total_return` 与 `pnl_service` 的「已扣买入费」对齐）。
    断言随之反转，**不是**为了让红灯变绿而放宽——原来那条断言守的是
    「`amount` 仍是成交毛额」，而这条性质在别处有独立守卫：
    写入侧 `position_service.process_sell`（卖出 `amount = 价 × 量`）、
    前端 `sellFormPayload.spec.ts`（载荷 `amount` 不冲减费用）。本函数只管
    现金流金额，两者不可混淆。
    """

    def test_sums_buy_and_sell_fee_in_yuan(self):
        txn = [
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000, fee=500),
            MockTransaction(dt.date(2025, 6, 1), BusinessType.SELL.code, 120000, fee=600),
        ]
        sink: dict = {}
        generate_cashflows(txn, current_value=0, fees_sink=sink)
        assert sink['fees'] == 11.0  # 5 元 + 6 元

    def test_buy_outflow_includes_fee(self):
        """买入：现金流出 = 成交额 + 费（这笔钱真的划走了）。"""
        txn = [MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000, fee=500)]
        assert generate_cashflows(txn, current_value=0) == [(dt.date(2025, 1, 1), -1005.0)]

    def test_sell_inflow_excludes_fee(self):
        """卖出：现金流入 = 成交额 − 费（到账是净额）。"""
        txn = [MockTransaction(dt.date(2025, 6, 1), BusinessType.SELL.code, 120000, fee=600)]
        assert generate_cashflows(txn, current_value=0) == [(dt.date(2025, 6, 1), 1194.0)]

    def test_no_fee_leaves_cashflows_untouched(self):
        """费用为 0 时与改造前逐位一致——大多数历史流水属于这一类。"""
        txn = [
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000),
            MockTransaction(dt.date(2025, 6, 1), BusinessType.SELL.code, 120000),
        ]
        assert generate_cashflows(txn, current_value=0) == [
            (dt.date(2025, 1, 1), -1000.0),
            (dt.date(2025, 6, 1), 1200.0),
        ]

    def test_counts_only_transactions_that_entered_cashflows(self):
        """被排除的现金等价物，其费用既不进合计也不进现金流——口径与现金流同一 scope。"""
        txn = [
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000, fee=500),
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000, asset_type='money_fund', fee=999),
        ]
        sink: dict = {}
        cf = generate_cashflows(txn, current_value=0, fees_sink=sink)
        assert sink['fees'] == 5.0
        assert cf == [(dt.date(2025, 1, 1), -1005.0)]

    def test_null_and_malformed_fee_degrade_to_zero(self):
        """历史数据 fee 可为 NULL、测试桩可能是字符串：一律 0，不抛错。"""
        txn = [
            MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000, fee=None),
            MockTransaction(dt.date(2025, 1, 2), BusinessType.BUY.code, 100000, fee='oops'),
            MockTransaction(dt.date(2025, 1, 3), BusinessType.BUY.code, 100000, fee=0),
        ]
        sink: dict = {}
        cf = generate_cashflows(txn, current_value=0, fees_sink=sink)
        assert sink['fees'] == 0.0
        assert cf == [
            (dt.date(2025, 1, 1), -1000.0),
            (dt.date(2025, 1, 2), -1000.0),
            (dt.date(2025, 1, 3), -1000.0),
        ]

    def test_sink_absent_does_not_change_cashflows(self):
        """不传 sink 只影响「有没有把合计带出来」，不影响现金流本身。"""
        txn = [MockTransaction(dt.date(2025, 1, 1), BusinessType.BUY.code, 100000, fee=500)]
        assert generate_cashflows(txn, current_value=0) == [(dt.date(2025, 1, 1), -1005.0)]
