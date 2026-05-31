# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:24
# File : xalpha_adapter.py
# -*- coding: utf-8 -*-
# app/services/sync/adapters/xalpha_adapter.py
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
import xalpha as xa
from loguru import logger

from app.services.sync.adapters.base import DataSourceAdapter


class XalphaAdapter(DataSourceAdapter):
    def __init__(self):
        xa.set_backend(backend='csv', path='data/xalpha_cache')
        self._fund_nav_errors = None
        self.logger = logger.bind(adapter='xalpha')

    def get_name(self) -> str:
        return 'xalpha'

    def get_version(self) -> str:
        return xa.__version__ if hasattr(xa, '__version__') else 'unknown'

    # ── xalpha 不支持基金列表 ──
    def fetch_fund_list(self) -> List[dict]:
        raise NotImplementedError('xalpha 不支持全市场基金列表')

    # ── 基金净值 ──
    def fetch_fund_nav(
        self,
        fund_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        """获取基金历史净值，使用 xalpha 官方 API"""
        if not hasattr(self, '_fund_nav_errors'):
            self._fund_nav_errors = set()

        try:
            # 正确用法：xa.fundinfo(code) 返回基金对象，其 .price 属性是 DataFrame
            fund = xa.fundinfo(fund_code)
            nav = fund.price  # DataFrame，列名: date, netvalue, totvalue

            if nav is None or nav.empty:
                self.logger.debug(f'基金 {fund_code} 无净值数据（可能为后端份额或场内ETF），已跳过')
                return []

            # 按日期范围过滤
            if start_date:
                nav = nav[nav['date'] >= pd.Timestamp(start_date)]
            if end_date:
                nav = nav[nav['date'] <= pd.Timestamp(end_date)]

            records = []
            for _, row in nav.iterrows():
                records.append(
                    {
                        'fund_code': fund_code,
                        'date': row['date'].date()
                        if hasattr(row['date'], 'date')
                        else pd.Timestamp(row['date']).date(),
                        'unit_nav': float(row['netvalue']),
                        'acc_nav': float(row['totvalue']),
                    }
                )
            return records
        except xa.exceptions.FundTypeError:
            self.logger.debug(f'基金 {fund_code} 是货币基金，跳过净值同步')
            return []
        except Exception as e:
            # 首次报错才记录日志，避免刷屏
            if not hasattr(self, '_fund_nav_errors'):
                self._fund_nav_errors = set()
            if fund_code not in self._fund_nav_errors:
                self.logger.warning(f'获取基金 {fund_code} 净值失败: {e}')
                self._fund_nav_errors.add(fund_code)
            return []

    # 在 app/services/sync/adapters/xalpha_adapter.py 类中新增方法

    def fetch_fund_fee(self, fund_code: str) -> Dict[str, Any]:
        """
        获取基金费率信息 (xalpha)
        返回字典包含:
            - purchase_rate: 优惠申购费率 (float 百分比)
            - redemption_schedule: 赎回费率阶梯列表 [{'start': int, 'end': int or None, 'rate': float}, ...]
            - management_rate: 管理费率 (暂不可用, 返回 None)
        解析失败返回空字典。
        """
        result = {}
        try:
            fund = xa.fundinfo(fund_code)
        except Exception as e:
            self.logger.warning(f'xalpha 初始化基金 {fund_code} 失败: {e}')
            return result

        # 申购费率 (优惠后)
        try:
            rate_str = fund.rate  # 如 "0.15%"
            if rate_str and isinstance(rate_str, str):
                result['purchase_rate'] = float(rate_str.rstrip('%'))
        except Exception:
            pass

        # 赎回费率阶梯
        try:
            feeinfo = fund.feeinfo  # 如 ['小于7天', '1.50%', '大于等于7天，小于30天', '0.75%', ...]
            if isinstance(feeinfo, list) and len(feeinfo) >= 2:
                schedule = []
                # 按相邻两个一组解析
                for i in range(0, len(feeinfo), 2):
                    if i + 1 >= len(feeinfo):
                        break
                    desc = feeinfo[i]  # "小于7天"
                    rate_str = feeinfo[i + 1]  # "1.50%"
                    rate = float(rate_str.rstrip('%')) if isinstance(rate_str, str) else None
                    # 解析天数区间 (简化处理: 提取数字)
                    import re

                    numbers = re.findall(r'\d+', desc)
                    if '大于等于' in desc and '小于' in desc:
                        start = int(numbers[0]) if numbers else None
                        end = int(numbers[1]) if len(numbers) > 1 else None
                    elif '小于' in desc:
                        start = 0
                        end = int(numbers[0]) if numbers else None
                    elif '大于等于' in desc:
                        start = int(numbers[0]) if numbers else None
                        end = None
                    else:
                        start = None
                        end = None
                    if start is not None and rate is not None:
                        schedule.append({'start_day': start, 'end_day': end, 'rate': rate})
                result['redemption_schedule'] = schedule
        except Exception:
            pass

        return result

    # ── 基金经理 ──
    def fetch_fund_manager(self, fund_code: str) -> List[dict]:
        raise NotImplementedError('xalpha 不支持基金经理信息，请使用 AkshareAdapter')

    # ── xalpha 不支持股票相关 ──
    def fetch_stock_list(self, market: Optional[str] = None) -> List[dict]:
        raise NotImplementedError('xalpha 不支持股票列表')

    def fetch_stock_price(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        raise NotImplementedError('xalpha 不支持股票行情')
