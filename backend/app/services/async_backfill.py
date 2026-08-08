# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 17:21
# File : async_backfill.py
# -*- coding: utf-8 -*-
"""
异步数据回填工具。

在用户新增持仓或自选标的时，后台静默拉取历史净值/行情数据。
使用轻量级线程，不阻塞主请求，失败静默处理。
"""

import threading

from loguru import logger

from app.core.database import SessionLocal
from app.core.db_utils import bulk_insert_if_not_exists
from app.domains.funds.models import DailyWorth, MoneyFundDailyWorth
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.sync.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter


def _backfill_fund_nav(fund_code: str):
    db = SessionLocal()
    try:
        adapter = XalphaAdapter()
        records = adapter.fetch_fund_nav(fund_code)
        if not records:
            return

        money_records = []
        normal_records = []
        for r in records:
            if r.get('is_money_fund'):
                money_records.append(
                    {
                        'fund_code': fund_code,
                        'date': r['date'],
                        'nav_per_10k': r['unit_nav'],
                    }
                )
            else:
                normal_records.append(
                    {
                        'fund_code': fund_code,
                        'date': r['date'],
                        'unit_nav': r['unit_nav'],
                        'acc_nav': r.get('acc_nav', 0),
                    }
                )

        if normal_records:
            total = bulk_insert_if_not_exists(
                db,
                DailyWorth,
                normal_records,
                unique_key='fund_code',  # 兼容旧参数
                unique_columns=['fund_code', 'date'],  # 实际使用的联合键
            )
            logger.info(f'异步回填基金 {fund_code} 净值 {total} 条')
        if money_records:
            total = bulk_insert_if_not_exists(
                db,
                MoneyFundDailyWorth,
                money_records,
                unique_key='fund_code',
                unique_columns=['fund_code', 'date'],
            )
            logger.info(f'异步回填货币基金 {fund_code} 收益 {total} 条')
    except Exception as e:
        db.rollback()
        logger.warning(f'异步回填基金 {fund_code} 净值失败: {e}')
    finally:
        db.close()


def _backfill_stock_price(symbol: str):
    db = SessionLocal()
    try:
        sec = db.query(Security).filter(Security.symbol == symbol).first()
        if not sec:
            return
        security_id = sec.id
        stock_symbol = sec.symbol

        adapter = AkshareAdapter()
        records = adapter.fetch_stock_price(symbol)
        if not isinstance(records, list) or not records:
            return

        allowed_columns = {c.name for c in PriceHistory.__table__.columns}
        clean_records = []
        for r in records:
            r['security_id'] = security_id
            r['symbol'] = stock_symbol
            filtered = {k: v for k, v in r.items() if k in allowed_columns}
            clean_records.append(filtered)

        if clean_records:
            total = bulk_insert_if_not_exists(
                db,
                PriceHistory,
                clean_records,
                unique_key='symbol',
                unique_columns=['symbol', 'trade_date'],
            )
            logger.info(f'异步回填股票 {symbol} 行情 {total} 条')
    except Exception as e:
        db.rollback()
        logger.warning(f'异步回填股票 {symbol} 行情失败: {e}')
    finally:
        db.close()


def trigger_backfill(asset_type: str, code: str):
    """
    触发异步回填。根据资产类型自动选择回填方式。

    Args:
        asset_type: 'fund' 或 'stock'
        code: 基金代码（6位数字）或股票代码（如 SH600519）
    """
    if asset_type == 'fund':
        target_func = _backfill_fund_nav
    elif asset_type in ('stock', 'etf', 'bond'):
        target_func = _backfill_stock_price
    else:
        return

    thread = threading.Thread(target=target_func, args=(code,), daemon=True)
    thread.start()
    logger.debug(f'已触发异步回填: {asset_type} {code}')
