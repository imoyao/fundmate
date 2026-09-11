# -*- coding: utf-8 -*-
"""测试 FundScaleSyncJob：全市场规模（亿元）覆盖式回填（#1286 数据底座）。

覆盖点：
1. 规模 = 份额 × 单位净值 ÷ 1e8，按 Decimal 精度落库；
2. 只更新本地已存在的基金，**不新建**（L3 不预建全库）；
3. 份额/净值缺一的条目在校验阶段剔除；
4. 第二次运行覆盖旧值（不是「已存在即跳过」）。
"""

from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund
from app.services.sync.jobs.fund_scale_job import FundScaleSyncJob


@pytest.fixture
def job(db):
    return FundScaleSyncJob(MagicMock(), db)


def test_scale_estimates_and_only_updates_existing(job, db):
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.add(Fund(fund_code='510300', name='沪深300ETF'))
    db.commit()

    # 全市场列表里含一只本地没有的基金（应被忽略，不得新建）
    job.adapter.fetch_fund_scale.return_value = [
        {'fund_code': '000001', 'shares': 1.0e9, 'nav': 1.5},
        {'fund_code': '510300', 'shares': 1.89149e10, 'nav': 4.6147},
        {'fund_code': '999999', 'shares': 1.0e8, 'nav': 2.0},
    ]

    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'

    a = db.query(Fund).filter_by(fund_code='000001').first()
    # 1e9 份 × 1.5 元 = 1.5e9 元 = 15.0 亿（SafeNumeric 读出为 Decimal，转 float 比对）
    assert float(a.scale) == 15.0
    assert float(a.recent_shares) == 1.0e9

    b = db.query(Fund).filter_by(fund_code='510300').first()
    assert float(b.scale) == pytest.approx(round(1.89149e10 * 4.6147 / 1e8, 2))

    assert db.query(Fund).filter_by(fund_code='999999').first() is None


def test_items_missing_shares_or_nav_are_dropped(job, db):
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.adapter.fetch_fund_scale.return_value = [
        {'fund_code': '000001', 'shares': None, 'nav': 1.5},  # 缺份额 → 无效
        {'fund_code': '000001', 'shares': 1.0e9, 'nav': None},  # 缺净值 → 无效
    ]

    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    assert db.query(Fund).filter_by(fund_code='000001').first().scale is None


def test_second_run_overwrites_previous_value(job, db):
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.adapter.fetch_fund_scale.return_value = [{'fund_code': '000001', 'shares': 1.0e9, 'nav': 1.5}]
    job.run(full_sync=True, targets=['__full__'])
    assert float(db.query(Fund).filter_by(fund_code='000001').first().scale) == 15.0

    # 规模随行情变化：第二次必须以新值覆盖，而不是「已存在即跳过」。
    # 注意 SyncJob 实例是一次性的（基类 run() 见到 status=SUCCESS 即不再执行），
    # 故重跑须新建实例——编排层每次执行取的也是各自实例。
    job2 = FundScaleSyncJob(job.adapter, db)
    job.adapter.fetch_fund_scale.return_value = [{'fund_code': '000001', 'shares': 2.0e9, 'nav': 1.5}]
    job2.run(full_sync=True, targets=['__full__'])
    assert float(db.query(Fund).filter_by(fund_code='000001').first().scale) == 30.0


def test_no_local_match_skips_without_error(job, db):
    job.adapter.fetch_fund_scale.return_value = [{'fund_code': '999999', 'shares': 1.0e8, 'nav': 2.0}]
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    assert db.query(Fund).count() == 0


def test_empty_source_allowed(job, db):
    job.adapter.fetch_fund_scale.return_value = []
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'


def test_in_query_is_chunked_beyond_sqlite_variable_limit(job, db):
    """in_ 分批：超过 SQLite 变量上限（999）不报错。"""
    codes = [f'{i:06d}' for i in range(1500)]
    db.add_all([Fund(fund_code=c, name=f'基金{c}') for c in codes])
    db.commit()

    job.adapter.fetch_fund_scale.return_value = [{'fund_code': c, 'shares': 1.0e8, 'nav': 2.0} for c in codes]
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    assert db.query(Fund).filter(Fund.scale.isnot(None)).count() == 1500
