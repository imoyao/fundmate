# backend/tests/domains/test_d20_portfolio_phase1.py
"""
D20 一期回归测试：持仓级组合归属（positions.portfolio_id）。

覆盖：
1. 组合持仓查询仅用 ledger_id / portfolio_id 关联，不再依赖 account_name。
2. 账户改名后持仓仍归属本组合（断链防护）。
3. 持仓改派（PATCH portfolio_id）后从原组合消失、出现在新组合。
4. 同账户持仓不会被错误计入无关组合（无重复计数 / 串仓 / 跨家庭）。
5. 迁移回填：ledger_id 决定 portfolio_id 继承，且不覆盖已显式改派的持仓。

注：测试库 family_id 约定为 1；跨家庭用 family_id=2 直接造数据模拟。
"""

from datetime import date

from sqlalchemy import text

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position


def _make_ledger(db, name='测试账户', portfolio_id=None, family_id=1):
    ledger = Ledger(
        family_id=family_id,
        name=name,
        ledger_type='stock',
        portfolio_id=portfolio_id,
    )
    db.add(ledger)
    db.commit()
    db.refresh(ledger)
    return ledger


def _make_position(db, ledger, portfolio_id=None, symbol='000001', name='测试股票', family_id=1):
    pos = Position(
        family_id=family_id,
        symbol=symbol,
        name=name,
        market='CN',
        asset_type='stock',
        ledger_id=ledger.id,
        account_name=ledger.name,
        quantity=Money.shares_to_min_unit(100),  # 100 份 (min_unit = 0.0001)
        avg_price=Money.yuan_to_cents(10.0),  # 10 元/份 (分)
        current_price=Money.yuan_to_cents(12.0),
        currency='CNY',
        confirm_date=date(2024, 1, 1),
        portfolio_id=portfolio_id,
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return pos


def _get_holdings(client, portfolio_id):
    resp = client.get(f'/api/portfolios/{portfolio_id}/holdings/')
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


class TestPortfolioHoldingsLinkage:
    """组合持仓归属：关联键校验（ledger_id / portfolio_id，非 account_name）。"""

    def test_holdings_uses_ledger_id_not_account_name(self, client, db):
        """持仓按 ledger_id 关联账户默认组合，改名后依然归属。"""
        portfolio = Portfolio(name='默认组合')
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)

        ledger = _make_ledger(db, name='原账户名', portfolio_id=portfolio.id)
        _make_position(db, ledger)  # 不显式指定 portfolio_id，走继承

        # 改名账户
        ledger.name = '改名后的账户'
        db.commit()

        data = _get_holdings(client, portfolio.id)
        symbols = {p['symbol'] for p in data}
        assert '000001' in symbols, '账户改名后持仓应仍归属原组合'

    def test_position_explicit_portfolio_id_takes_precedence(self, client, db):
        """持仓显式 portfolio_id 优先于账户默认组合。"""
        pa = Portfolio(name='组合A')
        pb = Portfolio(name='组合B')
        db.add_all([pa, pb])
        db.commit()
        for p in (pa, pb):
            db.refresh(p)
        # 组合 B 也需有账户关联，否则 get_portfolio_holdings 因 ledger_ids 为空提前返回
        _make_ledger(db, name='账户B', portfolio_id=pb.id)

        ledger = _make_ledger(db, portfolio_id=pa.id)  # 账户默认组合 = A
        pos = _make_position(db, ledger, portfolio_id=pb.id)  # 持仓显式指向 B

        data_a = _get_holdings(client, pa.id)
        data_b = _get_holdings(client, pb.id)
        assert all(p['symbol'] != pos.symbol for p in data_a), '持仓不应出现在账户默认组合'
        assert any(p['symbol'] == pos.symbol for p in data_b), '持仓应出现在显式指定组合'

    def test_no_cross_portfolio_leak(self, client, db):
        """另一组合的持仓不应泄漏进本组合（无串仓 / 重复计数）。"""
        pa = Portfolio(name='组合A')
        pb = Portfolio(name='组合B')
        db.add_all([pa, pb])
        db.commit()
        for p in (pa, pb):
            db.refresh(p)

        ledger_a = _make_ledger(db, name='账户A', portfolio_id=pa.id)
        ledger_b = _make_ledger(db, name='账户B', portfolio_id=pb.id)
        _make_position(db, ledger_a, portfolio_id=pa.id, symbol='AAA')
        _make_position(db, ledger_b, portfolio_id=pb.id, symbol='BBB')

        data_a = _get_holdings(client, pa.id)
        data_b = _get_holdings(client, pb.id)
        assert {p['symbol'] for p in data_a} == {'AAA'}
        assert {p['symbol'] for p in data_b} == {'BBB'}


class TestPositionReassign:
    """持仓改派组合（PATCH portfolio_id）。"""

    def test_reassign_moves_position_between_portfolios(self, client, db):
        pa = Portfolio(name='组合A')
        pb = Portfolio(name='组合B')
        db.add_all([pa, pb])
        db.commit()
        for p in (pa, pb):
            db.refresh(p)
        # 组合 B 也需有账户关联，否则 get_portfolio_holdings 因 ledger_ids 为空提前返回
        _make_ledger(db, name='账户B', portfolio_id=pb.id)

        ledger = _make_ledger(db, portfolio_id=pa.id)
        pos = _make_position(db, ledger, portfolio_id=pa.id)

        # 改派到 B
        resp = client.patch(
            f'/api/positions/{pos.id}/',
            json={'portfolio_id': pb.id},
        )
        assert resp.status_code == 200, resp.get_json()

        data_a = _get_holdings(client, pa.id)
        data_b = _get_holdings(client, pb.id)
        assert all(p['symbol'] != pos.symbol for p in data_a), '改派后不应留在原组合'
        assert any(p['symbol'] == pos.symbol for p in data_b), '改派后应出现在新组合'

    def test_reassign_to_other_family_is_forbidden(self, client, db):
        """禁止跨家庭改派组合（404）。"""
        pa = Portfolio(name='组合A')
        pb = Portfolio(name='别人家的组合', family_id=2)
        db.add_all([pa, pb])
        db.commit()
        db.refresh(pa)
        db.refresh(pb)

        ledger = _make_ledger(db, portfolio_id=pa.id)
        pos = _make_position(db, ledger, portfolio_id=pa.id)

        resp = client.patch(
            f'/api/positions/{pos.id}/',
            json={'portfolio_id': pb.id},
        )
        assert resp.status_code == 404, resp.get_json()

    def test_position_out_carries_portfolio_id(self, client, db):
        """持仓改派接口返回携带 portfolio_id。"""
        pa = Portfolio(name='组合A')
        db.add(pa)
        db.commit()
        db.refresh(pa)
        ledger = _make_ledger(db, portfolio_id=pa.id)
        pos = _make_position(db, ledger, portfolio_id=pa.id)

        resp = client.patch(f'/api/positions/{pos.id}/', json={'portfolio_id': pa.id})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['data']['portfolio_id'] == pa.id


class TestMigrationBackfill:
    """迁移回填：portfolio_id 继承账户默认组合，且不覆盖已显式改派。"""

    def test_backfill_inherits_ledger_default(self, db):
        portfolio = Portfolio(name='默认组合')
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)

        ledger = _make_ledger(db, portfolio_id=portfolio.id)
        pos = _make_position(db, ledger)  # 未指定 portfolio_id

        # 模拟迁移回填逻辑
        db.execute(
            text(
                'UPDATE positions SET portfolio_id = ('
                'SELECT l.portfolio_id FROM ledgers l WHERE l.id = positions.ledger_id) '
                'WHERE positions.portfolio_id IS NULL'
            )
        )
        db.commit()
        db.refresh(pos)
        assert pos.portfolio_id == portfolio.id

    def test_backfill_does_not_override_explicit(self, db):
        pa = Portfolio(name='组合A')
        pb = Portfolio(name='组合B')
        db.add_all([pa, pb])
        db.commit()
        for p in (pa, pb):
            db.refresh(p)

        ledger = _make_ledger(db, portfolio_id=pa.id)
        pos = _make_position(db, ledger, portfolio_id=pb.id)  # 显式指向 B

        db.execute(
            text(
                'UPDATE positions SET portfolio_id = ('
                'SELECT l.portfolio_id FROM ledgers l WHERE l.id = positions.ledger_id) '
                'WHERE positions.portfolio_id IS NULL'
            )
        )
        db.commit()
        db.refresh(pos)
        assert pos.portfolio_id == pb.id, '已显式改派的持仓不应被回填覆盖'
