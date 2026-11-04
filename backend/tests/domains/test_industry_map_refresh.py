# -*- coding: utf-8 -*-
"""手动补齐行业映射端点（POST /api/portfolios/industry-map/refresh/）。

纪律：job 侧不跨域查 user 域——symbol 由组合域收集（collect_family_map_symbols），
视图喂 targets。本文件钉住：收集口径、去重、无持仓跳过、编排器调用参数。
"""

from datetime import date

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position


def _make_position(db, ledger, symbol, asset_type='stock', qty=100):
    db.add(
        Position(
            symbol=symbol,
            name=symbol,
            asset_type=asset_type,
            account_name=ledger.name,
            ledger_id=ledger.id,
            market='CN_A',
            quantity=Money.shares_to_min_unit(qty),
            avg_price=Money.yuan_to_price_units(10.0),
            current_price=Money.yuan_to_price_units(12.0),
            confirm_date=date.today(),
            price_date=None,
        )
    )


class _StubOrchestrator:
    """记录 run_job 入参；job 结果原样返回。"""

    last_init_db = None
    last_call = None

    def __init__(self, db):
        _StubOrchestrator.last_init_db = db

    def run_job(self, job_name, full_sync=False, targets=None):
        _StubOrchestrator.last_call = {'job': job_name, 'full_sync': full_sync, 'targets': list(targets or [])}
        return {'status': 'success', 'stats': {'inserted': len(targets or [])}}


@pytest.fixture(autouse=True)
def _reset_stub_state():
    """类属性跨测试残留会让「未调用」断言吃到上一个用例的记录。"""
    _StubOrchestrator.last_init_db = None
    _StubOrchestrator.last_call = None
    yield
    _StubOrchestrator.last_init_db = None
    _StubOrchestrator.last_call = None


def test_no_stock_positions_skips_job(client, db, monkeypatch):
    """家庭里没有股票/转债持仓 ⇒ skipped，不构造编排器（不发任何外部请求）。"""
    monkeypatch.setattr('app.domains.portfolios.views.DataSyncOrchestrator', _StubOrchestrator)

    resp = client.post('/api/portfolios/industry-map/refresh/')

    assert resp.status_code == 200
    assert resp.json['data'] == {'skipped': True, 'reason': 'no_stock_positions', 'symbols': []}
    assert _StubOrchestrator.last_call is None


def test_collects_stock_and_bond_symbols_deduped(client, db, monkeypatch):
    """股票 + 可转债都收集；跨账户重复代码去重保序；基金/ETF 不收。"""
    portfolio = Portfolio(name='映射触发组合')
    db.add(portfolio)
    db.commit()
    l1 = Ledger(name='账户一', portfolio_id=portfolio.id)
    l2 = Ledger(name='账户二', portfolio_id=portfolio.id)
    db.add_all([l1, l2])
    db.commit()
    _make_position(db, l1, '600519')
    _make_position(db, l2, '600519')  # 跨账户重复 → 只问一次
    _make_position(db, l1, '110059', asset_type='bond')
    _make_position(db, l1, '510300', asset_type='etf')  # ETF 走穿透链路，不进映射 targets
    _make_position(db, l1, '000198', asset_type='money_fund')  # 类现金不收
    db.commit()

    monkeypatch.setattr('app.domains.portfolios.views.DataSyncOrchestrator', _StubOrchestrator)

    resp = client.post('/api/portfolios/industry-map/refresh/')

    assert resp.status_code == 200
    data = resp.json['data']
    assert data['skipped'] is False
    assert data['symbols'] == ['600519', '110059']
    assert _StubOrchestrator.last_call == {
        'job': 'security_industry_maps',
        'full_sync': False,
        'targets': ['600519', '110059'],
    }
    assert data['status'] == 'success'
    assert data['stats'] == {'inserted': 2}


def test_zero_quantity_position_not_collected(client, db, monkeypatch):
    """已清仓（quantity=0）的持仓不触发映射补齐。"""
    portfolio = Portfolio(name='清仓组合')
    db.add(portfolio)
    db.commit()
    ledger = Ledger(name='清仓账户', portfolio_id=portfolio.id)
    db.add(ledger)
    db.commit()
    _make_position(db, ledger, '600519', qty=0)
    db.commit()

    monkeypatch.setattr('app.domains.portfolios.views.DataSyncOrchestrator', _StubOrchestrator)

    resp = client.post('/api/portfolios/industry-map/refresh/')

    assert resp.json['data']['skipped'] is True
    assert _StubOrchestrator.last_call is None
