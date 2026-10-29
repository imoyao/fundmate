# -*- coding: utf-8 -*-
"""#2617 持仓结构（资产类别 / 股基分列 Top N / 集中度）。

锁定四件事：
1. **三类占比**按市值，且三类之和 = 总市值（守恒，不重不漏）；
2. **股基分列**——股票与基金各自排名，不合并；`other` 只出总额不参与榜单；
3. **跨账户同标的先合并再排名**（否则「前 5 大」被账户拆分挤掉、集中度低估）；
4. **作用域**：`ledger_id` 只算该账户，`ledger_id` 与 `portfolio_id` 互斥。
"""

import pytest

from app.domains.ledgers.models import Ledger
from app.services.position_structure import build_position_structure


def _pos(
    make_position,
    *,
    symbol,
    price,
    quantity,
    asset_type='stock',
    account='账户甲',
    name=None,
    ledger_id=None,
    is_money_fund=None,
):
    kwargs = dict(
        symbol=symbol,
        name=name or symbol,
        quantity=quantity,
        avg_price=price,
        current_price=price,
        asset_type=asset_type,
        account_name=account,
    )
    # 仅在显式指定时传 ledger_id —— 传 None 会让 fixture 跳过自动建账本
    if ledger_id is not None:
        kwargs['ledger_id'] = ledger_id
    if is_money_fund is not None:
        kwargs['is_money_fund'] = is_money_fund
    return make_position(**kwargs)


def _seed_mixed(make_position):
    # 股票 6 只：1000 / 800 / 600 / 400 / 200 / 100 元
    for symbol, qty in [
        ('600001', 100),
        ('600002', 80),
        ('600003', 60),
        ('600004', 40),
        ('600005', 20),
        ('600006', 10),
    ]:
        _pos(make_position, symbol=symbol, price=10.0, quantity=qty)
    # 基金 1 只 500 元
    _pos(make_position, symbol='110011', price=5.0, quantity=100, asset_type='fund', name='混合基金')
    # 债券 200 元（归「其他」）
    _pos(make_position, symbol='019547', price=1.0, quantity=200, asset_type='bond', name='国债')


def _by_class(data):
    return {row['key']: row for row in data['by_asset_class']}


def test_三类占比守恒且金额正确(db, make_position):
    _seed_mixed(make_position)

    d = build_position_structure(db, family_id=1)

    classes = _by_class(d)
    assert classes['stock']['value_cny'] == pytest.approx(3100.0)
    assert classes['fund']['value_cny'] == pytest.approx(500.0)
    assert classes['other']['value_cny'] == pytest.approx(200.0)
    assert d['total_cny'] == pytest.approx(3800.0)
    # 三类之和 = 总额（不重不漏）
    assert sum(row['value_cny'] for row in d['by_asset_class']) == pytest.approx(d['total_cny'])
    assert classes['stock']['ratio_of_total'] == pytest.approx(81.58, abs=0.02)


def test_股基分列且前5集中度按组算(db, make_position):
    _seed_mixed(make_position)

    d = build_position_structure(db, family_id=1)
    stock = d['groups']['stock']
    fund = d['groups']['fund']

    # 股票 6 只、Top 默认 5 条；基金只有 1 只
    assert stock['count'] == 6
    assert len(stock['top']) == 5
    assert [row['symbol'] for row in stock['top']] == ['600001', '600002', '600003', '600004', '600005']
    assert fund['count'] == 1
    # 股票前 5 = 1000+800+600+400+200 = 3000 / 3100
    assert stock['top5_ratio_of_group'] == pytest.approx(96.77, abs=0.02)
    assert d['concentration']['top5_ratio_of_stock'] == pytest.approx(96.77, abs=0.02)
    # 基金只有一只 ⇒ 组内集中度 100%
    assert d['concentration']['top5_ratio_of_fund'] == pytest.approx(100.0, abs=0.01)
    # 整体前 5 = 1000+800+600+500(基金)+400 = 3300 / 3800
    assert d['concentration']['top5_ratio_of_total'] == pytest.approx(86.84, abs=0.02)


def test_跨账户同标的先合并再排名(db, make_position):
    """同一基金在两个账户各 500 元 ⇒ 合并为 1000 元、accounts=2，不占两个榜位。"""
    _pos(
        make_position, symbol='110011', price=5.0, quantity=100, asset_type='fund', account='账户甲', name='同一只基金'
    )
    _pos(
        make_position, symbol='110011', price=5.0, quantity=100, asset_type='fund', account='账户乙', name='同一只基金'
    )
    _pos(make_position, symbol='600001', price=10.0, quantity=90, account='账户甲')

    d = build_position_structure(db, family_id=1)
    fund_top = d['groups']['fund']['top']

    assert d['groups']['fund']['count'] == 1
    assert len(fund_top) == 1
    assert fund_top[0]['value_cny'] == pytest.approx(1000.0)
    assert fund_top[0]['accounts'] == 2


def test_ledger作用域只算该账户(db, make_position):
    _pos(make_position, symbol='600001', price=10.0, quantity=100, account='账户甲')
    pos_b = _pos(make_position, symbol='110011', price=5.0, quantity=100, asset_type='fund', account='账户乙')

    d = build_position_structure(db, family_id=1, ledger_id=pos_b.ledger_id)

    assert d['scope'] == 'ledger'
    assert d['total_cny'] == pytest.approx(500.0)
    assert _by_class(d)['stock']['value_cny'] == pytest.approx(0.0)
    assert d['groups']['stock']['count'] == 0
    assert d['groups']['stock']['top5_ratio_of_group'] is None  # 无股票 ⇒ 占比 None 不填 0


def test_组合与账户互斥(db):
    with pytest.raises(ValueError, match='互斥'):
        build_position_structure(db, family_id=1, ledger_id=1, portfolio_id=1)


def test_top_n夹取到合法区间(db, make_position):
    _seed_mixed(make_position)
    assert len(build_position_structure(db, family_id=1, top_n=2)['groups']['stock']['top']) == 2
    assert len(build_position_structure(db, family_id=1, top_n=999)['groups']['stock']['top']) == 6


def test_空库诚实回空(db):
    d = build_position_structure(db, family_id=1)
    assert d['total_cny'] == 0
    assert all(row['ratio_of_total'] is None for row in d['by_asset_class'])
    assert d['concentration']['top5_ratio_of_total'] is None


# ── 视角由账户类型决定（#2739）────────────────────────────────────────────


def _ledger_of(db, name, ledger_type):
    """按名字取/建指定类型的账本（fixture 默认建 bank，故这里显式指定）。"""
    ledger = db.query(Ledger).filter_by(name=name, family_id=1).first()
    if ledger is None:
        ledger = Ledger(name=name, ledger_type=ledger_type, family_id=1)
        db.add(ledger)
        db.flush()
    else:
        ledger.ledger_type = ledger_type
        db.flush()
    return ledger


def test_组合与家庭级无固定视角(db, make_position):
    """组合/家庭级跨类型账户混合 ⇒ view=None，前端据此保留切换控件。"""
    _pos(make_position, symbol='600001', price=10.0, quantity=100, account='账户甲')

    fam = build_position_structure(db, family_id=1)
    assert fam['view'] is None
    assert fam['ledger_type'] is None
    assert fam['cash_like_cny'] == pytest.approx(0.0)


def test_证券账户固定股票视角且ETF归权益侧(db, make_position):
    """证券账户 ⇒ view='stock'；ETF 与股票同榜（否则 ETF 市值会被固定视角藏起来）。"""
    ledger = _ledger_of(db, '证券账户', 'stock')
    _pos(make_position, symbol='600001', price=10.0, quantity=100, ledger_id=ledger.id)
    _pos(
        make_position,
        symbol='510300',
        price=4.0,
        quantity=100,
        asset_type='etf',
        name='沪深300ETF',
        ledger_id=ledger.id,
    )
    _pos(
        make_position,
        symbol='110011',
        price=5.0,
        quantity=100,
        asset_type='fund',
        name='场外基金',
        ledger_id=ledger.id,
    )

    d = build_position_structure(db, family_id=1, ledger_id=ledger.id)

    assert d['view'] == 'stock'
    assert d['ledger_type'] == 'stock'
    # ETF 进股票组（与股票同榜）
    assert d['groups']['stock']['count'] == 2
    assert {row['symbol'] for row in d['groups']['stock']['top']} == {'600001', '510300'}
    assert d['groups']['fund']['count'] == 1
    # 场外基金仍归基金侧（不因固定视角被改写），但视角固定为股票故它不在主榜
    assert _by_class(d)['fund']['value_cny'] == pytest.approx(500.0)
    assert _by_class(d)['stock']['value_cny'] == pytest.approx(1400.0)


def test_基金账户固定基金视角(db, make_position):
    ledger = _ledger_of(db, '基金账户', 'fund')
    _pos(
        make_position,
        symbol='110011',
        price=5.0,
        quantity=100,
        asset_type='fund',
        name='混合基金',
        ledger_id=ledger.id,
    )
    _pos(make_position, symbol='600001', price=10.0, quantity=100, ledger_id=ledger.id)

    d = build_position_structure(db, family_id=1, ledger_id=ledger.id)

    assert d['view'] == 'fund'
    assert d['ledger_type'] == 'fund'
    assert d['groups']['fund']['count'] == 1
    # 股票仍在股票侧，但不进主榜（视角固定为基金）
    assert d['groups']['stock']['count'] == 1


def test_银行账户固定基金视角(db, make_position):
    """银行账户除现金外按基金视角处理（owner 裁定）。"""
    ledger = _ledger_of(db, '银行账户', 'bank')
    _pos(
        make_position,
        symbol='110011',
        price=5.0,
        quantity=100,
        asset_type='fund',
        name='银行理财',
        ledger_id=ledger.id,
    )

    d = build_position_structure(db, family_id=1, ledger_id=ledger.id)

    assert d['view'] == 'fund'
    assert d['ledger_type'] == 'bank'


def test_账户级货基走类现金排除出持仓榜(db, make_position):
    """货基是现金等价物，不是持仓：排除出榜且不进集中度分母，但金额要如实报出。

    真实数据形态是 `type='fund'` + `is_money_fund=True`（实测基金账户 11 只）。
    """
    ledger = _ledger_of(db, '基金账户', 'fund')
    _pos(
        make_position,
        symbol='110011',
        price=5.0,
        quantity=100,
        asset_type='fund',
        name='混合基金',
        ledger_id=ledger.id,
    )
    _pos(
        make_position,
        symbol='000198',
        price=1.0,
        quantity=1000,
        asset_type='fund',
        name='场内货基',
        ledger_id=ledger.id,
        is_money_fund=True,
    )

    d = build_position_structure(db, family_id=1, ledger_id=ledger.id)

    assert d['cash_like_cny'] == pytest.approx(1000.0)
    assert d['total_cny'] == pytest.approx(500.0)  # 货基不在持仓总额内
    assert d['groups']['fund']['count'] == 1
    assert d['concentration']['top5_ratio_of_total'] == pytest.approx(100.0, abs=0.01)


def test_账户级asset_type为money_fund同样走类现金(db, make_position):
    """另一条判定路径：`asset_type='money_fund'`（逆回购等现金等价物同族）。"""
    ledger = _ledger_of(db, '基金账户', 'fund')
    _pos(
        make_position,
        symbol='511990',
        price=100.0,
        quantity=10,
        asset_type='money_fund',
        name='场内货基',
        ledger_id=ledger.id,
    )

    d = build_position_structure(db, family_id=1, ledger_id=ledger.id)

    assert d['cash_like_cny'] == pytest.approx(1000.0)
    assert d['total_cny'] == pytest.approx(0.0)
    assert d['groups']['fund']['count'] == 0


def test_组合级货基不排除维持现状(db, make_position):
    """组合级保留切换 ⇒ 货基沿用原口径（不排除），避免误伤已上线的组合页。

    真实数据形态是 `type='fund'` + `is_money_fund=True`（实测 20 只），
    它在原实现里进「基金」桶、参与 Top 榜 —— 本次不得改动这一点。
    """
    _pos(
        make_position,
        symbol='110011',
        price=5.0,
        quantity=100,
        asset_type='fund',
        name='混合基金',
        account='账户甲',
    )
    _pos(
        make_position,
        symbol='000198',
        price=1.0,
        quantity=1000,
        asset_type='fund',
        name='场内货基',
        account='账户甲',
        is_money_fund=True,
    )

    d = build_position_structure(db, family_id=1)

    assert d['view'] is None
    assert d['cash_like_cny'] == pytest.approx(0.0)
    assert d['total_cny'] == pytest.approx(1500.0)
    # 货基仍在基金桶、参与 Top（维持原口径）
    assert d['groups']['fund']['count'] == 2
    assert {row['symbol'] for row in d['groups']['fund']['top']} == {'110011', '000198'}


def test_组合级asset_type为money_fund归其他桶(db, make_position):
    """`asset_type='money_fund'`（另一条判定路径）在原实现里归「其他」桶、只出总额。"""
    _pos(
        make_position,
        symbol='511990',
        price=100.0,
        quantity=10,
        asset_type='money_fund',
        name='场内货基',
        account='账户甲',
    )

    d = build_position_structure(db, family_id=1)

    assert d['view'] is None
    assert _by_class(d)['other']['value_cny'] == pytest.approx(1000.0)
    assert d['groups']['fund']['count'] == 0


def test_账户级三类占比仍然守恒(db, make_position):
    """排除货基后，三类之和 = 持仓总额（不重不漏）。"""
    ledger = _ledger_of(db, '证券账户', 'stock')
    _pos(make_position, symbol='600001', price=10.0, quantity=100, ledger_id=ledger.id)
    _pos(
        make_position,
        symbol='019547',
        price=1.0,
        quantity=200,
        asset_type='bond',
        name='国债',
        ledger_id=ledger.id,
    )
    _pos(
        make_position,
        symbol='511990',
        price=100.0,
        quantity=10,
        asset_type='money_fund',
        name='场内货基',
        ledger_id=ledger.id,
    )

    d = build_position_structure(db, family_id=1, ledger_id=ledger.id)

    assert sum(row['value_cny'] for row in d['by_asset_class']) == pytest.approx(d['total_cny'])
    assert d['total_cny'] == pytest.approx(1200.0)


def test_账户级说明含视角与口径提示(db, make_position):
    """口径说明必须写清「视角已固定」与货基处理，否则用户无从判断数字含义。"""
    ledger = _ledger_of(db, '证券账户', 'stock')
    _pos(make_position, symbol='600001', price=10.0, quantity=100, ledger_id=ledger.id)

    d = build_position_structure(db, family_id=1, ledger_id=ledger.id)

    assert d['notes'][0].startswith('本账户是证券账户')
    assert 'ETF' in d['notes'][0]
    assert '货币基金走类现金' in d['notes'][0]


# ── 接口契约（#2617）──────────────────────────────────────────────────────


def test_接口信封与数据(client, db, make_position):
    _seed_mixed(make_position)
    resp = client.get('/api/summary/position-structure/')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert 'data' in payload and 'message' in payload
    data = payload['data']
    assert data['scope'] == 'family'
    assert data['total_cny'] == pytest.approx(3800.0)
    assert {row['key'] for row in data['by_asset_class']} == {'stock', 'fund', 'other'}
    assert len(data['groups']['stock']['top']) == 5


def test_接口互斥参数回400(client):
    resp = client.get('/api/summary/position-structure/?ledger_id=1&portfolio_id=1')
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload['error_code'] == 1001
    assert '互斥' in payload['message']


def test_接口top_n非法回400(client):
    resp = client.get('/api/summary/position-structure/?top_n=abc')
    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001
