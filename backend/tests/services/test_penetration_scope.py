# -*- coding: utf-8 -*-
"""#2595 穿透三级口径测试（family / ledger / portfolio）。

锁定四件事：
1. **口径解析唯一出口**：组合级语义（显式归属 + 成员账本继承）与归因 #2135
   完全一致，均委托 `services/scope.py`——本测试即两端口径一致性的锚。
2. **可加性**：Σ 账户穿透金额 ≡ 家庭级（同一持仓集合的两视图，不是两套算法）。
3. 参数契约：`ledger_id` 与 `portfolio_id` 互斥；组合不存在 / 非本家庭报错。
4. 出参 scope 标记：`scope` / `ledger_id` / `portfolio_id` 如实回显。
"""

import pytest

from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.penetration import build_penetration
from app.services.scope import ERR_MUTEX, ERR_NO_PORTFOLIO, filter_positions_by_scope


def _alloc(db, fund_code, industry_code, industry_name, ratio, *, scheme='csrc', period='2026Q2'):
    from datetime import date

    db.add(
        FundIndustryAlloc(
            fund_code=fund_code,
            report_period=period,
            report_date=date(2026, 6, 30),
            industry_code=industry_code,
            industry_name=industry_name,
            scheme=scheme,
            ratio=ratio,
            source='eastmoney',
        )
    )


from app.domains.funds.models import FundIndustryAlloc  # noqa: E402  (与造数工具同置)

# ── services/scope.py 单元 ────────────────────────────────────────────────


def test_scope_互斥参数抛错(make_position):
    make_position(symbol='000201', asset_type='fund', name='甲', quantity=100, current_price=1.0)
    db_positions = None  # 占位：filter 的互斥检查发生在查询之前，用空列表也成立
    with pytest.raises(ValueError, match=ERR_MUTEX):
        filter_positions_by_scope(None, 1, db_positions or [], ledger_id=1, portfolio_id=1)


def test_scope_组合不存在抛错(db, make_position):
    make_position(symbol='000202', asset_type='fund', name='乙', quantity=100, current_price=1.0)
    with pytest.raises(ValueError, match=ERR_NO_PORTFOLIO):
        filter_positions_by_scope(db, 1, [], portfolio_id=99999)


def test_scope_非本家庭组合视为不存在(db, make_position):
    make_position(symbol='000203', asset_type='fund', name='丙', quantity=100, current_price=1.0)
    other_family_pf = Portfolio(family_id=2, name='别家组合', is_deleted=False)
    db.add(other_family_pf)
    db.commit()
    with pytest.raises(ValueError, match=ERR_NO_PORTFOLIO):
        filter_positions_by_scope(db, 1, [], portfolio_id=other_family_pf.id)


# ── build_penetration 三级口径 ────────────────────────────────────────────


def _make_portfolio(db, name='测试组合'):
    pf = Portfolio(family_id=1, name=name, is_deleted=False)
    db.add(pf)
    db.commit()
    return pf


def _attach_ledger_to_portfolio(db, ledger_id, portfolio_id):
    db.query(Ledger).filter(Ledger.id == ledger_id).update({'portfolio_id': portfolio_id})
    db.commit()


def test_穿透_组合口径_显式归属与继承归属都算(db, make_position):
    """组合 = 成员账本继承 + 持仓显式归属；组合外账户持仓不出现。"""
    pf = _make_portfolio(db)
    _alloc(db, '000301', 'C39', '制造业', 100.0)

    # 继承路径：成员账本甲的基金 ⇒ 进组合
    pos_a = make_position(symbol='000301', name='继承基金', quantity=1000, current_price=2.0, asset_type='fund', account_name='组合甲账户')
    _attach_ledger_to_portfolio(db, pos_a.ledger_id, pf.id)
    # 显式路径：非成员账本乙、但持仓显式归属 ⇒ 进组合
    make_position(symbol='000302', name='显式基金', quantity=1000, current_price=1.0, asset_type='fund', account_name='组合乙账户', portfolio_id=pf.id)
    _alloc(db, '000302', 'C39', '制造业', 100.0)
    # 组合外：账本乙的另一只基金 ⇒ 不出现
    make_position(symbol='000303', name='组合外基金', quantity=1000, current_price=3.0, asset_type='fund', account_name='组合乙账户')
    db.commit()

    data = build_penetration(db, 1, portfolio_id=pf.id)
    assert data['scope'] == 'portfolio'
    assert data['portfolio_id'] == pf.id
    # 组合市值 = 2000（继承）+ 1000（显式），不含组合外 3000
    assert data['total_value_cny'] == 3000.0
    # 两只组合内基金都有行业配置 ⇒ 全额穿透；组合外基金被排除
    assert data['coverage']['penetrated_cny'] == 3000.0
    industries = {i['code'] for i in data['industries']}
    assert 'C39' in industries


def test_穿透_账户口径_只含该账本持仓(db, make_position):
    _alloc(db, '000401', 'C39', '制造业', 100.0)
    make_position(symbol='000401', name='甲账户基金', quantity=1000, current_price=2.0, asset_type='fund', account_name='账户A')
    make_position(symbol='000402', name='乙账户基金', quantity=1000, current_price=5.0, asset_type='fund', account_name='账户B')
    db.commit()

    ledger_id = db.query(Ledger).filter_by(name='账户A', family_id=1).first().id
    data = build_penetration(db, 1, ledger_id=ledger_id)
    assert data['scope'] == 'ledger'
    assert data['ledger_id'] == ledger_id
    assert data['total_value_cny'] == 2000.0


def test_穿透_可加性_Σ账户等于家庭(db, make_position):
    """同一持仓集合：家庭级 total ≡ Σ 各账户级 total（视图可加，算法唯一）。"""
    make_position(symbol='000501', name='A基金', quantity=1000, current_price=2.0, asset_type='fund', account_name='可加A')
    make_position(symbol='000502', name='B基金', quantity=1000, current_price=3.0, asset_type='fund', account_name='可加B')
    db.commit()

    family_total = build_penetration(db, 1)['total_value_cny']
    ledgers = db.query(Ledger).filter(Ledger.family_id == 1, Ledger.name.in_(['可加A', '可加B'])).all()
    ledger_sum = sum(build_penetration(db, 1, ledger_id=item.id)['total_value_cny'] for item in ledgers)
    assert ledger_sum == pytest.approx(family_total)


def test_穿透_家庭级出参缺省标记(db, make_position):
    make_position(symbol='000601', name='默认基金', quantity=100, current_price=1.0, asset_type='fund')
    db.commit()
    data = build_penetration(db, 1)
    assert data['scope'] == 'family'
    assert data['ledger_id'] is None and data['portfolio_id'] is None


# ── API 契约（信封 / 互斥 400 / scope 回显）────────────────────────────────


def test_穿透接口_契约信封与scope回显(client, db, make_position):
    make_position(symbol='000701', name='接口基金', quantity=100, current_price=1.0, asset_type='fund')
    db.commit()
    resp = client.get('/api/summary/penetration/')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert 'data' in payload and 'message' in payload
    assert payload['data']['scope'] == 'family'


def test_穿透接口_互斥参数回400(client):
    resp = client.get('/api/summary/penetration/?ledger_id=1&portfolio_id=1')
    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001


def test_穿透接口_组合不存在回400(client):
    resp = client.get('/api/summary/penetration/?portfolio_id=99999')
    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001
