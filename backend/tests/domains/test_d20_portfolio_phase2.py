# -*- coding: utf-8 -*-
"""D20 二期（A0 + A1）：组合成员是持仓，收益也按持仓归因。

## 背景

D20 一期把 `positions.portfolio_id` 落了库，但两处仍以「组合 = 账户集合」为前提：

1. **可见性**（A0）：`build_portfolio_holdings` 开头 `if not ledger_ids: return []`——
   组合必须先绑账户才可见。而 `ledgers.portfolio_id` 是单值，A 账户的默认组合只能是固收+，
   于是「成长组合」绑不上该账户，即使持仓已显式指派，整个组合也看不见。
2. **收益**（A1）：`calculate_portfolio_xirr_by_id` 的市值按 `Position.ledger_id.in_(ledger_ids)`
   取、`generate_portfolio_cashflows` 的流水按 `collect_flows(ledger_ids)` 取——不认
   `positions.portfolio_id`。同一账户下分属两个组合时，两个组合都会把整账户算成自己的。

本文件锁住这两条，并锁住两个容易回退的边界：

- 无账户组合**仍可**算出年化（历史实现返回全 0）；
- 已清仓持仓（`quantity == 0`）的买卖流水**仍计入**组合现金流——否则清仓即丢历史收益。

## 单位约定（与 `test_portfolio_xirr_units.py` 一致）

`asset_type='bond'` 走 `current_price`，不依赖 NAV / 行情表；金额入参是**元**，
fixture 内部转分；`quantity` 入参是**份**，内部转 min_unit。
"""

from datetime import date, timedelta

from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.performance.calculators import calculate_portfolio_xirr_by_id
from app.services.performance.xirr_engine import generate_portfolio_cashflows

ONE_YEAR_AGO = date.today() - timedelta(days=365)


def _portfolio(db, name):
    pf = Portfolio(name=name, family_id=1)
    db.add(pf)
    db.commit()
    db.refresh(pf)
    return pf


def _ledger(db, name, portfolio_id=None):
    ledger = Ledger(name=name, ledger_type='fund', family_id=1, portfolio_id=portfolio_id)
    db.add(ledger)
    db.commit()
    db.refresh(ledger)
    return ledger


def _get_holdings(client, portfolio_id):
    resp = client.get(f'/api/portfolios/{portfolio_id}/holdings/')
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


class TestPortfolioWithoutLedger:
    """A0：组合不关联任何账户，仅靠持仓显式归属也应可见。"""

    def test_explicit_position_makes_portfolio_visible(self, client, db, make_position):
        """无账户组合：显式指派持仓后，组合详情必须看得到它。

        历史实现因 `ledger_ids` 为空直接 `return []`，这一条必然失败。
        """
        pf = _portfolio(db, '成长组合（不绑账户）')
        ledger = _ledger(db, '微众银行')  # 账户默认组合是别的（此处 None）

        make_position(
            ledger_id=ledger.id,
            portfolio_id=pf.id,
            symbol='GROWTH',
            name='成长基金',
            asset_type='bond',
            quantity=1000,
            avg_price=1.0,
            current_price=1.2,
        )

        data = _get_holdings(client, pf.id)
        assert {p['symbol'] for p in data} == {'GROWTH'}, '无账户组合应靠显式持仓归属可见'

    def test_portfolio_with_neither_ledger_nor_position_is_empty(self, client, db):
        """既无账户也无持仓 → 空列表（不是 500，也不能凭空造行）。"""
        pf = _portfolio(db, '空组合')
        assert _get_holdings(client, pf.id) == []


class TestHoldingsAssignmentMode:
    """D20 二期 UI：持仓行必须透出**归属方式**，而不只是「归属于本组合」这个结果。

    前端「所属组合」列要区分两种状态：显式指派（用户指定过）与账户继承（没人指定，
    靠账户默认组合带进来）。两者在库里的差别就是 `positions.portfolio_id` 是否为 NULL，
    但持仓接口此前只回组合**内容**、不回**方式**——前端拿不到就只能一律显示组合名，
    于是用户改派完也看不出是否生效。这一组锁定该字段的透出与语义。
    """

    def test_holdings_expose_explicit_and_inherited_mode(self, client, db, make_position):
        """继承态透出 ``None``，显式态透出目标组合 id；显式必须压过账户继承。"""
        income = _portfolio(db, '固收+')
        growth = _portfolio(db, '成长策略')
        # 账户默认组合 = 固收+ ⇒ 未指派的持仓走继承路径进入固收+
        ledger = _ledger(db, '微众银行', portfolio_id=income.id)

        make_position(
            ledger_id=ledger.id,
            portfolio_id=None,
            symbol='BOND',
            name='债基',
            asset_type='bond',
            quantity=1000,
            avg_price=1.0,
            current_price=1.1,
        )
        make_position(
            ledger_id=ledger.id,
            portfolio_id=growth.id,
            symbol='GROWTH',
            name='成长基金',
            asset_type='bond',
            quantity=500,
            avg_price=2.0,
            current_price=2.2,
        )

        income_rows = {row['symbol']: row for row in _get_holdings(client, income.id)}
        assert income_rows['BOND']['portfolio_id'] is None, '继承态必须透出 None（前端标「随账户」）'
        assert 'GROWTH' not in income_rows, '显式指派到别的组合的持仓，不得靠账户继承混进来'

        growth_rows = {row['symbol']: row for row in _get_holdings(client, growth.id)}
        assert growth_rows['GROWTH']['portfolio_id'] == growth.id, '显式态必须透出目标组合 id'

    def test_list_positions_exposes_portfolio_id(self, client, db, make_position):
        """盘点页持仓表走 ``GET /api/positions/`` **分页**路径，也必须透出 portfolio_id。

        两条路径的序列化方式不同（holdings 是 dict 直出，分页走
        ``PositionOut.model_dump()``），任一处漏声明字段都会被静默丢掉——这正是
        ``is_money_fund`` / ``prev_close`` 在同 schema 里反复踩过的坑（见 schemas.py 注释）。
        只测 holdings 不足以证明盘点页能拿到归属。
        """
        pf = _portfolio(db, '成长策略')
        ledger = _ledger(db, '微众银行')
        make_position(
            ledger_id=ledger.id,
            portfolio_id=pf.id,
            symbol='GROWTH',
            name='成长基金',
            asset_type='bond',
            quantity=100,
            avg_price=1.0,
            current_price=1.0,
        )

        resp = client.get('/api/positions/')
        assert resp.status_code == 200, resp.get_json()
        rows = [row for row in resp.get_json()['data'] if row['symbol'] == 'GROWTH']
        assert rows, '分页路径应返回刚建的持仓'
        assert rows[0]['portfolio_id'] == pf.id, '分页路径必须透出 portfolio_id（否则前端只能显示「—」）'

    def test_ledger_positions_expose_portfolio_id(self, client, db, make_position):
        """账户详情页持仓表走 ``GET /api/ledgers/<id>/positions/`` **第三条**序列化路径。

        它有别于前两条：既不是 dict 直出（holdings），也不经过 ``PositionOut``
        （``/api/positions/``），而是 ``LedgerService.get_positions_paginated``
        手工拼列表。三条路径各自独立声明字段，任一处漏掉都会让该页的「所属组合」
        列永远显示「—」——功能没坏，但用户看不出归类生效，等同于坏。

        这里同时锁住两种状态：显式指派（具体 id）与账户继承（None）。
        """
        income = _portfolio(db, '固收+')
        growth = _portfolio(db, '成长策略')
        ledger = _ledger(db, '微众银行', portfolio_id=income.id)

        make_position(
            ledger_id=ledger.id,
            portfolio_id=None,
            symbol='BOND',
            name='债基',
            asset_type='bond',
            quantity=1000,
            avg_price=1.0,
            current_price=1.1,
        )
        make_position(
            ledger_id=ledger.id,
            portfolio_id=growth.id,
            symbol='GROWTH',
            name='成长基金',
            asset_type='bond',
            quantity=500,
            avg_price=2.0,
            current_price=2.2,
        )

        resp = client.get(f'/api/ledgers/{ledger.id}/positions/')
        assert resp.status_code == 200, resp.get_json()
        rows = {row['symbol']: row for row in resp.get_json()['data']['items']}
        assert rows['BOND']['portfolio_id'] is None, '账户持仓接口必须透出继承态 None'
        assert rows['GROWTH']['portfolio_id'] == growth.id, '账户持仓接口必须透出显式指派 id'


class TestPortfolioXirrByPosition:
    """A1：组合收益按持仓归因，不再按账户批量吸走。"""

    def test_two_portfolios_in_one_ledger_do_not_leak(self, db, make_position, make_transaction):
        """同一账户里两支持仓分属两个组合 → 各自的现金流只含自己那一笔。

        这是 A1 的核心断言：历史实现按 ledger_id 取流水，两个组合都会拿到 2000 元本金。
        """
        pf_default = _portfolio(db, '固收+组合')
        pf_growth = _portfolio(db, '成长组合')
        ledger = _ledger(db, '微众银行', portfolio_id=pf_default.id)  # 账户默认固收+

        pos_bond = make_position(
            ledger_id=ledger.id,
            portfolio_id=None,  # 未指派 → 继承账户默认组合（固收+）
            symbol='BOND',
            name='固收+基金',
            asset_type='bond',
            quantity=1000,
            avg_price=1.0,
            current_price=1.0,
        )
        pos_growth = make_position(
            ledger_id=ledger.id,
            portfolio_id=pf_growth.id,  # 显式指派 → 成长组合（压过账户继承）
            symbol='GROWTH',
            name='成长基金',
            asset_type='bond',
            quantity=1000,
            avg_price=1.0,
            current_price=1.0,
        )
        make_transaction(
            pos_bond.id,
            ledger.id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            symbol='BOND',
        )
        make_transaction(
            pos_growth.id,
            ledger.id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            symbol='GROWTH',
        )
        db.commit()

        cf_default = generate_portfolio_cashflows(db, pf_default.id, current_value=0.0)
        cf_growth = generate_portfolio_cashflows(db, pf_growth.id, current_value=0.0)

        assert cf_default == [(ONE_YEAR_AGO, -1000.0)], f'固收+组合串入了成长流水: {cf_default}'
        assert cf_growth == [(ONE_YEAR_AGO, -1000.0)], f'成长组合串入了固收+流水: {cf_growth}'

    def test_portfolio_without_ledger_has_xirr(self, db, make_position, make_transaction):
        """A0+A1：无账户组合也能算出年化（历史实现 `_empty_xirr_result()` 全 0）。"""
        pf = _portfolio(db, '成长组合')
        ledger = _ledger(db, '微众银行')  # 不绑任何组合
        pos = make_position(
            ledger_id=ledger.id,
            portfolio_id=pf.id,
            symbol='GROWTH',
            name='成长基金',
            asset_type='bond',
            quantity=1000,
            avg_price=1.0,
            current_price=1.2,
        )
        make_transaction(
            pos.id,
            ledger.id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            symbol='GROWTH',
        )
        db.commit()

        r = calculate_portfolio_xirr_by_id(db, pf.id, family_id=1)

        assert r['cashflow_count'] == 2, f'应为「买入 + 期末虚拟卖出」两笔，实际 {r}'
        assert r['current_value'] == 1200.0
        assert r['net_invested'] == 1000.0
        assert abs(r['xirr'] - 0.2) < 0.01, f'一年 20% 应算得出来，实际 {r["xirr"]}'

    def test_ledger_cash_is_not_attributed_to_position_portfolio(self, db, make_position, make_transaction):
        """账户入金（L1）不进持仓级组合现金流。

        入金是账户级事实、没有持仓归属。组合成员是持仓之后，本金只能由「买入」回答；
        把 L1 也算进来会让同一账户的两个组合重复认领同一笔本金。
        """
        pf = _portfolio(db, '成长组合')
        ledger = _ledger(db, '微众银行', portfolio_id=pf.id)
        pos = make_position(
            ledger_id=ledger.id,
            portfolio_id=pf.id,
            symbol='GROWTH',
            name='成长基金',
            asset_type='bond',
            quantity=1000,
            avg_price=1.0,
            current_price=1.0,
        )
        make_transaction(
            pos.id,
            ledger.id,
            txn_type='deposit',
            amount=5000,
            confirm_date=ONE_YEAR_AGO,
            symbol='GROWTH',
        )
        make_transaction(
            pos.id,
            ledger.id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            symbol='GROWTH',
        )
        db.commit()

        cf = generate_portfolio_cashflows(db, pf.id, current_value=0.0)

        assert cf == [(ONE_YEAR_AGO, -1000.0)], f'入金不应进组合现金流: {cf}'


class TestClearedPositionHistory:
    """已清仓持仓的流水必须留在组合现金流里。"""

    def test_cleared_position_keeps_its_cashflows(self, db, make_position, make_transaction):
        """`quantity == 0` 的持仓：市值端不计，但买卖流水仍属本组合历史。

        若取持仓时误加 `quantity > 0`，清仓那一刻整段收益会从现金流里消失。
        """
        pf = _portfolio(db, '已清仓组合')
        ledger = _ledger(db, '微众银行', portfolio_id=pf.id)
        pos = make_position(
            ledger_id=ledger.id,
            portfolio_id=pf.id,
            symbol='OLD',
            name='已清仓基金',
            asset_type='bond',
            quantity=0,  # 已清仓
            avg_price=1.0,
            current_price=1.0,
        )
        make_transaction(
            pos.id,
            ledger.id,
            txn_type='buy',
            asset_type='bond',
            amount=1000,
            confirm_date=ONE_YEAR_AGO,
            symbol='OLD',
        )
        make_transaction(
            pos.id,
            ledger.id,
            txn_type='sell',
            asset_type='bond',
            amount=1200,
            confirm_date=date.today(),
            symbol='OLD',
        )
        db.commit()

        cf = generate_portfolio_cashflows(db, pf.id, current_value=0.0)

        assert cf == [(ONE_YEAR_AGO, -1000.0), (date.today(), 1200.0)], f'清仓后历史流水丢失: {cf}'

        r = calculate_portfolio_xirr_by_id(db, pf.id, family_id=1)
        assert r['current_value'] == 0.0, '已清仓持仓不应计入市值'
        assert r['total_withdrawn'] == 1200.0
