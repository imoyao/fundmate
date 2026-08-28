from datetime import date

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position


def test_portfolio_holdings_empty(client, db):
    """空组合返回空列表"""
    portfolio = Portfolio(name='测试组合')
    db.add(portfolio)
    db.commit()

    resp = client.get(f'/api/portfolios/{portfolio.id}/holdings/')
    assert resp.status_code == 200
    assert resp.json['data'] == []


def test_portfolio_holdings_with_position(client, db):
    """有持仓的组合返回正确数据"""
    portfolio = Portfolio(name='有持仓组合')
    db.add(portfolio)
    db.commit()

    ledger = Ledger(name='测试账户', portfolio_id=portfolio.id)
    db.add(ledger)
    db.commit()

    position = Position(
        symbol='000001',
        name='测试股票',
        asset_type='stock',
        account_name='测试账户',
        ledger_id=ledger.id,
        market='CN_A',
        quantity=Money.shares_to_min_unit(100),
        avg_price=Money.yuan_to_price_units(10.0),
        current_price=Money.yuan_to_price_units(12.0),
        confirm_date=date.today(),
    )
    db.add(position)
    db.commit()

    resp = client.get(f'/api/portfolios/{portfolio.id}/holdings/')
    assert resp.status_code == 200
    data = resp.json['data']
    assert len(data) == 1
    assert data[0]['symbol'] == '000001'
    assert data[0]['market_value'] == 1200.0
    assert data[0]['pnl'] == 200.0


def test_portfolio_holdings_nonexistent(client):
    """不存在的组合返回404"""
    resp = client.get('/api/portfolios/99999/holdings/')
    assert resp.status_code == 404
