"""账户级资金流动（#2616）回归：L1 出入金、月度上卷、单位与账户隔离。

钉的是「账户页能不能说清这笔钱」的四条底线：
- 只有跨出账户的钱算入金/出金（买入/卖出是 L2，不进这两个数）；
- 净投入 = 入金 − 出金（不混已实现盈亏，见 `docs/spec/cashflow-layers.md`）；
- 金额一律是元（`transactions.amount` 存分，回归 #2610 那类 100 倍错误）；
- `ledger_id` 必须真的隔离——A 的入金不能出现在 B 的响应里。
"""

import datetime as dt

from app.domains.ledgers.models import Ledger
from app.services.cash_flow_service import build_ledger_cash_flow

DAY = dt.date(2026, 3, 2)
DAY2 = dt.date(2026, 3, 20)
DAY3 = dt.date(2026, 4, 1)


def _ledger(db, name, ledger_type='fund'):
    ledger = Ledger(name=name, ledger_type=ledger_type, family_id=1)
    db.add(ledger)
    db.flush()
    return ledger


def _seed_account(db, make_position, make_transaction, ledger, rows):
    pos = make_position(
        symbol='AAA', name='测试标的', ledger_id=ledger.id, asset_type='bond', quantity=0, current_price=1.0
    )
    for txn_type, amount, day in rows:
        make_transaction(
            pos.id, ledger.id, txn_type=txn_type, asset_type='bond', amount=amount, confirm_date=day, symbol='AAA'
        )
    db.commit()
    return pos


def test_cash_flow_totals_and_monthly(db, make_position, make_transaction):
    """入金 10 万 / 买入 8 万 / 卖出 9 万 / 出金 2 万。"""
    ledger = _ledger(db, '资金流动账户')
    _seed_account(
        db,
        make_position,
        make_transaction,
        ledger,
        [
            ('deposit', 100000, DAY),
            ('buy', 80000, DAY),
            ('sell', 90000, DAY2),
            ('withdraw', 20000, DAY3),
        ],
    )

    data = build_ledger_cash_flow(db, 1, ledger.id, '2026-03-01', '2026-04-30')

    totals = data['totals']
    # 只有 deposit / withdraw 进外部资金流（买入卖出是 L2，不进这两个数）
    assert totals['deposit'] == 100000.0
    assert totals['withdraw'] == 20000.0
    # 净投入 = 入金 − 出金；卡面示例的 7 万把已实现盈亏混进了投入，见 D67
    assert totals['net_invested'] == 80000.0
    # 现金残差 = 10 − 2 − 8 + 9 万
    assert totals['cash_residual'] == 90000.0
    assert totals['end_asset'] == round(totals['market_value'] + 90000.0, 2)
    assert totals['total_return'] == round(totals['end_asset'] - 80000.0, 2)
    assert totals['has_deposit_record'] is True

    flows = data['external_flows']
    assert len(flows) == 2, '只有入金与出金两笔'
    assert flows[0]['direction'] == 'in' and flows[0]['amount'] == 100000.0
    assert flows[1]['direction'] == 'out' and flows[1]['amount'] == 20000.0

    monthly = {item['month']: item for item in data['monthly']}
    assert monthly['2026-03']['deposit'] == 100000.0
    assert monthly['2026-03']['withdraw'] == 0.0
    assert monthly['2026-04']['withdraw'] == 20000.0
    assert monthly['2026-04']['net'] == -20000.0


def test_amount_unit_is_yuan(db, make_position, make_transaction):
    """单位纪律：返回值量级必须与 `transactions.amount / 100` 一致（不是分）。"""
    ledger = _ledger(db, '单位账户')
    # 入金 1234.56 元（若实现把「分」当「元」，这里会变成 123456.0）
    _seed_account(db, make_position, make_transaction, ledger, [('deposit', 1234.56, DAY)])

    data = build_ledger_cash_flow(db, 1, ledger.id)
    assert data['totals']['deposit'] == 1234.56
    assert data['coverage']['amount_unit'] == 'yuan'


def test_ledger_isolation(db, make_position, make_transaction):
    """账户隔离：A 的入金不得出现在 B 的响应里。"""
    ledger_a = _ledger(db, '账户A')
    ledger_b = _ledger(db, '账户B')
    _seed_account(db, make_position, make_transaction, ledger_a, [('deposit', 50000, DAY)])
    _seed_account(db, make_position, make_transaction, ledger_b, [('deposit', 3000, DAY2)])

    data_a = build_ledger_cash_flow(db, 1, ledger_a.id)
    data_b = build_ledger_cash_flow(db, 1, ledger_b.id)

    assert data_a['totals']['deposit'] == 50000.0
    assert data_b['totals']['deposit'] == 3000.0
    assert [flow['amount'] for flow in data_a['external_flows']] == [50000.0]
    assert [flow['amount'] for flow in data_b['external_flows']] == [3000.0]


def test_without_deposit_record_flags_zero_net_invested(db, make_position, make_transaction):
    """只导过交易的账户：净投入为 0 且要显式标记，页面才能提示「未录入金」。"""
    ledger = _ledger(db, '只导交易的账户')
    _seed_account(db, make_position, make_transaction, ledger, [('buy', 10000, DAY)])

    data = build_ledger_cash_flow(db, 1, ledger.id)
    assert data['totals']['net_invested'] == 0.0
    assert data['totals']['has_deposit_record'] is False
    assert data['external_flows'] == []


def test_range_filters_list_but_not_cumulative_totals(db, make_position, make_transaction):
    """区间只影响列表/月度/曲线；累计指标恒为自开户以来（否则切区间会看到「累计 0」）。"""
    ledger = _ledger(db, '区间账户')
    _seed_account(
        db,
        make_position,
        make_transaction,
        ledger,
        [('deposit', 100000, DAY), ('withdraw', 20000, DAY3)],
    )

    narrow = build_ledger_cash_flow(db, 1, ledger.id, '2026-04-01', '2026-04-30')

    assert len(narrow['external_flows']) == 1
    assert narrow['external_flows'][0]['direction'] == 'out'
    assert narrow['totals']['deposit'] == 100000.0, '累计入金必须自开户以来'
    assert narrow['totals']['net_invested'] == 80000.0


def test_unknown_ledger_raises(db):
    """跨家庭 / 不存在的账户一律报错，不返回空壳数据。"""
    import pytest

    with pytest.raises(ValueError):
        build_ledger_cash_flow(db, 1, 999999)
