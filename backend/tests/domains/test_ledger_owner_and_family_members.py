# -*- coding: utf-8 -*-
"""#1173 账户归属家庭成员 + 家庭成员管理 API + 按成员筛选。

覆盖验收四条：
1. 账户可指定归属成员，且该字段可写可读（含展示名）；
2. 家庭成员可增删改、可改角色（邀请 → 首次登录认领）；
3. 持仓列表与汇总支持按成员筛选（含「成员无账户 ⇒ 空集」不退化成全量）；
4. 前端入口不在此测（见 frontend 侧组件），后端只保证契约。

口径要点（改动前先读）：
- `owner_user_id` 是**家庭内切片**，`family_id` 才是隔离维度，两者不可互相替代；
- 未指定归属（NULL）的账户属于「家庭共享池」，不计入任何成员；
- 成员的账户集合换算统一走 `services/owner_scope`。
"""

from app.core.money import Money
from app.domains.families.models import Family
from app.domains.users.identity import UserIdentity
from app.domains.users.models import User


def _user(db, **kwargs) -> User:
    """建一个家庭成员（`users` 行）。"""
    if kwargs.get('family_id') and kwargs['family_id'] != 1:
        # users.family_id 有 FK 到 families.id，先保证目标家庭存在
        if db.get(Family, kwargs['family_id']) is None:
            db.add(Family(id=kwargs['family_id'], name=f'家庭{kwargs["family_id"]}'))
            db.flush()
    user = User(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _ledger(client, name: str, owner_user_id=None, channel_category='bank') -> dict:
    payload = {'name': name, 'channel_category': channel_category}
    if owner_user_id is not None:
        payload['owner_user_id'] = owner_user_id
    resp = client.post('/api/ledgers/', json=payload)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


# ────────────────────────── 1. 账户归属成员 ──────────────────────────


def test_ledger_owner_user_is_writable_and_readable(client, db):
    wife = _user(db, username='wife', nickname='老婆')
    created = _ledger(client, '招行-老婆', owner_user_id=wife.id)
    assert created['owner_user_id'] == wife.id
    assert created['owner_user_name'] == '老婆'

    # 列表与详情同样回显（不只是创建响应）
    listed = client.get('/api/ledgers/').get_json()['data']
    row = next(item for item in listed if item['id'] == created['id'])
    assert row['owner_user_id'] == wife.id
    detail = client.get(f'/api/ledgers/{created["id"]}/').get_json()['data']
    assert detail['owner_user_name'] == '老婆'

    # 显式传 null = 取消归属；不传 = 不改动
    resp = client.patch(f'/api/ledgers/{created["id"]}/', json={'owner_user_id': None})
    assert resp.status_code == 200
    assert resp.get_json()['data']['owner_user_id'] is None
    assert resp.get_json()['data']['owner_user_name'] is None


def test_ledger_owner_rejects_other_family_member(client, db):
    """跨家庭串人必须拦住：users.id 全局唯一，只校验「存在」就会挂到别人名下。"""
    stranger = _user(db, username='stranger', family_id=2)
    resp = client.post('/api/ledgers/', json={'name': '越权账户', 'channel_category': 'bank', 'owner_user_id': stranger.id})
    assert resp.status_code == 400
    assert '不属于当前家庭' in resp.get_json()['message']


# ────────────────────────── 2. 家庭成员管理 ──────────────────────────


def test_invite_member_then_claim_on_first_login(client, db):
    resp = client.post('/api/families/1/members/', json={'email': 'Wife@Example.com', 'role': 'viewer'})
    assert resp.status_code == 200, resp.get_json()
    invited = resp.get_json()['data']
    assert invited['email'] == 'wife@example.com'
    assert invited['role'] == 'viewer'
    # 尚未登录 ⇒ 待认领
    assert invited['pending'] is True

    # 重复邀请（同家庭）409
    assert client.post('/api/families/1/members/', json={'email': 'wife@example.com'}).status_code == 409
    # 非法邮箱 400
    assert client.post('/api/families/1/members/', json={'email': 'not-an-email'}).status_code == 400

    # 首次登录认领：绑定 supabase_id，**保留邀请时设定的家庭与角色**
    claims = {'sub': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'email': 'WIFE@example.com'}
    claimed = UserIdentity.provision(db, claims)
    assert claimed.id == invited['id']
    assert claimed.supabase_id == claims['sub']
    assert claimed.family_id == 1
    assert claimed.role == 'viewer'
    # 认领后再次 provision 幂等（不会再建号）
    assert UserIdentity.provision(db, claims).id == claimed.id


def test_update_member_role_and_last_admin_guard(client, db):
    member = _user(db, username='son', role='member')
    resp = client.patch(f'/api/families/1/members/{member.id}/', json={'role': 'viewer', 'nickname': '儿子'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['role'] == 'viewer' and data['nickname'] == '儿子'

    # 默认用户 1 是唯一主理人：降级必须被拒（否则家庭再无管理员）
    resp = client.patch('/api/families/1/members/1/', json={'role': 'member'})
    assert resp.status_code == 409

    # 非法角色
    assert client.patch(f'/api/families/1/members/{member.id}/', json={'role': 'owner'}).status_code == 400
    # 跨家庭成员 → 404（不泄露存在性）
    outsider = _user(db, username='outsider', family_id=2)
    assert client.patch(f'/api/families/1/members/{outsider.id}/', json={'role': 'member'}).status_code == 404


def test_remove_member_clears_ledger_owner_and_blocks_self(client, db):
    member = _user(db, username='daughter', role='member')
    ledger = _ledger(client, '女儿的账户', owner_user_id=member.id)

    # 不能移除自己（默认登录身份是用户 1）
    assert client.delete('/api/families/1/members/1/').status_code == 400

    resp = client.delete(f'/api/families/1/members/{member.id}/')
    assert resp.status_code == 200
    assert db.query(User).filter_by(id=member.id).first() is None
    # 账户留在原家庭，归属置空（账户与数据不随人走）
    detail = client.get(f'/api/ledgers/{ledger["id"]}/').get_json()['data']
    assert detail['owner_user_id'] is None


def test_family_members_admin_only_for_write(client, db):
    member = _user(db, username='plain', role='member')
    headers = {'X-User-Id': str(member.id)}
    assert client.post('/api/families/1/members/', json={'email': 'x@example.com'}, headers=headers).status_code == 403
    assert client.delete(f'/api/families/1/members/{member.id}/', headers=headers).status_code == 403


# ────────────────────────── 3. 按成员筛选 ──────────────────────────


def test_positions_filter_by_owner(client, db, make_position):
    wife = _user(db, username='wife2')
    mine = _ledger(client, '共同账户')
    hers = _ledger(client, '她的账户', owner_user_id=wife.id)
    make_position(symbol='600000', name='浦发银行', account_name='共同账户', ledger_id=mine['id'], asset_type='stock')
    make_position(symbol='000001', name='平安银行', account_name='她的账户', ledger_id=hers['id'], asset_type='stock')

    resp = client.get(f'/api/positions/?owner_user_id={wife.id}')
    assert resp.status_code == 200
    symbols = [item['symbol'] for item in resp.get_json()['data']]
    assert symbols == ['000001']

    # 不传参数 = 家庭全量（既有语义不变）
    all_symbols = {item['symbol'] for item in client.get('/api/positions/').get_json()['data']}
    assert {'600000', '000001'} <= all_symbols


def test_positions_filter_empty_owner_returns_nothing(client, db, make_position):
    """成员名下无账户 ⇒ 空集，**不得**退化成「不过滤」。"""
    nobody = _user(db, username='nobody')
    make_position(symbol='600000', name='浦发银行', account_name='共同账户2', asset_type='stock')
    resp = client.get(f'/api/positions/?owner_user_id={nobody.id}')
    assert resp.status_code == 200
    assert resp.get_json()['data'] == []


def test_summary_filter_by_owner(client, db, make_position):
    wife = _user(db, username='wife3')
    shared = _ledger(client, '共享账户')
    hers = _ledger(client, '她的账户3', owner_user_id=wife.id)
    make_position(
        symbol='600000',
        name='浦发银行',
        account_name='共享账户',
        ledger_id=shared['id'],
        asset_type='stock',
        market_value_override=Money.yuan_to_cents(300),
    )
    make_position(
        symbol='000001',
        name='平安银行',
        account_name='她的账户3',
        ledger_id=hers['id'],
        asset_type='stock',
        market_value_override=Money.yuan_to_cents(700),
    )

    full = client.get('/api/summary/').get_json()['data']
    assert full['total_assets_cny'] == 1000.0

    scoped = client.get(f'/api/summary/?owner_user_id={wife.id}').get_json()['data']
    assert scoped['total_assets_cny'] == 700.0
    # account_groups 与汇总同口径
    assert {g['name'] for g in scoped['account_groups']} == {'她的账户3'}

    # 无账户成员 ⇒ 全零，而不是全家庭
    nobody = _user(db, username='nobody2')
    empty = client.get(f'/api/summary/?owner_user_id={nobody.id}').get_json()['data']
    assert empty['total_assets_cny'] == 0.0
    assert empty['account_groups'] == []
