# -*- coding: utf-8 -*-
"""测试 IndexValuationLgSyncJob：近 5 年窗口裁剪 / 覆盖式 upsert / 无源指数跳过（#1407）。"""

from datetime import date, timedelta

from app.domains.indices.models import IndexValuationBaseline
from app.services.index_percentile import PERCENTILE_WINDOW_DAYS
from app.services.sync.jobs.index_valuation_lg_job import LG_TARGETS, IndexValuationLgSyncJob


class _FakeAdapter:
    """假数据源：000300 有乐咕序列（含窗口外老点），999999 无覆盖。"""

    def fetch_index_pe_lg(self, index_code: str):
        if index_code != '000300':
            return []
        today = date.today()
        return [
            # 窗口外的老点（6 年前）——必须被裁掉
            {
                'index_code': '000300',
                'index_name': '沪深300',
                'trade_date': today - timedelta(days=PERCENTILE_WINDOW_DAYS + 100),
                'pe_ttm': 8.0,
                'source': 'lg',
            },
            # 窗口内两点
            {
                'index_code': '000300',
                'index_name': '沪深300',
                'trade_date': today - timedelta(days=90),
                'pe_ttm': 12.0,
                'source': 'lg',
            },
            {
                'index_code': '000300',
                'index_name': '沪深300',
                'trade_date': today - timedelta(days=30),
                'pe_ttm': 12.5,
                'source': 'lg',
            },
            # pe_ttm 为 None 的脏行——validate 应剔除
            {
                'index_code': '000300',
                'index_name': '沪深300',
                'trade_date': today - timedelta(days=10),
                'pe_ttm': None,
                'source': 'lg',
            },
        ]


def test_lg_job_trims_window_and_saves(db):
    job = IndexValuationLgSyncJob(_FakeAdapter(), db)
    result = job.run(targets=['000300', '999999'])
    assert result['status'] == 'success'

    rows = db.query(IndexValuationBaseline).order_by(IndexValuationBaseline.trade_date).all()
    # 窗口外老点与 None 行都被裁掉，只剩窗口内 2 点
    assert len(rows) == 2
    assert rows[0].pe_ttm == 12.0
    assert rows[1].pe_ttm == 12.5
    assert rows[0].source == 'lg'


def test_lg_job_upsert_idempotent(db):
    job = IndexValuationLgSyncJob(_FakeAdapter(), db)
    job.run(targets=['000300'])
    job.run(targets=['000300'])

    rows = db.query(IndexValuationBaseline).all()
    assert len(rows) == 2  # 重复跑不翻倍


def test_lg_targets_are_explicit_whitelist():
    """目标池必须显式（数据策略硬约束 §3）：空 targets 退化到白名单而非全库。"""
    assert LG_TARGETS == [
        '000016',
        '000010',
        '000009',
        '000015',
        '000300',
        '000903',
        '000905',
        '000906',
        '000852',
    ]
