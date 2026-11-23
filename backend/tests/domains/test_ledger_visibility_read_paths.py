# -*- coding: utf-8 -*-
"""#3246 第三段：可见性接入**明细读路径**（持仓 / 流水 / 导出）.

测试环境未启用鉴权时 `auth_before_request` 回退到 seed 的默认用户 1（与
`test_ledger_visibility_api.py` 同一套做法）。所以「看不见」用**把行上的
`owner_user_id` 改成 2** 来模拟，而不是注入第二套 identity——本文件测的是
「可见性有没有接到明细查询上」，不是鉴权框架本身。

每个用例都成对断言「不可见的看不见」+「共享/无主的仍看得见」：只断言前者时，
一个「把所有人都挡住」的实现也能全绿——那不是通过，是恰好挡住了正确的那一半。

**流水必须经 HTTP 造**（`POST /api/positions/` 买入），不能用 `make_transaction`
直写：`db` fixture 是 `_RoutingSession`，直写 `Transaction` 会落到裸查询看不到的
域，`/api/transactions` 恒返回 0 条——那样「不可见的看不见」会以「全都看不见」
的形式假绿（与 #3091 同源的盲区）。
"""

from app.domains.ledgers.models import Ledger
from app.domains.ledgers.visibility import restrict_visible
from app.domains.transactions.models import Transaction

DEFAULT_USER_ID = 1
OTHER_USER_ID = 2


def _ledger(db, name, visibility='shared', owner_user_id=None):
    row = Ledger(name=name, ledger_type='bank', family_id=1, visibility=visibility, owner_user_id=owner_user_id)
    db.add(row)
    db.commit()
    return row.id


def _two_ledgers(db):
    """共享账户（自己）+ 别人的私有账户."""
    shared_id = _ledger(db, '家庭共享')
    private_id = _ledger(db, '别人的私房钱', visibility='private', owner_user_id=OTHER_USER_ID)
    return shared_id, private_id


def _buy(client, ledger_id, symbol, price=1.0, quantity=100):
    """走真实请求链路买入：同时落持仓与流水，且落在端点能读到的那一侧."""
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


# ── 判定片段本身（纯函数级，先证口径再证接线） ──────────────────────────────


def test_restrict_visible_none_means_no_filter(client, db):
    """``None`` = 不按可见性筛：离线/内部调用与改造前的行为逐字一致."""
    shared_id, _ = _two_ledgers(db)
    _buy(client, shared_id, '000001')

    q = restrict_visible(db.query(Transaction), Transaction.ledger_id, None)
    assert q.count() == db.query(Transaction).count() == 1


def test_restrict_visible_empty_set_keeps_only_unowned(db, make_transaction):
    """空集不是「全挡住」：无主明细（``ledger_id IS NULL``）按家庭共有放行.

    理由见 ``visibility.restrict_visible`` 的 docstring。若改成「空集即空结果」，
    用户导入时还没分配账户的资产会凭空消失。
    """
    shared_id = _ledger(db, '甲')
    make_transaction(position_id=None, ledger_id=None, txn_type='buy', amount=100.0)
    make_transaction(position_id=None, ledger_id=shared_id, txn_type='buy', amount=200.0)

    rows = restrict_visible(db.query(Transaction), Transaction.ledger_id, set()).all()
    assert [r.amount for r in rows] == [10000]


# ── 持仓列表 ────────────────────────────────────────────────────────────────


def test_position_list_hides_private_ledger_of_other_user(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')
    _buy(client, private_id, '000002')

    payload = client.get('/api/positions/').get_json()
    assert {row['symbol'] for row in payload['data']} == {'SZ000001'}
    assert payload['total'] == 1, '不可见账户的持仓不能只藏行、却仍被计入 total'


def test_position_list_keeps_unowned_rows(client, db, make_position):
    """``ledger_id IS NULL`` 的持仓（导入暂存/未归档）仍可见——与片段级口径同源."""
    _two_ledgers(db)
    make_position(symbol='000003', name='未归档持仓', ledger_id=None, asset_type='stock', quantity=10, avg_price=1.0)

    names = {row['name'] for row in client.get('/api/positions/').get_json()['data']}
    assert names == {'未归档持仓'}


def test_position_drawer_404_for_invisible_position(client, db):
    shared_id, private_id = _two_ledgers(db)
    visible = _buy(client, shared_id, '000001')
    hidden = _buy(client, private_id, '000002')

    assert client.get(f'/api/positions/{visible["id"]}/transactions/').status_code == 200
    assert client.get(f'/api/positions/{hidden["id"]}/transactions/').status_code == 404


def test_login_user_still_sees_own_private_ledger(client, db):
    """自己的私有账户必须看得见——否则「默认独有」变成了「默认谁都看不见」."""
    own_id = _ledger(db, '我的私房钱', visibility='private', owner_user_id=DEFAULT_USER_ID)
    _buy(client, own_id, '000004')

    assert {row['symbol'] for row in client.get('/api/positions/').get_json()['data']} == {'SZ000004'}


# ── 流水：列表 / 汇总 / 详情 / 导出 ─────────────────────────────────────────


def test_transaction_list_hides_private_ledger(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')
    _buy(client, private_id, '000002', price=9.99)

    payload = client.get('/api/transactions/').get_json()
    assert {row['symbol'] for row in payload['data']} == {'SZ000001'}
    assert payload['total'] == 1


def test_transaction_summary_excludes_invisible(client, db):
    """汇总条与列表必须减掉同一批行；只减一边会「列表 1 条、汇总算 2 条」地静默对不上."""
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')
    _buy(client, private_id, '000002', price=9.99)

    data = client.get('/api/transactions/summary/').get_json()['data']
    assert data['buy'] == {'count': 1, 'amount': 100.0}


def test_transaction_detail_404_for_invisible(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')
    hidden = _buy(client, private_id, '000002', price=9.99)

    ids = {row['symbol']: row['id'] for row in client.get('/api/transactions/').get_json()['data']}
    assert client.get(f'/api/transactions/{ids["SZ000001"]}/').status_code == 200
    # 私有账户那条连 id 都拿不到（列表已藏）：它的持仓抽屉 404、构造任意 id 探测也 404
    assert client.get(f'/api/positions/{hidden["id"]}/transactions/').status_code == 404
    assert client.get('/api/transactions/999999/').status_code == 404


def test_export_csv_excludes_invisible(client, db):
    """导出是「数据主权」通道，最容易漏——它不经过列表端点，单独一条读路径."""
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')
    _buy(client, private_id, '000002', price=9.99)

    body = client.get('/api/transactions/export/').get_data(as_text=True)
    assert 'SZ000001' in body
    assert 'SZ000002' not in body
