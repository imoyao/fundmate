# -*- coding: utf-8 -*-
"""全市场名录类 job 的「空 ⇒ 失败」回归网。

事故形态（#1179 同族）：`fund_list` / `stock_list` / `fund_scale` 是**全市场列表**类 job
（基金上万只、证券数千只），抓取结果为 0 条只可能是上游结构变更 / 接口异常 / 解析失配，
绝不是「今天没有数据」。旧行为 `_allow_empty_data=True` 把它当成功 ⇒
市场底座静默停更、日志一片绿。

本文件钉住：抓到 0 条 ⇒ job **failed**；抓到数据 ⇒ 仍 success。
"""

from app.services.sync.jobs.fund_list_job import FundListSyncJob
from app.services.sync.jobs.fund_scale_job import FundScaleSyncJob
from app.services.sync.jobs.stock_list_job import StockListSyncJob


class _EmptyAdapter:
    """三个全市场数据源全部返回空（模拟上游结构变更 / 解析失配）。"""

    def fetch_fund_list(self):
        return []

    def fetch_security_catalog(self):
        return []

    def fetch_fund_scale(self):
        return []


class _OkAdapter:
    """正常返回一条（用于确认「有数据时不该被误判成失败」）。"""

    def fetch_fund_list(self):
        return [{'fund_code': '000001', 'name': '测试基金'}]

    def fetch_security_catalog(self):
        return [{'symbol': '600000', 'name': '测试证券', 'type': 'stock'}]

    def fetch_fund_scale(self):
        return [{'fund_code': '000001', 'shares': '1.0', 'nav': '1.0'}]


def test_fund_list_empty_is_failure(db):
    """基金名录抓不到一条 ⇒ 必须 failed（不是 success）。"""
    job = FundListSyncJob(_EmptyAdapter(), db)
    result = job.run(targets=['__full__'])
    assert result['status'] == 'failed', '上游一条都没抓到却报 success，市场底座会静默停更'
    assert '空数据' in str(result.get('stats', {}).get('error', ''))


def test_stock_list_empty_is_failure(db):
    """证券名录抓不到一条 ⇒ 必须 failed。"""
    job = StockListSyncJob(_EmptyAdapter(), db)
    result = job.run(targets=['__full__'])
    assert result['status'] == 'failed'


def test_fund_scale_empty_is_failure(db):
    """基金规模列表抓不到一条 ⇒ 必须 failed。"""
    job = FundScaleSyncJob(_EmptyAdapter(), db)
    result = job.run(targets=['__full__'])
    assert result['status'] == 'failed'


def test_fund_list_with_data_still_succeeds(db):
    """有数据时不得被误判成失败（守卫不能变成常态红灯）。"""
    job = FundListSyncJob(_OkAdapter(), db)
    result = job.run(targets=['__full__'])
    assert result['status'] == 'success', result
    assert result['stats']['success'] == 1


def test_stock_list_with_data_still_succeeds(db):
    job = StockListSyncJob(_OkAdapter(), db)
    result = job.run(targets=['__full__'])
    assert result['status'] == 'success', result


def test_fund_scale_with_data_still_succeeds(db):
    job = FundScaleSyncJob(_OkAdapter(), db)
    result = job.run(targets=['__full__'])
    assert result['status'] == 'success', result
