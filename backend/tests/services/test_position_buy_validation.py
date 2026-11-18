# -*- coding: utf-8 -*-
"""_validate_buy_inputs 的申购段分支（2026-11-08）。

背景：5 只 2023 年转债中签以申购码（如 SZ072998）进 commit，别名解析失败后
被代码段规则判成 stock，套上「100 股一手」报错——数量规则不是问题所在，
错误必须指到真正的动作（补全上市代码）上。
"""

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
