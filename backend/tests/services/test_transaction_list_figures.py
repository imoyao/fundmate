# -*- coding: utf-8 -*-
"""交易列表行携带「当时成本 / 收益贡献」两列（#2857）。

## 为什么这两个字段必须并进主表

原先它们来自**第二个请求**（`/api/products/trade-timeline/` → `contributions`），
再由前端按 `txn_id ↔ row.id` 关联。这套结构的失效方式是静默的：两个请求各自取数，
一个到了、一个没到，界面就只剩一列 `--`，没有日志也没有提示。真机上表现为
「交易记录两列全空 + 走势卡没有买卖点」，用户连报三次却分不清是哪一种。

并进主表后只剩一次请求、一份口径。这里钉住三件事：

1. 按 `symbol` 过滤时两列**有值**，且与时间线重放同源（同一函数，不是第二份算法）；
2. **不带 `symbol` 时不重放**（账本全量列表既不显示这两列，逐页重放等于白烧 CPU），
   两列为 `None`；
3. 不参与重放的类型（拆分 / 扣税 / 其他）为 `None` 而**不是 `0.0`**——
   `0` 是「这笔不产生已实现」（买入建仓），与「没有数据」是两件事，
   共用一个值就等于允许它们互相冒充。
"""

from datetime import datetime

from app.services.transaction_service import build_transaction_list


def _day(y, m, d):
    return datetime(y, m, d, 10, 0, 0)


def _list(db, **filters):
    return build_transaction_list(db, family_id=1, page=1, per_page=50, filters=filters)['data']


def _txn(make_transaction, pos, **kwargs):
    kwargs.setdefault('symbol', pos.symbol)
    kwargs.setdefault('position_id', pos.id)
    kwargs.setdefault('ledger_id', pos.ledger_id)
    return make_transaction(**kwargs)


def test_rows_carry_cost_and_contribution_when_filtered_by_symbol(db, make_position, make_transaction):
    """按 symbol 过滤：买入行 100 元成本 / 0 贡献，卖出行成本归零 / +45 贡献。"""
    pos = make_position(symbol='SZ000568', quantity=100, avg_price=1.0, account_name='测试账户')
    _txn(
        make_transaction,
        pos,
        txn_type='buy',
        quantity=100,
        price=1.0,
        amount=100,
        trade_date=_day(2026, 1, 5),
    )
    _txn(
        make_transaction,
        pos,
        txn_type='sell',
        quantity=100,
        price=1.5,
        amount=150,
        fee=500,  # 分，即 5 元
        trade_date=_day(2026, 3, 5),
    )

    rows = _list(db, symbol='SZ000568')
    by_type = {r['type']: r for r in rows}

    assert by_type['buy']['cost_after_yuan'] == 100.0
    assert by_type['buy']['profit_contribution_yuan'] == 0.0
    # 卖出：净回款 150 − 5 = 145，释放成本 100 → 已实现 +45；清仓后成本 0
    assert by_type['sell']['cost_after_yuan'] == 0.0
    assert by_type['sell']['profit_contribution_yuan'] == 45.0


def test_rows_without_symbol_filter_do_not_replay(db, make_position, make_transaction):
    """不带 symbol：两列为 None（不重放），不做「无数据 = 0」的伪装。"""
    pos = make_position(symbol='SZ000568', quantity=100, avg_price=1.0, account_name='测试账户')
    _txn(make_transaction, pos, txn_type='buy', quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))

    rows = _list(db)

    assert rows, '未过滤的列表仍应返回行'
    assert all(r['cost_after_yuan'] is None for r in rows)
    assert all(r['profit_contribution_yuan'] is None for r in rows)


def test_types_outside_replay_are_null_not_zero(db, make_position, make_transaction):
    """拆分 / 扣税 / 其他不参与重放 → None（前端渲染 `--`），不是 0。"""
    pos = make_position(symbol='SZ000568', quantity=100, avg_price=1.0, account_name='测试账户')
    _txn(make_transaction, pos, txn_type='buy', quantity=100, price=1.0, amount=100, trade_date=_day(2026, 1, 5))
    _txn(make_transaction, pos, txn_type='split', quantity=0, price=0, amount=0, trade_date=_day(2026, 2, 5))

    rows = _list(db, symbol='SZ000568')
    split_row = next(r for r in rows if r['type'] == 'split')

    assert split_row['cost_after_yuan'] is None, '没有口径 ≠ 成本为 0'
    assert split_row['profit_contribution_yuan'] is None, '没有口径 ≠ 不赚钱'


def test_figures_follow_symbol_scope_not_literal_symbol(db, make_position, make_transaction):
    """行与两列的匹配口径同源：持仓写裸码、流水写带前缀码时仍能对上（symbol_scope）。"""
    pos = make_position(symbol='000568', quantity=100, avg_price=1.0, account_name='测试账户')
    _txn(
        make_transaction,
        pos,
        symbol='SZ000568',
        txn_type='buy',
        quantity=100,
        price=1.0,
        amount=100,
        trade_date=_day(2026, 1, 5),
    )

    rows = _list(db, symbol='SZ000568')

    assert len(rows) == 1
    assert rows[0]['cost_after_yuan'] == 100.0, '列表命中哪批流水，重放就必须命中同一批'
