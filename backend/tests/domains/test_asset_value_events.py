# -*- coding: utf-8 -*-
"""资产值变动事件 A1–A11 判据（D99 / D100，设计 §11）。

走真实 test_client + 临时文件 SQLite，不 mock 服务：这些用例要同时钉住
「append-only 事件 + 投影缓存」的不变量与 HTTP 契约。
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_USER
from app.domains.assets.models import Asset

TODAY = date.today()
PAST_30 = (TODAY - timedelta(days=30)).isoformat()


def _new_asset(client, *, major='liability', amount=1_000_000, name='房贷', start_date='2026-01-01'):
    payload = {'major_category': major, 'name': name, 'amount': amount}
    if start_date is not None:
        payload['start_date'] = start_date
    resp = client.post('/api/assets/', json=payload)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']['id']


def _patch(client, aid, **payload):
    return client.patch(f'/api/assets/{aid}/', json=payload)


def _events(client, aid):
    resp = client.get(f'/api/assets/{aid}/value-events/')
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _asof(client, aid, day):
    resp = client.get(f'/api/assets/{aid}/value-at/?date={day}')
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


def _amount(client, aid):
    rows = client.get('/api/assets/').get_json()['data']
    return next(r['amount'] for r in rows if r['id'] == aid)


def _asset_summary(client):
    return client.get('/api/assets/summary/').get_json()


def test_a2_dual_timestamps(client):
    """补录 30 天前 ⇒ effective_date=该日、recorded_at=今天，两者绝不混用。"""
    aid = _new_asset(client)
    resp = _patch(client, aid, delta=-3000, effective_date=PAST_30, client_token='a2-token')
    assert resp.status_code == 200
    rows = _events(client, aid)['data']
    assert len(rows) == 1
    ev = rows[0]
    assert ev['effective_date'] == PAST_30
    assert ev['recorded_at'] is not None
    assert ev['recorded_at'][:10] != PAST_30
    # SQLite 的 func.now() 是 UTC，允许本地日与 UTC 日跨一天，但必须落在今天/昨天
    assert ev['recorded_at'][:10] in {TODAY.isoformat(), (TODAY - timedelta(days=1)).isoformat()}
    assert ev['delta'] == -3000.0
    assert ev['value_after'] == 997000.0


def test_a3_system_backfill_rejected(client):
    """只贴历史日期、不提供变动事实 ⇒ 400；delta 与 amount 不可同时提交。"""
    aid = _new_asset(client)
    assert _patch(client, aid, effective_date='2026-01-15').status_code == 400
    assert _patch(client, aid, delta=-100, amount=999900).status_code == 400
    assert _patch(client, aid, change_note='只写说明').status_code == 400
    assert _events(client, aid)['data'] == []
    assert _amount(client, aid) == 1_000_000.0


def test_a3_static_assets_stay_out_of_pnl_calendar():
    """静态资产不进收益日历（设计 §10）：_WATCHED 继续排除 Asset。"""
    from app.services.pnl_snapshot_store import _WATCHED

    assert Asset not in _WATCHED


def test_a4_out_of_order_zero_recompute(client):
    """先录 11 月、再补 10 月：两条 delta 原样不动，历史与当前值全部对得上。

    这是设计 §8 实现期修订的回归判据：用「变动后绝对值」反推 delta 时，
    本例会退化成 10 月 105 万 / 11 月 95 万 / 当前 95 万。
    """
    aid = _new_asset(client, amount=1_000_000)
    assert _patch(client, aid, delta=-50000, effective_date='2026-11-01', client_token='a4-nov').status_code == 200
    first = _events(client, aid)['data']
    assert len(first) == 1 and first[0]['delta'] == -50000.0

    assert _patch(client, aid, delta=-50000, effective_date='2026-10-01', client_token='a4-oct').status_code == 200
    rows = _events(client, aid)['data']
    assert [e['effective_date'] for e in rows] == ['2026-10-01', '2026-11-01']
    assert [e['delta'] for e in rows] == [-50000.0, -50000.0]
    # 先录那条事件的 delta 没被改写（零重算）；value_after 是读时派生，允许随序列变化
    assert rows[1]['delta'] == first[0]['delta']

    assert _asof(client, aid, '2026-09-30') == {'valid': True, 'value': 1_000_000.0}
    assert _asof(client, aid, '2026-10-15')['value'] == 950000.0
    assert _asof(client, aid, '2026-11-15')['value'] == 900000.0
    assert _amount(client, aid) == 900000.0


INVARIANT_CASES = [
    ('liability', 1_400_000, [-3000, -3000, -3000]),  # 房贷逐月还款
    ('liability', 1_400_000, [-1_260_000, +1_260_000]),  # 输错后冲销（correction）
    ('real_estate', 2_000_000, [+200000, -50000]),  # 房产重估
    ('receivable', 50_000, [+20000, -10000, -5000]),  # 别人欠我们的钱
    ('liability', 100_000, [+50_000, -10_000]),  # 新增借款后部分归还
    ('cash', 8_000, [+2000, -500, +100, -600]),  # 现金账户双向变动
]


@pytest.mark.parametrize('major,opening,deltas', INVARIANT_CASES)
def test_a5_invariants_i1_i2(client, major, opening, deltas):
    """I1：amount − Σdelta ≡ 初始余额；I2：任一 as-of 值恒 ≥ 0 且逐条折叠一致。"""
    aid = _new_asset(client, major=major, amount=opening, name=f'{major}-不变量')
    for i, delta in enumerate(deltas):
        day = f'2026-03-{i + 1:02d}'
        assert _patch(client, aid, delta=delta, effective_date=day, client_token=f'a5-{major}-{i}').status_code == 200

    rows = _events(client, aid)['data']
    assert len(rows) == len(deltas)
    current = _amount(client, aid)
    total = sum(e['delta'] for e in rows)
    initial = current - total
    assert initial == float(opening)  # I1
    assert initial >= 0  # I2（下界）

    running = initial
    for ev in rows:
        running += ev['delta']
        assert ev['value_after'] == running  # 逐条「变动后值」读时折叠，不落库
        assert ev['value_after'] >= 0  # I2
        assert _asof(client, aid, ev['effective_date'])['value'] == running
    assert current == initial + total


def test_a6_missing_lower_bound_never_extrapolates(client):
    """D100：start_date 为空 ⇒ 整条序列不提供 as-of；早于下界 ⇒ valid=false。"""
    aid_unknown = _new_asset(client, start_date=None, name='无起账日')
    assert _asof(client, aid_unknown, '2026-06-01') == {'value': None, 'valid': False}
    # 时间线仍可读（只是不能回答时点值），缺数据不画 0、不插值
    assert _patch(client, aid_unknown, delta=-1000, client_token='a6-unknown').status_code == 200
    assert len(_events(client, aid_unknown)['data']) == 1
    assert _asof(client, aid_unknown, '2026-06-01') == {'value': None, 'valid': False}

    aid = _new_asset(client, start_date='2026-06-01', name='有起账日')
    assert _asof(client, aid, '2026-05-31') == {'value': None, 'valid': False}
    assert _asof(client, aid, '2026-06-01')['valid'] is True
    assert _asof(client, aid, '2026-06-01')['value'] == 1_000_000.0


def test_a7_soft_delete_keeps_anchor(client):
    """status='closed' 不删 assets 行与事件行，I1 仍成立（D100 / 清仓不删行同源）。"""
    aid = _new_asset(client)
    assert _patch(client, aid, delta=-3000, effective_date='2026-05-01', client_token='a7').status_code == 200
    before = _events(client, aid)['data']
    assert _patch(client, aid, status='closed').status_code == 200
    after = _events(client, aid)['data']
    assert [e['id'] for e in after] == [e['id'] for e in before]
    assert _amount(client, aid) - sum(e['delta'] for e in after) == 1_000_000.0


def test_a8_family_snapshots_unchanged(client):
    """补录不得改写家庭级历史；先落一条真实快照，避免「空列表前后相同」的恒真判据。"""
    aid = _new_asset(client)
    snap = client.post('/api/summary/snapshots/', json={})
    assert snap.status_code == 200
    before = client.get('/api/summary/snapshots/').get_json()
    assert before['data'], '快照列表不应为空，否则本判据恒真'

    assert _patch(client, aid, delta=-3000, effective_date='2026-01-15', client_token='a8').status_code == 200
    after = client.get('/api/summary/snapshots/').get_json()
    assert after == before


def test_a9_idempotent_replay(client):
    """同一 client_token 重放两次 ⇒ 一行事件、amount 只变一次。"""
    aid = _new_asset(client)
    payload = {'delta': -3000, 'effective_date': PAST_30, 'client_token': 'a9-same'}
    assert _patch(client, aid, **payload).status_code == 200
    assert _patch(client, aid, **payload).status_code == 200
    assert len(_events(client, aid)['data']) == 1
    assert _amount(client, aid) == 997000.0


def test_a10_rename_writes_no_event_and_keeps_totals(client):
    """A10 + A1：只改名不写事件；改名后大类汇总按 id 归一，无重复 / 漏算。"""
    aid = _new_asset(client)
    before = _asset_summary(client)
    assert _patch(client, aid, name='招商银行房贷（改名）').status_code == 200
    # 显式提交 delta=0 也不该写事件：Σdelta 不变却多出无意义行（设计 §5.2）
    assert _patch(client, aid, delta=0, client_token='a10-zero').status_code == 200
    assert _events(client, aid)['data'] == []
    assert _amount(client, aid) == 1_000_000.0
    assert _asset_summary(client) == before


def test_a11_domain_registry_and_append_only_source():
    """A11：新表登记 user 域；服务层不存在事件行的 UPDATE / DELETE 路径。"""
    assert DATA_DOMAIN_REGISTRY['asset_value_events'] == DOMAIN_USER
    src = Path(__file__).parents[2] / 'app' / 'services' / 'asset_value_event_service.py'
    body = src.read_text(encoding='utf-8')
    assert 'db.delete(AssetValueEvent' not in body
    assert 'update(AssetValueEvent' not in body


def test_negative_balance_rejected(client):
    """恒正口径：把余额减成负数必须被拒，不夹紧成 0（否则 I1 / I2 会被悄悄破坏）。"""
    aid = _new_asset(client, amount=1000)
    resp = _patch(client, aid, delta=-2000, client_token='negative')
    assert resp.status_code == 400
    assert _events(client, aid)['data'] == []
    assert _amount(client, aid) == 1000.0


def test_legacy_amount_still_works(client):
    """旧客户端传绝对 amount 仍可用，换算成 delta 后走同一个写者（向后兼容）。"""
    aid = _new_asset(client)
    assert _patch(client, aid, amount=997000, client_token='legacy').status_code == 200
    rows = _events(client, aid)['data']
    assert len(rows) == 1 and rows[0]['delta'] == -3000.0
    assert _amount(client, aid) == 997000.0
