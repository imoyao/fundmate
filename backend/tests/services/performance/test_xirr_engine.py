import datetime as dt

from app.services.importer.mappings import BusinessType
from app.services.performance.xirr_engine import (
    _exclude_internal_transfers,
    calculate_xirr,
    generate_cashflows,
)


class MockTransaction:
    def __init__(self, confirm_date, txn_type, amount, trade_date=None, asset_type=None):
        self.confirm_date = confirm_date
        self.trade_date = trade_date
        self.txn_type = txn_type
        self.amount = amount
        # 货基 / 逆回购 / 现金需被 XIRR 排除（决策文档 §2.1-4），故需可指定资产类型
        self.asset_type = asset_type


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
        """组合内两账户之间同日等额对敲，应被识别为内部划转并成对剔除。"""
        candidates = [
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.WITHDRAW.code,
                'account_name': '支付宝',
            },
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.DEPOSIT.code,
                'account_name': '天天基金',
            },
        ]
        excluded = _exclude_internal_transfers(candidates, {'支付宝', '天天基金'})
        assert excluded == {0, 1}

    def test_case9_external_transfer_not_excluded(self):
        """对手方不在本组合内（真实外部出入金），不得当成内部划转剔除。"""
        candidates = [
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.WITHDRAW.code,
                'account_name': '支付宝',
            },
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.DEPOSIT.code,
                'account_name': '银行卡',  # 不属于本组合账户
            },
        ]
        excluded = _exclude_internal_transfers(candidates, {'支付宝', '天天基金'})
        assert excluded == set()

    def test_case9_transfer_amount_mismatch_not_excluded(self):
        """金额不等不构成划转配对。"""
        candidates = [
            {
                'date': dt.date(2024, 3, 1),
                'amount': 5000.0,
                'amount_cents': 500000,
                'txn_type': BusinessType.WITHDRAW.code,
                'account_name': '支付宝',
            },
            {
                'date': dt.date(2024, 3, 1),
                'amount': 4000.0,
                'amount_cents': 400000,
                'txn_type': BusinessType.DEPOSIT.code,
                'account_name': '天天基金',
            },
        ]
        excluded = _exclude_internal_transfers(candidates, {'支付宝', '天天基金'})
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
