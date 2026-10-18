# -*- coding: utf-8 -*-
"""转换纯算术（``compute_conversion_maths``）的真实确认单校准（#2348）。

## 为什么用真实确认单做用例

基金公司 App 的确认单能同时给出「转出金额 / 转入金额 / 差额」三个数，它们必须满足

    转出金额 == 转入金额 + 差额        （费用为 0 时）
    转出金额 − 费用 == 转入金额 + 差额  （费用非 0 时）

这条恒等式与**净值/份额的取整口径**强相关：差一分钱就意味着我们和基金公司
对「先截断还是先四舍五入」的理解不一致。把它钉在纯函数用例上，比在 DB 集成测试里
排查快得多（DB 用例出错时你分不清是算法错了还是夹具错了）。

下面四组数字全部来自用户的实际确认单（2026-10-18 提供），**不是构造的**。
"""

from decimal import Decimal

import pytest

from app.services.conversion_service import compute_conversion_maths


def _dec(**kwargs) -> dict:
    return {k: Decimal(str(v)) for k, v in kwargs.items()}


def test_case_a_refund_to_money_fund():
    """算例 A：国联鑫起点C → 万家宏观择时C，差额 64.26 进货基。

    确认单：转出 2293.98 份 × 1.2087 = 2772.73；手续费 0；
    转入 2708.47 元（净值 3.3222 → 815.26 份）；差额 64.26 → 富国收益宝货币B。
    """
    m = compute_conversion_maths(
        **_dec(qty='2293.98', out_nav='1.2087', in_nav='3.3222', total_fee='0'),
        in_amount=Decimal('2708.47'),
    )

    assert m.out_amount == Decimal('2772.73')
    assert m.net_amount == Decimal('2772.73')
    assert m.in_amount_used == Decimal('2708.47')
    assert m.refund_amount == Decimal('64.26')
    assert m.supplement_amount == Decimal('0')
    # 确认单上的转入份额 815.26（展示 2 位，我们存 4 位）
    assert m.in_quantity.quantize(Decimal('0.01')) == Decimal('815.26')
    # 守恒：转出金额 = 转入金额 + 差额
    assert m.out_amount == m.in_amount_used + m.refund_amount


def test_case_b_refund_to_cash_by_in_quantity():
    """算例 B：宏利睿智稳健A → 博时战略新材料C，按**份额**指定转入、差额 202.61 退余额宝。

    确认单：转出 14729.52 份 × 1.0116 = 14900.38；手续费 0；
    转入 16481.02 份（净值 0.8918 → 14697.77 元）；差额 202.61 退回余额宝。

    这是「用户只知道份额、不知道金额」的真实场景——按金额反算会差几分钱，
    必须让份额成为输入。
    """
    m = compute_conversion_maths(
        **_dec(qty='14729.52', out_nav='1.0116', in_nav='0.8918', total_fee='0'),
        in_quantity=Decimal('16481.02'),
    )

    assert m.out_amount == Decimal('14900.38')
    assert m.in_amount_used == Decimal('14697.77')
    assert m.refund_amount == Decimal('202.61')
    # 份额按用户输入原样保留（2 位 → 存 4 位不改变数值）
    assert m.in_quantity == Decimal('16481.0200')
    assert m.out_amount == m.in_amount_used + m.refund_amount


def test_case_c_with_redeem_fee_and_tolerance():
    """算例 C：东方红红利低波A → 交银优选回报C，含赎回费 19.33。

    确认单：转出 5540.00 份 × 1.3956 = 7731.62；转出手续费 19.33；
    转入 1512.07 份（净值 5.0550 → 7643.51 元）；App 记「长款退还 68.76」。

    我们算 68.78，与 App 差 **0.02**。这笔含「同花顺钱包冻结 764.36 份」的垫资机制，
    差额口径与标准转换不同，故按 ±0.05 容差断言——**不把差异当 bug，也不放宽容差到无意义**。
    """
    m = compute_conversion_maths(
        **_dec(qty='5540.00', out_nav='1.3956', in_nav='5.0550', total_fee='19.33'),
        in_quantity=Decimal('1512.07'),
    )

    assert m.out_amount == Decimal('7731.62')
    assert m.net_amount == Decimal('7712.29')
    assert m.in_amount_used == Decimal('7643.51')
    assert m.refund_amount == Decimal('68.78')
    assert abs(m.refund_amount - Decimal('68.76')) <= Decimal('0.05')
    # 含费用时的守恒式
    assert m.out_amount - Decimal('19.33') == m.in_amount_used + m.refund_amount


def test_case_d_supplement_when_in_amount_exceeds_net():
    """算例 D：差额可以反向（转入 > 净额 = 需垫资），对应确认单的「份额调增」场景。"""
    m = compute_conversion_maths(
        **_dec(qty='1000', out_nav='1', in_nav='2', total_fee='0'),
        in_amount=Decimal('1200.00'),
    )

    assert m.supplement_amount == Decimal('200.00')
    assert m.refund_amount == Decimal('0')
    # 垫资不改变账：转入腿仍按净额计（v1 由 submit 拦截）
    assert m.in_amount_used == Decimal('1000.00')
    assert m.in_quantity == Decimal('500.0000')


def test_unspecified_means_all_net_in():
    """都不指定 = 净额全部转入（最常见的默认路径）。"""
    m = compute_conversion_maths(**_dec(qty='1000', out_nav='1', in_nav='2', total_fee='14.88'))

    assert m.in_amount_used == m.net_amount == Decimal('985.12')
    assert m.refund_amount == Decimal('0')
    assert m.supplement_amount == Decimal('0')
    assert m.in_quantity == Decimal('492.5600')


def test_rejects_both_in_amount_and_in_quantity():
    """金额与份额只能二选一——同时给等于让算法猜哪个是真相源。"""
    with pytest.raises(ValueError, match='只能指定一个'):
        compute_conversion_maths(
            **_dec(qty='1000', out_nav='1', in_nav='2', total_fee='0'),
            in_amount=Decimal('500'),
            in_quantity=Decimal('250'),
        )


def test_rejects_in_quantity_with_three_decimals():
    """转入份额录入 2 位（§5.2）；3 位会让「净值 × 份额」多出一档误差。"""
    with pytest.raises(ValueError, match='最多 2 位小数'):
        compute_conversion_maths(
            **_dec(qty='1000', out_nav='1', in_nav='2', total_fee='0'),
            in_quantity=Decimal('250.125'),
        )


def test_rejects_fee_swallowing_the_whole_amount():
    """费用 >= 转出金额：净额非正，账没有意义，必须报错而不是算出负份额。"""
    with pytest.raises(ValueError, match='不足以覆盖费用'):
        compute_conversion_maths(**_dec(qty='100', out_nav='1', in_nav='2', total_fee='100'))
