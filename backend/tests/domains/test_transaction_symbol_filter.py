# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/12
# File : test_transaction_symbol_filter.py

"""交易流水按 symbol 过滤（#2104 · 产品详情页「交易记录」区块）。

口径复用 `symbol_scope` 的「同一产品」判定（与持仓列表 #1966 / 持有年化 #1972 一致）：
`transactions.symbol` 是字面量快照、无 norm 列，先经持仓侧归一匹配收集真实写法再 `IN`，
故 `SZ000001` 与 `000001.SZ` 视为同一只产品。
"""

from tests.domains.test_positions import _get, _post


def test_symbol_filter_hits_matching_transactions(client):
    _post(
        client,
        '/api/positions/',
        {
            'symbol': 'SZ000001',
            'name': '平安银行',
            'type': 'stock',
            'market': 'CN_A',
            'account_name': '测试账户',
            'quantity': 100,
            'avg_price': 10,
            'trade_date': '2026-01-01',
        },
    )
    _post(
        client,
        '/api/positions/',
        {
            'symbol': 'SH600519',
            'name': '贵州茅台',
            'type': 'stock',
            'market': 'CN_A',
            'account_name': '测试账户',
            'quantity': 100,
            'avg_price': 1500,
            'trade_date': '2026-01-01',
        },
    )
    # 查询 SZ000001 的流水
    resp = _get(client, '/api/transactions', {'symbol': 'SZ000001'})

    assert resp.status_code == 200
    rows = resp.get_json()['data']
    # 至少有一条 SZ000001 的买入流水
    assert any(t['symbol'] == 'SZ000001' for t in rows)
    # 不应出现 SH600519 的流水
    assert not any(t['symbol'] == 'SH600519' for t in rows)


def test_symbol_filter_unmatched_returns_empty(client):
    _post(
        client,
        '/api/positions/',
        {
            'symbol': 'SZ000001',
            'name': '平安银行',
            'type': 'stock',
            'market': 'CN_A',
            'account_name': '测试账户',
            'quantity': 100,
            'avg_price': 10,
            'trade_date': '2026-01-01',
        },
    )

    resp = _get(client, '/api/transactions', {'symbol': 'SZ999999'})

    assert resp.status_code == 200
    assert resp.get_json()['data'] == []


def test_symbol_filter_stored_symbol_matches(client):
    """写入侧归一后，按归一化 symbol 查询能命中。

    注意：`transactions.symbol` 是字面量快照，落库形态由写入侧 `process_buy_or_deposit`
    的 venue 归一决定（`000001.SZ` → `SZ000001`），本测试只验证「查询形态与落库形态
    一致」这条基础链路；「查询形态 ≠ 落库形态」由下方
    `test_symbol_filter_matches_varied_writings` 覆盖。
    """
    _post(
        client,
        '/api/positions/',
        {
            'symbol': '000001.SZ',
            'name': '平安银行',
            'type': 'stock',
            'market': 'CN_A',
            'account_name': '测试账户',
            'quantity': 100,
            'avg_price': 10,
            'trade_date': '2026-01-01',
        },
    )

    # 后端归一化后 symbol 为 SZ000001，按此查询
    resp = _get(client, '/api/transactions', {'symbol': 'SZ000001'})

    assert resp.status_code == 200
    rows = resp.get_json()['data']
    assert len(rows) >= 1
    assert any(t['symbol'] == 'SZ000001' for t in rows)


def test_symbol_filter_matches_varied_writings(client):
    """查询写法与流水快照写法不一致时，经 symbol_scope 两步法仍能命中（证伪测试）。

    场景：流水/持仓落库为 `SZ000001`（写入侧 venue 归一），但产品详情页 URL 传来的
    是 `000001.SZ` / 裸码等其它写法。字面量等值实现下本用例必红（假阴性显示
    「暂无交易记录」）；两步法先按持仓侧归一身份键收集真实写法再 `IN`，故应命中。
    """
    _post(
        client,
        '/api/positions/',
        {
            'symbol': 'SZ000001',
            'name': '平安银行',
            'type': 'stock',
            'market': 'CN_A',
            'account_name': '测试账户',
            'quantity': 100,
            'avg_price': 10,
            'trade_date': '2026-01-01',
        },
    )

    # 落库写法为 SZ000001，用另一种写法查询
    resp = _get(client, '/api/transactions', {'symbol': '000001.SZ'})

    assert resp.status_code == 200
    rows = resp.get_json()['data']
    assert any(t['symbol'] == 'SZ000001' for t in rows)
