# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/3 23:21
# File : test_orchestrator.py
# tests/services/importer/test_orchestrator.py
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import SBException
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.importer.records import StandardTransactionRecord


def test_validate_file_type_rejects_fund_in_stock_account():
    orch = ImportOrchestrator.__new__(ImportOrchestrator)  # 不需要 db session
    records = [
        StandardTransactionRecord(
            confirm_date=date.today(),
            asset_type='fund',
            symbol='014330',
            name='国联优势产业混合C',
            business_type='buy',
            amount=Decimal('10.0'),
            account_name='我的基金账户',
            source='standard_fund',
        ),
        StandardTransactionRecord(
            confirm_date=date.today(),
            asset_type='fund',
            symbol='016600',
            name='万家品质生活混合C',
            business_type='buy',
            amount=Decimal('10.89'),
            account_name='我的基金账户',
            source='standard_fund',
        ),
    ]
    with pytest.raises(SBException, match='多数记录为基金代码'):
        orch.validate_file_type(records, expected_source='standard_stock')


def test_validate_file_type_accepts_stock_in_stock_account():
    orch = ImportOrchestrator.__new__(ImportOrchestrator)
    records = [
        StandardTransactionRecord(
            confirm_date=date.today(),
            asset_type='stock',
            symbol='SH600519',
            name='贵州茅台',
            business_type='buy',
            amount=Decimal('165000.0'),
            account_name='我的股票账户',
            source='standard_stock',
        ),
    ]
    orch.validate_file_type(records, expected_source='standard_stock')  # 不应抛出异常
