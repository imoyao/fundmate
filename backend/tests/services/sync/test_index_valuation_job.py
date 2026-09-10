# -*- coding: utf-8 -*-
"""测试 IndexValuationSyncJob：估值落库 / 覆盖式 upsert / 无文件指数跳过（#1285/#1394）。"""

from datetime import date

from app.domains.indices.models import IndexValuation
from app.services.sync.jobs.index_valuation_job import IndexValuationSyncJob


class _FakeAdapter:
    """假数据源：000300 有官方估值，999999 无（模拟无 indicator 文件的指数）。"""

    def fetch_index_valuation_csindex(self, index_code: str):
        if index_code != '000300':
            return []
        return [
            {
                'index_code': '000300',
                'index_name': '沪深300',
                'trade_date': date(2026, 8, 13),
                'pe_1': 14.6,
                'pe_2': 17.1,
                'dividend_yield_1': 2.5,
                'dividend_yield_2': 2.2,
                'source': 'csindex',
            },
            {
                'index_code': '000300',
                'index_name': '沪深300',
                'trade_date': date(2026, 8, 14),
                'pe_1': 14.73,
                'pe_2': 17.3,
                'dividend_yield_1': 2.52,
                'dividend_yield_2': 2.19,
                'source': 'csindex',
            },
        ]


def test_index_valuation_job_upsert(db):
    job = IndexValuationSyncJob(_FakeAdapter(), db)
    # 指定目标含一个无文件指数，应被跳过而非报错
    result = job.run(targets=['000300', '999999'])
    assert result['status'] == 'success'

    rows = db.query(IndexValuation).order_by(IndexValuation.trade_date).all()
    assert len(rows) == 2
    assert rows[0].index_name == '沪深300'
    assert float(rows[-1].pe_1) == 14.73
    assert float(rows[-1].dividend_yield_1) == 2.52


def test_index_valuation_job_idempotent(db):
    job = IndexValuationSyncJob(_FakeAdapter(), db)
    job.run(targets=['000300'])
    job.run(targets=['000300'])
    # 覆盖式 upsert：同 (index_code, trade_date) 不重复插入
    assert db.query(IndexValuation).count() == 2
