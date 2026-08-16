# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/3 23:21
# File : test_orchestrator.py
# tests/services/importer/test_orchestrator.py
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import SBException
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.transactions.models import Transaction
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


# ── B1–B5 修复回归（2026-08-17） ──


def test_commit_split_price_converted_to_cents(db):
    """B1 修复：SPLIT（转股）价格按分入库，与 BOND_REDEEM 口径一致。"""
    orch = ImportOrchestrator(db, family_id=1)
    record = StandardTransactionRecord(
        confirm_date=date(2026, 8, 1),
        asset_type='stock',
        symbol='SH600001',
        name='测试转股',
        business_type='split',
        amount=Decimal('0'),
        account_name='测试账户',
        shares=Decimal('100'),
        nav=Decimal('10.5'),
    )
    result = orch.commit([record])
    assert result['imported'] == 1
    txn = db.query(Transaction).filter_by(txn_type='split').first()
    assert txn is not None
    assert txn.price == Money.yuan_to_cents(10.5)  # 1050 分
    assert txn.quantity == Money.shares_to_min_unit(100)


def test_commit_from_preview_passes_net_amount(db):
    """B2 修复：commit_from_preview 透传 net_amount（净发生金额），现金类行按净额入账。"""
    ledger = Ledger(name='银行卡', ledger_type='bank', family_id=1)
    db.add(ledger)
    db.commit()

    orch = ImportOrchestrator(db, family_id=1)
    row = {
        'symbol': '000001',
        'name': '货币基金',
        'type': 'money_fund',
        'op_type': 'deposit',
        'amount': 100.0,
        'quantity': None,
        'price': None,
        'fee': 0.0,
        'trade_date': '2026-08-01',
        'account_name': '',
        'ledger_id': ledger.id,
        'contract_id': 'TXN001',
        'net_amount': 88.5,
        'source': 'ths_stock',
        'import_hash': 'h1',
    }
    result = orch.commit_from_preview([row])
    assert result['imported'] == 1
    txn = db.query(Transaction).filter_by(import_hash='h1').first()
    assert txn is not None
    assert txn.amount == Money.yuan_to_cents(88.5)


def test_commit_cash_missing_ledger_counts_skipped(db):
    """B4 修复：现金管理产品缺 ledger_id 跳过时计入 skipped（原漏计数）。"""
    orch = ImportOrchestrator(db, family_id=1)
    row = {
        'symbol': '000001',
        'name': '货币基金',
        'type': 'money_fund',
        'op_type': 'deposit',
        'amount': 100.0,
        'quantity': None,
        'price': None,
        'fee': 0.0,
        'trade_date': '2026-08-01',
        'account_name': '',
        'ledger_id': None,
        'contract_id': 'TXN002',
        'net_amount': 88.5,
        'source': 'ths_stock',
        'import_hash': 'h2',
    }
    result = orch.commit_from_preview([row])
    assert result['imported'] == 0
    assert result['skipped'] == 1


def test_commit_from_preview_none_amount_safe(db):
    """B5 修复：amount/quantity/price/fee 为 None 时不抛 Decimal 异常，走业务校验。"""
    orch = ImportOrchestrator(db, family_id=1)
    row = {
        'symbol': 'SH600519',
        'name': '贵州茅台',
        'type': 'stock',
        'op_type': 'buy',
        'amount': None,
        'quantity': None,
        'price': None,
        'fee': None,
        'trade_date': '2026-08-01',
        'account_name': '测试账户',
        'ledger_id': None,
        'contract_id': 'TXN003',
        'source': 'ths_stock',
        'import_hash': 'h3',
    }
    result = orch.commit_from_preview([row])
    # 不崩溃；因缺数量被业务校验拦下计入 errors
    assert result['imported'] == 0
    assert result['errors'] != []
