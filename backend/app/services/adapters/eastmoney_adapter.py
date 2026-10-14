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
import threading
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

#: 东财基金搜索联想接口（#2037 方案 A 的**单只基金公司取数口**）。
#: 一次请求即返回 `FundBaseInfo.JJGS`（基金公司简称）/ `JJGSID`（东财权威 code）。
#:
#: 为什么不用 akshare `fund_info_ths`（既有 `fetch_fund_detail` 的取数口）：#2037 要在**详情页
#: 请求路径**上按需回填，实测 `import akshare` 单独就 4.65s、单次 `fund_info_ths` 0.57s——
#: 前者会把首屏直接拖到 5s 量级，且为拿一个公司名付出整条重链路（V8 / 限流面全占）。
_FUND_SUGGEST_URL = 'https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx'

# 该接口的**模块级长连接 Session**（2026-10-11 实测驱动，勿退回 `requests.get`）：
# 首次请求要付 TLS 握手 + DNS，实测 **1.8~2.8s**；连接复用后单次只要 **43~87ms**（约 30 倍）。
# 本函数在详情页请求路径上，模块级 `requests.get` 每次都新建 Session，等于把握手成本付给
# 每个冷开用户——那才是「按需回填拖垮首屏」的主要来源，不是接口本身慢。
# `requests.Session` **不是线程安全的**（连接池会被并发读写打乱），故请求期间持锁：
# 实测带锁并发 3 只 = 2.9s 总耗时（仅首只付握手），无锁并发 = 3.5s 且两只都吃到握手。
_suggest_session: Optional[requests.Session] = None
_suggest_session_lock = threading.Lock()


def _get_suggest_session() -> requests.Session:
    """取模块级 Session（惰性建 + 双检锁）。"""
    global _suggest_session
    if _suggest_session is None:
        with _suggest_session_lock:
            if _suggest_session is None:
                # requests_patch（app 启动时安装）会在 Session.__init__ 上挂重试适配器并
                # 强制直连；此处直接新建即可继承，无需自己配 headers / adapter。
                _suggest_session = requests.Session()
    return _suggest_session


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


def fetch_fund_company_of(fund_code: str, timeout: int = 6) -> Optional[Dict[str, str]]:
    """查**单只**基金的基金公司（`{'name': 简称, 'code': 东财权威 code}`），查不到返回 None。

    #2037 方案 A（L3 按需回填）的取数口：详情页发现 `funds.company_id` 为空时按 symbol
    单只回填，不做全库（`data-strategy.md` L3「按需取 + 缓存 + 可降级」）。

    **超时 6s 的取舍**：复用连接后单次实测 43~87ms，6s 是「上游已明显异常」的阈值；
    留足 `requests_patch` 的 Retry（3 次）仍不至于让首屏等到分钟级。

    **为什么 `code` 只是随行返回、调用方不必用**：`JJGSID` 与 `fetch_fund_company_list()`
    的 code 是同一体系（2026-10-11 实测：易方达 80000229 / 华夏 80000222 / 天弘 80041198
    两侧逐行一致），故仍由 `company_resolver.resolve_company_identity` 统一解析——
    本函数只负责把**东财简称**带出去，不做第二次身份解析，避免两份标准漂移。

    模糊搜索会返回多个候选，**必须按 `CODE` 精确回选**本只：直接取 `Datas[0]` 在 key
    命中多只（如「001」之于 001xxx 全系列，实测此时返回 None 而非错配）时会张冠李戴。
    命中项缺 `FundBaseInfo` 时视为查不到（返回 None），由调用方降级 `—`，
    不拿相邻基金的资料顶替。
    """
    code = (fund_code or '').strip()
    if not code:
        return None
    try:
        with _suggest_session_lock:  # Session 非线程安全，请求期间独占
            resp = _get_suggest_session().get(_FUND_SUGGEST_URL, params={'m': 1, 'key': code}, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning(f'查询基金 {code} 的基金公司失败: {e}')
        return None

    hit = next((d for d in (payload.get('Datas') or []) if d.get('CODE') == code), None)
    base = (hit or {}).get('FundBaseInfo') or {}
    name = (base.get('JJGS') or '').strip()
    if not name:
        return None
    return {'name': name, 'code': str(base.get('JJGSID') or '')}


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
