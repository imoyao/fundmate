# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/29 23:11
# File : views.py
import os
from datetime import datetime

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.trading_calendar import is_trading_day, next_trading_day
from app.core.utils import get_confirm_date

utils_bp = APIBlueprint('utils', __name__, url_prefix='/api/utils')


@utils_bp.get('/trading-days/<date>/')
def get_trading_day(date: str):
    """
    查询指定日期是否为**A 股开盘日**（周一至周五 且 非法定节假日）。

    注意与「法定工作日」的区别：调休补班的周末（如 2026-10-10 周六）打工人要上班，
    但交易所休市，本接口返回 false。判定统一走交易日历唯一出口
    （`app.core.trading_calendar`，#1217）。
    """
    try:
        d = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        abort(400, '日期格式错误，应为 YYYY-MM-DD')

    return jsonify({'data': {'date': date, 'is_trading_day': is_trading_day(d)}, 'message': 'ok'})


@utils_bp.get('/config/')
def get_platform_config():
    """下发平台级配置（双层估值开关的平台级总闸，issue #826）。

    为什么单独开这个只读 GET 端点：
    - 实时估值是「用户级开关（前端 localStorage）+ 平台级总闸（后端 env）」双层结构，
      平台级为总闸：数据源压力过大或合规收紧时，运维改 env `REALTIME_QUOTES_ENABLED`
      即可一键关闭全站实时估值，无需发版、无需前端配合；
    - 探市页 `/explore` 免登录也使用实时估值（useRealtimeQuotes），匿名访客必须能读到
      总闸，故本端点须免登录（见 core/auth.py 白名单），且无副作用、不落库。
    - 默认 true（未配置时保持现状），避免默认关闭导致线上估值突然消失。
    """
    raw = os.getenv('REALTIME_QUOTES_ENABLED', 'true')
    enabled = raw.strip().lower() in ('1', 'true', 'yes', 'on')
    return jsonify({'data': {'realtime_quotes_enabled': enabled}, 'message': 'ok'})


@utils_bp.get('/fund-confirm-dates/')
def calc_fund_confirm_date():
    """
    计算场外基金的实际净值日和确认日。
    参数：
        trade_date: 购买日期 (YYYY-MM-DD)
        fund_type: 基金类型 (domestic / qdii)，默认 domestic
        is_after_15: 是否在15:00之后 (true/false)，默认 false
    """
    trade_date_str = request.args.get('trade_date', '')
    fund_type = request.args.get('fund_type', 'domestic')
    is_after_15 = request.args.get('is_after_15', 'false').lower() == 'true'

    try:
        trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
    except ValueError:
        abort(400, '购买日期格式错误，应为 YYYY-MM-DD')

    try:
        # 1. 调用已有的万能工具函数，计算真正的确认日 (T+1/T+2)
        confirm_date = get_confirm_date(trade_date, fund_type=fund_type, is_after_15=is_after_15)

        # 2. 利用原逻辑反推"实际净值日（用于拉取净值）"
        # 如果是 15:00 后，净值日 = 顺延的下一**开盘日**；否则净值日 = 原日期。
        actual_trade_date = trade_date
        if is_after_15:
            actual_trade_date = next_trading_day(trade_date)

        return jsonify(
            {
                'data': {
                    'actual_trade_date': actual_trade_date.isoformat(),  # 用于前端拉取净值
                    'confirm_date': confirm_date.isoformat(),  # 用于前端展示 T+1 确认日
                },
                'message': 'ok',
            }
        )
    except Exception as e:
        abort(400, f'确认日计算失败: {str(e)}')


@utils_bp.get('/enums/')
def get_enums():
    """下发前端需要的枚举中文标签（单一真相源，避免前后端各维护一套）。

    为什么单独开这个端点：
    - 持仓来源（Position.source）的中文 label 在后端 app.core.constants.POSITION_SOURCE_LABELS
      定义，是唯一真相源；前端展示「来源徽标」时必须从这里取，禁止手抄第二份（否则两处漂移）。
    - 免登录：探市页 /explore 免登录也展示持仓来源徽标，匿名访客需能读取。
    - 后续新增需要前后端一致的枚举标签，统一在此下发，不要在 /constants/index.ts 再写一份。
    """
    from app.core.asset_types import (
        ASSET_CATEGORY_LABELS,
        ASSET_TYPE_LABELS,
        INVESTMENT_MINOR_CATEGORIES,
    )
    from app.core.constants import MARKET_LABELS, OP_TYPE_LABEL, POSITION_SOURCE_LABELS

    return jsonify(
        {
            'data': {
                'position_source': POSITION_SOURCE_LABELS,
                'asset_type': ASSET_TYPE_LABELS,
                'asset_category': ASSET_CATEGORY_LABELS,
                # #1354：投资理财下的细分子类（写 minor_category），前端禁止再建平级大类
                'investment_minor': INVESTMENT_MINOR_CATEGORIES,
                'op_type_labels': OP_TYPE_LABEL,
                # #1286：市场码 → 中文标签（含无市场实体 '' → 通用）
                'market': MARKET_LABELS,
            },
            'message': 'ok',
        }
    )
