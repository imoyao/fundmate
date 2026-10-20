# -*- coding: utf-8 -*-
"""基金转换提交（P1）落库测试。

对应设计文档 docs/working-notes/fund-conversion-design-2026-10-17.md §8 P1 验收：
转出持仓减、转入持仓增、两条流水同 link_group_id、资产总额守恒（±费用）、
XIRR 不异常；外加退款腿（类现金/账户现金）、垫资拦截、幂等重复提交。

数字口径与 test_conversion_estimate.py 主用例一致：
转出 1000 份 @1.0、赎回费 13.50、补差费 1.38、净额 985.12、转入 @2.0 → 492.56 份。
"""

import json
from datetime import date, timedelta

import pytest

from app.core.constants import CASH_SYMBOL
from app.core.exceptions import SBException
from app.core.money import Money
from app.domains.funds.models import DailyWorth, FeeRatio, Fund, PurchaseRule, RedeemRule
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.conversion_service import ConversionService

TRADE_DATE = date(2026, 10, 15)
BUY_CONFIRM_DATE = TRADE_DATE - timedelta(days=3)
IDEMPOTENCY_KEY = 'a' * 32


def _seed_fund(db, code, name, *, purchase_rate=None, redeem_rules=None, fund_type_id=None):
    """建基金行 + 费率阶梯。

    规则行必须**复用**：``purchase_rules`` / ``redeem_rules`` 是全局区间表，生产侧一律走
    ``FundService._get_or_create_*``，同一区间只有一行；``uq_purchase_rules_quota`` /
    ``uq_redeem_rules_range``（2026-10-18）把这条契约落到了数据库层。夹具若给每只基金
    各建一份同样的区间行，多只基金的用例就会撞唯一约束——那说明夹具不反映生产口径。
    """
    fund = Fund(fund_code=code, name=name, fund_type_id=fund_type_id)
    db.add(fund)
    db.flush()
    if purchase_rate is not None:
        rule = db.query(PurchaseRule).filter(
            PurchaseRule.start_quota == 0, PurchaseRule.end_quota.is_(None)
        ).first() or PurchaseRule(start_quota=0, end_quota=None)
        db.add(rule)
        db.flush()
        db.add(FeeRatio(fund_code=code, fee_type='purchase', rate=purchase_rate, purchase_rule_id=rule.id))
    for start_day, end_day, rate in redeem_rules or []:
        rule = db.query(RedeemRule).filter(
            RedeemRule.start_day == start_day, RedeemRule.end_day == end_day
        ).first() or RedeemRule(start_day=start_day, end_day=end_day)
        db.add(rule)
        db.flush()
        db.add(FeeRatio(fund_code=code, fee_type='redeem', rate=rate, redeem_rule_id=rule.id))
    db.commit()
    return fund


def _seed_two_funds(db):
    _seed_fund(db, '000001', '转出基金', purchase_rate=0.001, redeem_rules=[(0, 7, 0.015), (7, None, 0.0)])
    _seed_fund(db, '000002', '转入基金', purchase_rate=0.015, redeem_rules=[(0, 7, 0.015), (7, None, 0.0)])
    db.add(DailyWorth(fund_code='000001', date=TRADE_DATE, unit_nav=1.0))
    db.add(DailyWorth(fund_code='000002', date=TRADE_DATE, unit_nav=2.0))
    db.commit()


def _make_out_position(db, make_position, make_transaction, *, quantity=1000, avg_price=0.9):
    pos = make_position(
        symbol='000001',
        name='转出基金',
        asset_type='fund',
        account_name='转换测试账户',
        quantity=quantity,
        avg_price=avg_price,
        current_price=1.0,
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=quantity,
        price=avg_price,
        confirm_date=BUY_CONFIRM_DATE,
        trade_date=BUY_CONFIRM_DATE,
        symbol='000001',
    )
    return pos


def _bind_money_fund(db, ledger_id):
    """给账户绑定类现金产品（转换退款腿 money_fund 模式的前提）。"""
    fund = _seed_fund(db, '000198', '测试货基')
    ledger = db.get(Ledger, ledger_id)
    ledger.linked_money_fund_id = fund.id
    db.commit()
    return fund


def _submit(db, pos, **kwargs):
    params = {
        'out_position_id': pos.id,
        'in_symbol': '000002',
        'idempotency_key': IDEMPOTENCY_KEY,
        'family_id': 1,
        'trade_date': TRADE_DATE,
    }
    params.update(kwargs)
    return ConversionService.submit_conversion(db, **params)


def _group_txns(db):
    """转换组内的流水（排除 FIFO 试算用的历史买入批次）。"""
    return db.query(Transaction).filter_by(link_group_id=IDEMPOTENCY_KEY).order_by(Transaction.id).all()


def test_submit_two_legs_paired_and_conserved(db, make_position, make_transaction):
    """双基金落库：两腿同组、持仓一减一增、资产守恒（差 = 费用）。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    result = _submit(db, pos)

    # 转出持仓清空：行保留但标记 cleared（#2343 清仓不删行），不再出现在当前持仓视图
    out_pos = db.query(Position).filter_by(symbol='000001').first()
    assert out_pos is not None
    assert out_pos.id == pos.id
    assert out_pos.ownership_status == 'cleared'
    assert Money.min_unit_to_shares(out_pos.quantity) == 0
    assert out_pos.cleared_at is not None
    # 转入持仓建立，份额 4 位入库（985.12 / 2.0）
    in_pos = db.query(Position).filter_by(symbol='000002').first()
    assert in_pos is not None
    assert Money.min_unit_to_shares(in_pos.quantity) == 492.56
    assert in_pos.ledger_id == pos.ledger_id
    # #2406：转入腿必须显式带 name / market / account_name 三张展示快照。
    # 历史缺陷（#2406 本体）：in_data 只传 symbol，name 退回 6 位编码、market 落
    # NULL（presenter 兜 'UNKNOWN' → 前端「未知资产」）、account_name 落 NULL
    # （PR #2404 已修）。这条断言就是验收标准「持仓显示基金名而非编码」的回归网。
    assert in_pos.name == '转入基金'
    assert in_pos.market == 'CN_A'
    assert in_pos.account_name == '转换测试账户'

    txns = _group_txns(db)
    assert len(txns) == 2  # 无自动申购孤儿流水（§4.4.7）
    out_txn, in_txn = txns
    assert out_txn.txn_type == 'sell' and in_txn.txn_type == 'buy'
    assert out_txn.link_group_id == in_txn.link_group_id == IDEMPOTENCY_KEY
    # 费用只记 OUT 腿；IN 腿 fee=0、金额为净额
    assert out_txn.fee == 1488
    assert in_txn.fee == 0
    assert in_txn.amount == 98512
    # #2406：转入腿流水的 position_name 同源自 name 快照（历史缺传 → 交易列表「未知资产」）
    assert in_txn.position_name == '转入基金'
    # 已实现盈亏落 OUT 腿
    assert out_txn.realized_pnl == 8512
    # extra.conversion 元数据：同组号、角色互为对手方
    out_extra = json.loads(out_txn.extra)['conversion']
    in_extra = json.loads(in_txn.extra)['conversion']
    assert out_extra['group_no'] == in_extra['group_no']
    assert out_extra['role'] == 'out' and in_extra['role'] == 'in'
    assert out_extra['counter_symbol'] == '000002' and in_extra['counter_symbol'] == '000001'
    assert out_extra['fee_breakdown'] == {'redeem': 13.5, 'compensate': 1.38}
    # 幂等哈希按 leg 角色派生
    assert out_txn.import_hash == f'{IDEMPOTENCY_KEY}#conv-out'
    assert in_txn.import_hash == f'{IDEMPOTENCY_KEY}#conv-in'

    # 资产守恒：转入持仓市值 − 转出持仓原市值 = −费用（分，精确相等）
    in_market = Money.multiply_price_quantity(in_pos.current_price, in_pos.quantity)
    assert in_market - 100000 == -1488

    assert result['status'] == 'pending'
    assert result['group_no'].startswith('C20261015')
    assert result['in']['quantity'] == 492.56
    assert result['warnings'] == []


def test_submit_all_out_uses_exact_position_shares(db, make_position, make_transaction):
    """全部转出按持仓 4 位精确值，不受 2 位录入精度限制（D8）。"""
    _seed_two_funds(db)
    # 持仓 1000.1234 份（4 位精度）
    pos = _make_out_position(db, make_position, make_transaction, quantity=1000.1234)

    result = _submit(db, pos)

    assert result['out']['quantity'] == 1000.1234
    out_txn = db.query(Transaction).filter_by(txn_type='sell').first()
    assert Money.min_unit_to_shares(out_txn.quantity) == 1000.1234


def test_submit_rejects_more_than_two_decimal_shares(db, make_position, make_transaction):
    """显式转出份额超过 2 位小数：拒绝（§5.2 入参校验）。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='最多 2 位小数'):
        _submit(db, pos, out_quantity=100.123)


def test_submit_refund_leg_money_fund(db, make_position, make_transaction):
    """指定转入金额 < 净额：第三条腿落类现金孤儿流水（position_id 为空）。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)
    _bind_money_fund(db, pos.ledger_id)

    result = _submit(db, pos, in_amount=800.00, refund_mode='money_fund')

    txns = _group_txns(db)
    assert len(txns) == 3
    refund_txn = txns[2]
    assert refund_txn.txn_type == 'buy'
    assert refund_txn.asset_type == 'money_fund'
    assert refund_txn.symbol == '000198'
    assert refund_txn.entry_status == 'orphan'
    assert refund_txn.position_id is None
    assert refund_txn.amount == 18512  # 985.12 − 800.00
    assert refund_txn.link_group_id == IDEMPOTENCY_KEY
    assert refund_txn.import_hash == f'{IDEMPOTENCY_KEY}#conv-refund'
    assert json.loads(refund_txn.extra)['conversion']['role'] == 'refund'
    # 转入腿按指定金额（过滤掉 FIFO 试算用的历史买入批次）
    in_txn = db.query(Transaction).filter_by(link_group_id=IDEMPOTENCY_KEY, txn_type='buy', asset_type='fund').first()
    assert Money.cents_to_yuan(in_txn.amount) == 800.00
    assert result['refund']['mode'] == 'money_fund'


def test_submit_refund_leg_account_cash(db, make_position, make_transaction):
    """退款退回账户现金：deposit 孤儿流水，symbol=__CASH__。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    _submit(db, pos, in_amount=800.00, refund_mode='account_cash')

    refund_txn = db.query(Transaction).filter_by(asset_type='cash').first()
    assert refund_txn is not None
    assert refund_txn.txn_type == 'deposit'
    assert refund_txn.symbol == CASH_SYMBOL
    assert refund_txn.entry_status == 'orphan'
    assert refund_txn.amount == 18512


def test_submit_rejects_supplement(db, make_position, make_transaction):
    """转入金额 > 净额（垫资）：D6 v1 拒绝。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='暂不支持垫资'):
        _submit(db, pos, in_amount=2000.00)


def test_submit_requires_refund_mode_when_refund_exists(db, make_position, make_transaction):
    """有退款但未选去向：拒绝（不允许差额凭空消失）。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='必须选择退款去向'):
        _submit(db, pos, in_amount=800.00)


def test_submit_rejects_money_fund_mode_without_binding(db, make_position, make_transaction):
    """未绑定类现金产品时选 money_fund 去向：拒绝并指引。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='未绑定类现金产品'):
        _submit(db, pos, in_amount=800.00, refund_mode='money_fund')


def test_submit_no_auto_purchase_even_when_enabled(db, make_position, make_transaction):
    """账户开了自动申购也不得触发：转换回款由退款腿显式落账（§4.4.7 回归）。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)
    _bind_money_fund(db, pos.ledger_id)
    ledger = db.get(Ledger, pos.ledger_id)
    ledger.auto_purchase_money_fund = True  # 开启开关，仍不得自动申购
    db.commit()

    _submit(db, pos)  # 全额转入、无退款

    txns = _group_txns(db)
    assert len(txns) == 2
    assert all(t.asset_type != 'money_fund' for t in txns)


def test_submit_idempotent_same_key_rejected(db, make_position, make_transaction):
    """同幂等键重复提交：预检命中抛 SBException(409/1003)，不产生第二组流水。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    first = _submit(db, pos)
    with pytest.raises(SBException) as exc_info:
        _submit(db, pos)
    err = exc_info.value
    assert err.status_code == 409
    assert err.code == 1003
    # detail 带原组号：前端重发可直接跳到已落库的那笔结果
    assert err.detail['link_group_id'] == first['link_group_id']
    assert err.detail['duplicated'] is True
    # 仍然只有一组两条流水
    assert len(_group_txns(db)) == 2


def test_submit_rejects_same_and_unknown_fund(db, make_position, make_transaction):
    """提交层同样拦截同名/不存在转入基金（与试算同源校验）。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='转入基金不能与转出基金相同'):
        _submit(db, pos, in_symbol='000001')
    with pytest.raises(ValueError, match='转入基金不存在'):
        _submit(db, pos, in_symbol='999999')


def test_submit_endpoint_contract(client, db, make_position, make_transaction):
    """端点契约：200 信封 + 同键重发 409（幂等）。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)
    # make_transaction 只 flush 不 commit：夹具会话持写锁会挡住请求侧写入
    # （DELETE journal 下读者/写者互斥），POST 前必须落定（同 test_positions.py 模式）
    db.commit()

    payload = {
        'out_position_id': pos.id,
        'in_symbol': '000002',
        'trade_date': TRADE_DATE.isoformat(),
        'idempotency_key': IDEMPOTENCY_KEY,
    }
    resp = client.post('/api/positions/conversion/', json=payload)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['message'] == 'ok'
    assert body['data']['link_group_id'] == IDEMPOTENCY_KEY

    # 同键重发 → 409（幂等预检命中，不产生第二组流水）
    resp2 = client.post('/api/positions/conversion/', json=payload)
    assert resp2.status_code == 409
    body2 = resp2.get_json()
    assert body2['error_code'] == 1003
    assert body2['data']['duplicated'] is True
    assert body2['data']['link_group_id'] == IDEMPOTENCY_KEY


# ── #2348：按份额转入 / 人工修正费用（落库侧） ──────────────────


def test_submit_by_in_quantity_stores_exact_shares(db, make_position, make_transaction):
    """按份额转入：落库份额与用户输入**完全一致**（不再由金额反算）。

    确认单上写的是份额。若只收金额再反算，4 位取整会让份额差 0.0001，
    对账时看着像丢了半份——所以份额必须能作为入参直达落库。
    """
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    result = _submit(db, pos, in_quantity=400.00, refund_mode='account_cash')

    in_txn = db.query(Transaction).filter_by(link_group_id=IDEMPOTENCY_KEY, txn_type='buy', asset_type='fund').first()
    # Transaction.quantity 存的是最小单位（份额 × 10000），断言前必须换算
    assert Money.min_unit_to_shares(in_txn.quantity) == pytest.approx(400.0, abs=1e-6)
    assert Money.cents_to_yuan(in_txn.amount) == 800.00
    # 差额落退款腿，金额守恒
    refund_txn = db.query(Transaction).filter_by(asset_type='cash').first()
    assert refund_txn.amount == 18512
    assert result['in']['quantity'] == pytest.approx(400.0, abs=1e-6)
    assert result['refund']['amount'] == 185.12


def test_submit_fee_override_persisted_in_extra(db, make_position, make_transaction):
    """人工修正费用：OUT 腿记修正后的费用，`extra` 同时留估算值（可审计）。

    只记修正值 = 事后无法判断「这笔费用是算出来的还是人填的」，
    出了对账争议就说不清，故两者都存。
    """
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    _submit(db, pos, fee_override={'redeem': 0, 'compensate': 0})

    out_txn = db.query(Transaction).filter_by(link_group_id=IDEMPOTENCY_KEY, txn_type='sell').first()
    assert Money.cents_to_yuan(out_txn.fee) == 0.00
    extra = json.loads(out_txn.extra)['conversion']
    assert extra['fee_override_applied'] is True
    assert extra['fee_breakdown'] == {'redeem': 0.0, 'compensate': 0.0}
    assert extra['fee_estimated'] == {'redeem': 13.5, 'compensate': 1.38}
    # 费用归零后净额 = 转出金额，转入份额按 1000/2.0 计
    in_txn = db.query(Transaction).filter_by(link_group_id=IDEMPOTENCY_KEY, txn_type='buy', asset_type='fund').first()
    assert Money.min_unit_to_shares(in_txn.quantity) == pytest.approx(500.0, abs=1e-6)


def test_submit_api_accepts_in_quantity_and_fee_override(client, db, make_position, make_transaction):
    """API 层：新增的两个入参能被 schema 接收并透传到服务（回归网）。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)
    db.commit()

    payload = {
        'out_position_id': pos.id,
        'in_symbol': '000002',
        'in_quantity': 400.0,
        'fee_override': {'redeem': 0, 'compensate': 0},
        'refund_mode': 'account_cash',
        'trade_date': TRADE_DATE.isoformat(),
        'idempotency_key': IDEMPOTENCY_KEY,
    }
    resp = client.post('/api/positions/conversion/', json=payload)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    assert data['in']['quantity'] == pytest.approx(400.0, abs=1e-6)
    assert data['out']['fee'] == 0.0
    assert data['out']['fee_overridden'] is True
    # 费用被修正为 0 ⇒ 净额 1000，400 份 × 2.0 = 800，差额 200
    assert data['refund']['amount'] == 200.0


def test_submit_in_leg_fills_account_name(db, make_position, make_transaction):
    """转入腿必须带 account_name，不能只传 ledger_id。

    根因回归（2026-10-18 实测 position 618 / transaction 3001）：转换「转入腿」
    只传 ledger_id，positions/transactions 的 account_name 落成 NULL；按账户分组时
    None 作字典键让 flask.jsonify(sort_keys=True) 抛 TypeError，整个持仓列表 500。
    """
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    _submit(db, pos)

    in_pos = db.query(Position).filter_by(symbol='000002').first()
    assert in_pos is not None
    assert in_pos.ledger_id == pos.ledger_id
    assert in_pos.account_name == '转换测试账户'

    in_txn = (
        db.query(Transaction)
        .filter(Transaction.link_group_id == IDEMPOTENCY_KEY, Transaction.txn_type == 'buy')
        .first()
    )
    assert in_txn is not None
    assert in_txn.account_name == '转换测试账户'
