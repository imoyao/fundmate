# -*- coding: utf-8 -*-
"""
Xalpha 数据源适配器（基金净值、费率）。

职责：
- 封装 xalpha 库的调用
- 将 xalpha 返回的数据转换为统一格式的字典列表
- 所有方法防御性地处理 None / 空数据 / 类型异常
"""

from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
import xalpha as xa
from loguru import logger

from app.services.sync.adapters.base import DataSourceAdapter


class XalphaAdapter(DataSourceAdapter):
    def __init__(self):
        self.logger = logger.bind(adapter='xalpha')
        # 启用 xalpha 本地 CSV 缓存，避免重复网络请求
        xa.set_backend(backend='csv', path='data/xalpha_cache')

    def get_name(self) -> str:
        return 'xalpha'

    def get_version(self) -> str:
        return getattr(xa, '__version__', 'unknown')

    # ── 基金列表（不支持） ──

    def fetch_fund_list(self) -> List[dict]:
        raise NotImplementedError('xalpha 不支持全市场基金列表')

    # ── 基金净值 ──

    def fetch_fund_nav(
        self,
        fund_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        """
        获取基金历史净值。
        返回统一格式的列表，单只基金失败返回空列表，不抛异常。
        """
        # 防御：记录已报错的基金代码，避免日志刷屏
        if not hasattr(self, '_fund_nav_errors'):
            self._fund_nav_errors = set()

        try:
            fund = xa.fundinfo(fund_code)
            nav_df = fund.price
        except xa.exceptions.FundTypeError:
            # 货币基金：静默跳过
            self.logger.debug(f'基金 {fund_code} 是货币基金，跳过净值同步')
            return []
        except Exception as e:
            self._log_fund_error_once(fund_code, f'xalpha 初始化失败: {e}')
            return []

        if nav_df is None or nav_df.empty:
            return []

        return self._parse_nav_dataframe(nav_df, fund_code)

    def _parse_nav_dataframe(self, nav_df: pd.DataFrame, fund_code: str) -> List[dict]:
        """将 xalpha 返回的净值 DataFrame 转换为统一格式的字典列表"""
        records = list()

        # 日期过滤
        nav_df = self._filter_nav_by_date(nav_df)

        for idx, row in nav_df.iterrows():
            records.append(
                {
                    'fund_code': fund_code,
                    'date': self._extract_date(idx),
                    'unit_nav': float(row.get('netvalue', 0)),
                    'acc_nav': float(row.get('totvalue', 0)),
                }
            )
        return records

    @staticmethod
    def _filter_nav_by_date(nav_df: pd.DataFrame) -> pd.DataFrame:
        """过滤净值 DataFrame 的日期范围（预留扩展）"""
        return nav_df

    @staticmethod
    def _extract_date(idx) -> date:
        """从 DataFrame 索引中提取日期对象"""
        if hasattr(idx, 'date'):
            return idx.date()
        return pd.Timestamp(idx).date()

    def _log_fund_error_once(self, fund_code: str, message: str) -> None:
        """同一只基金的同类型错误只记录一次，避免日志刷屏"""
        if fund_code not in self._fund_nav_errors:
            self.logger.warning(f'基金 {fund_code}: {message}')
            self._fund_nav_errors.add(fund_code)

    # ── 基金经理（不支持） ──

    def fetch_fund_manager(self, fund_code: str) -> List[dict]:
        raise NotImplementedError('xalpha 不支持基金经理信息，请使用 AkshareAdapter')

    # ── 股票相关（不支持） ──

    def fetch_stock_list(self, market: Optional[str] = None) -> List[dict]:
        raise NotImplementedError('xalpha 不支持股票列表')

    def fetch_stock_price(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        raise NotImplementedError('xalpha 不支持股票行情')

    # ── 费率信息 ──

    def fetch_fund_fee(self, fund_code: str) -> Dict[str, Any]:
        """
        获取基金费率信息。
        返回字典包含 purchase_rate 和 redemption_schedule。
        解析失败返回空字典。
        """
        try:
            fund = xa.fundinfo(fund_code)
        except Exception as e:
            self.logger.warning(f'xalpha 初始化基金 {fund_code} 失败: {e}')
            return {}

        result = {}

        # 申购费率
        purchase_rate = self._extract_purchase_rate(fund)
        if purchase_rate is not None:
            result['purchase_rate'] = purchase_rate

        # 赎回费率阶梯
        schedule = self._parse_redemption_schedule(fund.feeinfo)
        if schedule:
            result['redemption_schedule'] = schedule

        return result

    @staticmethod
    def _extract_purchase_rate(fund) -> Optional[float]:
        """提取申购费率（优惠后）"""
        try:
            rate_str = fund.rate
            if rate_str and isinstance(rate_str, str):
                return float(rate_str.rstrip('%'))
        except (ValueError, AttributeError):
            pass
        return None

    @staticmethod
    def _parse_redemption_schedule(feeinfo) -> List[dict]:
        """
        将 xalpha 返回的赎回费率列表解析为结构化阶梯。

        xalpha 格式: ['小于7天', '1.50%', '大于等于7天，小于30天', '0.75%', ...]
        解析后: [{"start_day": 0, "end_day": 7, "rate": 1.5}, ...]
        """
        schedule = list()
        if not isinstance(feeinfo, list) or len(feeinfo) < 2:
            return schedule

        import re

        for i in range(0, len(feeinfo), 2):
            if i + 1 >= len(feeinfo):
                break

            desc = feeinfo[i]
            rate_str = feeinfo[i + 1]

            # 解析费率百分比
            try:
                rate = float(rate_str.rstrip('%'))
            except (ValueError, AttributeError):
                continue

            # 解析天数区间
            numbers = re.findall(r'\d+', desc)
            if not numbers:
                continue

            if '大于等于' in desc and '小于' in desc:
                start = int(numbers[0])
                end = int(numbers[1]) if len(numbers) > 1 else None
            elif '小于' in desc:
                start = 0
                end = int(numbers[0])
            elif '大于等于' in desc:
                start = int(numbers[0])
                end = None
            else:
                continue

            schedule.append({'start_day': start, 'end_day': end, 'rate': rate})

        return schedule
