# -*- coding: utf-8 -*-
"""持仓诊断输出结构测试（#2225 验收第 1 条）——策略状态 + 依据指标。

`diagnose_holdings` / `diagnose_symbol` 此前无任何测试，第 1 条验收
（「任一持仓标的可返回当前策略状态 + 依据指标」）处于无判据状态。
"""

from datetime import date, timedelta

from app.services.strategy_engine.data_provider import DataProvider
from app.services.strategy_engine.diagnosis import diagnose_holdings, diagnose_symbol

D0 = date(2025, 1, 1)


def _mk_worth(db, code: str, day: date, nav: float) -> None:
    from app.domains.funds.models import DailyWorth

    db.add(DailyWorth(fund_code=code, date=day, unit_nav=nav))
    db.flush()


def _seed_nav(db, symbol: str = '000001', days: int = 260):
    for i in range(days):
        _mk_worth(db, symbol, D0 - timedelta(days=days - 200) + timedelta(days=i), 1.0 + i * (1.59 / (days - 1)))


def test_diagnose_holdings_returns_signals_with_evidence(app, db, make_position, make_transaction):
    """任一持仓标的：返回信号 + 依据指标 + data_sufficient（#2225 验收第 1 条）。"""
    from datetime import datetime

    _seed_nav(db)
    pos = make_position(
        symbol='000001',
        name='华夏成长',
        asset_type='fund',
        quantity=1000.0,
        avg_price=1.0,
        account_name='测试账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        symbol='000001',
        quantity=1000.0,
        price=1.0,
        trade_date=datetime(2025, 1, 1),
        confirm_date=D0,
    )

    result = diagnose_holdings(DataProvider(db), family_id=1)
    assert result['holding_count'] >= 1
    item = result['items'][0]

    # 结构：symbol / 信号列表 / 数据充分性 / as_of
    assert item['symbol'] == '000001'
    assert item['data_sufficient'] is True
    assert item['as_of']
    assert item['signals'], '至少一个可运行策略产出信号'

    # 每个信号带状态与依据（Signal.to_dict 契约：action/state/reason/metrics）
    for sig in item['signals']:
        assert sig['action'], '信号必须有 action'
        assert sig['state'], '信号必须有 state'
        assert sig['reason'], '信号必须带依据说明'
        assert 'metrics' in sig, '信号必须带依据指标'


def test_diagnose_symbol_insufficient_history_degrades(app, db):
    """净值极少时策略层诚实降级：产出 watch，不编造进攻型信号。

    口径说明：`data_sufficient` 的既有语义是「有净值序列」（非长度充足），
    真正的降级判据在策略层——test_trend 的 insufficient_history 用例覆盖，
    这里验证端到端输出不出现买入型动作。
    """
    _mk_worth(db, '000002', D0, 1.0)
    _mk_worth(db, '000002', D0 + timedelta(days=1), 1.01)

    result = diagnose_symbol(DataProvider(db), symbol='000002', name='新基金', asset_type='fund')
    assert result['signals'], '策略仍应产出（降级）信号'
    for sig in result['signals']:
        assert sig['action'] != 'buy', '数据不足不得给出买入型信号'
        assert sig['action'] != 'sell', '数据不足不得给出卖出型信号'


def test_diagnose_holdings_empty_family(app, db):
    """无持仓家庭：holding_count=0、items 空，不炸。"""
    result = diagnose_holdings(DataProvider(db), family_id=999)
    assert result['holding_count'] == 0
    assert result['items'] == []
