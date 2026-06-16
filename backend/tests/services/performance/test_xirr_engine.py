import datetime as dt

from app.services.importer.mappings import BusinessType
from app.services.performance.xirr_engine import calculate_xirr, generate_cashflows


class MockTransaction:
    def __init__(self, confirm_date, txn_type, amount, trade_date=None):
        self.confirm_date = confirm_date
        self.trade_date = trade_date
        self.txn_type = txn_type
        self.amount = amount


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
