# -*- coding: utf-8 -*-
"""`group_by=account` 分组键的回归网。

## 锁的是什么

分组结果是**以账户 ID 为键的字典**，经 `flask.jsonify(..., sort_keys=True)` 序列化。

#2372 之前键是 `account_name`（**可编辑快照**），两个问题：
- 真库存在重名账户（支付宝×2 / 天天基金×2），同名账户的持仓会被**并成一组**，
  账户改名后前端按名回查整组落空；
- `Position.account_name` 允许 NULL，`None` 作字典键不报错，但排序时 `str` 与
  `None` 不可比 ⇒ `TypeError: '<' not supported between 'str' and 'NoneType'`
  ⇒ 整个列表接口 500。

改用 ledger_id（真外键）作键后两点一并解决：
- 键与账户一一对应，改名 / 重名都不影响——行内仍带 ledger_id + account_name 供展示；
- 未归档持仓（``ledger_id IS NULL``）归哨兵键 ``'unfiled'``，None 根本不会成为键。
"""

from app.domains.ledgers.models import Ledger


def _make_ledger(db, name):
    """建账户行并返回 id（**不去重**：重名账户是 #2372 的核心场景）。"""
    ledger = Ledger(name=name, ledger_type='bank', family_id=1)
    db.add(ledger)
    db.flush()
    return ledger.id


def test_group_by_account_key_is_ledger_id_not_name(client, db, make_position):
    """重名账户必须分成两组——键用 ledger_id，不按 account_name 合并（#2372）。"""
    ledger_a = _make_ledger(db, '支付宝')
    ledger_b = _make_ledger(db, '支付宝')  # 真库存在重名账户
    db.commit()

    make_position(symbol='000601', name='基金A', asset_type='fund', account_name='支付宝', ledger_id=ledger_a)
    make_position(symbol='000601', name='基金B', asset_type='fund', account_name='支付宝', ledger_id=ledger_b)
    db.commit()

    resp = client.get('/api/positions/?group_by=account')

    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()['data']
    assert sorted(data.keys()) == sorted([str(ledger_a), str(ledger_b)])
    assert [p['name'] for p in data[str(ledger_a)]] == ['基金A']
    assert [p['name'] for p in data[str(ledger_b)]] == ['基金B']


def test_group_by_account_unfiled_sentinel_key(client, db, make_position):
    """未归档持仓归哨兵键 ``'unfiled'``——None 绝不能成为字典键（sort_keys TypeError）。"""
    # 显式传 ledger_id=None，避免夹具按 account_name 自动建账本
    make_position(symbol='519771', name='测试基金', asset_type='fund', account_name=None, ledger_id=None)

    resp = client.get('/api/positions/?group_by=account')

    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()['data']
    assert list(data.keys()) == ['unfiled']
    # 行内快照仍在（供展示）：键才是关联依据
    assert data['unfiled'][0]['symbol'] == '519771'
