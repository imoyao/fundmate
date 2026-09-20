# -*- coding: utf-8 -*-
# app/services/adapters/eastmoney_adapter.py
"""天天基金/东财一等数据源适配器（组合 akshare + xalpha）。

为什么存在：此前 akshare 与 xalpha 是两个平行适配器，fund_list 等 Job 写死绑
akshare。#1168 把"天天基金/东财"提升为一等数据源——本适配器复用 akshare 的列表/
经理/详情/股票接口与 xalpha 的东财直连净值/费率，对外统一为 'eastmoney'，并补充
akshare 缺失的基金公司 code 拉取（fetch_fund_company）。
"""

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.services.adapters.akshare_adapter import AkshareAdapter
from app.services.adapters.base import DataSourceAdapter
from app.services.adapters.xalpha_adapter import XalphaAdapter

#: 天天基金基金公司列表（JS 里的 `op:[...]` 数组，每行 [code, name]）。
# 为什么取数在本模块、而不是 `sync/company_resolver.py`（#1607 批次 3）：这是**第三方取数**，
# 按 `architecture.md` §2「业务层不裸调第三方库、统一经 adapter 封装」应归适配器层；
# 此前是 resolver 自己裸 `requests.get`、适配器反向转调 resolver，依赖方向刚好反了
# （也是 R5 守卫抓出来的真实反向边）。
_EASTMONEY_COMPANY_URL = 'http://fund.eastmoney.com/js/jjjz_gs.js'


def fetch_fund_company_list() -> List[Dict[str, str]]:
    """抓取并解析天天基金基金公司列表，返回 [{code, name}, ...]。"""
    resp = requests.get(_EASTMONEY_COMPANY_URL, timeout=15)
    resp.encoding = 'utf-8'
    text = resp.text
    m = re.search(r'op:(\[.*?\])\s*}', text, re.DOTALL)
    if not m:
        logger.warning('解析基金公司列表失败：未找到 op 数组')
        return []
    arr = json.loads(m.group(1))
    return [{'code': str(row[0]), 'name': str(row[1])} for row in arr if len(row) >= 2]


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
        """拉天天基金 fund_company 表（code+name）。"""
        return fetch_fund_company_list()
