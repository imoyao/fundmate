# -*- coding: utf-8 -*-
"""家庭成员档案 HTTP 端点（#1173）的回归网。

服务层的业务规则测试见 `tests/services/test_family_member_service.py`。
本文件锁**HTTP 契约层**的东西——那些起服务层测试起不来：

1. 路由与尾斜杠（仓库约定：列表端点带尾斜杠）；
2. 权限：写操作 admin-only，读操作对全角色开放
   （viewer 也要能看见账户归属是谁，否则账户列表里会出现无名账户）；
3. 响应信封形状（``{data, message}``）；
4. 账户列表的归属字段真的带出来了（``owner_member_id`` / ``owner_member_name``）；
5. 持仓/汇总的成员筛选参数真的生效（端点层，不只是 service 层）。
"""

import pytest

from app.domains.families.models import MEMBER_ROLE_SPOUSE, FamilyMember


@pytest.fixture
def member(db):
    # 必须 commit（不只 flush）：SQLite 的文件锁在 flush 后仍持有，
    # HTTP 请求走另一个 session 写同表会撞 "database is locked"。
    m = FamilyMember(family_id=1, name='老婆', role=MEMBER_ROLE_SPOUSE)
    db.add(m)
    db.commit()
    return m


def test_list_member_profiles_endpoint(client, db, member):
    """GET 成员档案列表：返回档案而非登录账号。"""
    resp = client.get('/api/families/members/profiles/')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'ok'
    names = [item['name'] for item in body['data']]
    assert '老婆' in names


def test_create_member_profile_endpoint(client, db):
    """POST 新增成员档案。"""
    resp = client.post('/api/families/members/profiles/', json={'name': '小孩', 'role': 'child'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['name'] == '小孩'
    assert data['role_label'] == '子女'


def test_create_member_profile_rejects_bad_payload(client, db):
    """空称谓 → 422（schema 层拦，不进业务规则）。"""
    resp = client.post('/api/families/members/profiles/', json={'name': '  '})
    assert resp.status_code == 422


def test_update_member_profile_endpoint(client, db, member):
    """PATCH 改成员档案。"""
    resp = client.patch(f'/api/families/members/profiles/{member.id}/', json={'name': '媳妇'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['name'] == '媳妇'


def test_update_member_profile_404_for_unknown(client, db):
    """不存在的成员 → 404（不泄露存在性）。"""
    resp = client.patch('/api/families/members/profiles/999999/', json={'name': 'X'})
    assert resp.status_code == 404


def test_delete_member_profile_is_soft(client, db, member):
    """DELETE 成员 → 软删（行还在，is_active=False）。"""
    resp = client.delete(f'/api/families/members/profiles/{member.id}/')
    assert resp.status_code == 200
    assert resp.get_json()['data']['is_active'] is False
    # 行仍在库里
    from app.core.database import SessionLocal

    with SessionLocal() as s:
        assert s.query(FamilyMember).filter_by(id=member.id).first() is not None


def test_member_profile_write_requires_admin(client, db, member):
    """写操作仅主理人：普通成员 → 403。"""
    from app.domains.users.models import User

    user = db.query(User).filter_by(id=1).first()
    original_role = user.role
    user.role = 'member'
    db.commit()
    try:
        resp = client.post('/api/families/members/profiles/', json={'name': '偷偷加的'}, headers={'X-User-Id': '1'})
        assert resp.status_code == 403
    finally:
        user.role = original_role
        db.commit()


def test_member_profile_read_allows_viewer(client, db, member):
    """读操作对 viewer 开放——账户归属要能被看见。"""
    from app.domains.users.models import User

    user = db.query(User).filter_by(id=1).first()
    original_role = user.role
    user.role = 'viewer'
    db.commit()
    try:
        resp = client.get('/api/families/members/profiles/')
        assert resp.status_code == 200
    finally:
        user.role = original_role
        db.commit()


def test_ledger_list_carries_owner_member(client, db, member):
    """账户列表带出归属成员 ID 与称谓。"""
    resp = client.post('/api/ledgers/', json={'name': '老婆的招行', 'owner_member_id': member.id})
    assert resp.status_code == 200
    ledger_id = resp.get_json()['data']['id']

    resp = client.get('/api/ledgers/')
    assert resp.status_code == 200
    items = {item['id']: item for item in resp.get_json()['data']}
    assert items[ledger_id]['owner_member_id'] == member.id
    assert items[ledger_id]['owner_member_name'] == '老婆'


def test_ledger_update_owner_member_persists(client, db, member):
    """⚠️ 端点层回归：PATCH 账户改归属必须真生效。

    症状若是「200 但归属没变」，说明 `update_ledger` 的白名单漏了这个键——
    该模块用 `if 'X' in data:` 逐字段过滤，未列出的键被**静默忽略**。
    """
    resp = client.post('/api/ledgers/', json={'name': '招行'})
    ledger_id = resp.get_json()['data']['id']

    resp = client.patch(f'/api/ledgers/{ledger_id}/', json={'owner_member_id': member.id})
    assert resp.status_code == 200
    assert resp.get_json()['data']['owner_member_id'] == member.id

    # 再读一次，确认落库
    resp = client.get(f'/api/ledgers/{ledger_id}/')
    assert resp.get_json()['data']['owner_member_id'] == member.id


def test_ledger_update_owner_member_rejects_cross_family(client, db):
    """跨家庭成员 → 400（不静默接受）。"""
    foreign = FamilyMember(family_id=2, name='别家的人', role='other')
    db.add(foreign)
    db.commit()
    resp = client.post('/api/ledgers/', json={'name': '招行'})
    ledger_id = resp.get_json()['data']['id']

    resp = client.patch(f'/api/ledgers/{ledger_id}/', json={'owner_member_id': foreign.id})
    assert resp.status_code == 400


def test_positions_endpoint_accepts_member_filter(client, db, member):
    """持仓列表接受 member_id 参数（不报错即说明参数被识别）。"""
    resp = client.get(f'/api/positions/?member_id={member.id}')
    assert resp.status_code == 200
    assert resp.get_json()['data'] == []


def test_summary_endpoints_accept_member_filter(client, db, member):
    """汇总端点接受 member_id 参数。"""
    for path in ('/api/summary/', '/api/summary/sankey/', '/api/summary/distributions/', '/api/summary/groups/'):
        resp = client.get(f'{path}?member_id={member.id}')
        assert resp.status_code == 200, path


def test_summary_rejects_invalid_member_id(client, db):
    """非法 member_id → 422（静默忽略会让用户以为筛了、实际看的是全量）。

    422 而非 400：走 `parse_query` 的 pydantic 校验，与 positions 域
    `PositionListRequest` 同一套惯例（`parse_query` / `parse_body` 均 abort 422）。
    """
    resp = client.get('/api/summary/?member_id=abc')
    assert resp.status_code == 422
