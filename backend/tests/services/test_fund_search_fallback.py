# -*- coding: utf-8 -*-
"""基金搜索外部兜底回归测试（#1363）。

本地 funds 表无命中时应走 akshare fund_name_em 兜底；历史 bug：import 类名
误拼 AKShareAdapter → ImportError 被 except 静默吞掉，兜底自引入起从未生效。
"""

from app.services.fund_service import FundService
from app.services.sync.adapters.akshare_adapter import AkshareAdapter


def test_external_fallback_hits_when_local_miss(monkeypatch, db):
    """本地无命中时外部兜底应命中（mock 适配器数据源，隔离外部网络）。"""
    monkeypatch.setattr(
        AkshareAdapter,
        'fetch_fund_list',
        lambda self: [{'fund_code': '026029', 'name': '银河水星现金添利货币A', 'fund_type': '货币型'}],
    )
    results = FundService.search_funds(db, '026029')
    assert results, '本地无命中时外部兜底应生效（#1363 回归）'
    assert results[0]['code'] == '026029'
    assert results[0]['is_money_fund'] is True
