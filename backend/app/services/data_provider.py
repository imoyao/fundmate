# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/12 18:33
# File : data_provider.py
"""数据提供者 - 基于 xalpha 获取并同步基金、证券、可转债等数据"""

import random
import time
from datetime import date, timedelta
from functools import wraps

import pandas as pd
import xalpha as xa
from loguru import logger

from app.core.database import SessionLocal
from app.core.symbol_utils import get_normalizer
from app.domains.funds.models import DailyWorth

# xalpha 已在 app.database 中通过 xa.set_backend() 配置了 CSV 缓存，此处直接使用


def retry_and_sleep(max_retries=3, base_delay=1.0):
    """简单的重试+请求间隔装饰器"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    time.sleep(base_delay + random.uniform(0.3, 1.0))
                    return result
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        wait = base_delay * (2**attempt) + random.uniform(0.5, 2.0)
                        logger.warning(f'[{func.__name__}] 第 {attempt + 1} 次失败，{wait:.1f}s 后重试: {e}')
                        time.sleep(wait)
            logger.error(f'[{func.__name__}] 重试 {max_retries} 次后仍失败: {last_error}')
            return None  # 静默失败，不阻断后续任务

        return wrapper

    return decorator


class DataProvider:
    """对外提供数据同步服务，所有方法接受可选的 db session"""

    # ── 基金相关 ──────────────────────────────

    @staticmethod
    @retry_and_sleep(max_retries=3, base_delay=1.5)
    def sync_fund_daily_worth(fund_code: str, days_back: int = 30, db=None):
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            import xalpha as xa

            info = xa.fundinfo(fund_code)
            nav_df = info.price
            if nav_df is None or nav_df.empty:
                return
            # 强制转换索引为 DatetimeIndex，避免 numpy.ndarray 导致的比较错误
            nav_df.index = pd.to_datetime(nav_df.index)
            start_date = pd.Timestamp(date.today() - timedelta(days=days_back))
            nav_df = nav_df[nav_df.index >= start_date]

            count = 0
            for idx, row in nav_df.iterrows():
                nav_date = idx.date() if hasattr(idx, 'date') else pd.Timestamp(idx).date()
                unit_nav = float(row['unit_nav'])
                acc_nav = float(row.get('acc_nav', unit_nav))
                existing = db.query(DailyWorth).filter_by(fund_code=fund_code, date=nav_date).first()
                if not existing:
                    db.add(DailyWorth(fund_code=fund_code, date=nav_date, unit_nav=unit_nav, acc_nav=acc_nav))
                    count += 1
            db.commit()
            logger.info(f'已同步 {fund_code} 近 {days_back} 天净值，新增 {count} 条')
        except Exception as e:
            logger.error(f'{fund_code} 净值同步失败: {e}')
            db.rollback()
        finally:
            if close_db:
                db.close()

    # ── 证券相关 ──────────────────────────────
    @staticmethod
    @retry_and_sleep(max_retries=3, base_delay=1.0)
    def sync_security_daily_quote(symbol: str, days_back: int = 5, db=None):
        """
        获取证券近期日线行情，打印最新收盘价到日志。
        传入的 symbol 应为标准化后的代码 (如 HK00700, SH600519, US:AAPL)。
        该方法内部会再标准化一次，以兼容可能的旧格式。
        """
        try:
            normalizer = get_normalizer()

            # 防御性标准化：若是旧格式，先转为标准格式
            norm_code, market = normalizer.normalize(symbol)
            if not norm_code:
                logger.warning(f'无法识别证券代码: {symbol}')
                return

            # 转换为 xalpha 需要的代码
            xa_code = normalizer.to_xalpha_code(norm_code)
            if not xa_code:
                logger.warning(f'无法将标准化代码转换为 xalpha 格式: {norm_code}')
                return

            today_str = date.today().isoformat()
            logger.debug(f'获取 {symbol} -> {xa_code} 近 {days_back} 天行情')
            df = xa.get_daily(xa_code, prev=days_back, end=today_str)

            if df is None or df.empty:
                logger.warning(f'{symbol} 无行情数据')
                return

            latest = df.iloc[-1]
            if 'close' in df.columns:
                close_price = latest['close']
                trade_date = latest.name
                logger.info(f'{symbol} 最新行情 | 日期:{trade_date} 收盘:{close_price:.2f}')
            else:
                logger.warning(f'{symbol} 返回数据缺少 close 列，列名: {df.columns.tolist()}')
        except Exception as e:
            logger.error(f'{symbol} 行情同步失败: {e}')

    # ── 货币基金 ──────────────────────────────

    @staticmethod
    @retry_and_sleep(max_retries=2, base_delay=1.0)
    def sync_money_fund(fund_code: str, db=None):
        """同步货币基金万份收益与七日年化（不落库，仅日志打印）"""
        try:
            import xalpha as xa

            mf = xa.mfundinfo(fund_code)
            if not mf.price.empty:
                recent = mf.price.iloc[-1]
                logger.info(
                    f"{fund_code} 万份收益:{recent.get('unit_nav', 'N/A')}, " f"七日年化:{recent.get('acc_nav', 'N/A')}"
                )
        except Exception as e:
            logger.error(f'{fund_code} 货币基金同步失败: {e}')

    # ── 预留扩展 ──────────────────────────────

    @staticmethod
    def sync_fund_list(db=None):
        """首次运行时可手动调用，通过外部数据源（如 AKShare/本地CSV）填充基金基本信息。
        目前建议从已准备好的测试数据开始，未来可对接更稳定的全量基金列表接口。
        """
        logger.info('基金列表同步尚未实现，可使用 tools/insert_test_data.py 手动添加。')
        # 可直接从 xalpha 的基金信息缓存中提取？xalpha 没有全量列表，暂不实现。
        pass
