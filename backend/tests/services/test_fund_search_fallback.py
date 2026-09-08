# -*- coding: utf-8 -*-
"""基金搜索外部兜底回归测试（#1363）。

本地 funds 表无命中时应走 akshare fund_name_em 兜底；历史 bug：import 类名
误拼 AKShareAdapter → ImportError 被 except 静默吞掉，兜底自引入起从未生效。
"""

from app.domains.funds.models import Fund
from app.services.fund_service import FundService
from app.services.sync.adapters.akshare_adapter import AkshareAdapter


def test_external_fallback_hits_when_local_miss(monkeypatch, db):
    """本地无命中时外部兜底应命中（mock 适配器数据源，隔离外部网络）。

    防御点：
    1) 确保本地 funds 表不含 026029，否则会命中本地而非外部兜底，失去回归意义；
    2) _FUND_NAME_EM_CACHE 是进程级缓存，全量套件里其他用例可能已预热它，
       导致本测试的 monkeypatch 被跳过、走陈旧缓存。故用 monkeypatch 整体替换
       缓存对象（而非改其内部字段），确保必走被 mock 的 fetch_fund_list，
       且测试后由 monkeypatch 自动还原，避免引用错位（否则会出现
       「本地单跑通过、CI 全量失败」的假象）。
    """
    # 防御 1：清掉可能残留的 026029（函数级内存库一般已空，这里仅作显式保证）
    db.query(Fund).filter(Fund.fund_code == '026029').delete()
    db.commit()
    # 防御 2：整体替换进程级缓存对象，强制走被 mock 的 fetch_fund_list
    monkeypatch.setattr(FundService, '_FUND_NAME_EM_CACHE', {'ts': 0.0, 'data': None})
    monkeypatch.setattr(
        AkshareAdapter,
        'fetch_fund_list',
        lambda self: [{'fund_code': '026029', 'name': '银河水星现金添利货币A', 'fund_type': '货币型'}],
    )
    results = FundService.search_funds(db, '026029')
    assert results, '本地无命中时外部兜底应生效（#1363 回归）'
    assert results[0]['code'] == '026029'
    assert results[0]['is_money_fund'] is True
