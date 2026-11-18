# -*- coding: utf-8 -*-
"""多标的流水匹配的回归网（`DataProvider.trades(symbols=...)`）。

背景：2026-11-12 17:03 `GET /api/strategy/engine/behavior/` 500，
`symbol_scope.build_transaction_symbol_conditions` 的 4 个等式按标的展平进单个 `or_()`，
265 行持仓 → 1060 个 OR 项 > SQLite `SQLITE_MAX_EXPR_DEPTH=1000`。

判据不只看「现在能跑」：
- 大标的数用例在修复前的实现下会**真的抛异常**（反向验证的锚点）；
- 候选集合与单标的口径逐一对齐（防第三份身份键实现漂移）；
- OR 项数不随标的数线性增长（防止日后有人把 `IN` 又改回 `==` 链）。
"""

from datetime import date, datetime

from sqlalchemy import or_

from app.domains.transactions.models import Transaction
from app.services.strategy_engine.data_provider import DataProvider
from app.services.symbol_scope import build_transaction_symbol_conditions
from app.services.transaction_symbol_scope import build_transaction_scope, symbol_identity_candidates

_SAMPLES = ('000001', 'SZ000001', '016462', 'SH600519', '00700.HK')


def _seed_trade(db, make_position, make_transaction, symbol='000001', pos=None):
    # 多笔流水共用同一个持仓：positions 有 (ledger_id, symbol_norm) 唯一约束，
    # 给每笔流水各造一个持仓会在第二个写法变体上直接撞 IntegrityError。
    pos = pos or make_position(
        symbol='000001',
        name='测试标的',
        asset_type='fund',
        quantity=1000.0,
        avg_price=1.0,
        account_name='测试账户',
    )
    return make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        symbol=symbol,
        quantity=1000.0,
        price=1.0,
        trade_date=datetime(2025, 1, 1),
        confirm_date=date(2025, 1, 1),
    )


def _old_chain(symbols):
    """修复前的口径：所有标的的所有等式展平进一个 or_()（仅测试内对照用）。"""
    return or_(*[cond for s in symbols for cond in build_transaction_symbol_conditions(s)])


def test_trades_with_many_symbols_stays_within_sqlite_expression_depth(db, make_position, make_transaction):
    """300 个标的（>1000/4）不得再触发 Expression tree is too large，且流水照常命中。"""
    _seed_trade(db, make_position, make_transaction, symbol='000001')
    symbols = [f'{i:06d}' for i in range(300)]

    trades = DataProvider(db).trades(1, symbols=symbols)

    assert len(trades) == 1, '大标的数下流水仍应按身份键命中'
    assert trades[0].symbol == '000001'


def test_scope_matches_old_or_chain_on_real_rows(db, make_position, make_transaction):
    """新旧口径命中集合完全一致：字面量行、身份键行都要在，无关行都不能在。"""
    pos = make_position(
        symbol='000001', name='测试标的', asset_type='fund', quantity=1000.0, avg_price=1.0, account_name='测试账户'
    )
    literal_row = _seed_trade(db, make_position, make_transaction, symbol='000001', pos=pos)
    variant_row = _seed_trade(db, make_position, make_transaction, symbol='SZ000001', pos=pos)
    _seed_trade(db, make_position, make_transaction, symbol='999999', pos=pos)
    # 写完再改写 norm：模拟 #1662 迁移前的空 norm 降级行，以及写法变体行的身份键形态。
    db.query(Transaction).filter(Transaction.id == literal_row.id).update({'symbol_norm': ''})
    db.query(Transaction).filter(Transaction.id == variant_row.id).update({'symbol_norm': 'EXCHANGE:SZ000001'})
    db.flush()
    db.expire_all()

    symbols = ['000001']
    old_ids = {r.id for r in db.query(Transaction).filter(_old_chain(symbols)).all()}
    new_ids = {r.id for r in db.query(Transaction).filter(build_transaction_scope(symbols)).all()}

    assert old_ids == new_ids, '两列 IN 必须与 N×4 个 OR 等式等价'
    assert literal_row.id in new_ids, '字面量降级行不能漏'
    assert variant_row.id in new_ids, '写法变体行应经 symbol_norm 身份键命中'


def test_identity_candidates_match_single_symbol_scope():
    """三种 venue 候选与 `symbol_scope` 单标的版逐一对齐（单一真相源防漂移）。"""
    for symbol in _SAMPLES:
        expected = {
            cond.right.value
            for cond in build_transaction_symbol_conditions(symbol)
            if getattr(cond.left, 'key', None) == 'symbol_norm'
        }
        assert symbol_identity_candidates(symbol) == expected, f'{symbol} 的身份键候选漂移'


def test_or_terms_do_not_grow_with_symbols():
    """1200 个标的：WHERE 恒为两列各一个 IN（OR 项数 2），参数去重且有序可复现。"""
    symbols = [f'{i:06d}' for i in range(1200)]
    condition = build_transaction_scope(symbols)

    assert len(condition.clauses) == 2, f'两列 IN 的 OR 项数恒为 2，实际 {len(condition.clauses)}'
    params = [v for v in condition.compile().params.values() if isinstance(v, list)]
    assert len(params) == 2
    assert all(p == sorted(p) for p in params), 'IN 列表应有序，保证编译出的 SQL 可复现'
    assert sum(len(p) for p in params) <= 4 * len(symbols), '参数数不得比「每标的 4 个等式」更多'


def test_empty_symbols_matches_nothing(db, make_position, make_transaction):
    """空输入必须不匹配任何行：`or_()` 空参会编译成空串，等于把全表读回来。"""
    _seed_trade(db, make_position, make_transaction)

    rows = db.query(Transaction).filter(build_transaction_scope([])).all()

    assert rows == []


def test_normalization_failure_keeps_literal_only(monkeypatch):
    """归一失败沿用单标的版降级：只留字面量，不让整个查询挂掉。"""

    def _boom(*_args, **_kwargs):
        raise RuntimeError('归一模拟失败')

    monkeypatch.setattr('app.services.transaction_symbol_scope.symbol_identity', _boom)

    assert symbol_identity_candidates('000001') == set()
    compiled = str(build_transaction_scope(['000001']).compile(compile_kwargs={'literal_binds': True}))
    assert 'transactions.symbol IN' in compiled
    assert 'symbol_norm' not in compiled
