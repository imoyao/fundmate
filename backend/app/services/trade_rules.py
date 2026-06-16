# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 13:32
# File : trade_rules.py
# -*- coding: utf-8 -*-
"""
交易规则模块
提供品种交易规则配置和买入/卖出数量校验。
当前版本使用函数式设计，后续可封装为 TradeLotRuleEngine 类。
"""

from loguru import logger

# ---------- 规则配置 ----------


def _get_rule(symbol: str, market: str, asset_type: str) -> dict:
    """
    根据标的信息返回交易规则字典。
    包含字段：min_unit (最小交易单位), step (步长), lot (一手数量)。
    """
    # 可转债：区分沪市/深市
    if asset_type == 'bond':
        if symbol.startswith('11'):
            return {'min_unit': 10, 'step': 10, 'lot': 10}  # 沪市：卖出也10张整数倍
        if symbol.startswith('12'):
            return {'min_unit': 10, 'step': 1, 'lot': 10}  # 深市：卖出无整手限制
        return {'min_unit': 10, 'step': 10, 'lot': 10}

    # 股票/ETF
    if asset_type in ('stock', 'etf'):
        # A股市场
        if market in ('SH', 'SZ', 'CN_A'):
            if symbol.startswith('688') and market in ('SH', 'CN_A'):
                return {'min_unit': 200, 'step': 1, 'lot': 200}  # 科创板
            if market == 'BJ' or symbol.startswith('8'):
                return {'min_unit': 100, 'step': 1, 'lot': 100}  # 北交所
            # 沪深主板/创业板
            return {'min_unit': 100, 'step': 100, 'lot': 100}
        # 境外市场
        return {'min_unit': 1, 'step': 1, 'lot': 1}

    # 其他品种不设限制
    return {'min_unit': 1, 'step': 1, 'lot': 1}


# ---------- 校验函数 ----------


def validate_buy(symbol: str, market: str, asset_type: str, current_hold: float, order_qty: float) -> tuple[bool, str]:
    """
    买入数量校验。
    :param asset_type: 资产类别
    :param market: 所属市场
    :param symbol: 编码
    :param current_hold: 现有持仓数量（份额，可带小数）
    :param order_qty: 本次买入数量（份额，可带小数）
    """
    if order_qty <= 0:
        return False, '买入数量必须大于0'
    rule = _get_rule(symbol, market, asset_type)
    min_unit = rule['min_unit']
    step = rule['step']
    if current_hold < min_unit:
        return True, ''
    else:
        if order_qty < min_unit:
            msg = f'买入数量不能低于{min_unit}股/张'
            logger.warning(f'{msg}: symbol={symbol}, current_hold={current_hold}, order_qty={order_qty}, rule={rule}')
            return False, msg
        if (order_qty - min_unit) % step != 0:
            msg = f'买入数量必须符合{min_unit}股/张起，步长{step}'
            logger.warning(f'{msg}: symbol={symbol}, current_hold={current_hold}, order_qty={order_qty}, rule={rule}')
            return False, msg
        return True, ''


def validate_sell(symbol: str, market: str, asset_type: str, total_hold: float, order_qty: float) -> tuple[bool, str]:
    """
    卖出数量校验。
    :param total_hold: 总持仓数量（份额，可带小数）
    :param order_qty: 本次卖出数量（份额，可带小数）
    """
    if order_qty <= 0:
        return False, '卖出数量必须大于0'
    if order_qty > total_hold:
        return False, '卖出数量不能超过持仓数量'
    rule = _get_rule(symbol, market, asset_type)
    min_unit = rule['min_unit']
    step = rule['step']
    if order_qty == total_hold:
        return True, ''
    if total_hold < min_unit:
        msg = f'当前持仓不足{min_unit}股/张，只能一次性全部卖出（当前持有{total_hold}）'
        logger.warning(f'{msg}: symbol={symbol}, total_hold={total_hold}, order_qty={order_qty}, rule={rule}')
        return False, msg
    if order_qty < min_unit:
        msg = f'卖出数量不能低于{min_unit}股/张'
        logger.warning(f'{msg}: symbol={symbol}, total_hold={total_hold}, order_qty={order_qty}, rule={rule}')
        return False, msg
    if (order_qty - min_unit) % step != 0:
        msg = f'卖出数量必须符合{min_unit}股/张起，步长{step}'
        logger.warning(f'{msg}: symbol={symbol}, total_hold={total_hold}, order_qty={order_qty}, rule={rule}')
        return False, msg
    if order_qty != total_hold and (total_hold - order_qty) < min_unit and (total_hold - order_qty) != 0:
        msg = '禁止单独卖出不足一手的零散持仓'
        logger.warning(f'{msg}: symbol={symbol}, total_hold={total_hold}, order_qty={order_qty}, rule={rule}')
        return False, msg
    return True, ''
