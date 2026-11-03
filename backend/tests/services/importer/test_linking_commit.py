# -*- coding: utf-8 -*-
"""配对组从「解析」活到「落库」的端到端用例（#2836）。

为什么不能用纯逻辑单测代替：`parse` 与 `confirm` 是两次独立 HTTP 调用，中间隔着
一次 JSON 序列化往返。`link_group_id` / `consumed_by` 这类「解析期算出来、落库期
才用上」的字段，只要重建 record 时漏透传就会**静默丢失**——前端照样折叠、导入
照样成功，错的是「利息与税各自成孤儿」这种要查库才看得见的结果。
"""

import io

from app.domains.transactions.models import Transaction

THS_HEADER = (
    '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额'
    '\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称'
    '\t佣金\t过户费\t清算费(B股)\t币种\n'
)


def _post_ths(client, *rows: str):
    content = THS_HEADER + '\n'.join(rows)
    resp = client.post('/api/importers/parse?template=ths', data={'file': (io.BytesIO(content.encode()), 'ths.csv')})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['data']


class TestLinkGroupSurvivesConfirm:
    def test_interest_and_tax_land_in_same_group(self, client, db):
        """兑息 220 + 税 −44 落库后仍是同一组。"""
        rows = _post_ths(
            client,
            '128119\t龙大转债\t债券兑息\t0\t0\t0\t110\t220.0\t0\t0\t0\t0\t\t20260716\t龙大转债\t0\t0\t0\t人民币',
            '128119\t龙大转债\t债券兑息兑付\t0\t0\t0\t110\t-44.0\t0\t0\t0\t0\t\t20260716\t龙大转债\t0\t0\t0\t人民币',
        )
        assert rows[0]['link_group_id'], '解析阶段就该打上组：前端折叠依赖它'
        assert rows[0]['link_group_id'] == rows[1]['link_group_id']

        data = client.post('/api/importers/confirm', json=rows).get_json()['data']
        assert data['imported'] == 2

        interest = db.query(Transaction).filter_by(txn_type='dividend').one()
        tax = db.query(Transaction).filter_by(txn_type='dividend_tax').one()
        # 核心断言：组名穿过了 confirm 的重建环节，没有退化成 None
        assert interest.link_group_id
        assert interest.link_group_id == tax.link_group_id

    def test_ratio_warning_reaches_the_preview_row(self, client, db):
        """税率不符的提示要能到前端（只提示，不阻断、不拆组）。"""
        rows = _post_ths(
            client,
            '128119\t龙大转债\t债券兑息\t0\t0\t0\t110\t220.0\t0\t0\t0\t0\t\t20260716\t龙大转债\t0\t0\t0\t人民币',
            '128119\t龙大转债\t债券兑息兑付\t0\t0\t0\t110\t-44.0\t0\t0\t0\t0\t\t20260716\t龙大转债\t0\t0\t0\t人民币',
        )
        # 正常 20% 时不该有提示
        assert rows[0]['link_warning'] == ''

        rows = _post_ths(
            client,
            '113649\t丰山转债\t债券兑息\t0\t0\t0\t60\t90.0\t0\t0\t0\t0\t\t20260626\t丰山转债\t0\t0\t0\t人民币',
            '113649\t丰山转债\t债券兑息兑付\t0\t0\t0\t60\t-30.0\t0\t0\t0\t0\t\t20260626\t丰山转债\t0\t0\t0\t人民币',
        )
        assert '20%' in rows[0]['link_warning']
        assert rows[0]['link_warning'] == rows[1]['link_warning']


class TestConsumedRowIsSkipped:
    def test_share_transfer_after_redeem_is_not_booked(self, client, db):
        """兑付已清仓，随后那行「股份转出」不能再入账（双重扣份额）。

        真实交割单顺序就是兑付在前、转出在后；若不消费，第二次扣份额要么再清一次、
        要么因持仓已空降级成孤儿流水——两种都是账面上多出来的东西。
        """
        # 先建仓：110 张 @ 113 元
        buy_rows = _post_ths(
            client,
            '128119\t龙大转债\t证券买入\t110\t113.0\t12430.0\t110\t-12430.0\t0\t0\t0\t0\t\t20260105\t龙大转债\t0\t0\t0\t人民币',
        )
        client.post('/api/importers/confirm', json=buy_rows)

        rows = _post_ths(
            client,
            '128119\t龙大转债\t债券兑付\t110\t113.0\t12430.0\t0\t12430.0\t0\t0\t0\t0\t\t20260716\t龙大转债\t0\t0\t0\t人民币',
            '128119\t龙大转债\t股份转出\t110\t0\t0\t0\t0\t0\t0\t0\t0\t\t20260716\t龙大转债\t0\t0\t0\t人民币',
        )
        # 解析阶段就应标好「被消费」，让用户在预览里能看见它不会入账
        assert rows[1]['consumed_by'] == 'redeem_share_clearing'

        data = client.post('/api/importers/confirm', json=rows).get_json()['data']
        assert data['imported'] == 1, '只该有兑付一条入账'
        assert data['skipped'] == 1, '被消费的转出行计入 skipped，回执可解释'

        # 账面只有买入 + 兑付两条，没有半点儿「股份转出」的痕迹
        types = sorted(t.txn_type for t in db.query(Transaction).all())
        assert types == ['bond_redeem', 'buy']

    def test_cash_withdraw_after_redeem_is_not_consumed(self, client, db):
        """同日有兑付，但转出带着现金：那是真的把钱取走了，绝不能被吞。

        只断言「没被消费」而不走 confirm —— 带现金的取出在真实交割单里是卖出
        或银证转账，不会顶着「股份转出」这个名字出现；这条用例守的是 guard
        本身（映射或券商格式一旦变化，别把资金取出误判成兑付的副产物）。
        """
        rows = _post_ths(
            client,
            '128119\t龙大转债\t债券兑付\t110\t113.0\t12430.0\t0\t12430.0\t0\t0\t0\t0\t\t20260716\t龙大转债\t0\t0\t0\t人民币',
            '128119\t龙大转债\t股份转出\t0\t0\t0\t0\t-5000.0\t0\t0\t0\t0\t\t20260716\t龙大转债\t0\t0\t0\t人民币',
        )
        assert rows[1]['consumed_by'] == '', '带现金的取出不是兑付副产物'
