# -*- coding: utf-8 -*-
"""
@Time ： 2023/2/2 18:04
@File ：test_fund_models.py
@IDE ：PyCharm
"""
from backend.tests.factories import FundFactory


class TestFund:

    def test_factory(self):
        """Test user factory."""
        fund = FundFactory(
            name='南方基金南方东英银河联昌富时亚太低碳精选ETF南方基金南方东英银河联昌富时亚太低碳精选ETF')
        assert fund
        assert fund.name
