# -*- coding: utf-8 -*-
"""场内证券（股票/ETF/可转债）持仓跨账本聚合（#1132）测试。

覆盖：产品 / 机构两维度分组正确、金额口径正确、排序与分页、数据日期（快照日）、
app 维度废弃后的降级、空数据兜底、不含 fund/money_fund 持仓。
设计见 docs/working-notes/securities-aggregation-design-2026-08-29.md（D1~D4 已确认）。
#1133：app 维度已收敛去掉（本质即销售机构），仅保留向后兼容的降级行为。
"""

from datetime import date

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta, SalesInstitution


def _make_securities_ledger(db, name, sales_institution_id=None, frontend_app=None, ledger_type='stock'):
    ledger = Ledger(
        name=name,
        ledger_type=ledger_type,
        family_id=1,
        sales_institution_id=sales_institution_id,
        frontend_app=frontend_app,
    )
    db.add(ledger)
    db.flush()
    return ledger


def _make_securities_position(db, ledger, symbol, name, asset_type, quantity, current_price, ownership_status='active'):
    pos = Position(
        symbol=symbol,
        name=name,
        market='CN_A',
        asset_type=asset_type,
        ledger_id=ledger.id,
        family_id=1,
        quantity=quantity,
        avg_price=current_price,
        current_price=current_price,
        ownership_status=ownership_status,
    )
    db.add(pos)
    db.flush()
    return pos


def test_securities_aggregation_by_product(client, db):
    """按产品聚合：跨账本同标的合并，sources 含来源账本列表。"""
    l1 = _make_securities_ledger(db, '华泰证券', frontend_app='self')
    l2 = _make_securities_ledger(db, '同花顺', frontend_app='tonghuashun')

    # 贵州茅台 600519（stock）：l1 100份@1000元 + l2 200份@1000元 = 300份 / 300000元
    _make_securities_position(db, l1, '600519', '贵州茅台', 'stock', 100 * 10000, 1000 * 10000)
    _make_securities_position(db, l2, '600519', '贵州茅台', 'stock', 200 * 10000, 1000 * 10000)
    # 沪深300ETF 510300（etf）：仅 l2 50份@4元 = 200元
    _make_securities_position(db, l2, '510300', '沪深300ETF', 'etf', 50 * 10000, 4 * 10000)
    # 浦发转债 110059（bond）：仅 l1 10份@100元 = 1000元
    _make_securities_position(db, l1, '110059', '浦发转债', 'bond', 10 * 10000, 100 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    by_symbol = {g['symbol']: g for g in data['groups']}
    assert set(by_symbol.keys()) == {'600519', '510300', '110059'}
    # 600519 跨两个账本合并：300份 / 300000元
    assert by_symbol['600519']['quantity'] == 300 * 10000
    assert by_symbol['600519']['market_value_cents'] == 300000 * 100
    assert len(by_symbol['600519']['sources']) == 2
    assert by_symbol['510300']['market_value_cents'] == 200 * 100
    assert by_symbol['110059']['market_value_cents'] == 1000 * 100
    assert data['total_market_value_cents'] == (300000 + 200 + 1000) * 100


def test_securities_aggregation_by_institution(client, db):
    """按销售机构聚合：同一机构下多账本合并。"""
    si1 = SalesInstitution(org_name='华泰证券', org_type='证券公司')
    si2 = SalesInstitution(org_name='中信证券', org_type='证券公司')
    db.add_all([si1, si2])
    db.flush()
    l1 = _make_securities_ledger(db, '华泰A', sales_institution_id=si1.id)
    l2 = _make_securities_ledger(db, '华泰B', sales_institution_id=si1.id)
    l3 = _make_securities_ledger(db, '中信', sales_institution_id=si2.id)
    _make_securities_position(db, l1, '600519', '贵州茅台', 'stock', 100 * 10000, 1000 * 10000)
    _make_securities_position(db, l2, '600519', '贵州茅台', 'stock', 100 * 10000, 1000 * 10000)
    _make_securities_position(db, l3, '510300', '沪深300ETF', 'etf', 50 * 10000, 4 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/securities-aggregation/?dimension=institution')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    by_inst = {g['key']: g for g in data['groups']}
    assert set(by_inst.keys()) == {si1.id, si2.id}
    # 华泰机构下两只账本共持 600519 200份 / 200000元
    assert by_inst[si1.id]['market_value_cents'] == 200000 * 100
    assert by_inst[si2.id]['market_value_cents'] == 200 * 100


def test_securities_aggregation_app_dimension_deprecated(client, db):
    """#1133：'app' 维度已废弃（本质即销售机构），传入时静默降级为 'institution'。"""
    si1 = SalesInstitution(org_name='华泰证券', org_type='证券公司')
    db.add(si1)
    db.flush()
    l1 = _make_securities_ledger(db, '华泰证券', sales_institution_id=si1.id, frontend_app='self')
    _make_securities_position(db, l1, '600519', '贵州茅台', 'stock', 100 * 10000, 1000 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/securities-aggregation/?dimension=app')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    # 降级后返回 institution 维度结构：分组 key 为机构 id，并带出机构中文名
    assert data['dimension'] == 'institution'
    assert [g['key'] for g in data['groups']] == [si1.id]
    assert data['groups'][0]['institution_name'] == '华泰证券'


def test_securities_aggregation_institution_pagination(client, db):
    """场内证券按渠道展示同样按展平条目分页（#1265，与场外基金同一实现）。"""
    si1 = SalesInstitution(org_name='华泰证券', org_type='证券公司')
    si2 = SalesInstitution(org_name='中信证券', org_type='证券公司')
    db.add_all([si1, si2])
    db.flush()
    # si1：3 个产品，市值 3000 / 2000 / 1000 元
    for symbol, qty in (('600001', 300), ('600002', 200), ('600003', 100)):
        ledger = _make_securities_ledger(db, f'华泰-{symbol}', sales_institution_id=si1.id)
        _make_securities_position(db, ledger, symbol, f'证券{symbol}', 'stock', qty * 10000, 10 * 10000)
    # si2：2 个产品，市值 500 / 400 元
    for symbol, qty in (('600004', 50), ('600005', 40)):
        ledger = _make_securities_ledger(db, f'中信-{symbol}', sales_institution_id=si2.id)
        _make_securities_position(db, ledger, symbol, f'证券{symbol}', 'stock', qty * 10000, 10 * 10000)
    db.commit()

    def _page(p: int) -> dict:
        resp = client.get(f'/api/ledgers/securities-aggregation/?dimension=institution&page={p}&page_size=2')
        assert resp.status_code == 200
        return resp.get_json()['data']

    def _symbols(data: dict) -> list:
        return [i['symbol'] for g in data['groups'] for i in g['items']]

    d1 = _page(1)
    assert d1['total'] == 5
    assert d1['total_pages'] == 3
    assert _symbols(d1) == ['600001', '600002']
    assert d1['groups'][0]['market_value_cents'] == 6000 * 100

    d2 = _page(2)
    assert _symbols(d2) == ['600003', '600004']
    assert len(d2['groups']) == 2

    d3 = _page(3)
    assert _symbols(d3) == ['600005']
    assert d3['groups'][0]['market_value_cents'] == 900 * 100


def test_securities_aggregation_sorted_and_paged(client, db):
    """默认按市值降序；分页生效，且 total / 汇总市值均按全量口径计算。"""
    l1 = _make_securities_ledger(db, '华泰证券')
    _make_securities_position(db, l1, '600519', '贵州茅台', 'stock', 100 * 10000, 1000 * 10000)  # 100000 元
    _make_securities_position(db, l1, '110059', '浦发转债', 'bond', 10 * 10000, 100 * 10000)  # 1000 元
    _make_securities_position(db, l1, '510300', '沪深300ETF', 'etf', 50 * 10000, 4 * 10000)  # 200 元
    db.commit()

    # 默认降序：金额高者在前
    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product')
    data = resp.get_json()['data']
    assert [g['symbol'] for g in data['groups']] == ['600519', '110059', '510300']
    assert data['total'] == 3

    # 升序：金额低者在前
    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product&order=asc')
    data = resp.get_json()['data']
    assert [g['symbol'] for g in data['groups']] == ['510300', '110059', '600519']

    # 分页：每页 2 条，第 2 页仅剩 1 条，但 total 与汇总市值仍为全量口径
    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product&page=2&page_size=2')
    data = resp.get_json()['data']
    assert (data['page'], data['page_size'], data['total_pages']) == (2, 2, 2)
    assert data['total'] == 3
    assert len(data['groups']) == 1
    assert data['total_market_value_cents'] == (100000 + 1000 + 200) * 100


def test_securities_aggregation_snapshot_date(client, db):
    """数据日期取全部持仓中最早的快照日（最滞后的一笔），并同时给出最近的一笔。"""
    l1 = _make_securities_ledger(db, '华泰证券')
    p1 = _make_securities_position(db, l1, '600519', '贵州茅台', 'stock', 100 * 10000, 1000 * 10000)
    p2 = _make_securities_position(db, l1, '510300', '沪深300ETF', 'etf', 50 * 10000, 4 * 10000)
    db.flush()
    # p1 为 6 月导入、p2 为 8 月导入 → 页面「数据日期」应展示最早的 06-12
    db.add(
        PositionImportMeta(position_id=p1.id, symbol='600519', family_id=1, snapshot_date=date(2026, 6, 12), source='')
    )
    db.add(
        PositionImportMeta(position_id=p2.id, symbol='510300', family_id=1, snapshot_date=date(2026, 8, 20), source='')
    )
    db.commit()

    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product')
    data = resp.get_json()['data']
    assert data['snapshot_date'] == '2026-06-12'
    assert data['snapshot_date_latest'] == '2026-08-20'


def test_securities_aggregation_excludes_fund_positions(client, db):
    """聚合不含 fund/money_fund 持仓（与 #1101 正交）。"""
    l1 = _make_securities_ledger(db, '华泰证券')
    # 场内证券
    _make_securities_position(db, l1, '600519', '贵州茅台', 'stock', 100 * 10000, 1000 * 10000)
    # 场外基金（应被排除）
    _make_securities_position(db, l1, '000001', '华夏成长', 'fund', 100 * 10000, 10 * 10000)
    # 货基（应被排除）
    _make_securities_position(db, l1, '000002', '余额宝', 'money_fund', 100 * 10000, 1 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    by_symbol = {g['symbol']: g for g in data['groups']}
    assert set(by_symbol.keys()) == {'600519'}
    assert data['total_market_value_cents'] == 100000 * 100


def test_securities_aggregation_excludes_inactive(client, db):
    """ownership_status != 'active' 的持仓不参与聚合（与 fund_aggregation 同口径）。"""
    l1 = _make_securities_ledger(db, '华泰证券')
    _make_securities_position(
        db, l1, '600519', '贵州茅台', 'stock', 100 * 10000, 1000 * 10000, ownership_status='active'
    )
    _make_securities_position(db, l1, '510300', '沪深300ETF', 'etf', 50 * 10000, 4 * 10000, ownership_status='shadow')
    db.commit()

    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    by_symbol = {g['symbol']: g for g in data['groups']}
    assert set(by_symbol.keys()) == {'600519'}
    assert data['total_market_value_cents'] == 100000 * 100


def test_securities_aggregation_empty(client, db):
    """空数据兜底：total=0、groups=[]，且数据日期为 None。"""
    resp = client.get('/api/ledgers/securities-aggregation/?dimension=product')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['total_market_value_cents'] == 0
    assert data['groups'] == []
    assert data['dimension'] == 'product'
    assert data['total'] == 0
    assert data['snapshot_date'] is None
