# -*- coding: utf-8 -*-
"""Q3 第 10 个只读工具的接线单测（ToolExecutor 真实链路，内存 SQLite）。

钉住三件事：工具真被注册且能跑通、输出沿用「算不出就声明缺口」的诚实纪律、
以及 P1 服务端权威 family_id 覆盖仍然生效（新增工具不得开越权口子）。
"""

from datetime import date

from app.domains.temperature.models import MarketMultiItem
from app.services.ai_recognizer.tools import TOOLS_METADATA, ToolExecutor

TOOL = 'get_rebalance_reference'


def test_tool_is_registered_and_metadata_declares_family_id():
    meta = next(m for m in TOOLS_METADATA if m['name'] == TOOL)
    assert 'family_id' in meta['parameters']['properties']
    assert '客观参考，非投资建议' in meta['description']


def test_empty_db_declares_gaps_without_fabricating_numbers():
    r = ToolExecutor.run(TOOL, {})
    assert r['status'] == 'success', r.get('msg')
    data = r['data']
    assert data['disclaimer'] == '客观参考，非投资建议'
    assert data['coverage']['position_count'] == 0
    assert data['coverage']['total_market_value_yuan'] == 0
    assert [s for s in data['signals'] if s['type'] == 'single_position_weight'] == []
    declared = {m['type'] for m in data['missing_signals']}
    assert {'industry_concentration', 'deviation_from_mean'} <= declared


def test_positions_produce_real_weights(db, make_position):
    make_position(
        symbol='110011',
        name='甲基金',
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.1,
        account_name='测试账户',
    )
    make_position(
        symbol='600000',
        name='乙股票',
        asset_type='stock',
        quantity=50,
        avg_price=2.0,
        current_price=1.8,
        account_name='测试账户',
    )
    r = ToolExecutor.run(TOOL, {})
    assert r['status'] == 'success', r.get('msg')
    weights = [s for s in r['data']['signals'] if s['type'] == 'single_position_weight']
    assert [w['symbol'] for w in weights] == ['110011', '600000']
    assert weights[0]['weight_pct'] == 55.0
    assert weights[1]['weight_pct'] == 45.0
    assert r['data']['coverage']['total_market_value_yuan'] == 200.0


def test_local_valuation_percentile_is_used_when_present(db):
    db.add(
        MarketMultiItem(
            source='wind_valuation',
            item_type='index',
            item_code='000300.SH',
            item_name='沪深300',
            data={'pe_percentile': 85, 'valuation_date': '2026-11-10'},
            collected_at=date(2026, 11, 10),
            stale=False,
        )
    )
    db.commit()
    r = ToolExecutor.run(TOOL, {})
    assert r['status'] == 'success', r.get('msg')
    valuation = [s for s in r['data']['signals'] if s['type'] == 'valuation_context']
    assert len(valuation) == 1
    assert valuation[0]['pe_percentile'] == 85
    assert valuation[0]['note'] == '估值偏高'
    assert valuation[0]['level'] == 'watch'
    assert not any(m['type'] == 'valuation_context' for m in r['data']['missing_signals'])


def test_server_ctx_overrides_frontend_family_id():
    r = ToolExecutor.run(TOOL, {'family_id': 999}, server_ctx={'family_id': 1})
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['scope'] == 'family_id=1'


def test_unknown_benchmark_is_rejected_by_schema():
    r = ToolExecutor.run(TOOL, {'benchmark': 'NOT_AN_INDEX'})
    assert r['status'] == 'error'
    assert 'benchmark' in r['msg']


def test_undeclared_param_is_rejected():
    r = ToolExecutor.run(TOOL, {'allocation_source': 'hack'})
    assert r['status'] == 'error'
    assert '未知参数' in r['msg']
