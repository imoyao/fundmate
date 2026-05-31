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
from app.domains.funds.models import DailyWorth, MoneyFundDailyWorth
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter
from app.services.sync.money_fund_utils import compute_money_fund_yields


def _backfill_fund_nav(fund_code: str):
    db = SessionLocal()
    try:
        adapter = XalphaAdapter()
        fund, is_money_fund = adapter.get_fund_with_type(fund_code)
        if fund is None:
            return

        nav_df = fund.price
        if nav_df is None or nav_df.empty:
            return

        if is_money_fund:
            records = compute_money_fund_yields(nav_df)
            for r in records:
                r['fund_code'] = fund_code
            target_model = MoneyFundDailyWorth
        else:
            records = []
            for idx, row in nav_df.iterrows():
                date_val = idx.date() if hasattr(idx, 'date') else idx
                records.append(
                    {
                        'fund_code': fund_code,
                        'date': date_val,
                        'unit_nav': float(row.get('netvalue', 0)),
                        'acc_nav': float(row.get('totvalue', 0)),
                    }
                )
            target_model = DailyWorth

        existing_dates = {row[0] for row in db.query(target_model.date).filter_by(fund_code=fund_code).all()}
        new_records = [r for r in records if r['date'] not in existing_dates]
        if new_records:
            db.bulk_insert_mappings(target_model, new_records)
            db.commit()
            logger.info(f'异步回填基金 {fund_code} 净值 {len(new_records)} 条')
    except Exception as e:
        logger.warning(f'异步回填基金 {fund_code} 净值失败: {e}')
    finally:
        db.close()


def _backfill_stock_price(symbol: str):
    """
    回填单只股票的全部历史行情。
    此函数在线程中运行，所有异常被静默处理。
    """
    from app.core.database import SessionLocal
    from app.domains.price_history.models import PriceHistory
    from app.domains.securities.models import Security
    from app.services.sync.adapters.akshare_adapter import AkshareAdapter

    db = SessionLocal()
    try:
        # 查找 security_id
        sec = db.query(Security).filter(Security.symbol == symbol).first()
        if not sec:
            return

        adapter = AkshareAdapter()
        records = adapter.fetch_stock_price(symbol)
        if not isinstance(records, list) or not records:
            return

        # 关联 security_id 并去重
        for r in records:
            r['security_id'] = sec.id

        existing = set(
            (row.security_id, row.trade_date)
            for row in db.query(PriceHistory.security_id, PriceHistory.trade_date)
            .filter(PriceHistory.security_id == sec.id)
            .all()
        )
        new_records = [r for r in records if (r['security_id'], r['trade_date']) not in existing]
        if new_records:
            db.bulk_insert_mappings(PriceHistory, new_records)
            db.commit()
            logger.info(f'异步回填股票 {symbol} 行情 {len(new_records)} 条')
    except Exception as e:
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
