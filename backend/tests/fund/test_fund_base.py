# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/2/20 21:40
# File : test_fund_base.py
import pytest

from backend.fundmate.fund.base import FundMiddleWare


class TestFundMiddleWare:

    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_fd_mw = FundMiddleWare()

    @pytest.mark.parametrize("amount,charge_rate,is_round,expected", [
        (10000, 0.15, True, 14.98),
        (10000, 0.15, False, 14.98),
        (3000, 0.015, True, 0.45),
        (3000, 0.015, True, 0.45),
    ])
    def test_charge_amount(self, amount, charge_rate, is_round, expected):
        result = self.test_fd_mw.charge_amount(amount, charge_rate, is_round)
        if not is_round:
            assert result == pytest.approx(expected, 0.01)
        else:
            assert result == expected

    @pytest.mark.parametrize("amount,charge_rate,is_round,expected", [
        (10000, 0.15, True, 9985.02),
        (10000, 0.15, False, 9985.02),
        (3000, 0.015, False, 2999.55),
    ])
    def test_real_amount(self, amount, charge_rate, is_round, expected):
        result = self.test_fd_mw.real_amount(amount, charge_rate, is_round)
        if not is_round:
            assert result == pytest.approx(expected, 0.01)
        else:
            assert result == expected

    @pytest.mark.parametrize("amount,charge_rate,daily_value,expected", [
        (10000, 0.15, 5.5340, 1804.3),
        (3000, 0.015, 0.9280, 3232.27),
    ])
    def test_share_holders(self, amount, charge_rate, daily_value, expected):
        result = self.test_fd_mw.share_holders(amount, charge_rate, daily_value)
        assert result == expected

    @pytest.mark.parametrize("amount,charge_rate,daily_value,expected", [
        (3000, 0.15, 5.5340, {'charge_amount': 4.49, 'real_amount': 2995.51, 'hold_value': 541.29}),
        (3000, 0.15, 5.2280, {'charge_amount': 4.49, 'real_amount': 2995.51, 'hold_value': 572.97}),
    ])
    def test_cal_purchase_info(self, amount, charge_rate, daily_value, expected):
        result = self.test_fd_mw.cal_purchase_info(amount, charge_rate, daily_value)
        assert result == expected
        assert isinstance(result.get('hold_value'), float)

    @pytest.mark.parametrize("portion,charge_rate,daily_value,expected", [
        (3000, 0.15, 5.2245, {'charge_amount': 23.51, 'real_amount': 15649.99}),
        (3000, 0.015, 5.2280, {'charge_amount': 2.35, 'real_amount': 15681.65}),
    ])
    def test_cal_redeem_info(self, portion, charge_rate, daily_value, expected):
        result = self.test_fd_mw.cal_redeem_info(portion, charge_rate, daily_value)
        assert result == expected
        assert isinstance(result.get('real_amount'), float)
