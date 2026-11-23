# -*- coding: utf-8 -*-
"""#3246 第二段：可见性接入账户域（创建写 scope + 列表/单账户过滤）.

测试环境未启用鉴权时，`auth_before_request` 会回退到 seed 的默认用户 1。所以：

- 「自己创建的账户可见」直接用默认用户验证；
- 「另一个账号看不见」通过把行上的 `owner_user_id` 改成 2 来模拟——不必注入第二套
  identity/JWT，否则这组用例就变成「鉴权框架的测试」，而不是「可见性接入的测试」。

`shared` 的用例同样把 owner 改成 2：可见性只看 visibility，不看 owner（D125）。
"""

from app.domains.ledgers import access
from app.domains.ledgers.models import Ledger

DEFAULT_USER_ID = 1
OTHER_USER_ID = 2


def _create(client, **payload):
    payload.setdefault('name', '招行')
    resp = client.post('/api/ledgers/', json=payload)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


def _reassign(db, ledger_id, user_id):
    row = db.query(Ledger).filter(Ledger.id == ledger_id).one()
    row.owner_user_id = user_id
    db.commit()


def test_created_ledger_is_private_to_current_user(client, db):
    created = _create(client, name='我的两融')

    row = db.query(Ledger).filter(Ledger.id == created['id']).one()
    assert row.visibility == 'private'
    assert row.owner_user_id == DEFAULT_USER_ID


def test_owner_sees_it_in_list_and_detail(client):
    created = _create(client, name='我的基金')

    ids = [item['id'] for item in client.get('/api/ledgers/').get_json()['data']]
    assert created['id'] in ids
    assert client.get(f'/api/ledgers/{created["id"]}/').status_code == 200


def test_other_user_cannot_see_or_touch_private_ledger(client, db):
    created = _create(client, name='私有账户')
    _reassign(db, created['id'], OTHER_USER_ID)

    ids = [item['id'] for item in client.get('/api/ledgers/').get_json()['data']]
    assert created['id'] not in ids
    # 详情/改名/删除统一 404（不 403，避免泄露「该 id 存在」）
    assert client.get(f'/api/ledgers/{created["id"]}/').status_code == 404
    assert client.patch(f'/api/ledgers/{created["id"]}/', json={'name': '改名'}).status_code == 404
    assert client.delete(f'/api/ledgers/{created["id"]}/').status_code == 404


def test_shared_ledger_visible_regardless_of_owner(client, db):
    created = _create(client, name='家庭现金', visibility='shared')
    _reassign(db, created['id'], OTHER_USER_ID)

    ids = [item['id'] for item in client.get('/api/ledgers/').get_json()['data']]
    assert created['id'] in ids
    assert client.get(f'/api/ledgers/{created["id"]}/').status_code == 200


def test_invalid_visibility_rejected(client):
    resp = client.post('/api/ledgers/', json={'name': 'X', 'visibility': 'secret'})
    assert resp.status_code == 400


def test_resolve_scope_defaults_and_fallbacks():
    # 缺省 private + 当前用户为判定主体
    assert access.resolve_ledger_scope({}, 7) == ('private', 7, None)
    # 显式 shared 不写 owner（判定不看它）
    assert access.resolve_ledger_scope({'visibility': 'shared'}, 7) == ('shared', None, None)
    # 无身份上下文（本地未鉴权）：私有无法判定 ⇒ 降级 shared，避免账户对所有人消失
    assert access.resolve_ledger_scope({}, None) == ('shared', None, None)
    # 非法值不静默降级，交给调用方 400
    assert access.resolve_ledger_scope({'visibility': 'bogus'}, 7) == (None, None, '可见性取值无效')
