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
from app.domains.agent.models import AgentSession, AgentTrace
from app.services.ai_recognizer import llm as llm_module

_BASE = datetime(2026, 9, 26, 12, 0, 0, tzinfo=ZoneInfo('Asia/Shanghai'))


def _seed(
    db,
    session_id,
    *,
    user_id=1,
    goal='分析账户收益',
    title='',
    messages=None,
    turn_count=0,
    updated_at=None,
):
    row = AgentSession(
        session_id=session_id,
        user_id=user_id,
        goal=goal,
        title=title,
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
        title='现在市场温度是多少？',
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
    # title 为 2026-11-23 起的检索键（首条用户输入固化），见 session_list 模块注释
    assert set(item) == {'session_id', 'title', 'goal', 'preview', 'turn_count', 'created_at', 'updated_at'}
    assert item['title'] == '现在市场温度是多少？'
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


# ── 检索（q，2026-11-23 历史栏可检索） ──
def test_search_matches_title(client, db):
    """中文关键词命中标题；total 同步收敛——过滤发生在分页之前，不是「先取一页再筛」."""
    _seed(db, 'temp', title='现在市场温度是多少？', updated_at=_BASE + timedelta(minutes=1))
    _seed(db, 'tax', title='红利税怎么算？', updated_at=_BASE)

    payload = client.get('/api/agent/sessions/?q=温度').get_json()
    assert [it['session_id'] for it in payload['data']] == ['temp']
    assert payload['total'] == 1


def test_search_does_not_match_message_body(client, db):
    """v1 口径：只搜标题。正文在 JSON 列里是 \\uXXXX 转义形态，LIKE '%中文%' 永不命中——
    与其实现一个永远 0 命中的「正文搜索」，不如明确只搜标题（见 session_list 注释）."""
    _seed(
        db,
        'body-only',
        title='红利税怎么算？',
        messages=[{'user': '问的是红利税', 'assistant': '温度不在标题里'}],
    )

    payload = client.get('/api/agent/sessions/?q=温度').get_json()
    assert payload['data'] == []
    assert payload['total'] == 0


def test_search_escapes_like_wildcards(client, db):
    """`q='%'` 不能把整张表捞出来：未转义时 LIKE '%%%' 命中全部."""
    _seed(db, 'a', title='总资产')
    _seed(db, 'b', title='总负债')

    assert client.get('/api/agent/sessions/?q=%25').get_json()['total'] == 0  # %25 = '%'
    assert client.get('/api/agent/sessions/?q=_').get_json()['total'] == 0


def test_search_never_crosses_users(client, db):
    _seed(db, 'mine', title='市场温度')
    _seed(db, 'others', user_id=999, title='市场温度')

    payload = client.get('/api/agent/sessions/?q=市场温度').get_json()
    assert [it['session_id'] for it in payload['data']] == ['mine']


def test_search_blank_keyword_is_no_filter(client, db):
    _seed(db, 'x', title='甲')
    _seed(db, 'y', title='乙')

    assert client.get('/api/agent/sessions/?q=%20%20').get_json()['total'] == 2  # 两个空格


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
    # 标题在**新建时**固化 = 首条用户输入，历史栏据此可辨认、可搜索
    assert item['title'] == '现在市场温度是多少？'


def test_chat_second_turn_does_not_rewrite_title(client, monkeypatch):
    """续聊不得改标题：标题是「首条输入」，用当前轮覆盖等于每轮换一个标题."""

    def fake(content, system_prompt, **kwargs):
        return '{"action":"ask_clarification","missing_params":[],"content":"好的"}'

    monkeypatch.setattr(llm_module, 'call_llm', fake)
    first = client.post('/api/agent/chat/', json={'message': '第一句'}).get_json()['data']
    client.post('/api/agent/chat/', json={'message': '第二句', 'session_id': first['session_id']})

    items = client.get('/api/agent/sessions/').get_json()['data']
    item = next(it for it in items if it['session_id'] == first['session_id'])
    assert item['title'] == '第一句'
    assert item['preview'] == '第二句'  # 预览跟末条走，标题不跟


# ── 删除（2026-11 用户反馈「历史记录无法删除」）──
def test_delete_removes_session_and_its_traces(client, db):
    """删除会话要把该 session_id 的决策 trace 一起清掉，且不误伤别的会话.

    trace 是按 session_id 冗余关联（无 SQL FK），只删 agent_session 会留下
    无法归属的孤儿行——那既不是用户要的「删掉记录」，也让后续按 session 回放
    的脚本（agent_replay / agent_eval）读到半条链路。
    """
    _seed(db, 'del-1', title='要删掉的会话', messages=[{'user': 'a', 'assistant': 'b'}])
    db.add(AgentTrace(session_id='del-1', turn=1, tool_name='portfolio_summary'))
    db.add(AgentTrace(session_id='keep-1', turn=1, tool_name='market_temperature'))
    db.commit()

    resp = client.delete('/api/agent/sessions/del-1/')
    assert resp.status_code == 200
    assert resp.get_json()['data'] == {'session_id': 'del-1', 'deleted': True}

    assert client.get('/api/agent/sessions/del-1/').status_code == 404
    ids = [it['session_id'] for it in client.get('/api/agent/sessions/').get_json()['data']]
    assert 'del-1' not in ids

    db.expire_all()  # 请求走的是另一条 session，本地 identity map 已过期
    assert {r.session_id for r in db.query(AgentTrace).all()} == {'keep-1'}


def test_delete_other_user_session_404(client, db):
    """他人 session_id 一律 404，且**不得真的删掉**（越权探测不能有副作用）."""
    _seed(db, 'others-del', user_id=999)

    resp = client.delete('/api/agent/sessions/others-del/')
    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == ErrorCode.RESOURCE_NOT_FOUND.code

    db.expire_all()
    assert db.query(AgentSession).filter(AgentSession.session_id == 'others-del').first() is not None


def test_delete_unknown_session_404(client):
    resp = client.delete('/api/agent/sessions/never-existed/')
    assert resp.status_code == 404
    assert resp.get_json()['error_code'] == ErrorCode.RESOURCE_NOT_FOUND.code


def test_delete_twice_second_is_404(client, db):
    """重复删除：第二次 404（语义 = 本次请求没删掉任何东西），前端据此不再提示成功."""
    _seed(db, 'del-twice')

    assert client.delete('/api/agent/sessions/del-twice/').status_code == 200
    assert client.delete('/api/agent/sessions/del-twice/').status_code == 404
