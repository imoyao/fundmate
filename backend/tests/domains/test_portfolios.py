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


# ------------------------------------------------------------------
# PATCH ledger_ids 原子替换（#981：账户关联 diff 计算下沉后端）
# ------------------------------------------------------------------


def test_update_portfolio_ledger_ids_atomic_replace(client, db):
    """传 ledger_ids 即原子替换：集合外现挂账户解绑、集合内未挂账户绑定，同请求改字段"""
    portfolio = Portfolio(name='组合A')
    db.add(portfolio)
    db.commit()

    linked = Ledger(name='已挂账户', family_id=1, portfolio_id=portfolio.id)
    free = Ledger(name='待挂账户', family_id=1)
    db.add_all([linked, free])
    db.commit()

    resp = client.patch(
        f'/api/portfolios/{portfolio.id}/',
        json={'name': '组合A改', 'ledger_ids': [free.id]},
    )
    assert resp.status_code == 200
    assert resp.json['data']['name'] == '组合A改'

    db.expire_all()
    assert db.get(Ledger, linked.id).portfolio_id is None
    assert db.get(Ledger, free.id).portfolio_id == portfolio.id


def test_update_portfolio_ledger_ids_migrate_from_other_portfolio(client, db):
    """集合内的账户若挂在其它组合下，迁入本组合（对齐原前端逐个置值语义）"""
    pa = Portfolio(name='组合A')
    pb = Portfolio(name='组合B')
    db.add_all([pa, pb])
    db.commit()

    ledger = Ledger(name='迁入户', family_id=1, portfolio_id=pb.id)
    db.add(ledger)
    db.commit()

    resp = client.patch(f'/api/portfolios/{pa.id}/', json={'ledger_ids': [ledger.id]})
    assert resp.status_code == 200

    db.expire_all()
    assert db.get(Ledger, ledger.id).portfolio_id == pa.id


def test_update_portfolio_ledger_ids_empty_unlinks_all(client, db):
    """ledger_ids=[] 表示全部解绑"""
    portfolio = Portfolio(name='组合A')
    db.add(portfolio)
    db.commit()

    l1 = Ledger(name='户1', family_id=1, portfolio_id=portfolio.id)
    l2 = Ledger(name='户2', family_id=1, portfolio_id=portfolio.id)
    db.add_all([l1, l2])
    db.commit()

    resp = client.patch(f'/api/portfolios/{portfolio.id}/', json={'ledger_ids': []})
    assert resp.status_code == 200

    db.expire_all()
    assert db.get(Ledger, l1.id).portfolio_id is None
    assert db.get(Ledger, l2.id).portfolio_id is None


def test_update_portfolio_without_ledger_ids_keeps_links(client, db):
    """不传 ledger_ids（None）时不动任何关联——兼容既有调用方"""
    portfolio = Portfolio(name='组合A')
    db.add(portfolio)
    db.commit()

    ledger = Ledger(name='不动户', family_id=1, portfolio_id=portfolio.id)
    db.add(ledger)
    db.commit()

    resp = client.patch(f'/api/portfolios/{portfolio.id}/', json={'name': '新名'})
    assert resp.status_code == 200

    db.expire_all()
    assert db.get(Ledger, ledger.id).portfolio_id == portfolio.id


def test_update_portfolio_ledger_ids_foreign_family_rejected(client, db):
    """目标集合含非本家庭账户 → 整体 404，且零部分更新（原子性）"""
    portfolio = Portfolio(name='组合A')
    db.add(portfolio)
    db.commit()

    own = Ledger(name='本家户', family_id=1, portfolio_id=portfolio.id)
    foreign = Ledger(name='他家庭户', family_id=2)
    db.add_all([own, foreign])
    db.commit()

    resp = client.patch(
        f'/api/portfolios/{portfolio.id}/',
        json={'ledger_ids': [own.id, foreign.id]},
    )
    assert resp.status_code == 404

    # 原子性：校验失败发生在任何写之前，现挂关联不得被半更新
    db.expire_all()
    assert db.get(Ledger, own.id).portfolio_id == portfolio.id
    assert db.get(Ledger, foreign.id).portfolio_id is None
