# -*- coding: utf-8 -*-
# app/services/sync/adapters/eastmoney_adapter.py
"""天天基金/东财一等数据源适配器（组合 akshare + xalpha）。

为什么存在：此前 akshare 与 xalpha 是两个平行适配器，fund_list 等 Job 写死绑
akshare。#1168 把"天天基金/东财"提升为一等数据源——本适配器复用 akshare 的列表/
经理/详情/股票接口与 xalpha 的东财直连净值/费率，对外统一为 'eastmoney'，并补充
akshare 缺失的基金公司 code 拉取（fetch_fund_company）。
"""

from datetime import date
from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.sync.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.adapters.base import DataSourceAdapter
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter
from app.services.sync.company_resolver import fetch_fund_company_list


class EastmoneyAdapter(DataSourceAdapter):
    def __init__(self):
        self._akshare = AkshareAdapter()
        self._xalpha = XalphaAdapter()
        self.logger = logger.bind(adapter='eastmoney')

    def get_name(self) -> str:
        return 'eastmoney'

    def get_version(self) -> str:
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        return f'eastmoney-composite/akshare-{getattr(ak, "__version__", "unknown")}'

    def fetch_fund_list(self) -> List[dict]:
        return self._akshare.fetch_fund_list()

    def fetch_fund_manager(self, fund_code: str) -> List[dict]:
        return self._akshare.fetch_fund_manager(fund_code)

    def fetch_fund_detail(self, fund_code: str) -> Dict[str, Any]:
        return self._akshare.fetch_fund_detail(fund_code)

    def fetch_stock_list(self, market: Optional[str] = None) -> List[dict]:
        return self._akshare.fetch_stock_list(market)

    def fetch_stock_price(
        self, symbol: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> List[dict]:
        return self._akshare.fetch_stock_price(symbol, start_date, end_date)

    def fetch_fund_nav(
        self, fund_code: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> List[dict]:
        return self._xalpha.fetch_fund_nav(fund_code, start_date, end_date)

    def fetch_fund_fee(self, fund_code: str) -> Dict[str, Any]:
        return self._xalpha.fetch_fund_fee(fund_code)

    def fetch_fund_company(self) -> List[Dict[str, str]]:
        """拉天天基金 fund_company 表（code+name），委托 company_resolver。"""
        return fetch_fund_company_list()
