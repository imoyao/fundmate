# -*- coding: utf-8 -*-
"""持仓「产品名称 / 登记编码」编辑通路测试（#931 / D121）。

背景：银行理财没有中心产品目录（D121），`symbol`（登记编码）与 `name`（产品名）
都是**用户手填的**。而首次录入只有一个输入框，把产品名填进编码栏、或者编码打错一位，
都没有任何地方能改——这条用例组钉住第二个写路径，以及它最容易漏的那一半：

- `symbol` 不只是展示文本。它是持仓身份（`uq_positions_ledger_symbol_norm`），也是
  多处读侧 `Transaction.symbol == position.symbol` 的字面量匹配键。只改持仓不改流水，
  那些流水就指向一个不存在的标的，成本与已实现盈亏静默失联。
- 基金 / 股票的名称来自行情名录（外部真相源的投影），改它只会让持仓与名录对不上，
  故 fail closed 到 400，而不是静默忽略（静默忽略会让用户以为改成功了）。
"""

import pytest

from app.domains.transactions.models import Transaction


def _bank_wealth(make_position, **kwargs):
    return make_position(
        symbol=kwargs.pop('symbol', 'Z7001234ABCD'),
        name=kwargs.pop('name', '朝朝宝'),
        account_name='测试账户',
        asset_type='bank_wealth',
        **kwargs,
    )


def _patch(client, pos, payload):
    return client.patch(f'/api/ledgers/{pos.ledger_id}/positions/{pos.id}/', json=payload)


def test_renames_symbol_and_syncs_transactions(client, db, make_position, make_transaction):
    """改编码：持仓与它名下流水的快照一起改（否则成本/回款失联）。"""
    pos = _bank_wealth(make_position)
    txn = make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        symbol='Z7001234ABCD',
        position_name='朝朝宝',
    )
    db.commit()  # 夹具只 flush：不提交的话写锁还在，API 的会话会 database is locked

    resp = _patch(client, pos, {'symbol': 'Z7009999WXYZ'})

    assert resp.status_code == 200
    assert resp.json['data']['symbol'] == 'Z7009999WXYZ'
    db.expire_all()
    assert pos.symbol == 'Z7009999WXYZ'
    # 身份键随编码重算（mapper 事件），否则唯一约束对这条静默失效
    assert pos.symbol_norm == 'NO_VENUE:Z7009999WXYZ'
    # 批量 update 不触发 mapper 事件：流水侧的身份键必须显式写对
    row = db.query(Transaction).filter(Transaction.id == txn.id).one()
    assert row.symbol == 'Z7009999WXYZ'
    assert row.symbol_norm == 'NO_VENUE:Z7009999WXYZ'


def test_symbol_is_normalized_to_upper_without_spaces(client, db, make_position):
    """空白 + 小写归一到大写：同一编码两种写法会绕过唯一索引长出两行（#1662 复发）。"""
    pos = _bank_wealth(make_position)
    resp = _patch(client, pos, {'symbol': '  z7001234abcd  '})
    assert resp.status_code == 200
    assert resp.json['data']['symbol'] == 'Z7001234ABCD'
    db.expire_all()
    assert pos.symbol == 'Z7001234ABCD'


def test_case_only_change_does_not_trip_duplicate_check(client, db, make_position):
    """只改大小写时身份没变，不能自己跟自己撞「已有同编码持仓」。"""
    pos = _bank_wealth(make_position, symbol='z7001234abcd')
    resp = _patch(client, pos, {'symbol': 'Z7001234ABCD'})
    assert resp.status_code == 200
    db.expire_all()
    assert pos.symbol == 'Z7001234ABCD'


def test_rejects_symbol_already_taken_in_same_ledger(client, db, make_position):
    """同账户重复编码 400，且原值不动——不能等到 commit 时炸唯一索引（那是 500）。"""
    first = _bank_wealth(make_position, symbol='Z7001234ABCD')
    second = _bank_wealth(make_position, symbol='Z7009999WXYZ', name='稳赢 90 天')

    resp = _patch(client, second, {'symbol': 'Z7001234ABCD'})

    assert resp.status_code == 400
    assert '已有编码 Z7001234ABCD' in resp.json['message']
    db.expire_all()
    assert second.symbol == 'Z7009999WXYZ'
    assert first.symbol == 'Z7001234ABCD'


def test_rejects_empty_symbol(client, make_position):
    """编码是身份，不能清空；产品名可以。"""
    pos = _bank_wealth(make_position)
    resp = _patch(client, pos, {'symbol': '   '})
    assert resp.status_code == 400
    assert '登记编码不能为空' in resp.json['message']


@pytest.mark.parametrize('asset_type,symbol', [('fund', '110011'), ('stock', 'SZ000001')])
def test_rejects_identity_edit_for_catalog_types(client, make_position, asset_type, symbol):
    """基金 / 股票的名称与编码是行情名录的投影，用户改它只会与名录对不上。"""
    pos = make_position(
        symbol=symbol,
        name='名录里的名字',
        account_name='测试账户',
        asset_type=asset_type,
    )
    resp = _patch(client, pos, {'name': '我自己起的名字'})
    assert resp.status_code == 400
    assert '仅银行理财可修改产品名称与登记编码' in resp.json['message']


def test_renames_name_only_leaving_symbol_alone(client, db, make_position):
    """改名不动编码：两个字段可单独提交（只填了一个输入框的用户只改那一项）。"""
    pos = _bank_wealth(make_position)
    resp = _patch(client, pos, {'name': '  招银理财朝朝宝  '})
    assert resp.status_code == 200
    assert resp.json['data']['name'] == '招银理财朝朝宝'
    db.expire_all()
    assert pos.symbol == 'Z7001234ABCD'


def test_clearing_name_falls_back_to_symbol(client, db, make_position):
    """名字清空 = 回落到显示编码（空串会让展示层两种空值各判一次）。"""
    pos = _bank_wealth(make_position)
    resp = _patch(client, pos, {'name': '   '})
    assert resp.status_code == 200
    db.expire_all()
    assert pos.name is None
