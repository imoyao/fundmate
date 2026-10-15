# -*- coding: utf-8 -*-
"""持仓「配置目标（五笔钱）」编辑测试（#1123 P0）。

P0 范围：持仓明细的配置目标可编辑、写回 Position.allocation。
两条写路径都要过白名单（非法值 400，None 保持清空语义）：
- ledgers 域嵌套端点 PATCH /api/ledgers/<lid>/positions/<pid>/（前端持仓表行内编辑走此路径）；
- positions 域 PATCH /api/positions/<id>/（通用持仓更新）。
"""

VALID_ALLOC = 'speculative'


def _pos(make_position):
    """建一个可回读 PositionOut 的持仓（asset_type 必填：enrich 走 model_validate）"""
    return make_position(
        symbol='000001',
        name='平安银行',
        account_name='测试账户',
        asset_type='stock',
    )


def test_nested_patch_updates_allocation(client, make_position):
    """嵌套端点：合法五笔钱值写回并回显 label"""
    pos = _pos(make_position)
    resp = client.patch(
        f'/api/ledgers/{pos.ledger_id}/positions/{pos.id}/',
        json={'allocation': VALID_ALLOC},
    )
    assert resp.status_code == 200
    data = resp.json['data']
    assert data['allocation'] == VALID_ALLOC


def test_nested_patch_rejects_invalid_allocation(client, make_position):
    """嵌套端点：白名单外的值 400 拒绝，不落库"""
    pos = _pos(make_position)
    original = pos.allocation
    resp = client.patch(
        f'/api/ledgers/{pos.ledger_id}/positions/{pos.id}/',
        json={'allocation': 'not-a-bucket'},
    )
    assert resp.status_code == 400
    assert pos.allocation == original


def test_nested_patch_allows_null_allocation(client, make_position):
    """嵌套端点：None 保持可写（清空语义，与白名单收紧前行为一致）"""
    pos = _pos(make_position)
    resp = client.patch(
        f'/api/ledgers/{pos.ledger_id}/positions/{pos.id}/',
        json={'allocation': None},
    )
    assert resp.status_code == 200
    assert resp.json['data']['allocation'] is None


def test_positions_patch_updates_allocation(client, make_position):
    """positions 域端点：合法值写回"""
    pos = _pos(make_position)
    resp = client.patch(f'/api/positions/{pos.id}/', json={'allocation': VALID_ALLOC})
    assert resp.status_code == 200
    assert resp.json['data']['allocation'] == VALID_ALLOC


def test_positions_patch_rejects_invalid_allocation(client, make_position):
    """positions 域端点：白名单外的值拒收（schema validator → 4xx），不落库"""
    pos = _pos(make_position)
    original = pos.allocation
    resp = client.patch(f'/api/positions/{pos.id}/', json={'allocation': 'nope'})
    assert 400 <= resp.status_code < 500
    assert pos.allocation == original


def test_positions_patch_allows_null_allocation(client, make_position):
    """positions 域端点：None 清空语义保留"""
    pos = _pos(make_position)
    resp = client.patch(f'/api/positions/{pos.id}/', json={'allocation': None})
    assert resp.status_code == 200
    assert resp.json['data']['allocation'] is None
