# backend/tests/services/sync/test_dividend_commit_flow.py
"""#541 端到端：分红/送转/配股经 ImportOrchestrator 真正落到 transactions。

前面的用例只测「事件 → StandardTransactionRecord」，本文件测**落库之后**：
份额、成本、金额是否如预期。这才是用户看到的东西。
"""

from datetime import date, timedelta
from decimal import Decimal

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.sync.jobs.dividend_split_job import DividendSplitSyncJob


class _Adapter:
    def get_name(self):
        return 'fake'

    def get_version(self):
        return '1'


def _seed_position(db, symbol='SH600000', shares='1000', avg_price='10'):
    """造一个有**快照锚点**的持仓（与真实数据同形）。

    锚点是份额的事实源：`quantity = snapshot_quantity + Σ(confirm_date > snapshot_date 的流水)`。
    只造 quantity 不给锚点的持仓在「重算」路径里会被全量流水覆盖，那是不存在的形态。
    """
    from app.core.money import Money

    ledger = Ledger(name='默认证券账户', family_id=1, ledger_type='investment')
    db.add(ledger)
    db.flush()
    pos = Position(
        symbol=symbol,
        symbol_norm=f'EXCHANGE:{symbol}',
        name='测试股',
        market='CN_A',
        asset_type='stock',
        ledger_id=ledger.id,
        account_name=ledger.name,
        quantity=Money.shares_to_min_unit(Decimal(shares)),
        avg_price=Money.yuan_to_price_units(Decimal(avg_price)),
        current_price=Money.yuan_to_price_units(Decimal(avg_price)),
        # 锚点定在除权日之前：本文件的事件都发生在锚点之后，才能被计入
        snapshot_quantity=Money.shares_to_min_unit(Decimal(shares)),
        snapshot_avg_price=Money.yuan_to_price_units(Decimal(avg_price)),
        snapshot_date=date.today() - timedelta(days=60),
        anchor_kind='external',
        family_id=1,
    )
    db.add(pos)
    db.commit()
    return ledger, pos


def _run(db, events, symbol='SH600000'):
    job = DividendSplitSyncJob(_Adapter(), db)
    job.stats = {'total': 0, 'success': 0, 'skipped': 0, 'failed': 0, 'errors': []}
    validated = job._validate_data(events)
    fresh = job._deduplicate(validated)
    job._save_data(fresh)
    return job, validated, fresh


def test_cash_dividend_lands_with_amount_and_realized_pnl(db):
    ledger, pos = _seed_position(db)
    d = date.today() - timedelta(days=10)
    _job, validated, fresh = _run(db, [{'symbol': 'SH600000', 'ex_date': d, 'cash_ratio': 2.0, 'desc': '10派2元'}])
    assert validated and fresh
    # 归属持仓的流水不再回写 symbol 快照，按 position_id 归属（#541 落库实测）
    txns = db.query(Transaction).filter(Transaction.position_id.isnot(None)).all()
    assert len(txns) == 1
    t = txns[0]
    assert t.txn_type == 'dividend'
    assert t.amount == 20000  # 1000 股 / 10 × 2 元 = 200 元 = 20000 分
    assert t.realized_pnl == 20000, '现金分红应全额计入已实现盈亏（#1183 口径）'
    assert t.ledger_id == ledger.id, '自动抓取的分红必须落到持仓所在账本'
    # 现金分红不改份额
    db.expire_all()
    assert Money.min_unit_to_shares(db.query(Position).filter_by(symbol='SH600000').one().quantity) == 1000.0


def test_stock_split_adds_shares_and_dilutes_cost(db):
    _ledger, pos = _seed_position(db)
    d = date.today() - timedelta(days=10)
    _run(db, [{'symbol': 'SH600000', 'ex_date': d, 'transfer_ratio': 10.0, 'desc': '10转增10股'}])
    txns = db.query(Transaction).filter(Transaction.position_id.isnot(None)).all()
    assert len(txns) == 1
    assert txns[0].txn_type == 'split'
    assert txns[0].amount == 0
    db.expire_all()
    pos = db.query(Position).filter_by(symbol='SH600000').one()
    assert Money.min_unit_to_shares(pos.quantity) == 2000.0, '10 转 10 后份额应翻倍'
    # 成本总额不变 → 均价减半
    assert Decimal(str(Money.min_unit_to_shares(pos.avg_price))) == Decimal('5')


def test_rights_issue_payment_raises_cost_and_shares(db):
    """配股缴款：份额 +300、成本 +1500 元（不按一手校验，300 股恰好整手也要能过）。"""
    _ledger, _pos = _seed_position(db)
    d = date.today() - timedelta(days=10)
    _run(
        db,
        [
            {
                'symbol': 'SH600000',
                'ex_date': d,
                'rights_ratio': 3.0,
                'rights_price': 5.0,
                'pay_end': d,
                'desc': '10配3，配股价5元',
            }
        ],
    )
    txns = db.query(Transaction).filter(Transaction.position_id.isnot(None)).all()
    assert len(txns) == 1
    assert txns[0].txn_type == 'buy'
    assert txns[0].amount == 150000  # 300 股 × 5 元 = 1500 元
    from app.core.money import Money

    pos = db.query(Position).filter_by(symbol='SH600000').one()
    assert Money.min_unit_to_shares(pos.quantity) == 1300.0


def test_rerun_is_idempotent_even_after_position_grew(db):
    """同一事件重跑不重复记账，**且加仓后也不会重复**（幂等键不含持有份额）。"""
    _ledger, pos = _seed_position(db)
    d = date.today() - timedelta(days=10)
    event = {'symbol': 'SH600000', 'ex_date': d, 'cash_ratio': 2.0, 'desc': '10派2元'}
    _run(db, [event])
    _run(db, [event])
    assert db.query(Transaction).filter_by(txn_type='dividend').count() == 1

    # 用户加仓：同一笔分红算出来的金额变了，但幂等键不变 → 仍然只有一条
    from app.core.money import Money

    pos.quantity = Money.shares_to_min_unit(Decimal('5000'))
    db.commit()
    _job, _v, fresh = _run(db, [event])
    assert fresh == [], '加仓后重跑必须仍判定为已记录'
    assert db.query(Transaction).filter_by(txn_type='dividend').count() == 1


def test_zero_holding_records_nothing_rather_than_zero_amount(db):
    """没有持仓 → 不落 0 金额分红（0 值流水会占住幂等键，永久挡住正确值）。"""
    d = date.today() - timedelta(days=10)
    _job, validated, fresh = _run(db, [{'symbol': 'SH600000', 'ex_date': d, 'cash_ratio': 2.0, 'desc': '10派2元'}])
    assert validated == [] and fresh == []
    assert db.query(Transaction).filter_by(symbol='SH600000').count() == 0
