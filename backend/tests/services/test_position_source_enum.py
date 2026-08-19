# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/19
"""持仓来源 source 枚举归一化回归测试（issue 探市录入持仓 / PositionSource 约束）。

固化三件事，避免「散落字符串」与「前后端 label 漂移」回潮：
1. 单一真相源：PositionSource 枚举 + POSITION_SOURCE_LABELS 字典必须完整一致，
   前端只能从 /api/utils/enums 取 label，禁止再手抄。
2. 写入约束：Position.source 经 @validates 拦截非法字符串，把脏数据挡在落库前。
3. 探市录入：source='explore'、ledger_id=None（未归档）能正确落库并回读。
"""

import pytest

from app.core.constants import POSITION_SOURCE_LABELS, PositionSource
from app.domains.positions.models import Position, PositionImportMeta


# ───────────────────────────── 1. 单一真相源 ─────────────────────────────
def test_explore_member_exists():
    # 探市录入来源必须存在于枚举
    assert PositionSource.EXPLORE.value == 'explore'


def test_labels_cover_all_enum_members():
    # 每个枚举值都应有中文 label，反之亦然（无多余键、无缺失键）
    enum_values = {m.value for m in PositionSource}
    label_keys = set(POSITION_SOURCE_LABELS.keys())
    assert enum_values == label_keys, f'枚举与 label 不一致: 差集={enum_values ^ label_keys}'


def test_explore_label_is_explore_text():
    assert POSITION_SOURCE_LABELS[PositionSource.EXPLORE.value] == '探市录入'


# ───────────────────────────── 2. validates 约束 ─────────────────────────────
def test_validates_accepts_enum_instance(db):
    pos = Position(symbol='000001', name='测试', asset_type='fund', source=PositionSource.EXPLORE)
    db.add(pos)
    db.commit()
    db.refresh(pos)
    # 枚举实例被归一化为字符串值
    assert pos.source == 'explore'


def test_validates_accepts_explore_string(db):
    pos = Position(symbol='000001', name='测试', asset_type='fund', source='explore')
    db.add(pos)
    db.commit()
    db.refresh(pos)
    assert pos.source == 'explore'


def test_validates_accepts_manual_default(db):
    # 不传 source 时走 default=manual
    pos = Position(symbol='000001', name='测试', asset_type='fund')
    db.add(pos)
    db.commit()
    db.refresh(pos)
    assert pos.source == PositionSource.MANUAL.value


def test_validates_rejects_illegal_string(db):
    # 非法来源字符串在构造时即被 @validates 拦截（SQLAlchemy 在 setattr 时触发校验）
    with pytest.raises(ValueError):
        Position(symbol='000001', name='测试', asset_type='fund', source='some_random_hack')


# ───────────────────────────── 3. enums 下发接口 ─────────────────────────────
def test_enums_endpoint_returns_position_source(client):
    resp = client.get('/api/utils/enums/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert 'position_source' in data
    assert data['position_source']['explore'] == '探市录入'
    # 全部枚举键都应下发
    assert set(data['position_source'].keys()) == {m.value for m in PositionSource}


# ───────────────────────────── 4. 探市写入 positions ─────────────────────────────
def test_explore_position_with_null_ledger(db):
    # 探市录入：未归档（ledger_id=None）+ source=explore 必须能落库
    pos = Position(
        symbol='000001',
        name='探市测试',
        asset_type='fund',
        source=PositionSource.EXPLORE.value,
        ledger_id=None,
        notes='来自探市页面录入',
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    assert pos.id is not None
    assert pos.source == 'explore'
    assert pos.ledger_id is None
    assert pos.notes == '来自探市页面录入'


# ───────────────────── 5. position_import_meta 对称约束 ─────────────────────
def test_import_meta_accepts_enum_instance(db):
    meta = PositionImportMeta(position_id=1, symbol='000001', source=PositionSource.E_ACCOUNT)
    assert meta.source == 'e_account_holding'


def test_import_meta_accepts_empty_string(db):
    # 空串表示「无来源快照」，兼容历史数据，必须放行
    meta = PositionImportMeta(position_id=1, symbol='000001', source='')
    assert meta.source == ''


def test_import_meta_rejects_illegal_string(db):
    with pytest.raises(ValueError):
        PositionImportMeta(position_id=1, symbol='000001', source='some_random_hack')


# ───────────────────── 6. 未归档查询 + 就地归档接口 ─────────────────────
def test_list_positions_unarchived_filter(client, make_position):
    # 构造一条未归档（ledger_id=None, source=explore）与一条已归档持仓
    make_position(symbol='000001', name='探市A', asset_type='fund', source='explore')
    make_position(symbol='000002', name='已归档B', asset_type='fund', source='manual', account_name='中信')

    resp = client.get('/api/positions/?ledger_id=null')
    assert resp.status_code == 200
    rows = resp.get_json()['data']  # list_positions 直接返回持仓数组
    assert len(rows) == 1
    assert rows[0]['source'] == 'explore'
    assert rows[0]['ledger_id'] is None


def test_archive_unarchived_position(client, make_position):
    pos = make_position(symbol='000001', name='探市A', asset_type='fund', source='explore')
    # 归档前在未归档列表
    before = client.get('/api/positions/?ledger_id=null').get_json()['data']
    assert any(r['id'] == pos.id for r in before)

    # PATCH 绑定 ledger_id 完成归档
    patch = client.patch(f'/api/positions/{pos.id}/', json={'ledger_id': 1})
    assert patch.status_code == 200
    assert patch.get_json()['data']['ledger_id'] == 1

    # 归档后不再出现在未归档列表
    after = client.get('/api/positions/?ledger_id=null').get_json()['data']
    assert not any(r['id'] == pos.id for r in after)
