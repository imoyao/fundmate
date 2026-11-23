# -*- coding: utf-8 -*-
"""_validate_buy_inputs 的申购段分支（2026-11-08）。

背景：5 只 2023 年转债中签以申购码（如 SZ072998）进 commit，别名解析失败后
被代码段规则判成 stock，套上「100 股一手」报错——数量规则不是问题所在，
错误必须指到真正的动作（补全上市代码）上。
"""

from datetime import date

import pytest

from app.services.position_buy_command import _validate_buy_inputs


def test_subscription_code_lot_failure_names_the_real_problem():
    """申购段代码 + 套错 stock 规则 → 报「未解析上市代码」，不是「一手起买」。"""
    with pytest.raises(ValueError, match='申购码 SZ072998 未能解析上市代码'):
        _validate_buy_inputs(
            {'symbol': 'SZ072998', 'market': 'SZ'},
            'stock',
            'SZ072998',
            10,
            100.0,
            1000.0,
        )


def test_normal_stock_lot_failure_keeps_original_message():
    """普通股票碎股买入仍是原来的「一手起买」措辞（回归保障）。"""
    with pytest.raises(ValueError, match='一手起买'):
        _validate_buy_inputs(
            {'symbol': 'SZ000001', 'market': 'SZ'},
            'stock',
            'SZ000001',
            50,
            10.0,
            500.0,
        )


def test_bond_ten_lots_pass_validation():
    """可转债 10 张（1 手）本来就合法——中签行的正确形态是解析成 12x 段走这里。"""
    _validate_buy_inputs(
        {'symbol': 'SZ127078', 'market': 'SZ'},
        'bond',
        'SZ127078',
        10,
        100.0,
        1000.0,
    )


def test_maturity_date_allowed_for_reverse_repo_and_bank_wealth():
    """到期日只对「有到期语义」的品类开放（#931 / D121）。

    银行理财那条是重点：它是 balance 品类，而 `_validate_buy_inputs` 在 balance
    分支里**提前 return** —— 校验若写在那之后，理财自己反而校验不到。
    """
    _validate_buy_inputs(
        {'symbol': 'Z7001234ABCD', 'maturity_date': date(2027, 1, 15)},
        'bank_wealth',
        'Z7001234ABCD',
        0,
        0,
        100000.0,
        is_balance=True,
    )
    _validate_buy_inputs(
        {'symbol': 'SH204001', 'market': 'SH', 'maturity_date': date(2026, 12, 1), 'skip_lot_check': True},
        'reverse_repo',
        'SH204001',
        100,
        100.0,
        10000.0,
    )


def test_maturity_date_rejected_for_other_asset_types():
    """基金/股票没有到期日：传进来是上游接错字段，fail closed 而不是静默丢弃。"""
    with pytest.raises(ValueError, match='到期日仅适用于逆回购与银行理财'):
        _validate_buy_inputs(
            {'symbol': '110011', 'maturity_date': date(2027, 1, 1)},
            'fund',
            '110011',
            100,
            1.5,
            150.0,
        )
