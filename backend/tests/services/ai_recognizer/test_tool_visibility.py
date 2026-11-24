# -*- coding: utf-8 -*-
"""#3246 第三段 / D127：agent 工具的可见性收口（`server_ctx.visible_ledger_ids`）.

两条入口的语义必须分开，这里各钉一条：

- **HTTP 路径必注入**（`domains/agent/views.py`）—— 工具必须按可见账户取数；
- **MCP / 离线路径没有身份**（只有 `family_id` 环境变量）—— 缺键时「不筛」，
  与改造前逐字一致。若把缺键读成空集，本地 agent 会突然什么数据都拿不到（故障不是安全）。

另一个必须钉的是 **`visible_ledger_ids` 不进 schema**：它是授权结果，模型若能填一句
就等于自己发牌。所以走 `_INTERNAL_CTX_KEYS` 强制注入 + 校验放行。
"""

from app.domains.ledgers.models import Ledger
from app.services.ai_recognizer import tools as tools_mod
from app.services.ai_recognizer.tools import ToolExecutor

OTHER_USER_ID = 2


def _ledger(db, name, visibility='shared', owner_user_id=None):
    row = Ledger(name=name, ledger_type='bank', family_id=1, visibility=visibility, owner_user_id=owner_user_id)
    db.add(row)
    db.commit()
    return row.id


def _buy(client, ledger_id, symbol, price=1.0, quantity=100):
    resp = client.post(
        '/api/positions/',
        json={
            'symbol': symbol,
            'name': f'标的{symbol}',
            'type': 'stock',
            'market': 'CN_A',
            'ledger_id': ledger_id,
            'quantity': quantity,
            'avg_price': price,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['data']


def _two_ledgers(db):
    shared_id = _ledger(db, '家庭共享')
    private_id = _ledger(db, '别人的私房钱', visibility='private', owner_user_id=OTHER_USER_ID)
    return shared_id, private_id


# ── 上下文注入（不依赖数据） ────────────────────────────────────────────────


def test_internal_key_is_injected_even_though_schema_omits_it():
    """`visible_ledger_ids` 不在任何工具 schema 里，但仍要能被服务端注入."""
    merged = tools_mod.apply_server_context(
        'get_assets_overview', {'family_id': 999}, {'family_id': 1, 'visible_ledger_ids': [1, 2]}
    )
    assert merged['family_id'] == 1, 'schema 声明的键照旧被权威值覆盖'
    assert merged['visible_ledger_ids'] == [1, 2]


def test_internal_key_is_accepted_by_validation():
    """校验必须放行内部键，否则注入即报「未知参数」."""
    tools_mod._validate_params('get_assets_overview', {'family_id': 1, 'visible_ledger_ids': [1]})


def test_model_supplied_visible_ids_are_overridden_or_rejected():
    """模型/前端自己塞这个键：要么被权威值覆盖，要么当未知参数拒绝——两路都堵."""
    merged = tools_mod.apply_server_context(
        'get_assets_overview', {'visible_ledger_ids': [666]}, {'visible_ledger_ids': [1]}
    )
    assert merged['visible_ledger_ids'] == [1]


def test_absent_key_means_no_filter():
    """缺键 = 判定不出主体（MCP/离线），不筛；空集 = 什么都看不见，两者必须分开."""
    assert tools_mod._server_visible_ids({}) is None
    assert tools_mod._server_visible_ids({'visible_ledger_ids': []}) == set()


# ── 两个工具的实际取数 ──────────────────────────────────────────────────────


def test_assets_overview_respects_visible_ids(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001', price=1.0)  # 100 元
    _buy(client, private_id, '000002', price=5.0)  # 500 元

    r = ToolExecutor.run('get_assets_overview', {}, {'family_id': 1, 'visible_ledger_ids': [shared_id]})
    assert r['status'] == 'success'
    data = r['data']
    assert data['total_assets_cny'] == 100.0, 'agent 看到的总额必须是可见口径'
    assert data['family_scope']['total_assets_cny'] == 600.0, 'D127：家庭对照随工具一起下发'
    assert data['family_scope']['hidden_account_count'] == 1


def test_assets_overview_without_visible_ids_keeps_full_scope(client, db):
    """MCP/离线路径不注入 ⇒ 与改造前完全一致（家庭全量、无对照块）."""
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001', price=1.0)
    _buy(client, private_id, '000002', price=5.0)

    r = ToolExecutor.run('get_assets_overview', {}, {'family_id': 1})
    assert r['data']['total_assets_cny'] == 600.0
    assert r['data']['family_scope'] is None


def test_position_pnl_hides_invisible_ledger(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')
    _buy(client, private_id, '000002', price=5.0)

    r = ToolExecutor.run('list_position_pnl', {}, {'family_id': 1, 'visible_ledger_ids': [shared_id]})
    assert r['status'] == 'success'
    symbols = {item['symbol'] for item in r['data']['items']}
    assert symbols == {'SZ000001'}
