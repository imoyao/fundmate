# -*- coding: utf-8 -*-
"""GET /api/agent/sessions/ 与 /{session_id}/ HTTP 层测试（#1719 历史栏读路径）。

覆盖四件易碎的事：
1. 列表只回本人会话（跨用户不可见），字段齐备且**不含 messages**（只给 preview）；
2. 排序（更新时间倒序）与分页信封 {data,total,page,per_page}；
3. 详情回放 messages；他人 / 不存在的 session_id 一律 404（不泄露存在性）；
4. 与 chat 的闭环：真实发一轮后列表立即可见（「刷新后历史栏可见」的后端前提）。
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.exceptions import ErrorCode
from app.domains.agent.models import AgentSession
from app.services.ai_recognizer import llm as llm_module

_BASE = datetime(2026, 9, 26, 12, 0, 0, tzinfo=ZoneInfo('Asia/Shanghai'))


def _seed(db, session_id, *, user_id=1, goal='分析账户收益', messages=None, turn_count=0, updated_at=None):
    row = AgentSession(
        session_id=session_id,
        user_id=user_id,
        goal=goal,
        messages=messages if messages is not None else [],
        turn_count=turn_count,
        state={},
        summary='',
        key_facts={},
    )
    if updated_at is not None:
        row.updated_at = updated_at
    db.add(row)
    db.commit()
    return row


# ── 列表 ──
def test_list_returns_own_sessions_only_with_expected_fields(client, db):
    _seed(
        db,
        'mine-1',
        goal='看温度',
        messages=[{'user': '现在市场温度是多少？', 'assistant': '综合温度 29.6'}],
        turn_count=2,
    )
    _seed(db, 'others-1', user_id=999)

    resp = client.get('/api/agent/sessions/')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['message'] == 'ok'
    ids = [it['session_id'] for it in payload['data']]
    assert 'mine-1' in ids
    assert 'others-1' not in ids  # 跨用户不可见

    item = next(it for it in payload['data'] if it['session_id'] == 'mine-1')
    # 列表项字段 = 渲染历史栏所需最小集，且绝不能整列回传 messages
    assert set(item) == {'session_id', 'goal', 'preview', 'turn_count', 'created_at', 'updated_at'}
    assert item['goal'] == '看温度'
    assert item['preview'] == '现在市场温度是多少？'
    assert item['turn_count'] == 2
    assert item['created_at'] and item['updated_at']
    assert payload['total'] == len(payload['data'])


def test_list_empty(client):
    resp = client.get('/api/agent/sessions/')
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload['data'] == []
    assert payload['total'] == 0


def test_list_orders_by_updated_at_desc(client, db):
    _seed(db, 'older', updated_at=_BASE)
    _seed(db, 'newer', updated_at=_BASE + timedelta(hours=1))

    payload = client.get('/api/agent/sessions/').get_json()
    ids = [it['session_id'] for it in payload['data']]
    assert ids.index('newer') < ids.index('older')


def test_list_paginates(client, db):
    for i in range(3):
        _seed(db, f's{i}', updated_at=_BASE + timedelta(minutes=i))

    page1 = client.get('/api/agent/sessions/?page=1&per_page=2').get_json()
    assert len(page1['data']) == 2
    assert page1['total'] == 3
    assert page1['page'] == 1
    assert page1['per_page'] == 2
    # 倒序：最新的一条在第一页
    assert page1['data'][0]['session_id'] == 's2'

    page2 = client.get('/api/agent/sessions/?page=2&per_page=2').get_json()
    assert len(page2['data']) == 1
    assert page2['total'] == 3


def test_list_preview_is_truncated(client, db):
    _seed(db, 'long', messages=[{'user': '长' * 120, 'assistant': 'ok'}])
    payload = client.get('/api/agent/sessions/').get_json()
    assert len(payload['data'][0]['preview']) == 60


def test_list_preview_skips_empty_turns(client, db):
    _seed(db, 'mixed', messages=[{'user': '', 'assistant': 'a'}, {'user': '有内容的问题', 'assistant': 'b'}])
    payload = client.get('/api/agent/sessions/').get_json()
    assert payload['data'][0]['preview'] == '有内容的问题'


# ── 详情 ──
def test_detail_returns_messages(client, db):
    msgs = [{'user': '温度多少', 'assistant': '29.6'}, {'user': '贪恐呢', 'assistant': '21'}]
    _seed(db, 'mine-2', messages=msgs, turn_count=2)

    resp = client.get('/api/agent/sessions/mine-2/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['session_id'] == 'mine-2'
    assert data['messages'] == msgs
    assert data['turn_count'] == 2


def test_detail_unknown_session_404(client):
    resp = client.get('/api/agent/sessions/never-existed/')
    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == ErrorCode.RESOURCE_NOT_FOUND.code


def test_detail_other_user_session_404(client, db):
    """他人 session_id 一律 404——403 会泄露「该 id 存在」，与 chat 的越权口径一致。"""
    _seed(db, 'others-2', user_id=999, messages=[{'user': '别人的问题', 'assistant': 'a'}])

    resp = client.get('/api/agent/sessions/others-2/')
    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == ErrorCode.RESOURCE_NOT_FOUND.code
    assert '别人的问题' not in resp.get_data(as_text=True)


# ── 与 chat 闭环 ──
def test_chat_then_list_shows_new_session(client, monkeypatch):
    """发一轮后列表立即可见（历史栏「刷新即见」的后端前提）。"""

    def fake(content, system_prompt, **kwargs):
        return '{"action":"ask_clarification","missing_params":[],"content":"好的"}'

    monkeypatch.setattr(llm_module, 'call_llm', fake)
    created = client.post('/api/agent/chat/', json={'message': '现在市场温度是多少？'}).get_json()['data']
    assert created['session_id']

    payload = client.get('/api/agent/sessions/').get_json()
    item = next(it for it in payload['data'] if it['session_id'] == created['session_id'])
    assert item['preview'] == '现在市场温度是多少？'
