# -*- coding: utf-8 -*-
"""持仓「到期日」编辑通路测试（#931 / D121）。

背景：`positions.maturity_date` 在买入侧已放开到逆回购 + 银行理财（PR4），但**没有任何
修改入口**——账号里那条逆回购的到期日录错了，只能删了重录（等于丢流水）。本组用例钉住
「编辑」这第二条写路径：

1. 两类有语义的品类（逆回购 / 银行理财）能设、能清；
2. 其余品类 fail closed（400，不落库）——静默忽略会让「我明明设了」变成查不出的 NULL；
3. 格式非法 400，且**不覆盖**已有值；
4. 账户持仓列表把该字段下发（wire 值必须是 `YYYY-MM-DD`，否则前端日期控件读不了）。
"""

from datetime import date

import pytest


def _pos(make_position, asset_type: str, **kwargs):
    return make_position(
        symbol=kwargs.pop('symbol', 'Z7001234ABCD'),
        name=kwargs.pop('name', '朝朝宝'),
        account_name='测试账户',
        asset_type=asset_type,
        **kwargs,
    )


def _patch(client, pos, payload):
    return client.patch(f'/api/ledgers/{pos.ledger_id}/positions/{pos.id}/', json=payload)


@pytest.mark.parametrize('asset_type', ['bank_wealth', 'reverse_repo'])
def test_sets_maturity_date_for_both_semantic_types(client, make_position, asset_type):
    """逆回购（时间建模）与银行理财（仅记录）都能设到期日，回显 `YYYY-MM-DD`。"""
    pos = _pos(make_position, asset_type)
    resp = _patch(client, pos, {'maturity_date': '2027-03-01'})
    assert resp.status_code == 200
    assert resp.json['data']['maturity_date'] == '2027-03-01'


def test_rejects_maturity_date_for_fund(client, make_position):
    """基金没有到期日：400 且不落库（不是静默忽略）。"""
    pos = _pos(make_position, 'fund', symbol='110011', name='易方达中小盘')
    resp = _patch(client, pos, {'maturity_date': '2027-03-01'})
    assert resp.status_code == 400
    assert '到期日仅适用于逆回购与银行理财' in resp.json['message']
    assert pos.maturity_date is None


def test_clears_maturity_date(client, make_position):
    """清空（null）合法：填错的日期必须撤得掉，否则只能删持仓。"""
    pos = _pos(make_position, 'bank_wealth', maturity_date=date(2027, 3, 1))
    resp = _patch(client, pos, {'maturity_date': None})
    assert resp.status_code == 200
    assert resp.json['data']['maturity_date'] is None


def test_rejects_bad_format_without_touching_existing_value(client, make_position):
    """格式非法 400，且**不覆盖**已填对的日期（部分成功是最难查的形态）。"""
    pos = _pos(make_position, 'bank_wealth', maturity_date=date(2027, 3, 1))
    resp = _patch(client, pos, {'maturity_date': '2027/03/01'})
    assert resp.status_code == 400
    assert pos.maturity_date == date(2027, 3, 1)


def test_other_fields_still_editable_alongside(client, make_position):
    """到期日与配置目标同批提交：两个字段都生效（载荷不是互斥的）。"""
    pos = _pos(make_position, 'bank_wealth')
    resp = _patch(client, pos, {'maturity_date': '2027-03-01', 'allocation': 'stable'})
    assert resp.status_code == 200
    assert resp.json['data']['maturity_date'] == '2027-03-01'
    assert resp.json['data']['allocation'] == 'stable'


def test_ledger_positions_list_exposes_maturity_date(client, make_position):
    """持仓列表下发该字段：没它的话前端连「现在是哪天」都显示不出来。

    非到期日品类为 null（不是缺键）——缺键会让前端把「没设」与「品类不适用」混为一谈。
    """
    pos = _pos(make_position, 'bank_wealth', maturity_date=date(2027, 3, 1))
    fund = _pos(make_position, 'fund', symbol='110011', name='易方达中小盘')

    resp = client.get(f'/api/ledgers/{pos.ledger_id}/positions/', query_string={'page': 1, 'per_page': 20})
    assert resp.status_code == 200
    rows = {item['id']: item for item in resp.json['data']['items']}
    assert rows[pos.id]['maturity_date'] == '2027-03-01'
    assert rows[fund.id]['maturity_date'] is None
