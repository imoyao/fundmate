# -*- coding: utf-8 -*-
"""基金搜索外部兜底回归测试（#1363）。

本地 funds 表无命中时应走 akshare fund_name_em 兜底；历史 bug：import 类名
误拼 AKShareAdapter → ImportError 被 except 静默吞掉，兜底自引入起从未生效。
"""

from app.services.fund_service import FundService
from app.services.sync.adapters.akshare_adapter import AkshareAdapter


def test_external_fallback_hits_when_local_miss(monkeypatch, db):
    """本地无命中时外部兜底应命中（mock 适配器数据源，隔离外部网络）。

    注意：_FUND_NAME_EM_CACHE 是进程级缓存，全量套件里其他用例可能已预热它，
    导致本测试的 monkeypatch 被跳过、走陈旧缓存。故测试前必须把缓存清冷，
    确保真正走被 mock 的 fetch_fund_list（否则会出现「本地单跑通过、CI 全量失败」的假象）。
    """
    cache = FundService._FUND_NAME_EM_CACHE
    saved_data, saved_ts = cache['data'], cache['ts']
    cache['data'], cache['ts'] = None, 0.0
    try:
        monkeypatch.setattr(
            AkshareAdapter,
            'fetch_fund_list',
            lambda self: [{'fund_code': '026029', 'name': '银河水星现金添利货币A', 'fund_type': '货币型'}],
        )
        results = FundService.search_funds(db, '026029')
        assert results, '本地无命中时外部兜底应生效（#1363 回归）'
        assert results[0]['code'] == '026029'
        assert results[0]['is_money_fund'] is True
    finally:
        # 还原，避免本测试的兜底数据污染后续用例
        cache['data'], cache['ts'] = saved_data, saved_ts
