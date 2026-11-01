# -*- coding: utf-8 -*-
"""认证端点流水（D76 / #2780，`auth_audit.source='backend'`）。

覆盖三类判据：

1. **记到没记到**：resolve 命中 / 未命中 / 被限流、logout、资料变更各落一行；
   无关端点一行都不落（否则台账会被普通请求刷爆，等于没有台账）。
2. **记的内容对不对**：标识打码 + 可检索哈希、IP 截断、资料变更只记字段名不记值。
3. **记账失败不能反噬业务**：写库抛异常时请求仍按原状态码返回（D76 裁决二）。

第 3 条是这套实现最容易退化的地方——把 `flush` 里那层 try/except 去掉，前两类
测试全绿、业务也没坏，只有「数据库抽风时用户看到 500」这件事没人发现。
"""

import json

import pytest


def _create_user(db, username='alice', email='alice@example.com'):
    from app.domains.families.models import Family
    from app.domains.users.models import User

    if db.query(Family).filter(Family.id == 1).first() is None:
        db.add(Family(id=1, name='测试家庭'))
        db.flush()
    user = User(family_id=1, role='member', username=username, email=email)
    db.add(user)
    db.commit()
    return user


def _rows(event: str | None = None):
    """读台账。

    用**独立会话**而不是 `db` 夹具：审计是独立事务提交的，复用一个在请求前就打开的
    会话会读到它自己的快照（SQLite 隔离级别下看不到之后提交的行）。
    """
    from app.core.database import get_user_sessionmaker
    from app.domains.users.models import AuthAuditLog

    session = get_user_sessionmaker()()
    try:
        query = session.query(AuthAuditLog)
        if event:
            query = query.filter(AuthAuditLog.event == event)
        return query.order_by(AuthAuditLog.id.asc()).all()
    finally:
        session.close()


# ────────────────────────── 记到没记到 ──────────────────────────


def test_resolve_hit_recorded(client, db):
    """resolve 命中 → auth.resolve.hit，带打码标识。"""
    _create_user(db)
    resp = client.post('/api/auth/resolve', json={'identifier': 'alice@example.com'})
    assert resp.status_code == 200

    rows = _rows('auth.resolve.hit')
    assert len(rows) == 1
    row = rows[0]
    assert row.source == 'backend'
    assert row.identifier == 'al***@example.com'
    assert row.event == 'auth.resolve.hit'


def test_resolve_miss_recorded(client):
    """resolve 未命中 → auth.resolve.miss（枚举的主要信号）。"""
    resp = client.post('/api/auth/resolve', json={'identifier': 'nobody@example.com'})
    assert resp.status_code == 404

    rows = _rows('auth.resolve.miss')
    assert len(rows) == 1
    assert rows[0].identifier == 'no***@example.com'


def test_resolve_ratelimited_recorded(client):
    """超限的那次也要入账：否则「有人被限过」这件事在台账里不存在。"""
    from app.domains.auth.views import RESOLVE_RATE_LIMIT_PER_MINUTE

    for _ in range(RESOLVE_RATE_LIMIT_PER_MINUTE):
        client.post('/api/auth/resolve', json={'identifier': 'nobody'})
    resp = client.post('/api/auth/resolve', json={'identifier': 'nobody'})
    assert resp.status_code == 429

    rows = _rows('auth.resolve.ratelimited')
    assert len(rows) == 1
    assert json.loads(rows[0].detail)['status'] == 429
    # 被限流的那次尝试仍要能看出试的是什么（打码后）
    assert rows[0].identifier == 'n***y'


def test_logout_recorded(client):
    """logout 免登录也要留痕（否则「谁在什么时候退出」完全不可见）。"""
    resp = client.post('/api/auth/logout')
    assert resp.status_code == 200

    rows = _rows('auth.logout')
    assert len(rows) == 1
    assert rows[0].user_id is None  # 免登录端点，中间件不注入 g.current_user


def test_profile_update_recorded_without_values(client, db):
    """资料变更 → 只记改了哪些字段，**不记字段值**（昵称 / 头像 URL 属用户内容）。"""
    user = _create_user(db)
    resp = client.patch(
        '/api/users/me/',
        json={'nickname': '别落库的昵称'},
        headers={'X-User-Id': str(user.id)},
    )
    assert resp.status_code == 200

    rows = _rows('auth.profile.updated')
    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert json.loads(rows[0].detail)['fields'] == ['nickname']
    assert '别落库的昵称' not in rows[0].detail


def test_unrelated_endpoint_not_recorded(client):
    """其余端点一行都不记：审计表只装身份事件，不是访问日志。"""
    client.get('/api/health')
    client.post('/api/auth/resolve', json={'identifier': ''})  # 400，无可记录信息
    events = [r.event for r in _rows()]
    assert events == []


# ────────────────────────── 记的内容对不对 ──────────────────────────


def test_ip_truncated_and_ua_capped(client):
    """IP 抹掉主机位、UA 截断：台账要能归因，不需要精确到设备。"""
    client.post(
        '/api/auth/resolve',
        json={'identifier': 'nobody'},
        headers={'X-Forwarded-For': '203.0.113.42, 10.0.0.1', 'User-Agent': 'A' * 400},
        environ_base={'REMOTE_ADDR': '10.1.2.3'},
    )
    row = _rows('auth.resolve.miss')[0]
    assert row.ip == '203.0.113.0/24'  # 取首跳，与限流桶同一口径
    assert len(row.user_agent) == 120


def test_identifier_plaintext_never_stored(client):
    """明文标识（邮箱 / 用户名）不得出现在台账任何列。"""
    client.post('/api/auth/resolve', json={'identifier': 'sensitive.person@example.com'})
    row = _rows('auth.resolve.miss')[0]
    blob = f'{row.identifier or ""}{row.detail or ""}{row.user_agent or ""}'
    assert 'sensitive.person@example.com' not in blob
    assert 'sensitive' not in blob


def test_identifier_hash_is_case_insensitive_and_stable(client):
    """同一标识的大小写变体必须落成同一个指纹，否则「同一人试了 N 次」查不出来。"""
    client.post('/api/auth/resolve', json={'identifier': 'Alice@Example.com'})
    client.post('/api/auth/resolve', json={'identifier': 'alice@example.com'})
    digests = {json.loads(r.detail)['identifier_sha256'] for r in _rows('auth.resolve.miss')}
    assert len(digests) == 1


@pytest.mark.parametrize(
    'raw, expected',
    [
        ('alice@example.com', 'al***@example.com'),
        ('ab@example.com', '***@example.com'),  # 本地部分 ≤2 位不露
        ('InvestorWang', 'I***g'),
        ('abc', '***'),  # 太短，全遮
        ('', None),
        (None, None),
    ],
)
def test_mask_identifier(raw, expected):
    from app.domains.users.auth_audit import mask_identifier

    masked, digest = mask_identifier(raw)
    assert masked == expected
    assert (digest is None) == (expected is None)


@pytest.mark.parametrize(
    'raw, expected',
    [
        ('203.0.113.42', '203.0.113.0/24'),
        ('2001:db8:1:2:3:4:5:6', '2001:db8:1:2::/64'),
        ('unknown', None),
        ('not-an-ip', None),
        ('', None),
    ],
)
def test_mask_ip(raw, expected):
    from app.domains.users.auth_audit import mask_ip

    assert mask_ip(raw) == expected


# ────────────────────────── 记账失败不能反噬业务 ──────────────────────────


def test_write_failure_does_not_break_request(client, monkeypatch):
    """台账写失败时请求必须照原样返回（D76 裁决二：记账不阻断）。"""
    from app.domains.users import auth_audit

    def _boom(rows):
        raise RuntimeError('台账库不可用')

    monkeypatch.setattr(auth_audit, '_write', _boom)

    resp = client.post('/api/auth/resolve', json={'identifier': 'nobody'})
    assert resp.status_code == 404  # 业务状态码不受影响
    assert _rows() == []


def test_capture_failure_does_not_break_request(client, monkeypatch):
    """采集阶段抛异常同样不能外泄到响应。"""
    from app.domains.users import auth_audit

    def _boom(response):
        raise RuntimeError('采集炸了')

    monkeypatch.setattr(auth_audit, '_build_row', _boom)

    resp = client.post('/api/auth/resolve', json={'identifier': 'nobody'})
    assert resp.status_code == 404
    assert _rows() == []
