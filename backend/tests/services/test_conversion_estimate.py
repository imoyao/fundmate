# -*- coding: utf-8 -*-
"""基金转换试算（P0）测试。

对应设计文档 docs/working-notes/fund-conversion-design-2026-10-17.md §8 P0 验收：
纯函数级用例——2 基金 / 带退款 / 垫资拦截 / 费率缺失 / 全部转出 / 跨类型拒绝。

数字口径（主用例）：
- 转出 000001：净值 1.0000，持仓 1000 份，成本 0.9；
- 买入批次确认日在 T-3（命中 0~7 天 1.5% 赎回档），FIFO 赎回费 = 1000 × 0.9 × 1.5% = 13.50；
- 转出金额 = 1000 × 1.0 = 1000.00；净额（补差前）= 986.50；
- 转出申购档 0.1% → 0.99；转入申购档 1.5% → 14.80；
- 补差费 = (14.80 − 0.99) × 0.1 = 1.38；总费用 14.88；净转入 985.12；
- 转入 000002 净值 2.0000 → 预估份额 985.12 / 2 = 492.56；
- 已实现盈亏预估 = (1.0 − 0.9) × 1000 − 14.88 = 85.12。
"""

from datetime import date, timedelta

import pytest

from app.domains.funds.models import DailyWorth, FeeRatio, Fund, PurchaseRule, RedeemRule
from app.services.conversion_service import ConversionService

TRADE_DATE = date(2026, 10, 15)
BUY_CONFIRM_DATE = TRADE_DATE - timedelta(days=3)


def _seed_fund(db, code, name, *, purchase_rate=None, redeem_rules=None):
    """建基金行 + 费率阶梯。金额档单位为分（PurchaseRule.start_quota）。

    ## 规则行必须复用，不能每只基金各建一份

    ``purchase_rules`` / ``redeem_rules`` 是**全局**区间表：生产侧写入口一律走
    ``FundService._get_or_create_purchase_rule`` / ``_get_or_create_redeem_rule``，
    同一区间只存在一行；``uq_purchase_rules_quota`` / ``uq_redeem_rules_range``
    （2026-10-18）把这条契约落到了数据库层。此前夹具给每只基金都新建一份同样的
    区间行，转换类用例一多只基金就撞唯一约束——那说明夹具本就不反映生产口径。
    """
    fund = Fund(fund_code=code, name=name)
    db.add(fund)
    db.flush()
    if purchase_rate is not None:
        rule = (
            db.query(PurchaseRule).filter(PurchaseRule.start_quota == 0, PurchaseRule.end_quota.is_(None)).first()
            or PurchaseRule(start_quota=0, end_quota=None)  # 0 元起、无上限
        )
        db.add(rule)
        db.flush()
        db.add(FeeRatio(fund_code=code, fee_type='purchase', rate=purchase_rate, purchase_rule_id=rule.id))
    for start_day, end_day, rate in redeem_rules or []:
        rule = (
            db.query(RedeemRule).filter(RedeemRule.start_day == start_day, RedeemRule.end_day == end_day).first()
            or RedeemRule(start_day=start_day, end_day=end_day)
        )
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
    # FIFO 赎回费依赖买入批次（确认日决定持有天数档位）
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


def _estimate(db, pos, **kwargs):
    params = {
        'out_position_id': pos.id,
        'in_symbol': '000002',
        'family_id': 1,
        'trade_date': TRADE_DATE,
    }
    params.update(kwargs)
    return ConversionService.estimate_conversion(db, **params)


def test_estimate_two_funds_fee_and_net_amount(db, make_position, make_transaction):
    """双基金试算：费用拆分、净额守恒、预估份额、盈亏预估。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    result = _estimate(db, pos)

    assert result['warnings'] == []
    assert result['out']['amount'] == 1000.00
    assert result['out']['fee'] == 14.88
    assert result['out']['fee_breakdown'] == {'redeem': 13.50, 'compensate': 1.38}
    assert result['net_amount'] == 985.12
    # 资产守恒：转出金额 − 总费用 = 净转入金额
    assert round(result['out']['amount'] - result['out']['fee'], 2) == result['net_amount']
    assert result['in']['amount'] == 985.12
    assert result['in']['quantity'] == 492.56
    assert result['out']['realized_pnl_estimate'] == 85.12
    assert result['refund']['amount'] == 0
    assert result['supplement']['required'] is False


def test_estimate_with_refund_when_in_amount_below_net(db, make_position, make_transaction):
    """指定转入金额 < 净额：差额为退款，转入腿按指定金额计。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    result = _estimate(db, pos, in_amount=800.00)

    assert result['refund']['amount'] == 185.12
    assert result['in']['amount'] == 800.00
    assert result['in']['quantity'] == 400.00
    # 退款去向优先账户绑定的类现金；未绑定时只剩账户现金
    assert [o['type'] for o in result['refund']['options']] == ['account_cash']


def test_estimate_supplement_required_when_in_amount_above_net(db, make_position, make_transaction):
    """指定转入金额 > 净额（垫资）：D6 v1 不允许——试算标记 required 并给出差额。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    result = _estimate(db, pos, in_amount=2000.00)

    assert result['supplement']['required'] is True
    assert result['supplement']['amount'] == 1014.88
    # 垫资不改变账：转入腿仍按净额计
    assert result['in']['amount'] == 985.12


def test_estimate_all_shares_when_quantity_missing(db, make_position, make_transaction):
    """缺省转出份额 = 全部转出。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    result = _estimate(db, pos, out_quantity=None)

    assert result['out']['quantity'] == 1000
    assert result['net_amount'] == 985.12


def test_estimate_missing_fee_rules_warn_not_block(db, make_position, make_transaction):
    """费率缺失（D9）：不阻断，warnings 显式告警，费用按 0 预估。"""
    # 只建基金行与净值，不建任何费率阶梯
    _seed_fund(db, '000001', '转出基金')
    _seed_fund(db, '000002', '转入基金')
    db.add(DailyWorth(fund_code='000001', date=TRADE_DATE, unit_nav=1.0))
    db.add(DailyWorth(fund_code='000002', date=TRADE_DATE, unit_nav=2.0))
    db.commit()
    pos = _make_out_position(db, make_position, make_transaction)

    result = _estimate(db, pos)

    assert any('赎回费率缺失' in w for w in result['warnings'])
    assert any('申购费率数据缺失' in w for w in result['warnings'])
    assert result['out']['fee'] == 0
    assert result['out']['fee_breakdown'] == {'redeem': 0, 'compensate': 0}
    assert result['net_amount'] == 1000.00


def test_estimate_rejects_same_fund(db, make_position, make_transaction):
    """转入 = 转出：拒绝。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='转入基金不能与转出基金相同'):
        _estimate(db, pos, in_symbol='000001')


def test_estimate_rejects_unknown_in_fund(db, make_position, make_transaction):
    """转入基金不在名录：拒绝。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='转入基金不存在'):
        _estimate(db, pos, in_symbol='999999')


def test_estimate_rejects_non_fund_position(db, make_position, make_transaction):
    """转出持仓非基金（股票）：拒绝。"""
    _seed_two_funds(db)
    pos = make_position(
        symbol='600001',
        name='测试股票',
        asset_type='stock',
        account_name='转换测试账户',
        quantity=1000,
        avg_price=10.0,
    )

    with pytest.raises(ValueError, match='只有基金持仓可以转换'):
        _estimate(db, pos)


def test_estimate_rejects_over_available(db, make_position, make_transaction):
    """转出份额超过可用份额：拒绝。"""
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='超过可用份额'):
        _estimate(db, pos, out_quantity=1001)


def test_estimate_rejects_missing_nav(db, make_position, make_transaction):
    """净值缺失：拒绝试算（不给占位价，避免误导性预估份额）。"""
    _seed_two_funds(db)  # 有意不建 DailyWorth 之外的场景见下
    from app.domains.funds.models import DailyWorth as _DW

    db.query(_DW).delete()
    db.commit()
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='无净值'):
        _estimate(db, pos)


def test_estimate_rejects_money_fund_as_target(db, make_position, make_transaction, monkeypatch):
    """转入货基：拒绝（货基无费率阶梯、转换语义不成立）。

    货基判定走 market 名录（fund_utils.resolve_money_fund_flags）；测试夹具的
    user/market 双引擎隔离使 db 路由会话写的名录行对 market 会话不可见
    （既有模式见 test_fund_utils_money_fund.py：monkeypatch 屏蔽名录解析），
    故此处直接打桩「名录说是货基」，锁定转换服务的拒绝分支本身。
    """
    _seed_two_funds(db)
    _seed_fund(db, '000198', '测试货基')
    db.add(DailyWorth(fund_code='000198', date=TRADE_DATE, unit_nav=1.0))
    db.commit()
    monkeypatch.setattr(
        'app.services.fund_utils.resolve_money_fund_flags',
        lambda symbols: {s: True for s in symbols},
    )
    pos = _make_out_position(db, make_position, make_transaction)

    with pytest.raises(ValueError, match='不能转换至货币基金'):
        _estimate(db, pos, in_symbol='000198')
