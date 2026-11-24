# -*- coding: utf-8 -*-
"""#3246 第三段 / D127：汇总的**双口径**（顶层=可见，「家庭」对照块只到总额）.

判据来自用户 2026-11-23 的拍板（C 双口径）：父母账户这类场景要「知道家庭总资产、
但看不到父母的每笔明细」。所以顶层收敛到可见账户，另给一个只含三个总数的
``family_scope``，**且全可见时不给**（那时两层数字相同，给了只是让首页出现两张一样的卡）。

数据一律经 HTTP 造（`POST /api/positions/` / `POST /api/assets/`）：`db` fixture 直写
`Transaction` 会落到端点裸查询看不到的域，会让「不可见的看不见」以「全都看不见」假绿。
"""

from app.domains.ledgers.models import Ledger

OTHER_USER_ID = 2


def _ledger(db, name, visibility='shared', owner_user_id=None):
    row = Ledger(name=name, ledger_type='bank', family_id=1, visibility=visibility, owner_user_id=owner_user_id)
    db.add(row)
    db.commit()
    return row.id


def _buy(client, ledger_id, symbol, price=1.0, quantity=100):
    resp = client.post(
        '/api/positions/',
        json={
            'symbol': symbol,
            'name': f'标的{symbol}',
            'type': 'stock',
            'market': 'CN_A',
            'ledger_id': ledger_id,
            'quantity': quantity,
            'avg_price': price,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


def _cash(client, ledger_id, amount, name='活期'):
    resp = client.post(
        '/api/assets/', json={'major_category': 'cash', 'name': name, 'amount': amount, 'ledger_id': ledger_id}
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


def _two_ledgers(db):
    shared_id = _ledger(db, '家庭共享')
    private_id = _ledger(db, '别人的私房钱', visibility='private', owner_user_id=OTHER_USER_ID)
    return shared_id, private_id


def test_family_scope_absent_when_everything_visible(client, db):
    """全可见：顶层就是家庭口径，不再下发对照块（避免首页两张相同的卡）."""
    shared_id = _ledger(db, '家庭共享')
    _buy(client, shared_id, '000001')

    data = client.get('/api/summary/').get_json()['data']
    assert data['total_assets_cny'] == 100.0
    assert data['family_scope'] is None


def test_top_level_excludes_invisible_while_family_scope_keeps_it(client, db):
    """私有账户：顶层不含、家庭块含 —— 且两块的差额正好是被藏起来的那一份."""
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001', price=1.0)  # 100 元
    _buy(client, private_id, '000002', price=5.0)  # 500 元

    data = client.get('/api/summary/').get_json()['data']
    family = data['family_scope']
    assert data['total_assets_cny'] == 100.0, '顶层必须是可见口径'
    assert family is not None
    assert family['total_assets_cny'] == 600.0, '家庭块必须是全量口径'
    assert family['net_assets_cny'] == 600.0
    assert family['hidden_account_count'] == 1
    assert family['own_total_assets_cny'] == 100.0
    # 可加性：顶层 + 隐藏部分 == 家庭（两块若各算一套，这个恒等式会先破）
    assert data['total_assets_cny'] + (family['total_assets_cny'] - family['own_total_assets_cny']) == 600.0


def test_family_scope_carries_liabilities_too(client, db):
    """负债权重同样双口径：隐藏账户的负债只体现在家庭块里."""
    shared_id, private_id = _two_ledgers(db)
    _cash(client, shared_id, 1000.0)
    resp = client.post(
        '/api/assets/',
        json={'major_category': 'liability', 'name': '别人的房贷', 'amount': 800.0, 'ledger_id': private_id},
    )
    assert resp.status_code == 200, resp.get_json()

    data = client.get('/api/summary/').get_json()['data']
    assert data['total_liabilities_cny'] == 0.0
    assert data['family_scope']['total_liabilities_cny'] == 800.0
    assert data['family_scope']['net_assets_cny'] == 200.0


def test_account_groups_has_no_family_scope(client, db):
    """账户分组**不做**双口径：分组名就是账户名，给家庭口径等于把名字和金额列出来."""
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')
    _buy(client, private_id, '000002', price=5.0)

    data = client.get('/api/summary/').get_json()['data']
    names = {group['name'] for group in data['account_groups']}
    assert '家庭共享' in names
    assert '别人的私房钱' not in names


def test_distributions_exclude_invisible(client, db):
    """分布是明细派生指标，只给可见口径（含市场/账户维度）."""
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001', price=1.0)
    _buy(client, private_id, '000002', price=5.0)

    data = client.get('/api/summary/distributions/').get_json()['data']
    assert data['total_assets'] == 100.0


def test_unowned_rows_count_in_both_scopes(client, db, make_position):
    """无主持仓（``ledger_id IS NULL``）在两口径里都算 —— 与 restrict_visible 同一判据.

    若只在一侧算，就会出现「持仓列表有这行、总资产里没有」的死账。
    """
    _two_ledgers(db)
    make_position(
        symbol='000003',
        name='未归档持仓',
        ledger_id=None,
        asset_type='stock',
        quantity=10,
        avg_price=2.0,
        current_price=2.0,
    )

    data = client.get('/api/summary/').get_json()['data']
    assert data['total_assets_cny'] == 20.0
    # 全可见账户 + 无主行 ⇒ 没有「不可见账户」，故不给对照块
    assert data['family_scope'] is None
