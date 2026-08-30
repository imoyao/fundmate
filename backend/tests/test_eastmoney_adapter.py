# -*- coding: utf-8 -*-
# backend/tests/test_eastmoney_adapter.py
"""EastmoneyAdapter 单元测试（#1168 设计 A）。

为什么这样测：EastmoneyAdapter 是组合适配器，本身不含抓取逻辑，只委托 akshare /
xalpha / company_resolver。因此测试重点是"委托关系正确"与"对外名/版本正确"，
网络相关一律 mock，不真发请求（遵循 AGENTS.md 测试纪律）。
"""

from app.services.sync.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.adapters.eastmoney_adapter import EastmoneyAdapter
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter


def test_eastmoney_adapter_name_version():
    """对外名称必须是 'eastmoney'，版本号带 'eastmoney-composite' 前缀。"""
    adapter = EastmoneyAdapter()
    assert adapter.get_name() == 'eastmoney'
    assert 'eastmoney-composite' in adapter.get_version()


def test_eastmoney_fetch_fund_list_delegates(monkeypatch):
    """fetch_fund_list 必须委托给内部 akshare 适配器（数据同源，可验证）。"""
    fixed = [{'fund_code': '000001', 'name': '华夏成长', 'company_name': ''}]
    monkeypatch.setattr(AkshareAdapter, 'fetch_fund_list', lambda self: fixed)
    adapter = EastmoneyAdapter()
    assert adapter.fetch_fund_list() == fixed


def test_eastmoney_fetch_fund_nav_delegates(monkeypatch):
    """fetch_fund_nav 必须委托给内部 xalpha 适配器（东财直连净值）。"""
    fixed = [{'fund_code': '000001', 'date': '2026-01-01', 'unit_nav': 1.0}]
    monkeypatch.setattr(XalphaAdapter, 'fetch_fund_nav', lambda self, code, sd=None, ed=None: fixed)
    adapter = EastmoneyAdapter()
    assert adapter.fetch_fund_nav('000001') == fixed


def test_eastmoney_fetch_fund_company(monkeypatch):
    """fetch_fund_company 必须委托 company_resolver.fetch_fund_company_list。

    注意：适配器模块是 `from ... import fetch_fund_company_list` 直接导入，
    故需 patch 适配器模块内的该名字，而非 company_resolver 模块。
    """
    fixed = [{'code': '80163340', 'name': '安信基金'}]
    monkeypatch.setattr(
        'app.services.sync.adapters.eastmoney_adapter.fetch_fund_company_list',
        lambda: fixed,
    )
    adapter = EastmoneyAdapter()
    assert adapter.fetch_fund_company() == fixed
