# -*- coding: utf-8 -*-
"""`group_by=account` 分组键的回归网。

## 锁的是什么

分组结果是 **以账户名为键的字典**，经 `flask.jsonify(..., sort_keys=True)` 序列化。
`Position.account_name` 允许 NULL，``None`` 作字典键不报错，但排序时 ``str`` 与 ``None``
不可比 ⇒ `TypeError: '<' not supported between instances of 'str' and 'NoneType'`，
整个列表接口 500。分组键必须是字符串，缺账户名回退为「未指定账户」
（与 `summary_service.get_account_groups` 同口径）。
"""


def test_group_by_account_none_account_name_serializes(client, db, make_position):
    """account_name 为 NULL 的持仓不应让 /api/positions/?group_by=account 崩掉。"""
    # 显式传 ledger_id=None，避免 make_position 夹具按 account_name 自动建账本
    make_position(symbol='519771', name='测试基金', asset_type='fund', account_name=None, ledger_id=None)
    make_position(symbol='000001', name='平安银行', asset_type='stock', account_name='测试账户')

    resp = client.get('/api/positions/?group_by=account')

    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()['data']
    assert '未指定账户' in data
    assert '测试账户' in data
    assert [p['symbol'] for p in data['未指定账户']] == ['519771']


def test_group_by_account_all_none_still_serializes(client, db, make_position):
    """全为 NULL 账户名时同样不崩——只有 None 一个键也会触发排序比较。"""
    make_position(symbol='519771', name='测试基金', asset_type='fund', account_name=None, ledger_id=None)

    resp = client.get('/api/positions/?group_by=account')

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert list(resp.get_json()['data'].keys()) == ['未指定账户']
