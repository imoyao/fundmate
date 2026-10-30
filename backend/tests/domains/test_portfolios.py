from datetime import date

import pytest

from app.core.money import Money
from app.core.time_utils import today_shanghai
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position
from app.services.portfolio_service import (
    PortfolioNameConflict,
    assert_portfolio_name_available,
)


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
        price_date=today_shanghai(),  # #2210：确认口径已是今日价
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
    # #2210：持仓行携带 price_date + settled_today（与持仓明细 #2140 同名同义）
    assert data[0]['price_date'] == today_shanghai().isoformat()
    assert data[0]['settled_today'] is True


def test_portfolio_holdings_asset_rows_have_null_price_date(client, db, make_asset):
    """#2210：静态资产行无价格日期概念——price_date / settled_today 恒 null。"""
    portfolio = Portfolio(name='含资产组合')
    db.add(portfolio)
    db.commit()
    ledger = Ledger(name='资产账户', portfolio_id=portfolio.id)
    db.add(ledger)
    db.commit()
    make_asset(
        major_category='cash',
        name='家庭现金',
        amount=5000.0,
        ledger_id=ledger.id,
        account_name='资产账户',
    )

    resp = client.get(f'/api/portfolios/{portfolio.id}/holdings/')
    assert resp.status_code == 200
    data = resp.json['data']
    assert len(data) == 1
    assert data[0]['price_date'] is None
    assert data[0]['settled_today'] is None


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


# ── 组合名唯一（2026-10-30）──────────────────────────────────────────────────
#
# 此前这里一条用例都没有，因为**校验压根不存在**：同家庭可以建出两个「养老计划」，
# 而列表卡片的主标题就是 name。下面把口径逐条钉住：重名拒绝、空白/大小写折叠后
# 仍算重名、软删除后名字可复用、改名排除自身。


def test_create_portfolio_rejects_duplicate_name(client, db):
    """同家庭同名 → 409，且不落库"""
    db.add(Portfolio(name='养老计划'))
    db.commit()

    resp = client.post('/api/portfolios/', json={'name': '养老计划'})

    assert resp.status_code == 409
    assert '养老计划' in resp.json['message']
    db.expire_all()
    assert db.query(Portfolio).filter(Portfolio.is_deleted.is_(False)).count() == 1


def test_create_portfolio_trims_name_and_rejects_padded_duplicate(client, db):
    """首尾空白 / 内部连续空白 / 大小写都不构成「新名字」——归一化后仍判重名

    卡片标题渲染的是 name，`养老  计划` 与 `养老 计划` 在界面上完全一样，
    放过它们等于把重名问题换个写法留着。
    """
    resp1 = client.post('/api/portfolios/', json={'name': '  Retire  2026  '})
    assert resp1.status_code == 200
    assert resp1.json['data']['name'] == 'Retire 2026'  # 写库前已归一化

    resp2 = client.post('/api/portfolios/', json={'name': 'retire 2026'})
    assert resp2.status_code == 409


def test_create_portfolio_allows_name_of_soft_deleted(client, db):
    """软删除的组合不占名字——否则删了也建不回来"""
    old = Portfolio(name='旧组合', is_deleted=True)
    db.add(old)
    db.commit()

    resp = client.post('/api/portfolios/', json={'name': '旧组合'})

    assert resp.status_code == 200
    assert resp.json['data']['id'] != old.id


def test_portfolio_name_unique_is_family_scoped(client, db):
    """不同家庭各自命名：家庭 2 建「家庭一组合」不该被家庭 1 的同名挡住

    直接测服务层——HTTP 侧 family_id 来自登录态（`get_family_id()`），
    请求体里塞 family_id 是无效的，用接口测这件事只会测出「默认家庭」。
    """
    db.add(Portfolio(name='家庭一组合', family_id=1))
    db.commit()

    with pytest.raises(PortfolioNameConflict):
        assert_portfolio_name_available(db, 1, '家庭一组合')
    # 家庭 2 无同名 → 返回归一化后的名字，不抛错
    assert assert_portfolio_name_available(db, 2, ' 家庭一组合 ') == '家庭一组合'


def test_update_portfolio_rejects_duplicate_name(client, db):
    """改成一个已存在的名字 → 409，且原名不变"""
    a = Portfolio(name='组合A')
    b = Portfolio(name='组合B')
    db.add_all([a, b])
    db.commit()

    resp = client.patch(f'/api/portfolios/{b.id}/', json={'name': ' 组合a '})

    assert resp.status_code == 409
    db.expire_all()
    assert db.get(Portfolio, b.id).name == '组合B'


def test_update_portfolio_keeps_own_name(client, db):
    """保存表单时不改名（name 原样回传）不能被自己判成重名"""
    portfolio = Portfolio(name='组合A')
    db.add(portfolio)
    db.commit()

    resp = client.patch(f'/api/portfolios/{portfolio.id}/', json={'name': '组合A', 'purpose': '长期增值'})

    assert resp.status_code == 200
    assert resp.json['data']['purpose'] == '长期增值'


def test_update_portfolio_without_name_field_skips_check(client, db):
    """只改其它字段时不触发名字校验（exclude_unset 语义）"""
    portfolio = Portfolio(name='组合A')
    db.add(portfolio)
    db.commit()

    resp = client.patch(f'/api/portfolios/{portfolio.id}/', json={'description': '备注'})

    assert resp.status_code == 200
    assert resp.json['data']['name'] == '组合A'
