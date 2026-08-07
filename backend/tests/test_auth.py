# -*- coding: utf-8 -*-
"""鉴权中间件与多用户家庭地基测试（D1/D2/D4）。

覆盖：
- 白名单：health / temperature / logout 免登录；
- 强制登录模式（AUTH_ENABLED=true）：无 token 访问受保护端点返回 401 统一信封；
- JWT 验签链路：有效 token 关联本地用户；
- 开发模式（默认）：无 token 回退默认用户，兼容既有单用户流程；
- X-User-Id 旁路 + 家庭隔离（family_id 过滤）；
- viewer 只读分权：写方法统一 403；
- 家庭创建：创建者自动成为主理人；成员查看仅 admin。
"""

import pytest


@pytest.fixture
def auth_enabled(monkeypatch):
    """强制开启登录门禁。"""
    monkeypatch.setenv('AUTH_ENABLED', 'true')


def _create_user(db, supabase_id=None, family_id=1, role='member', username=None, email=None):
    from app.domains.users.models import User

    user = User(
        supabase_id=supabase_id,
        family_id=family_id,
        role=role,
        username=username or f'user_{supabase_id or id(db)}',
        email=email,
        is_active=1,
    )
    db.add(user)
    db.commit()
    return user


def test_health_public(client, auth_enabled):
    """health 免登录。"""
    resp = client.get('/api/health')
    assert resp.status_code == 200


def test_logout_public_without_token(client, auth_enabled):
    """强制登录模式下 logout 仍免登录（无 token 也能调用）。"""
    resp = client.post('/api/auth/logout')
    assert resp.status_code == 200


def test_protected_requires_auth(client, auth_enabled):
    """强制登录模式：无 token 访问受保护端点返回 401 统一信封。"""
    resp = client.get('/api/assets/')
    assert resp.status_code == 401
    body = resp.get_json()
    assert body['error_code'] == 1005  # ErrorCode.UNAUTHORIZED


def test_temperature_public_in_forced_mode(client, auth_enabled):
    """强制登录模式下探市接口仍免登录（不得 401）。"""
    resp = client.get('/api/temperature/overview')
    assert resp.status_code != 401


def test_default_mode_no_auth_needed(client, db):
    """开发/默认模式：无 token 回退默认用户，受保护接口正常返回。"""
    resp = client.get('/api/assets/')
    assert resp.status_code == 200


def test_auth_me_default_user(client):
    """GET /api/auth/me 返回默认用户信息（开发模式）。"""
    resp = client.get('/api/auth/me')
    assert resp.status_code == 200
    body = resp.get_json()['data']
    assert body['id'] == 1
    assert body['role'] in ('admin', 'member')


def test_jwt_auth_flow(client, db, monkeypatch):
    """JWT 验签链路：有效 token 关联到本地用户。"""
    import jwt as pyjwt

    secret = 'test-jwt-secret-0123456789abcdef'
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setenv('SUPABASE_JWT_SECRET', secret)

    # 预置一个 supabase 用户
    _create_user(db, supabase_id='sub-123', family_id=1, role='admin')

    token = pyjwt.encode({'sub': 'sub-123', 'exp': 9999999999}, secret, algorithm='HS256')
    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['supabase_id'] == 'sub-123'


def test_jit_provision_new_user(client, db, monkeypatch):
    """首次登录：有效 token 的 sub 无本地记录时自动创建用户（默认家庭1/member）。"""
    import jwt as pyjwt

    from app.core.database import SessionLocal
    from app.domains.users.models import User

    secret = 'test-jwt-secret-0123456789abcdef'
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setenv('SUPABASE_JWT_SECRET', secret)

    token = pyjwt.encode(
        {'sub': 'sub-new-user', 'email': 'new@example.com', 'user_metadata': {'username': '新用户'}, 'exp': 9999999999},
        secret,
        algorithm='HS256',
    )
    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['supabase_id'] == 'sub-new-user'
    assert data['role'] == 'member'
    assert data['family']['id'] == 1

    # 本地 users 表确有记录且字段来自 claims
    with SessionLocal() as s:
        user = s.query(User).filter_by(supabase_id='sub-new-user').first()
        assert user is not None
        assert user.email == 'new@example.com'
        assert user.username == '新用户'
        assert user.role == 'member'
        assert user.family_id == 1


def test_jit_provision_idempotent(client, db, monkeypatch):
    """重复登录不重复建号（唯一约束 + 回查）。"""
    import jwt as pyjwt

    from app.core.database import SessionLocal
    from app.domains.users.models import User

    secret = 'test-jwt-secret-0123456789abcdef'
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setenv('SUPABASE_JWT_SECRET', secret)

    token = pyjwt.encode({'sub': 'sub-idempotent', 'email': 'a@b.com', 'exp': 9999999999}, secret, algorithm='HS256')
    headers = {'Authorization': f'Bearer {token}'}
    assert client.get('/api/auth/me', headers=headers).status_code == 200
    assert client.get('/api/auth/me', headers=headers).status_code == 200

    with SessionLocal() as s:
        count = s.query(User).filter_by(supabase_id='sub-idempotent').count()
        assert count == 1
        # username 从 email 前缀推导
        assert s.query(User).filter_by(supabase_id='sub-idempotent').first().username == 'a'


def test_invalid_token_rejected(client, db, auth_enabled, monkeypatch):
    """伪造 token（验签失败）→ 401。"""
    monkeypatch.setenv('SUPABASE_JWT_SECRET', 'real-secret')
    resp = client.get('/api/auth/me', headers={'Authorization': 'Bearer bogus.token.here'})
    assert resp.status_code == 401


def test_family_isolation_via_x_user_id(client, db, make_asset):
    """X-User-Id 旁路 + 家庭隔离：仅返回当前用户所属家庭的资产。"""
    # 默认用户 1 在家庭 1；再建一个家庭 2 的用户
    user2 = _create_user(db, family_id=2, role='member')
    make_asset(family_id=1, name='家庭1资产', amount=100.0, major_category='cash')
    make_asset(family_id=2, name='家庭2资产', amount=200.0, major_category='cash')

    resp = client.get('/api/assets/', headers={'X-User-Id': str(user2.id)})
    assert resp.status_code == 200
    names = [item['name'] for item in resp.get_json()['data']]
    assert '家庭2资产' in names
    assert '家庭1资产' not in names


def test_viewer_readonly_denied(client, db):
    """viewer（只读）对写方法统一 403。"""
    viewer = _create_user(db, role='viewer')
    resp = client.post(
        '/api/assets/',
        headers={'X-User-Id': str(viewer.id)},
        json={'name': '只读尝试', 'major_category': 'cash', 'amount': 100},
    )
    assert resp.status_code == 403
    assert resp.get_json()['error_code'] == 1006  # ErrorCode.FORBIDDEN


def test_viewer_can_read(client, db, make_asset):
    """viewer 可读取家庭数据。"""
    viewer = _create_user(db, role='viewer')
    make_asset(family_id=1, name='可读资产', amount=100.0, major_category='cash')
    resp = client.get('/api/assets/', headers={'X-User-Id': str(viewer.id)})
    assert resp.status_code == 200
    assert any(item['name'] == '可读资产' for item in resp.get_json()['data'])


def test_create_family_sets_creator_as_admin(client, db):
    """创建家庭：创建者迁入新家庭并成为主理人。"""
    from app.domains.users.models import User

    resp = client.post('/api/families/', json={'name': '我的小家庭'})
    assert resp.status_code == 200
    family_id = resp.get_json()['data']['id']

    # 默认用户 1 已迁移到新家庭并升为 admin
    from app.core.database import SessionLocal

    with SessionLocal() as s:
        user = s.query(User).filter_by(id=1).first()
        assert user.family_id == family_id
        assert user.role == 'admin'


def test_family_members_admin_only(client, db, auth_enabled):
    """成员查看接口仅主理人可访问。"""
    _create_user(db, role='member', username='普通成员')
    # 强制登录模式下 X-User-Id 仍可旁路指定身份
    resp = client.get('/api/families/1/members/', headers={'X-User-Id': '1'})
    # 默认用户 1 是 admin（种子数据）
    assert resp.status_code == 200

    # 普通成员访问 → 403
    member = _create_user(db, role='member', username='另一成员')
    resp = client.get('/api/families/1/members/', headers={'X-User-Id': str(member.id)})
    assert resp.status_code == 403


def test_list_family_members_endpoint(client, db):
    """GET /api/users/ 返回当前家庭成员列表。"""
    _create_user(db, family_id=1, role='member', username='家人A')
    resp = client.get('/api/users/')
    assert resp.status_code == 200
    names = [item['username'] for item in resp.get_json()['data']]
    assert '家人A' in names


# ────────────────────────────── 越权防护（跨家庭） ──────────────────────────────


def test_cross_family_ledger_read_denied(client, db, make_asset):
    """家庭2 用户不能读取家庭1 的账户详情。"""
    user2 = _create_user(db, family_id=2, role='member')
    asset = make_asset(family_id=1, name='家庭1资产', amount=100.0, major_category='cash')
    ledger_id = asset.ledger_id

    resp = client.get(f'/api/ledgers/{ledger_id}/', headers={'X-User-Id': str(user2.id)})
    assert resp.status_code == 404  # 越权资源统一 404，不泄露存在性


def test_cross_family_ledger_update_denied(client, db, make_asset):
    """家庭2 用户不能修改家庭1 的账户。"""
    user2 = _create_user(db, family_id=2, role='member')
    asset = make_asset(family_id=1, name='家庭1资产', amount=100.0, major_category='cash')
    ledger_id = asset.ledger_id

    resp = client.patch(
        f'/api/ledgers/{ledger_id}/',
        headers={'X-User-Id': str(user2.id)},
        json={'name': '被篡改'},
    )
    assert resp.status_code == 404


def test_cross_family_position_transactions_denied(client, db, make_position):
    """家庭2 用户不能读取家庭1 持仓的交易明细。"""
    user2 = _create_user(db, family_id=2, role='member')
    pos = make_position(family_id=1, symbol='600000', name='浦发银行', quantity=100, avg_price=10, current_price=10)

    resp = client.get(f'/api/positions/{pos.id}/transactions/', headers={'X-User-Id': str(user2.id)})
    assert resp.status_code == 404


def test_cross_family_asset_delete_denied(client, db, make_asset):
    """家庭2 用户不能删除家庭1 的资产。"""
    user2 = _create_user(db, family_id=2, role='member')
    asset = make_asset(family_id=1, name='家庭1资产', amount=100.0, major_category='cash')

    resp = client.delete(f'/api/assets/{asset.id}/', headers={'X-User-Id': str(user2.id)})
    assert resp.status_code == 404

    # 资产仍在（未被删除）
    resp = client.get('/api/assets/', headers={'X-User-Id': '1'})
    assert any(item['name'] == '家庭1资产' for item in resp.get_json()['data'])


def test_cross_family_portfolio_xirr_denied(client, db, make_position):
    """家庭2 用户读取家庭1 组合 XIRR → 404。"""
    from app.domains.portfolios.models import Portfolio

    user2 = _create_user(db, family_id=2, role='member')
    pf = Portfolio(name='家庭1组合', family_id=1)
    db.add(pf)
    db.commit()
    portfolio_id = pf.id

    resp = client.get(
        f'/api/performance/xirr/?scope=portfolio&portfolio_id={portfolio_id}',
        headers={'X-User-Id': str(user2.id)},
    )
    assert resp.status_code == 404


def test_cross_family_watchlist_isolated(client, db):
    """watchlist 资产/分组按家庭隔离。"""
    from app.domains.watchlist.models import WatchlistGroup, WatchlistItem

    user2 = _create_user(db, family_id=2, role='member')
    db.add(WatchlistItem(symbol='600000', market='CN_A', venue='EXCHANGE', family_id=1))
    db.add(WatchlistItem(symbol='000001', market='CN_A', venue='EXCHANGE', family_id=2))
    db.add(WatchlistGroup(name='家庭1分组', family_id=1))
    db.commit()

    # 家庭1 只看到自己的
    resp = client.get('/api/watchlist/items/', headers={'X-User-Id': '1'})
    symbols = [i['symbol'] for i in resp.get_json()['data']]
    assert '600000' in symbols and '000001' not in symbols

    # 家庭2 只看到自己的
    resp = client.get('/api/watchlist/items/', headers={'X-User-Id': str(user2.id)})
    symbols = [i['symbol'] for i in resp.get_json()['data']]
    assert '000001' in symbols and '600000' not in symbols

    # 家庭2 不能读取家庭1 的分组
    group = db.query(WatchlistGroup).filter_by(name='家庭1分组').first()
    resp = client.patch(
        f'/api/watchlist/groups/{group.id}/',
        headers={'X-User-Id': str(user2.id)},
        json={'name': '被篡改'},
    )
    assert resp.status_code == 404


# ────────────────────────────── 登录标识解析（D10） ──────────────────────────────


def test_resolve_by_email(client, db):
    """邮箱精确匹配 → 返回规范邮箱。"""
    _create_user(db, username='alice', email='alice@example.com')
    resp = client.post('/api/auth/resolve', json={'identifier': 'alice@example.com'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['email'] == 'alice@example.com'


def test_resolve_by_username_case_insensitive(client, db):
    """用户名不区分大小写匹配。"""
    _create_user(db, username='InvestorWang', email='wang@example.com')
    resp = client.post('/api/auth/resolve', json={'identifier': 'investorwang'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['email'] == 'wang@example.com'


def test_resolve_email_takes_priority(client, db):
    """输入含 `@` 视为邮箱，即使与某用户名相同也走邮箱匹配。"""
    _create_user(db, username='a@b.com', email='real@example.com')
    _create_user(db, username='other', email='a@b.com')
    resp = client.post('/api/auth/resolve', json={'identifier': 'a@b.com'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['email'] == 'a@b.com'


def test_resolve_not_found(client, db):
    """未知标识 → 404。"""
    resp = client.post('/api/auth/resolve', json={'identifier': 'nobody'})
    assert resp.status_code == 404


def test_resolve_public_in_forced_mode(client, auth_enabled):
    """强制登录模式下 resolve 仍免登录（登录前必须可调用）。"""
    resp = client.post('/api/auth/resolve', json={'identifier': 'anything'})
    assert resp.status_code == 404  # 无匹配，但不被 401 拦截


def test_resolve_empty_identifier(client):
    """空标识 → 400。"""
    resp = client.post('/api/auth/resolve', json={'identifier': '   '})
    assert resp.status_code == 400


# ────────────────────────────── 个人资料更新（D10） ──────────────────────────────


def test_update_me_profile(client, db):
    """更新昵称/用户名/头像成功并回读。"""
    _create_user(db, username='old_name', email='me@example.com')
    resp = client.patch(
        '/api/users/me',
        json={
            'username': 'new_name',
            'nickname': '小贝',
            'avatar': 'https://api.dicebear.com/9.x/adventurer/svg?seed=abc',
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['username'] == 'new_name'
    assert data['nickname'] == '小贝'
    assert data['avatar'].startswith('https://api.dicebear.com')


def test_update_me_username_conflict(client, db):
    """用户名与他人冲突 → 409。"""
    _create_user(db, username='taken', email='taken@example.com')
    _create_user(db, username='me', email='me@example.com')
    resp = client.patch('/api/users/me', json={'username': 'taken'})
    assert resp.status_code == 409


def test_update_me_keeps_own_username(client, db):
    """保留自己的用户名不视为冲突。"""
    # 默认种子用户 username='local'（id=1），改回自己的名字不应触发 409
    resp = client.patch('/api/users/me', json={'username': 'local'})
    assert resp.status_code == 200


def test_update_me_partial(client, db):
    """只更新昵称，不影响用户名/头像。"""
    _create_user(db, username='partial', email='me@example.com')
    resp = client.patch('/api/users/me', json={'nickname': '仅改昵称'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['nickname'] == '仅改昵称'


def test_email_synced_from_claims(client, db, monkeypatch):
    """邮箱改绑后，claims.email 同步回本地 users.email（消除陈旧数据）。"""
    import jwt as pyjwt

    from app.core.database import SessionLocal
    from app.domains.users.models import User

    secret = 'test-jwt-secret-0123456789abcdef'
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setenv('SUPABASE_JWT_SECRET', secret)
    _create_user(db, supabase_id='sub-email', email='old@example.com')

    token = pyjwt.encode({'sub': 'sub-email', 'email': 'new@example.com', 'exp': 9999999999}, secret, algorithm='HS256')
    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['email'] == 'new@example.com'

    with SessionLocal() as s:
        user = s.query(User).filter_by(supabase_id='sub-email').first()
        assert user.email == 'new@example.com'
