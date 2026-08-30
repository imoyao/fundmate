# -*- coding: utf-8 -*-
"""红利再投资（dividend_reinvest）接线测试。

对应 issue #1177：此前红利再投资与现金分红合并进同一分支，落库时
`quantity=0`、notes 硬编码「现金分红」，持仓份额永不增加，且 XIRR 把它
当流出却没有对应的分红流入，投入被虚增、年化被低估。

修复后走「分红入账 + 按净值申购」两笔流水，以 link_group_id 配对。
"""

from datetime import date

from app.core.money import Money
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService


def _base_data(**overrides):
    """构造红利再投资入参，单位与 orchestrator 一致（元 / 份，未换算）。"""
    data = {
        'symbol': '000001',
        'account_name': '支付宝',
        'asset_type': 'fund',
        'op_type': 'dividend_reinvest',
        'quantity': 100.0,  # 再投资份额（份）
        'nav': 1.5,  # 当日净值（元）
        'dividend_amount': 150.0,  # 分红金额（元）= 100 × 1.5
        'trade_date': date(2026, 8, 1),
        'confirm_date': date(2026, 8, 1),
        'import_hash': 'reinvest-hash-001',
        'link_group_id': 'reinvest-grp-001',
        'family_id': 1,
    }
    data.update(overrides)
    return data


def _make_holding(make_position, symbol='000001', account='支付宝', quantity=1000, avg_price=1.0):
    return make_position(
        symbol=symbol,
        name='测试基金',
        asset_type='fund',
        account_name=account,
        quantity=quantity,
        avg_price=avg_price,
        current_price=1.5,
    )


def test_reinvest_increases_shares_and_pairs_transactions(db, make_position):
    """红利再投资：份额增加，且产生分红 + 申购两笔配对流水。"""
    pos = _make_holding(make_position)

    PositionService.process_orphan_dividend(db, _base_data())
    db.refresh(pos)

    # 份额：1000 + 100
    assert Money.min_unit_to_shares(pos.quantity) == 1100
    # 成本均价：(1000×1.0 + 100×1.5) / 1100 = 1.0455
    assert round(Money.price_units_to_yuan(pos.avg_price), 4) == 1.0455

    txns = db.query(Transaction).filter_by(position_id=pos.id).order_by(Transaction.id).all()
    assert len(txns) == 2

    dividend_txn = next(t for t in txns if t.txn_type == 'dividend')
    buy_txn = next(t for t in txns if t.txn_type == 'buy')

    # 金额相等：分红流入与再投资申购一进一出，净现金流为 0
    # （amount 恒为正，方向由 XIRR 引擎按 txn_type 分流）
    assert dividend_txn.amount == 15000
    assert buy_txn.amount == 15000

    # 两笔以 link_group_id 配对，便于前端折叠为一条「红利再投资」
    assert dividend_txn.link_group_id == 'reinvest-grp-001'
    assert buy_txn.link_group_id == 'reinvest-grp-001'

    # 去重键：主流水沿用原始 hash（重导命中即跳过整条），申购流水派生，
    # 避开 uq_txn_import_hash(COALESCE(ledger_id,-1), import_hash) 唯一约束
    assert dividend_txn.import_hash == 'reinvest-hash-001'
    assert buy_txn.import_hash == 'reinvest-hash-001#reinvest'

    # 申购流水带份额与净值；分红流水不改变份额
    assert Money.min_unit_to_shares(buy_txn.quantity) == 100
    assert round(Money.price_units_to_yuan(buy_txn.price), 4) == 1.5
    assert dividend_txn.quantity == 0


def test_reinvest_deduces_nav_when_missing(db, make_position):
    """净值缺失时按 分红金额 / 份额 反推，不因缺字段而失败。"""
    pos = _make_holding(make_position)

    PositionService.process_orphan_dividend(db, _base_data(nav=0))
    db.refresh(pos)

    assert Money.min_unit_to_shares(pos.quantity) == 1100
    buy_txn = db.query(Transaction).filter_by(txn_type='buy').first()
    assert round(Money.price_units_to_yuan(buy_txn.price), 4) == 1.5


def test_reinvest_degrades_to_cash_when_missing_shares(db, make_position):
    """缺份额时降级为现金分红：份额不变、只落一笔流水，不阻断整批导入。"""
    pos = _make_holding(make_position)

    PositionService.process_orphan_dividend(db, _base_data(quantity=0))
    db.refresh(pos)

    assert Money.min_unit_to_shares(pos.quantity) == 1000

    txns = db.query(Transaction).filter_by(position_id=pos.id).all()
    assert len(txns) == 1
    assert txns[0].txn_type == 'dividend'
    assert txns[0].amount == 15000


def test_cash_dividend_behaviour_unchanged(db, make_position):
    """现金分红不受影响：份额不变、单笔流水。"""
    pos = _make_holding(make_position, symbol='000002', account='天天基金', quantity=500, avg_price=2.0)

    PositionService.process_orphan_dividend(
        db,
        _base_data(
            symbol='000002',
            account_name='天天基金',
            op_type='dividend_cash',
            quantity=0,
            nav=0,
            dividend_amount=80.0,
            import_hash='cash-hash-001',
            link_group_id=None,
        ),
    )
    db.refresh(pos)

    assert Money.min_unit_to_shares(pos.quantity) == 500

    txns = db.query(Transaction).filter_by(position_id=pos.id).all()
    assert len(txns) == 1
    assert txns[0].txn_type == 'dividend'
    assert txns[0].amount == 8000
    assert Money.price_units_to_yuan(pos.avg_price) == 2.0


def test_reinvest_orphan_when_no_position(db):
    """找不到持仓时落孤儿流水，notes 标明是红利再投资。"""
    result = PositionService.process_orphan_dividend(db, _base_data())

    assert result is None

    txn = db.query(Transaction).filter_by(import_hash='reinvest-hash-001').first()
    assert txn is not None
    assert txn.entry_status == 'orphan'
    assert txn.quantity == 0
    assert '红利再投资' in (txn.notes or '')
