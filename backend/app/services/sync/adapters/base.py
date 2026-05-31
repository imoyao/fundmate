# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:23
# File : base.py
# -*- coding: utf-8 -*-
# app/services/sync/adapters/base.py

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional


class DataSourceAdapter(ABC):
    """所有数据源适配器的基类"""

    @abstractmethod
    def get_name(self) -> str:
        """返回数据源名称，如 'xalpha', 'akshare'"""
        pass

    @abstractmethod
    def get_version(self) -> str:
        """返回数据源版本号，用于审计"""
        pass

    # ── 基金相关 ──

    @abstractmethod
    def fetch_fund_list(self) -> List[dict]:
        """获取全市场公募基金基本信息"""
        pass

    @abstractmethod
    def fetch_fund_nav(
        self,
        fund_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        """获取指定基金的历史净值数据"""
        pass

    @abstractmethod
    def fetch_fund_manager(self, fund_code: str) -> List[dict]:
        """获取指定基金的基金经理信息"""
        pass

    # ── 股票相关 ──

    @abstractmethod
    def fetch_stock_list(self, market: Optional[str] = None) -> List[dict]:
        """获取指定市场的股票/ETF/可转债列表"""
        pass

    @abstractmethod
    def fetch_stock_price(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        """获取指定证券的历史日线行情"""
        pass

    # 基准指数（可选，暂不实现）
    # def fetch_benchmark_index(...)
