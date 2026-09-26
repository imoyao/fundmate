# -*- coding: utf-8 -*-
"""真实工具只读测试（#1121 S1-A + S1-C 日志留痕）。

五工具各自跑通真实 service（conftest 内存 SQLite；get_fund_nav 强制
allow_remote=False 不出网），另覆盖 schema 校验、P1 服务端覆盖断言，
以及 ToolExecutor.run 成功/失败必留 [agent.tool] 痕（S1-C）。
"""

from datetime import date

from loguru import logger

from app.services.ai_recognizer import tools as tools_mod
from app.services.ai_recognizer.tools import ToolExecutor


# ── 各工具正常路径（空库 / 种子库） ──
def test_assets_overview_empty_db():
    r = ToolExecutor.run('get_assets_overview', {})
    assert r['status'] == 'success'
    assert r['data']['total_assets_cny'] == 0
    assert r['data']['net_assets_cny'] == 0


def test_fund_nav_no_remote_on_empty_db():
    r = ToolExecutor.run('get_fund_nav', {'fund_codes': ['110011']})
    assert r['status'] == 'success'
    assert r['data']['navs'] == []  # 库里无净值 → 空结果，且不触发远程抓取


def test_market_temperature_empty_db():
    r = ToolExecutor.run('get_market_temperature', {})
    assert r['status'] == 'success'
    assert 'freshness' in r['data']
    assert 'conclusion' in r['data']


def test_watchlist_overview_empty_db():
    r = ToolExecutor.run('get_watchlist_overview', {})
    assert r['status'] == 'success'
    assert r['data']['items'] == []


def test_portfolio_performance_with_seed(db, make_position, make_transaction):
    """种子一笔买入 + 持仓市值，XIRR 真实算得出。"""
    pos = make_position(
        symbol='110011',
        name='测试基金',
        market='CN',
        asset_type='bond',  # fund 分支取 NavService 净值（测试库无净值会算 0），bond 走 current_price 兜底
        account_name='测试账户',
        quantity=100,
        avg_price=1.0,
        current_price=1.1,
        currency='CNY',
        confirm_date=date(2024, 1, 1),
    )
    make_transaction(position_id=pos.id, ledger_id=pos.ledger_id, txn_type='buy', quantity=100, price=1.0)
    db.commit()  # make_transaction 只 flush；工具用独立会话，必须提交才可见

    r = ToolExecutor.run('get_portfolio_performance', {})
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['total_invested'] == 100.0
    assert r['data']['current_value'] == 110.0


# ── list_position_pnl（#1711 逐持仓盈亏明细） ──
def test_position_pnl_empty_db():
    r = ToolExecutor.run('list_position_pnl', {})
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['items'] == []
    assert r['data']['count'] == 0


def test_position_pnl_multi_position_sorted(db, make_position):
    """多持仓：盈亏额/盈亏率数值正确，且按盈亏率降序（无成本价 None 沉底）。"""
    make_position(
        symbol='110011',
        name='赚的基金',
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.1,
        account_name='测试账户',
    )
    make_position(
        symbol='600000',
        name='亏的股票',
        asset_type='stock',
        quantity=50,
        avg_price=2.0,
        current_price=1.8,
        account_name='测试账户',
    )
    make_position(
        symbol='000001',
        name='无成本价',
        asset_type='stock',
        quantity=10,
        current_price=3.0,
        account_name='测试账户',
    )

    r = ToolExecutor.run('list_position_pnl', {})
    assert r['status'] == 'success', r.get('msg')
    items = r['data']['items']
    assert r['data']['count'] == 3
    # 排序：+10% 在前、-10% 在后、无成本价（None）沉底
    assert [it['pnl_rate'] for it in items] == [10.0, -10.0, None]

    top = items[0]
    assert top['symbol'] == '110011'
    assert top['cost'] == 100.0  # 1.0 元 × 100 份
    assert top['market_value'] == 110.0
    assert top['pnl'] == 10.0  # (1.1 − 1.0) × 100
    assert top['pnl_rate'] == 10.0

    loser = items[1]
    assert loser['symbol'] == '600000'
    assert loser['pnl'] == -10.0
    assert loser['pnl_rate'] == -10.0

    no_cost = items[2]
    assert no_cost['symbol'] == '000001'
    assert no_cost['pnl'] == 0.0
    assert no_cost['pnl_rate'] is None


def test_position_pnl_single_position(db, make_position):
    """单持仓：打平（现价 == 成本价）时盈亏与盈亏率均为 0，不是 None。"""
    make_position(
        symbol='510300',
        name='打平ETF',
        asset_type='etf',
        quantity=200,
        avg_price=4.0,
        current_price=4.0,
        account_name='测试账户',
    )
    r = ToolExecutor.run('list_position_pnl', {})
    assert r['status'] == 'success', r.get('msg')
    items = r['data']['items']
    assert len(items) == 1
    assert items[0]['pnl'] == 0.0
    assert items[0]['pnl_rate'] == 0.0


def test_position_pnl_family_isolated(db, make_position):
    """user 隔离：server_ctx 注入 family_id=1 时，他人（family_id=2）持仓不可见。"""
    make_position(
        symbol='110022',
        name='别人家的',
        family_id=2,
        quantity=100,
        avg_price=1.0,
        current_price=2.0,
    )
    r = ToolExecutor.run('list_position_pnl', {}, server_ctx={'family_id': 1})
    assert r['status'] == 'success', r.get('msg')
    assert r['data']['items'] == []
    assert r['data']['count'] == 0


# ── P1：服务端权威值覆盖候选值 ──
def test_server_ctx_overrides_frontend_candidate(monkeypatch):
    captured = {}

    def spy(params):
        captured.update(params)
        return {'ok': True}

    monkeypatch.setitem(tools_mod._FUNCTION_MAP, 'get_assets_overview', spy)
    r = ToolExecutor.run('get_assets_overview', {'family_id': 999}, server_ctx={'family_id': 1})
    assert r['status'] == 'success'
    assert captured['family_id'] == 1  # 权威值赢，候选值 999 不进工具


def test_server_ctx_skips_undeclared_key():
    # get_fund_nav 未声明 family_id：server_ctx 带了也不注入（否则会触发未知参数）
    r = ToolExecutor.run('get_fund_nav', {'fund_codes': ['110011']}, server_ctx={'family_id': 1})
    assert r['status'] == 'success'


def test_frontend_family_id_rejected_on_scopeless_tool():
    # 反向堵死：对未声明 family_id 的工具塞 family_id → 未知参数 fail-closed
    r = ToolExecutor.run('get_fund_nav', {'fund_codes': ['110011'], 'family_id': 999})
    assert r['status'] == 'error'
    assert '未知参数' in r['msg']


# ── schema 校验补强：类型与 enum ──
def test_type_check_rejects_string_family_id():
    r = ToolExecutor.run('get_assets_overview', {'family_id': 'abc'})
    assert r['status'] == 'error'
    assert '类型' in r['msg']


def test_enum_branch_via_probe(monkeypatch):
    """enum 校验分支（现网工具已无 enum 参数，用探针元信息钉住该路径）。"""
    monkeypatch.setitem(tools_mod._FUNCTION_MAP, '_enum_probe', lambda p: {'ok': True})
    base_meta = list(tools_mod.TOOLS_METADATA)
    monkeypatch.setattr(
        tools_mod,
        'TOOLS_METADATA',
        base_meta
        + [
            {
                'name': '_enum_probe',
                'description': 'probe',
                'parameters': {'type': 'object', 'properties': {'mode': {'type': 'string', 'enum': ['a', 'b']}}},
            }
        ],
    )
    assert ToolExecutor.run('_enum_probe', {'mode': 'a'})['status'] == 'success'
    r = ToolExecutor.run('_enum_probe', {'mode': 'z'})
    assert r['status'] == 'error'
    assert '不在允许值' in r['msg']


# ── S1-C：[agent.tool] 必留痕（成功 ok / 失败 fail 都要能按 tag 捞出来） ──
def _capture_run(name, params):
    captured = []
    hid = logger.add(lambda m: captured.append(str(m)), level='INFO')
    try:
        result = ToolExecutor.run(name, params)
    finally:
        logger.remove(hid)
    return result, ''.join(captured)


def test_run_leaves_log_trace_on_success():
    r, joined = _capture_run('get_assets_overview', {})
    assert r['status'] == 'success'
    assert '[agent.tool] ok name=get_assets_overview' in joined
    assert 'elapsed=' in joined


def test_run_leaves_log_trace_on_failure():
    r, joined = _capture_run('get_fund_nav', {'fund_codes': ['bad']})
    assert r['status'] == 'error'
    assert '[agent.tool] fail name=get_fund_nav' in joined
    assert 'err=' in joined
