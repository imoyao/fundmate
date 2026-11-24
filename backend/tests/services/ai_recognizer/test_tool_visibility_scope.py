# -*- coding: utf-8 -*-
"""#3246 后半：agent 剩余 6 个涉及账户的工具接上可见性（两类收口）.

两类必须分开测，因为**它们的正确性判据不同**：

- **集合型**（XIRR / 交易行为 / 自选）：输出是可定义在任意账户集合上的统计，把可见账户
  当成一个子组合后分子分母同口径，所以过滤后照常出数。这里断言「不可见账户的流水与
  市值确实没进来」。
- **门控型**（基准对比 / 收益归因 / 调仓参考）：输出语义绑死「家庭全量」——区间收益占全家
  的比例、Σ 可加性由引擎构造保证、行业穿透走 `build_penetration(db, family_id)`。部分可见
  时既不能原样给（数值里混着看不见的钱），也不能在工具层过滤后重算（另起一套账），
  故 `unavailable_reason='partial_visibility'`。

还有一条容易忽略的：**「传了集合」不等于「部分可见」**。普通成员恰好拥有全部账户时
可见集合是全集，门控不能触发——否则这类账号会莫名失去所有指标。
"""

import datetime as dt

from app.domains.ledgers.models import Ledger
from app.services.ai_recognizer.tools import ToolExecutor
from app.services.ai_recognizer.visibility_gate import partial_visibility_payload
from app.services.performance.calculators import calculate_portfolio_xirr

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


# ── 门控本身的三态 ─────────────────────────────────────────────────────────


def test_gate_is_none_when_identity_unknown(db):
    """`None` = 判定不出主体（MCP / 离线），不筛 ⇒ 照常算."""
    assert partial_visibility_payload(db, 1, None) is None


def test_gate_is_none_when_all_accounts_visible(db):
    """可见集合是全集时不能判成部分可见——普通成员拥有全部账户就会走到这里."""
    shared_id, private_id = _two_ledgers(db)
    assert partial_visibility_payload(db, 1, {shared_id, private_id}) is None


def test_gate_blocks_strict_subset_and_reports_counts(db):
    shared_id, private_id = _two_ledgers(db)
    blocked = partial_visibility_payload(db, 1, {shared_id})
    assert blocked is not None
    assert blocked['available'] is False
    assert blocked['unavailable_reason'] == 'partial_visibility'
    assert blocked['visible_account_count'] == 1
    assert blocked['hidden_account_count'] == 1
    assert blocked['hint'], '必须带「怎么办」，否则模型只会复述不可用'


def test_gate_blocks_empty_set(db):
    """空集不是特例：一个账户都看不见 ⇒ 隐藏数等于全部."""
    _two_ledgers(db)
    blocked = partial_visibility_payload(db, 1, set())
    assert blocked is not None
    assert blocked['visible_account_count'] == 0
    assert blocked['hidden_account_count'] == 2


def test_gate_ignores_ids_from_other_families(db):
    """别的家庭的 id 混进来不能算「可见」——否则越权 id 就能把门开大."""
    shared_id, _ = _two_ledgers(db)
    blocked = partial_visibility_payload(db, 1, {shared_id, 9999})
    assert blocked is not None
    assert blocked['visible_account_count'] == 1, '9999 不属于本家庭，不计入可见'


# ── 集合型：XIRR ────────────────────────────────────────────────────────────
#
# 这一组直接调服务函数并共用 `db`：XIRR 的现金流要求流水带 `confirm_date`，而
# `POST /api/positions/` 在未显式传确认日时只写 `trade_date`（confirm_date 落 NULL），
# 现金流会被引擎整批跳过（实测 `cashflow_count=0`）。走 HTTP 造不出可用的现金流，
# 只能显式给确认日；而显式造的数据又只有同一个 session 读得到（`db` fixture 是
# `_RoutingSession`，工具内部另开 session 会落到别的域）。所以这一组测的是
# 「服务层的 `visible_ids` 是否真的收窄了两条取数」，参数链另有 HTTP 级用例覆盖。


def _seed_stock(db, make_position, make_transaction, ledger_id, symbol, price):
    pos = make_position(
        symbol=symbol,
        name=f'标的{symbol}',
        quantity=100,
        avg_price=price,
        current_price=price,
        asset_type='stock',
        family_id=1,
        ledger_id=ledger_id,
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=ledger_id,
        txn_type='buy',
        quantity=100,
        price=price,
        confirm_date=dt.date(2026, 1, 5),
        symbol=symbol,
    )
    db.commit()
    return pos


def test_portfolio_xirr_excludes_invisible_ledger(db, make_position, make_transaction):
    shared_id, private_id = _two_ledgers(db)
    _seed_stock(db, make_position, make_transaction, shared_id, '000001', 1.0)  # 100 元
    _seed_stock(db, make_position, make_transaction, private_id, '000002', 5.0)  # 500 元

    partial = calculate_portfolio_xirr(db, family_id=1, visible_ids={shared_id})
    assert partial['total_invested'] == 100.0, '不可见账户的本金不能进 XIRR 分母'
    assert partial['cashflow_count'] == 1


def test_portfolio_xirr_without_visible_ids_keeps_full_scope(db, make_position, make_transaction):
    """`visible_ids=None` ⇒ 与改造前逐字一致（家庭全量）."""
    shared_id, private_id = _two_ledgers(db)
    _seed_stock(db, make_position, make_transaction, shared_id, '000001', 1.0)
    _seed_stock(db, make_position, make_transaction, private_id, '000002', 5.0)

    full = calculate_portfolio_xirr(db, family_id=1)
    assert full['total_invested'] == 600.0
    assert full['cashflow_count'] == 2


# ── 集合型：交易行为 ────────────────────────────────────────────────────────


def test_trading_behavior_excludes_invisible_ledger(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')
    _buy(client, private_id, '000002')
    _buy(client, private_id, '000003')

    r = ToolExecutor.run('get_trading_behavior', {}, {'family_id': 1, 'visible_ledger_ids': [shared_id]})
    assert r['status'] == 'success'
    assert r['data']['trading']['buy_count'] == 1, '只该计入可见账户那一笔买入'
    assert r['data']['trading']['total_count'] == 1


# ── 集合型：自选摘要（同一标的跨账户合计） ─────────────────────────────────


def test_watchlist_overview_market_value_excludes_invisible_ledger(client, db):
    """同一只票在两个账户都有仓位：合计市值必须只含可见账户的那一半."""
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001', price=1.0, quantity=100)  # 100 元
    _buy(client, private_id, '000001', price=1.0, quantity=100)  # 同一标的再 100 元

    r = ToolExecutor.run('get_watchlist_overview', {}, {'family_id': 1, 'visible_ledger_ids': [shared_id]})
    assert r['status'] == 'success'
    rows = [item for item in r['data']['items'] if item['symbol'] == 'SZ000001']
    assert rows, '买入即入自选：应有该标的'
    assert rows[0]['position_market_value'] == 100.0, '过滤前是 200，泄露的正是这 100'


# ── 门控型：三个工具在部分可见时明说不可用 ─────────────────────────────────


def test_benchmark_comparison_blocked_on_partial_visibility(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')

    r = ToolExecutor.run('get_portfolio_vs_benchmark', {}, {'family_id': 1, 'visible_ledger_ids': [shared_id]})
    assert r['status'] == 'success'
    assert r['data']['available'] is False
    assert r['data']['unavailable_reason'] == 'partial_visibility'


def test_return_attribution_blocked_on_partial_visibility(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')

    r = ToolExecutor.run('get_return_attribution', {}, {'family_id': 1, 'visible_ledger_ids': [shared_id]})
    assert r['status'] == 'success'
    assert r['data']['available'] is False
    assert r['data']['unavailable_reason'] == 'partial_visibility'
    assert 'items' not in r['data'], '不能给一份过滤过的 items 让模型自己去凑合计'


def test_rebalance_reference_blocked_on_partial_visibility(client, db):
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')

    r = ToolExecutor.run('get_rebalance_reference', {}, {'family_id': 1, 'visible_ledger_ids': [shared_id]})
    assert r['status'] == 'success'
    assert r['data']['available'] is False
    assert r['data']['unavailable_reason'] == 'partial_visibility'


def test_rebalance_reference_runs_when_all_accounts_visible(client, db):
    """全可见时门控不触发：不许因为「传了集合」就把指标拿掉."""
    shared_id, private_id = _two_ledgers(db)
    _buy(client, shared_id, '000001')

    r = ToolExecutor.run('get_rebalance_reference', {}, {'family_id': 1, 'visible_ledger_ids': [shared_id, private_id]})
    assert r['status'] == 'success'
    assert r['data'].get('unavailable_reason') != 'partial_visibility'
