# -*- coding: utf-8 -*-
"""交易域服务：品种交易规则校验 + 流水构造。

合并说明（2026-09-09）：原 ``trade_rules.py``（规则校验）与
``transaction_service.py``（仅一个 3 行的 ``TransactionService.create``）
是两个碎文件，但同属「交易写入链路」的两端——**先校验合法，再构造流水**，
拆开只会让调用方各 import 一次、且给「交易」这一概念留下两个入口。
合并后对外符号 ``TradeService`` / ``validate_buy`` / ``validate_sell`` /
``TransactionService`` 全部保留，行为不变。

当前版本使用函数式设计，后续可封装为 TradeLotRuleEngine 类。
"""

from sqlalchemy.orm import Session

from app.domains.transactions.models import Transaction

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


def validate_buy(symbol: str, market: str, asset_type: str, order_qty: float) -> tuple[bool, str]:
    """买入数量校验（A股规则）。

    A股买入必须按「一手」的整数倍申报，碎股只能卖、不能买：
      - 主板/创业板/北交所：100股一手；科创板：200股一手；
      - 买入数量必须 ≥ 一手 且为整手步长的整数倍。
    买入校验**与当前持仓量无关**：无论是否已持有该标的，只要本次
    买入数量本身合法即可。严禁把持仓量卷入买入校验——「不能超过持仓」
    是卖出(validate_sell)的职责，误卷会导致已持有时再次买入被错误拦截。
    基金/货币基金步长为1，不受整手限制。
    """
    if order_qty <= 0:
        return False, '买入数量必须大于0'
    rule = _get_rule(symbol, market, asset_type)
    min_unit = rule['min_unit']
    step = rule['step']
    if order_qty < min_unit:
        return False, f'买入数量不能低于{min_unit}股/张（一手起买）'
    # 基金/货币基金步长恒为1，直接跳过取模，避免浮点精度陷阱
    if asset_type not in ('fund', 'money_fund') and (order_qty - min_unit) % step != 0:
        return False, f'买入数量须为{min_unit}股/张的整数倍（步长{step}）'
    return True, ''


def validate_sell(symbol: str, market: str, asset_type: str, total_hold: float, order_qty: float) -> tuple[bool, str]:
    """
    卖出数量校验。
    :param asset_type:
    :param market:
    :param symbol:
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
        return False, f'当前持仓不足{min_unit}股/张，只能一次性全部卖出'
    if order_qty < min_unit:
        return False, f'卖出数量不能低于{min_unit}股/张'
    if (order_qty - min_unit) % step != 0:
        return False, f'卖出数量必须符合{min_unit}股/张起，步长{step}'
    if order_qty != total_hold and (total_hold - order_qty) < min_unit and (total_hold - order_qty) != 0:
        return False, '禁止单独卖出不足一手的零散持仓'
    return True, ''


class TradeService:
    """交易规则校验服务（零耦合，直接对接后端）"""

    @staticmethod
    def validate_transaction(
        symbol: str, market: str, asset_type: str, current_hold: float, order_qty: float, op_type: str
    ) -> dict:
        if op_type == 'buy':
            valid, msg = validate_buy(symbol, market, asset_type, order_qty)
        elif op_type == 'sell':
            valid, msg = validate_sell(symbol, market, asset_type, current_hold, order_qty)
        else:
            return {'valid': False, 'message': '不支持的操作类型'}

        return {'valid': valid, 'message': msg}


class TransactionService:
    """流水创建服务，仅负责构造对象，不管理事务边界。"""

    @staticmethod
    def create(db: Session, **kwargs) -> Transaction:
        """构造并添加流水到会话，由调用方统一提交。

        source（#1232 决策 11）：可选，透传到 Transaction.source（复用 PositionSource）。
        缺省 None（存量未标记来源语义）。记一笔/对账补录/交易导入由汇点层按场景传入。
        """
        txn = Transaction(**kwargs)
        db.add(txn)
        return txn


__all__ = ['TradeService', 'TransactionService', 'validate_buy', 'validate_sell']
