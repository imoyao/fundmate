# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/3 23:21
# File : test_orchestrator.py
# tests/services/importer/test_orchestrator.py
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import SBException
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.fund_service import FundService
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.importer.records import StandardTransactionRecord
from app.services.position_service import PositionService


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


def test_commit_split_records_orphan_when_no_position(db):
    """P2-2：导入送股无关联持仓时记孤儿流水（份额计入、价格/金额为零），不阻断导入。"""
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
    assert result['orphan_count'] == 1
    txn = db.query(Transaction).filter_by(txn_type='split').first()
    assert txn is not None
    assert txn.entry_status == 'orphan'
    assert txn.price == 0
    assert txn.quantity == Money.shares_to_min_unit(100)


def test_commit_split_associates_existing_position(db):
    """P2-2：导入送股有关联持仓时计入份额、均价被零成本份额稀释。"""
    PositionService.process_buy_or_deposit(
        db,
        {
            'symbol': 'SH600001',
            'name': '测试转股',
            'asset_type': 'stock',
            'quantity': 100,
            'avg_price': 10,
            'ledger_id': 1,
            'account_name': '测试账户',
            'family_id': 1,
            'trade_date': datetime(2026, 7, 1),
            'confirm_date': date(2026, 7, 1),
        },
    )
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
    assert result['orphan_count'] == 0
    pos = db.query(Position).filter_by(symbol='SH600001', account_name='测试账户', family_id=1).first()
    assert pos.quantity == Money.shares_to_min_unit(200)
    txn = db.query(Transaction).filter_by(txn_type='split', position_id=pos.id).first()
    assert txn is not None
    assert txn.entry_status == 'success'


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


# ── B3 修复回归 + 份额精度（2026-08-17） ──


def test_commit_savepoint_rolls_back_partial_write(db, monkeypatch):
    """B3 修复：单条记录中途抛错 → savepoint 回滚部分写入，后续记录正常导入。"""
    ledger = Ledger(name='证券账户A', ledger_type='stock', family_id=1)
    db.add(ledger)
    db.commit()

    orig = PositionService.process_buy_or_deposit

    def boom(db, data):
        if data['symbol'] == 'SH600001':
            # 模拟中途写入后抛错（已 add + flush 的持仓应随 savepoint 回滚）
            pos = Position(
                symbol=data['symbol'],
                name=data.get('name', ''),
                ledger_id=data.get('ledger_id'),
                family_id=data.get('family_id', 1),
                quantity=Money.shares_to_min_unit(100),
                avg_price=Money.yuan_to_price_units(10),
                current_price=Money.yuan_to_price_units(10),
            )
            db.add(pos)
            db.flush()
            raise ValueError('模拟中途异常')
        return orig(db, data)

    monkeypatch.setattr(PositionService, 'process_buy_or_deposit', boom)

    orch = ImportOrchestrator(db, family_id=1)
    bad = StandardTransactionRecord(
        confirm_date=date(2026, 8, 1),
        asset_type='stock',
        symbol='SH600001',
        name='失败标的',
        business_type='buy',
        amount=Decimal('1000'),
        account_name='证券账户A',
        ledger_id=ledger.id,
        shares=Decimal('100'),
        nav=Decimal('10'),
    )
    good = StandardTransactionRecord(
        confirm_date=date(2026, 8, 1),
        asset_type='stock',
        symbol='SH600002',
        name='正常标的',
        business_type='buy',
        amount=Decimal('2000'),
        account_name='证券账户A',
        ledger_id=ledger.id,
        shares=Decimal('200'),
        nav=Decimal('10'),
    )
    result = orch.commit([bad, good])
    assert result['imported'] == 1
    assert len(result['errors']) == 1
    assert result['errors'][0]['symbol'] == 'SH600001'
    # 失败条的部分写入已回滚，不残留
    assert db.query(Position).filter_by(symbol='SH600001', family_id=1).first() is None
    # 后续记录正常导入
    assert db.query(Position).filter_by(symbol='SH600002', family_id=1).first() is not None


def test_commit_failed_record_does_not_break_batch(db):
    """B3 修复：业务校验失败（一手起买）记录计入 errors，同批后续记录正常导入。"""
    ledger = Ledger(name='证券账户A', ledger_type='stock', family_id=1)
    db.add(ledger)
    db.commit()

    orch = ImportOrchestrator(db, family_id=1)
    bad = StandardTransactionRecord(
        confirm_date=date(2026, 8, 1),
        asset_type='stock',
        symbol='SH600001',
        name='碎股买入',
        business_type='buy',
        amount=Decimal('500'),
        account_name='证券账户A',
        ledger_id=ledger.id,
        shares=Decimal('50'),  # 不足一手（100 股）
        nav=Decimal('10'),
    )
    good = StandardTransactionRecord(
        confirm_date=date(2026, 8, 1),
        asset_type='stock',
        symbol='SH600002',
        name='正常买入',
        business_type='buy',
        amount=Decimal('2000'),
        account_name='证券账户A',
        ledger_id=ledger.id,
        shares=Decimal('200'),
        nav=Decimal('10'),
    )
    result = orch.commit([bad, good])
    assert result['imported'] == 1
    assert len(result['errors']) == 1
    assert '一手' in result['errors'][0]['error']
    assert db.query(Position).filter_by(symbol='SH600002', family_id=1).first() is not None


def test_commit_cash_follows_target_ledger_cross_import(db):
    """#1067 修复：跨账本重导含现金/货基交割单时，现金行应跟随目标账本，
    而非被强制塞进全局 bank 账本（否则会在 (bank, import_hash) 上撞车静默失败）。
    同一份货基行用相同 import_hash 导入两个不同账本，应各自成功、互不冲突。"""
    ledger_a = Ledger(name='证券账户A', ledger_type='stock', family_id=1)
    ledger_b = Ledger(name='证券账户B', ledger_type='stock', family_id=1)
    db.add_all([ledger_a, ledger_b])
    db.commit()

    orch = ImportOrchestrator(db, family_id=1)
    # 第一遍导入到 ledger_a（含货基行，import_hash 相同）
    row_a = {
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
        'ledger_id': ledger_a.id,
        'contract_id': 'TXN-X',
        'net_amount': 88.5,
        'source': 'ths_stock',
        'import_hash': 'same-hash',
    }
    res_a = orch.commit_from_preview([row_a])
    assert res_a['imported'] == 1

    # 第二遍跨账本重导到 ledger_b（相同 import_hash 模拟同一份交割单）
    row_b = dict(row_a)
    row_b['ledger_id'] = ledger_b.id
    res_b = orch.commit_from_preview([row_b])
    assert res_b['imported'] == 1

    # 两条货基交易分别归属各自账本，不撞
    txns = db.query(Transaction).filter_by(import_hash='same-hash').all()
    assert len(txns) == 2
    ledger_ids = {t.ledger_id for t in txns}
    assert ledger_ids == {ledger_a.id, ledger_b.id}
    # 没有现金行落到 bank 账本
    assert not any(t.ledger_id is None for t in txns)


def test_commit_cash_stays_in_target_ledger_even_when_bank_linked(db):
    """#1137 修正：目标账本已绑定现金账户（linked_cash_ledger_id 指向 bank）时，
    货基/现金回款仍应「留在投资账本本身」，不再被搬到绑定的 bank 账本——
    银证转账是用户显式操作，系统不代劳（自动搬账等价于凭空生成一笔银证转账）。"""
    bank = Ledger(name='招行卡', ledger_type='bank', family_id=1)
    stock = Ledger(name='证券账户', ledger_type='stock', family_id=1)
    db.add_all([bank, stock])
    db.flush()  # 先落库拿 id：未 flush 时 bank.id 为 None，绑定会被写成 NULL（存量 bug，2026-08-24 修复）
    stock.linked_cash_ledger_id = bank.id  # 绑定现金账户
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
        'ledger_id': stock.id,  # 目标账本是证券账户（未直接选 bank）
        'contract_id': 'TXN-Y',
        'net_amount': 88.5,
        'source': 'ths_stock',
        'import_hash': 'h-bound-bank',
    }
    res = orch.commit_from_preview([row])
    assert res['imported'] == 1
    txn = db.query(Transaction).filter_by(import_hash='h-bound-bank').first()
    assert txn is not None
    # 回款留在投资账本，不落绑定的 bank（不再隐式银证转账）
    assert txn.ledger_id == stock.id
    assert txn.ledger_id != bank.id
    assert txn.account_name == '证券账户'


def test_money_fund_row_and_explicit_transfer_are_independent(db):
    """#1137 回归：同批次内货基回款行与显式银证转账行互不干扰——
    货基行留在投资账本，转账行仍按 #1010 在 bank 生成反向流水。"""
    bank, stock = _make_linked_pair(db)

    orch = ImportOrchestrator(db, family_id=1)
    money_fund_row = {
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
        'ledger_id': stock.id,
        'contract_id': 'TXN-MF',
        'net_amount': 88.5,
        'source': 'ths_stock',
        'import_hash': 'mf-hash',
    }
    transfer_row = _make_transfer_row(ledger_id=stock.id, import_hash='transfer-hash-indep')
    res = orch.commit_from_preview([money_fund_row, transfer_row])

    # 货基行走投资分支；转账行走 #1010 闭环
    assert res['imported'] == 1
    assert res['cash_transfers_created'] == 1

    mf_txn = db.query(Transaction).filter_by(import_hash='mf-hash').first()
    assert mf_txn is not None
    assert mf_txn.ledger_id == stock.id  # 不被搬到 bank

    transfer_txn = db.query(Transaction).filter_by(import_hash='transfer-hash-indep').first()
    assert transfer_txn is not None
    assert transfer_txn.ledger_id == bank.id  # #1010 闭环仍然生效
    assert transfer_txn.txn_type == 'withdraw'  # 方向反转


def test_fill_missing_nav_and_shares_4_decimal_precision(db, monkeypatch):
    """份额精度修复：预估份额保留 4 位小数（与 min_unit 对齐），不再截断到 2 位。"""
    monkeypatch.setattr(FundService, 'get_fund_nav_map', lambda db, symbols, target_date: {'014330': Decimal('1.2345')})
    orch = ImportOrchestrator(db, family_id=1)
    rec = StandardTransactionRecord(
        confirm_date=date(2026, 8, 1),
        asset_type='fund',
        symbol='014330',
        name='测试基金',
        business_type='buy',
        amount=Decimal('1000.00'),
        account_name='测试账户',
    )
    orch._fill_missing_nav_and_shares([rec])
    assert rec.is_calculated is True
    assert rec.nav == Decimal('1.2345')
    # 1000.00 / 1.2345 = 810.044552... → 4 位小数 810.0446（2 位精度会截成 810.04）
    assert rec.shares == Decimal('810.0446')


# ── #1020 / #1065 去重作用域降级回归（2026-08-23） ──


def test_dedup_scope_downgraded_to_ledger(db):
    """#1065：去重作用域从 family 级降为 ledger 级。
    - 同 ledger 重复导入仍幂等防重（skipped）；
    - 跨 ledger 导入同一 import_hash 不再被误判重复（放行跨账本重导，#1020 修复点）。
    """
    ledger_a = Ledger(name='券商A', ledger_type='stock', family_id=1)
    ledger_b = Ledger(name='券商B', ledger_type='stock', family_id=1)
    db.add_all([ledger_a, ledger_b])
    db.commit()

    orch = ImportOrchestrator(db, family_id=1)
    base_row = {
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
        'contract_id': 'TXN-HX',
        'net_amount': 88.5,
        'source': 'ths_stock',
        'import_hash': 'HX-same-hash',
    }

    # 1) ledger A 首次导入 -> imported
    r1 = orch.commit_from_preview([{**base_row, 'ledger_id': ledger_a.id}])
    assert r1['imported'] == 1

    # 2) ledger A 重复导入同 hash -> 幂等防重，skipped
    r2 = orch.commit_from_preview([{**base_row, 'ledger_id': ledger_a.id}])
    assert r2['skipped'] == 1

    # 3) ledger B 导入同 hash -> 跨账本放行，imported（#1020 修复点）
    r3 = orch.commit_from_preview([{**base_row, 'ledger_id': ledger_b.id}])
    assert r3['imported'] == 1

    # 4) 两条交易分属不同 ledger，均在库
    assert db.query(Transaction).filter_by(import_hash='HX-same-hash').count() == 2


# ── #1010 银证转账闭环（2026-08-24） ──


def _make_transfer_row(**overrides):
    """构造同花顺解析器形态的银证转账预览行（证券侧视角）。"""
    row = {
        'symbol': '__CASH__',
        'name': '银行转证券',
        'type': 'cash',
        'op_type': 'deposit',
        'amount': 10000.0,
        'quantity': 0,
        'price': 0,
        'fee': 0.0,
        'trade_date': '2026-08-20',
        'account_name': '',
        'net_amount': 10000.0,
        'source': 'ths_stock',
        'import_hash': 'transfer-hash-1',
        'is_cash_transfer': True,
    }
    row.update(overrides)
    return row


def _make_linked_pair(db, stock_name='华泰证券', bank_name='招行卡'):
    """创建「证券账本 + 绑定现金账本」对。

    注意：必须先 flush 拿到 bank.id 再绑定——未落库前 bank.id 为 None，
    直接赋值会把 linked_cash_ledger_id 写成 NULL（B6 测曾因此静默失效）。
    """
    bank = Ledger(name=bank_name, ledger_type='bank', family_id=1)
    stock = Ledger(name=stock_name, ledger_type='stock', family_id=1)
    db.add_all([bank, stock])
    db.flush()
    stock.linked_cash_ledger_id = bank.id
    db.commit()
    return bank, stock


def test_cash_transfer_deposit_generates_inverted_bank_withdraw(db):
    """#1010：已关联现金账户时，证券侧「银行转证券」(deposit) 应在 bank 生成反向 withdraw。"""
    bank, stock = _make_linked_pair(db)

    orch = ImportOrchestrator(db, family_id=1)
    res = orch.commit_from_preview([_make_transfer_row(ledger_id=stock.id)])

    assert res['imported'] == 0  # 转账不计入投资 imported 口径
    assert res['skipped'] == 0
    assert res['cash_transfers_created'] == 1
    txn = db.query(Transaction).filter_by(import_hash='transfer-hash-1').first()
    assert txn is not None
    assert txn.txn_type == 'withdraw'  # 方向反转：银行侧取出
    assert txn.ledger_id == bank.id
    assert txn.asset_type == 'cash'
    assert txn.amount == Money.yuan_to_cents(10000.0)  # 整数分
    assert txn.account_name == '招行卡'


def test_cash_transfer_withdraw_generates_bank_deposit(db):
    """#1010：证券侧「证券转银行」(withdraw) 应在 bank 生成反向 deposit。"""
    bank, stock = _make_linked_pair(db)

    orch = ImportOrchestrator(db, family_id=1)
    res = orch.commit_from_preview(
        [
            _make_transfer_row(
                ledger_id=stock.id,
                op_type='withdraw',
                name='证券转银行',
                net_amount=-5000.5,
                amount=5000.5,
                import_hash='transfer-hash-2',
            )
        ]
    )

    assert res['cash_transfers_created'] == 1
    txn = db.query(Transaction).filter_by(import_hash='transfer-hash-2').first()
    assert txn is not None
    assert txn.txn_type == 'deposit'
    assert txn.amount == Money.yuan_to_cents(5000.5)  # 净额绝对值，负号只表达方向


def test_cash_transfer_without_linked_ledger_keeps_skipped(db):
    """#1010：未关联现金账户时维持旧行为——转账行计入 skipped，不产生任何流水。"""
    stock = Ledger(name='华泰证券', ledger_type='stock', family_id=1)
    db.add(stock)
    db.commit()

    orch = ImportOrchestrator(db, family_id=1)
    res = orch.commit_from_preview([_make_transfer_row(ledger_id=stock.id)])

    assert res['imported'] == 0
    assert res['skipped'] == 1
    assert res['cash_transfers_created'] == 0
    assert db.query(Transaction).filter_by(import_hash='transfer-hash-1').count() == 0


def test_cash_transfer_non_bank_link_treated_as_unlinked(db):
    """#1010：绑定目标非 bank 类型视为未有效绑定，转账行跳过（与 #1067 口径一致）。"""
    fund_ledger = Ledger(name='蚂蚁基金', ledger_type='fund', family_id=1)
    stock = Ledger(name='华泰证券', ledger_type='stock', family_id=1)
    stock.linked_cash_ledger_id = fund_ledger.id  # 非法绑定：指向非 bank
    db.add_all([fund_ledger, stock])
    db.commit()

    orch = ImportOrchestrator(db, family_id=1)
    res = orch.commit_from_preview([_make_transfer_row(ledger_id=stock.id)])

    assert res['skipped'] == 1
    assert res['cash_transfers_created'] == 0
    assert db.query(Transaction).filter_by(import_hash='transfer-hash-1').count() == 0


def test_cash_transfer_reimport_deduped_by_ledger_and_hash(db):
    """#1010：同一份交割单重导，现金侧记录按 (现金账本, import_hash) 幂等防重。"""
    bank, stock = _make_linked_pair(db)

    orch = ImportOrchestrator(db, family_id=1)
    r1 = orch.commit_from_preview([_make_transfer_row(ledger_id=stock.id)])
    r2 = orch.commit_from_preview([_make_transfer_row(ledger_id=stock.id)])

    assert r1['cash_transfers_created'] == 1
    assert r2['cash_transfers_created'] == 0
    assert r2['skipped'] == 1  # 重导计入 skipped，不翻倍
    assert db.query(Transaction).filter_by(import_hash='transfer-hash-1').count() == 1


def test_mixed_rows_transfer_and_invest_counted_separately(db):
    """#1010：转账与投资交易混排时各自独立计数，互不污染对方口径。"""
    bank, stock = _make_linked_pair(db)

    orch = ImportOrchestrator(db, family_id=1)
    invest_row = {
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
        'ledger_id': stock.id,
        'contract_id': 'TXN-MIX',
        'net_amount': 88.5,
        'source': 'ths_stock',
        'import_hash': 'mix-hash',
    }
    res = orch.commit_from_preview([invest_row, _make_transfer_row(ledger_id=stock.id)])

    assert res['imported'] == 1  # 仅投资交易
    assert res['cash_transfers_created'] == 1  # 仅转账
    assert res['skipped'] == 0
