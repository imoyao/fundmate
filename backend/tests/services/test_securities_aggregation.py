# -*- coding: utf-8 -*-
"""场内证券持仓跨账本聚合（#1132 / #1264）测试。"""

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, SalesInstitution


def _make_sec_ledger(db, name, sales_institution_id=None):
    ledger = Ledger(
        name=name,
        ledger_type='broker',
        family_id=1,
        sales_institution_id=sales_institution_id,
        frontend_app='guorn',
        is_aggregation=False,
    )
    db.add(ledger)
    db.flush()
    return ledger


def _make_sec_position(db, ledger, symbol, name, asset_type, quantity, price):
    pos = Position(
        symbol=symbol,
        name=name,
        market='CN_A',
        asset_type=asset_type,
        ledger_id=ledger.id,
        family_id=1,
        quantity=quantity,
        avg_price=price,
        current_price=price,
        ownership_status='active',
    )
    db.add(pos)
    db.flush()
    return pos


def test_securities_aggregation_by_product(client, db):
    """按证券产品聚合：跨账本同标的合并。"""
    l1 = _make_sec_ledger(db, '华泰')
    l2 = _make_sec_ledger(db, '中信')
    # 浦发银行 600000：l1 200份@10元 + l2 100份@10元 = 300份 / 3000元
    _make_sec_position(db, l1, '600000', '浦发银行', 'stock', 200 * 10000, 10 * 10000)
    _make_sec_position(db, l2, '600000', '浦发银行', 'stock', 100 * 10000, 10 * 10000)
    # 沪深300ETF 510300：仅 l1 100份@20元 = 2000元
    _make_sec_position(db, l1, '510300', '沪深300ETF', 'etf', 100 * 10000, 20 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    by_symbol = {g['symbol']: g for g in data['groups']}
    assert set(by_symbol.keys()) == {'600000', '510300'}
    assert by_symbol['600000']['quantity'] == 300 * 10000
    assert by_symbol['600000']['market_value_cents'] == 3000 * 100
    assert by_symbol['510300']['market_value_cents'] == 2000 * 100


def test_securities_aggregation_asset_type_breakdown(client, db):
    """证券聚合返回按 asset_type 聚类的 fund_type_breakdown（股票/ETF/可转债），供资产构成环形图（#1264）。"""
    si = SalesInstitution(org_name='华泰', org_type='券商')
    db.add(si)
    db.flush()
    l1 = _make_sec_ledger(db, '华泰A', sales_institution_id=si.id)

    # 股票 200股@10元、ETF 100份@20元、可转债 50张@30元
    _make_sec_position(db, l1, '600000', '浦发银行', 'stock', 200 * 10000, 10 * 10000)
    _make_sec_position(db, l1, '510300', '沪深300ETF', 'etf', 100 * 10000, 20 * 10000)
    _make_sec_position(db, l1, '113050', '国债转债', 'bond', 50 * 10000, 30 * 10000)
    db.commit()

    data = client.get('/api/ledgers/securities-aggregation/?dimension=product').get_json()['data']
    bd = data['fund_type_breakdown']
    names = [x['name'] for x in bd]
    assert '股票' in names
    assert 'ETF' in names
    assert '可转债' in names
    # 分类数 = 3（每个 asset_type 一类，无未分类证券）
    assert len(bd) == 3
    # 名称与 asset_type 映射正确，且市值按 股票=ETF=2000元 > 可转债=1500元 聚类
    by_name = {x['name']: x for x in bd}
    assert by_name['股票']['count'] == 1
    assert by_name['股票']['market_value_cents'] == 2000 * 100
    assert by_name['ETF']['count'] == 1
    assert by_name['ETF']['market_value_cents'] == 2000 * 100
    assert by_name['可转债']['count'] == 1
    assert by_name['可转债']['market_value_cents'] == 1500 * 100


def test_securities_aggregation_asset_type_filter(client, db):
    """证券聚合支持 asset_type 精确筛选（证券类型 Tab：#1266 / #1264）。"""
    l1 = _make_sec_ledger(db, '华泰A')
    _make_sec_position(db, l1, '600000', '浦发银行', 'stock', 200 * 10000, 10 * 10000)
    _make_sec_position(db, l1, '510300', '沪深300ETF', 'etf', 100 * 10000, 20 * 10000)
    _make_sec_position(db, l1, '113050', '国债转债', 'bond', 50 * 10000, 30 * 10000)
    db.commit()

    data = client.get('/api/ledgers/securities-aggregation/?dimension=product&asset_type=etf').get_json()['data']
    symbols = {g['symbol'] for g in data['groups']}
    assert symbols == {'510300'}
    assert data['total'] == 1
