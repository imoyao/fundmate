# -*- coding: utf-8 -*-
"""测试 FundPositionSyncJob：近似股票仓位的目标池红线（#1286 数据底座 / #1403）。

本文件的核心是**目标池不得退化为全库**这条红线（`data-strategy.md` §4.3.2 / §4.3.3）——
原 `fund_meta_job` 正是在这里出错：`db.query(Fund).all()` + 逐只 `fetch_fund_top_holdings`
= 全库 26,938 次 HTTP（≈13.5 小时），见 #1403。
"""

from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund
from app.services.sync.jobs.fund_position_job import FundPositionSyncJob

TEN_HOLDINGS = [{'stock_code': f'{i:06d}', 'stock_name': f'股{i}', 'ratio': 1.0} for i in range(10)]


@pytest.fixture
def job(db):
    return FundPositionSyncJob(MagicMock(), db)


def test_only_targets_are_fetched(job, db):
    """逐只抓取只对目标池发起——非目标基金不得被请求，也不得被写入。"""
    db.add_all(
        [
            Fund(fund_code='000001', name='测试基金A'),
            Fund(fund_code='110022', name='测试基金B'),
            Fund(fund_code='519066', name='非目标基金C'),
        ]
    )
    db.commit()
    job.adapter.fetch_fund_top_holdings.side_effect = lambda code: TEN_HOLDINGS

    result = job.run(full_sync=True, targets=['000001', '110022'])
    assert result['status'] == 'success'

    called = [c.args[0] for c in job.adapter.fetch_fund_top_holdings.call_args_list]
    assert called == ['000001', '110022']

    assert float(db.query(Fund).filter_by(fund_code='000001').first().equity_position) == 10.0
    assert float(db.query(Fund).filter_by(fund_code='110022').first().equity_position) == 10.0
    assert db.query(Fund).filter_by(fund_code='519066').first().equity_position is None


def test_full_placeholder_is_skipped_not_expanded_to_whole_table(job, db):
    """回归：`__full__` 对逐只抓取类 job 不构成有效目标池 → 显式跳过，禁止全库展开。"""
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    job.adapter.fetch_fund_top_holdings.assert_not_called()
    assert db.query(Fund).filter_by(fund_code='000001').first().equity_position is None


def test_empty_targets_are_skipped(job, db):
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    result = job.run(full_sync=True, targets=[])
    assert result['status'] == 'success'
    job.adapter.fetch_fund_top_holdings.assert_not_called()


def test_none_targets_are_skipped(job, db):
    """targets=None 同样表示「无受限目标池」，不得当作「全部」。"""
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    result = job.run(full_sync=True)
    assert result['status'] == 'success'
    job.adapter.fetch_fund_top_holdings.assert_not_called()


def test_pool_is_deduped_and_capped(job, monkeypatch):
    monkeypatch.setattr('app.services.sync.jobs.fund_position_job.MAX_TARGETS', 3)
    pool = job.resolve_pool(['a', 'b', 'a', '__full__', '', 'c', 'd'])
    assert pool == ['a', 'b', 'c']


def test_partial_failure_does_not_abort_batch(job, db):
    """单只失败只跳过该只，其余继续。"""
    db.add_all([Fund(fund_code='000001', name='A'), Fund(fund_code='110022', name='B')])
    db.commit()

    def side_effect(code):
        if code == '000001':
            raise RuntimeError('模拟数据源异常')
        return TEN_HOLDINGS

    job.adapter.fetch_fund_top_holdings.side_effect = side_effect
    result = job.run(full_sync=True, targets=['000001', '110022'])
    assert result['status'] == 'success'
    assert db.query(Fund).filter_by(fund_code='000001').first().equity_position is None
    assert float(db.query(Fund).filter_by(fund_code='110022').first().equity_position) == 10.0


def test_empty_holdings_leave_column_untouched(job, db):
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()
    job.adapter.fetch_fund_top_holdings.return_value = []

    result = job.run(full_sync=True, targets=['000001'])
    assert result['status'] == 'success'
    assert db.query(Fund).filter_by(fund_code='000001').first().equity_position is None


def test_only_top_ten_holdings_are_summed(job, db):
    """口径：只累加前十大重仓，第 11 条起不计入。"""
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()
    job.adapter.fetch_fund_top_holdings.return_value = [{'stock_code': f'{i:06d}', 'ratio': 1.0} for i in range(12)]

    job.run(full_sync=True, targets=['000001'])
    assert float(db.query(Fund).filter_by(fund_code='000001').first().equity_position) == 10.0
