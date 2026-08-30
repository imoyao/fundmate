# -*- coding: utf-8 -*-
"""基金持仓跨账本聚合（#1101）测试。"""

from urllib.parse import quote

import pytest

from app.domains.funds.models import Fund, FundType
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, SalesInstitution


def _make_fund_ledger(db, name, sales_institution_id=None, frontend_app=None, ledger_type='fund', is_aggregation=False):
    ledger = Ledger(
        name=name,
        ledger_type=ledger_type,
        family_id=1,
        sales_institution_id=sales_institution_id,
        frontend_app=frontend_app,
        is_aggregation=is_aggregation,
    )
    db.add(ledger)
    db.flush()
    return ledger


def _make_fund_position(db, ledger, symbol, name, quantity, current_price, ownership_status='active'):
    pos = Position(
        symbol=symbol,
        name=name,
        market='CN_A',
        asset_type='fund',
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


def test_fund_aggregation_by_product(client, db):
    """按基金产品聚合：跨账本同基金合并，E账户聚合账本持仓也计入。"""
    l1 = _make_fund_ledger(db, '支付宝', frontend_app='self')
    l2 = _make_fund_ledger(db, '爱基金', frontend_app='tonghuashun')
    le = _make_fund_ledger(db, '基金E账户', ledger_type='e_account', is_aggregation=True)

    # 华夏成长 000001：l1 100份@10元 + l2 200份@10元 + le 50份@10元 = 350份 / 3500元
    _make_fund_position(db, l1, '000001', '华夏成长', 100 * 10000, 10 * 10000)
    _make_fund_position(db, l2, '000001', '华夏成长', 200 * 10000, 10 * 10000)
    _make_fund_position(db, le, '000001', '华夏成长', 50 * 10000, 10 * 10000)
    # 易方达蓝筹 000002：仅 l2 50份@20元 = 1000元
    _make_fund_position(db, l2, '000002', '易方达蓝筹', 50 * 10000, 20 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/fund-aggregation/?dimension=product')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    by_symbol = {g['symbol']: g for g in data['groups']}
    assert set(by_symbol.keys()) == {'000001', '000002'}
    assert by_symbol['000001']['quantity'] == 350 * 10000
    assert by_symbol['000001']['market_value_cents'] == 3500 * 100
    assert by_symbol['000002']['market_value_cents'] == 1000 * 100
    assert data['total_market_value_cents'] == 4500 * 100
    # 000001 来源含 3 个账本（含 E账户聚合账本）
    assert len(by_symbol['000001']['sources']) == 3


def test_fund_aggregation_by_institution(client, db):
    """按销售机构聚合：同一机构下多账本合并。"""
    si1 = SalesInstitution(org_name='支付宝', org_type='独立基金销售机构')
    si2 = SalesInstitution(org_name='爱基金', org_type='独立基金销售机构')
    db.add_all([si1, si2])
    db.flush()
    l1 = _make_fund_ledger(db, '支付宝A', sales_institution_id=si1.id)
    l2 = _make_fund_ledger(db, '支付宝B', sales_institution_id=si1.id)
    l3 = _make_fund_ledger(db, '爱基金', sales_institution_id=si2.id)
    _make_fund_position(db, l1, '000001', '华夏成长', 100 * 10000, 10 * 10000)
    _make_fund_position(db, l2, '000001', '华夏成长', 100 * 10000, 10 * 10000)
    _make_fund_position(db, l3, '000002', '易方达蓝筹', 50 * 10000, 20 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/fund-aggregation/?dimension=institution')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    by_inst = {g['key']: g for g in data['groups']}
    assert set(by_inst.keys()) == {si1.id, si2.id}
    # 支付宝机构下两只账本共持 000001 200份 / 2000元
    assert by_inst[si1.id]['market_value_cents'] == 2000 * 100
    assert by_inst[si2.id]['market_value_cents'] == 1000 * 100


def test_fund_aggregation_excludes_aggregation_ledger_from_list(client, db):
    """账户列表应隐藏 is_aggregation 账本（#1101）。"""
    _make_fund_ledger(db, '基金E账户', ledger_type='e_account', is_aggregation=True)
    _make_fund_ledger(db, '支付宝', ledger_type='fund')
    db.commit()
    resp = client.get('/api/ledgers/')
    assert resp.status_code == 200
    names = [item['name'] for item in resp.get_json()['data']]
    assert '基金E账户' not in names
    assert '支付宝' in names


# ────────────────────────────────────────────────────────────────
# 聚合页检索/收益能力（#1219）：keyword 搜索、fund_type 筛选、收益率
# ────────────────────────────────────────────────────────────────
def _make_fund_type(db, name):
    ft = FundType(name=name)
    db.add(ft)
    db.flush()
    return ft


def _make_fund_record(db, code, name, fund_type_id=None):
    f = Fund(fund_code=code, name=name, fund_type_id=fund_type_id)
    db.add(f)
    db.flush()
    return f


def _make_pos_with_cost(db, ledger, symbol, name, quantity, price, cost):
    pos = Position(
        symbol=symbol,
        name=name,
        market='CN_A',
        asset_type='fund',
        ledger_id=ledger.id,
        family_id=1,
        quantity=quantity,
        avg_price=cost,
        current_price=price,
        ownership_status='active',
    )
    db.add(pos)
    db.flush()
    return pos


def test_fund_aggregation_keyword_filter(client, db):
    """keyword 支持按名称/代码模糊搜索，且汇总口径随过滤结果变化。"""
    l1 = _make_fund_ledger(db, '支付宝')
    _make_fund_position(db, l1, '000001', '华夏成长', 100 * 10000, 10 * 10000)
    _make_fund_position(db, l1, '000002', '易方达蓝筹', 50 * 10000, 20 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/fund-aggregation/?dimension=product&keyword=华夏')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert [g['symbol'] for g in data['groups']] == ['000001']
    assert data['total_market_value_cents'] == 1000 * 100

    resp = client.get('/api/ledgers/fund-aggregation/?dimension=product&keyword=000002')
    data = resp.get_json()['data']
    assert [g['symbol'] for g in data['groups']] == ['000002']


def test_fund_aggregation_fund_type_filter(client, db):
    """fund_type 分组字段与筛选（含 __none__ 未分类）。"""
    ft_stock = _make_fund_type(db, '股票型')
    ft_mixed = _make_fund_type(db, '混合型')
    _make_fund_record(db, '000001', '华夏成长', fund_type_id=ft_stock.id)
    _make_fund_record(db, '000002', '易方达蓝筹', fund_type_id=ft_mixed.id)

    l1 = _make_fund_ledger(db, '支付宝')
    _make_fund_position(db, l1, '000001', '华夏成长', 100 * 10000, 10 * 10000)
    _make_fund_position(db, l1, '000002', '易方达蓝筹', 50 * 10000, 20 * 10000)
    _make_fund_position(db, l1, '999999', '手动录入基金', 30 * 10000, 5 * 10000)
    db.commit()

    resp = client.get('/api/ledgers/fund-aggregation/?dimension=product')
    groups = {g['symbol']: g for g in resp.get_json()['data']['groups']}
    assert groups['000001']['fund_type'] == '股票型'
    assert groups['000002']['fund_type'] == '混合型'
    assert groups['999999']['fund_type'] is None
    # sources 明细同步带出 fund_type
    assert groups['000001']['sources'][0]['fund_type'] == '股票型'

    resp = client.get(f'/api/ledgers/fund-aggregation/?dimension=product&fund_type={quote("股票型")}')
    assert [g['symbol'] for g in resp.get_json()['data']['groups']] == ['000001']

    resp = client.get('/api/ledgers/fund-aggregation/?dimension=product&fund_type=__none__')
    assert [g['symbol'] for g in resp.get_json()['data']['groups']] == ['999999']


def test_fund_aggregation_return_pct(client, db):
    """收益率 = (市值 - 成本)/成本；无成本返回 None 且排序恒排最后。"""
    l1 = _make_fund_ledger(db, '支付宝')
    # 100份 @10元，成本8元 → 市值1000 / 成本800 / 收益200 / 收益率 25%
    _make_pos_with_cost(db, l1, '000001', '华夏成长', 100 * 10000, 10 * 10000, 8 * 10000)
    # 100份 @20元，成本25元 → 市值2000 / 成本2500 / 收益 -500 / 收益率 -20%
    _make_pos_with_cost(db, l1, '000002', '易方达蓝筹', 100 * 10000, 20 * 10000, 25 * 10000)
    # 无成本（avg_price=0）→ return_pct None
    _make_pos_with_cost(db, l1, '000003', '零成本基金', 100 * 10000, 5 * 10000, 0)
    db.commit()

    resp = client.get('/api/ledgers/fund-aggregation/?dimension=product')
    groups = {g['symbol']: g for g in resp.get_json()['data']['groups']}
    assert groups['000001']['cost_cents'] == 800 * 100
    assert groups['000001']['pnl_cents'] == 200 * 100
    assert groups['000001']['return_pct'] == pytest.approx(0.25)
    assert groups['000002']['return_pct'] == pytest.approx(-0.2)
    assert groups['000003']['return_pct'] is None

    # 按收益率降序：正收益在前，负收益随后，无成本恒排最后
    resp = client.get('/api/ledgers/fund-aggregation/?dimension=product&sort=return_pct&order=desc')
    symbols = [g['symbol'] for g in resp.get_json()['data']['groups']]
    assert symbols == ['000001', '000002', '000003']
