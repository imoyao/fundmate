# -*- coding: utf-8 -*-
"""组合列表卡片聚合（list_portfolio_cards）：口径与归属的 API 级验收。

归属口径 = ``portfolio_position_conditions`` 的内存版：显式 ``positions.portfolio_id``
永远优先，未指派才继承 ``ledger.portfolio_id``。市值含账户级现金（与详情页
holdings 一致）；盈亏比例分母是成本，零成本给 ``None`` 而不是 0。
"""

from datetime import date

from app.core.money import Money
from app.core.time_utils import today_shanghai
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position


def _make_position(db, ledger, *, portfolio_id=None, qty=100, avg=10.0, cur=12.0, asset_type='stock', **extra):
    pos = Position(
        symbol=extra.pop('symbol', '000001'),
        name=extra.pop('name', '测试股票'),
        asset_type=asset_type,
        account_name=ledger.name,
        ledger_id=ledger.id,
        portfolio_id=portfolio_id,
        market='CN_A',
        quantity=Money.shares_to_min_unit(qty),
        avg_price=Money.yuan_to_price_units(avg) if avg else 0,
        current_price=Money.yuan_to_price_units(cur),
        confirm_date=date.today(),
        price_date=today_shanghai(),
        **extra,
    )
    db.add(pos)
    return pos


def _list(client):
    resp = client.get('/api/portfolios/')
    assert resp.status_code == 200
    return {item['id']: item for item in resp.json['data']}


def test_card_aggregates_positions_accounts_and_target(client, db):
    """市值 / 盈亏 / 账户数 / 持仓数 / 目标达成率一次算全。"""
    p = Portfolio(name='卡片聚合组合', target_amount=10000.0)
    db.add(p)
    db.commit()
    l1 = Ledger(name='账户一', portfolio_id=p.id)
    l2 = Ledger(name='账户二', portfolio_id=p.id)
    db.add_all([l1, l2])
    db.commit()
    # 两只持仓：成本 10 × (100 + 100)，现价 12 → 市值 2400、盈亏 400、收益率 20%
    _make_position(db, l1, symbol='000001')
    _make_position(db, l2, symbol='600000', name='另一只')
    db.commit()

    card = _list(client)[p.id]
    assert card['market_value'] == 2400.0
    assert card['pnl'] == 400.0
    assert card['pnl_rate'] == 20.0
    assert card['account_count'] == 2
    assert card['position_count'] == 2
    assert card['target_progress'] == 24.0  # 2400 / 10000 × 100
    # 描述不上列表卡片（owner 拍板），但名称 / 目的 / 创建时间照旧
    assert 'description' not in card
    assert card['name'] == '卡片聚合组合'


def test_cash_counts_into_market_value_but_not_position_count(client, db, make_asset):
    """账户级现金计入市值（与详情页 holdings 口径一致），但不计持仓只数、不计盈亏。"""
    p = Portfolio(name='含现金组合')
    db.add(p)
    db.commit()
    ledger = Ledger(name='现金账户', portfolio_id=p.id)
    db.add(ledger)
    db.commit()
    _make_position(db, ledger, symbol='510300', name='ETF')
    make_asset(
        major_category='cash',
        name='活期现金',
        amount=1000.0,
        ledger_id=ledger.id,
        account_name=ledger.name,
    )
    db.commit()

    card = _list(client)[p.id]
    assert card['market_value'] == 1200.0 + 1000.0
    assert card['position_count'] == 1
    # 成本 1000（只有持仓行），盈亏 200
    assert card['pnl'] == 200.0
    assert card['pnl_rate'] == 20.0


def test_explicit_portfolio_id_wins_over_ledger_inheritance(client, db):
    """显式指派的持仓归新组合，不再出现在账户默认组合里。"""
    p_old = Portfolio(name='账户默认组合')
    p_new = Portfolio(name='显式指派组合')
    db.add_all([p_old, p_new])
    db.commit()
    ledger = Ledger(name='双组合账户', portfolio_id=p_old.id)
    db.add(ledger)
    db.commit()
    _make_position(db, ledger, portfolio_id=p_new.id, symbol='600036')
    db.commit()

    cards = _list(client)
    assert cards[p_new.id]['position_count'] == 1
    assert cards[p_new.id]['market_value'] == 1200.0
    assert cards[p_old.id]['position_count'] == 0
    assert cards[p_old.id]['market_value'] == 0.0


def test_unassigned_position_inherits_ledger_portfolio(client, db):
    """portfolio_id 为空的持仓继承账户默认组合（继承路径）。"""
    p = Portfolio(name='继承组合')
    db.add(p)
    db.commit()
    ledger = Ledger(name='继承账户', portfolio_id=p.id)
    db.add(ledger)
    db.commit()
    _make_position(db, ledger, portfolio_id=None, symbol='600030')
    db.commit()

    card = _list(client)[p.id]
    assert card['position_count'] == 1
    assert card['market_value'] == 1200.0


def test_money_fund_excluded_from_card_by_default(client, db):
    """类现金（货基）默认不算投资 → 不进市值也不进持仓数（口径 #1354 决策 #7）。"""
    p = Portfolio(name='含货基组合')
    db.add(p)
    db.commit()
    ledger = Ledger(name='货基账户', portfolio_id=p.id)
    db.add(ledger)
    db.commit()
    _make_position(db, ledger, symbol='000198', name='天弘货基', asset_type='money_fund')
    _make_position(db, ledger, symbol='600000', name='正股')
    db.commit()

    card = _list(client)[p.id]
    assert card['position_count'] == 1
    assert card['market_value'] == 1200.0


def test_zero_cost_gives_null_rate_not_zero(client, db):
    """无成本价的持仓：盈亏为 0，比例是 None（「不知道」≠「没赚没亏」）。"""
    p = Portfolio(name='无成本组合')
    db.add(p)
    db.commit()
    ledger = Ledger(name='无成本账户', portfolio_id=p.id)
    db.add(ledger)
    db.commit()
    _make_position(db, ledger, symbol='600000', avg=0, cur=12.0)
    db.commit()

    card = _list(client)[p.id]
    assert card['pnl'] == 0.0
    assert card['pnl_rate'] is None


def test_no_target_gives_null_progress(client, db):
    """未设 target_amount ⇒ target_progress 为 None（不是 0，不是报错）。"""
    p = Portfolio(name='无目标组合')
    db.add(p)
    db.commit()

    card = _list(client)[p.id]
    assert card['target_progress'] is None
    assert card['market_value'] == 0.0
    assert card['position_count'] == 0
    assert card['account_count'] == 0


def test_empty_family_list_still_ok(client, db):
    """一个组合都没有 ⇒ 空数组，不是 500。"""
    resp = client.get('/api/portfolios/')
    assert resp.status_code == 200
    assert isinstance(resp.json['data'], list)
