# -*- coding: utf-8 -*-
"""测试 FundRatingSyncJob：晨星星级评级（3 年期）覆盖式回填（#1440）。

覆盖点（对齐 fund_scale 同族用例 + 评级特有口径）：
1. rating/delta 落库与归一化（空评级 → NULL，不清零已有值由调用方保证）；
2. 只更新本地已存在的基金，**不新建**（L3 不预建全库）；
3. 上游一条都没返回 ⇒ **失败**（空 ≠ 没拿到，#1179 同族）；
4. 稳态重跑**一条 UPDATE 都不发**（评级月度更新，没变就不写）；
5. 多行变更必须压成几条 `CASE` 语句（Turso 上「每行一次往返」实测 0.16 s/行，#2522）；
6. asof 只在 rating/delta 变化时刷新（否则周频跑会把全表每周重写）。
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund
from app.services.sync.jobs.fund_rating_job import FundRatingSyncJob


@pytest.fixture
def job(db):
    return FundRatingSyncJob(MagicMock(), db)


def test_rating_and_delta_written_for_existing_funds(job, db):
    db.add(Fund(fund_code='000001', name='华夏成长混合'))
    db.add(Fund(fund_code='161725', name='招商中证白酒指数(LOF)A'))
    db.commit()

    job.adapter.fetch_fund_rating.return_value = [
        {'fund_code': '000001', 'rating': 3, 'delta': -1},
        {'fund_code': '161725', 'rating': 1, 'delta': 0},
    ]

    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'

    a = db.query(Fund).filter_by(fund_code='000001').first()
    assert a.morningstar_rating == 3
    assert a.morningstar_rating_delta == -1
    assert a.morningstar_rating_asof is not None

    b = db.query(Fund).filter_by(fund_code='161725').first()
    assert b.morningstar_rating == 1
    assert b.morningstar_rating_delta == 0


def test_none_rating_is_stored_as_null(job, db):
    """无评级（货基/新基金常态）→ NULL，而不是 0 或跳过不写。"""
    db.add(Fund(fund_code='000001', name='华夏成长混合'))
    db.commit()

    job.adapter.fetch_fund_rating.return_value = [{'fund_code': '000001', 'rating': None, 'delta': None}]
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'

    a = db.query(Fund).filter_by(fund_code='000001').first()
    assert a.morningstar_rating is None
    assert a.morningstar_rating_delta is None


def test_only_updates_existing_not_creates(job, db):
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.adapter.fetch_fund_rating.return_value = [
        {'fund_code': '000001', 'rating': 3, 'delta': -1},
        {'fund_code': '999999', 'rating': 5, 'delta': 1},  # 本地没有 → 不得新建
    ]
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    assert db.query(Fund).filter_by(fund_code='999999').first() is None


def test_empty_source_is_failure(job, db):
    """上游一条都没返回 ⇒ **失败**，不是成功。

    口径（#1179 同族）：全市场列表类 job 抓不到任何记录，只可能是上游结构变更 /
    接口异常 / 解析失配——不可能是「今天没有数据」。
    """
    job.adapter.fetch_fund_rating.return_value = []
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'failed'
    assert '空数据' in str(result.get('stats', {}).get('error', ''))


def test_invalid_rows_dropped_in_validate(job, db):
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.add(Fund(fund_code='110011', name='测试基金B'))
    db.commit()

    job.adapter.fetch_fund_rating.return_value = [
        {'fund_code': '000001', 'rating': 3, 'delta': -1},
        {'fund_code': '110011', 'rating': 9, 'delta': 0},  # 评级越域 → 剔除
        {'fund_code': 'abc', 'rating': 3, 'delta': 0},  # 代码形态 → 剔除
        {'fund_code': '000002', 'rating': 3, 'delta': 99},  # delta 越域 → 剔除
    ]
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    assert db.query(Fund).filter_by(fund_code='110011').first().morningstar_rating is None
    assert db.query(Fund).filter_by(fund_code='000002').first() is None


def test_rerun_with_same_values_emits_no_update(job, db):
    """同数据重跑：**一条 UPDATE 都不发**（评级月度更新，没变就不该写库）。"""
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.adapter.fetch_fund_rating.return_value = [{'fund_code': '000001', 'rating': 3, 'delta': -1}]
    job.run(full_sync=True, targets=['__full__'])

    job2 = FundRatingSyncJob(job.adapter, db)
    updates, stop = _capture_updates(db)
    try:
        result = job2.run(full_sync=True, targets=['__full__'])
    finally:
        stop()

    assert result['status'] == 'success'
    assert updates == [], f'评级没变却发了 {len(updates)} 条 UPDATE'


def test_changed_rows_refresh_asof_unchanged_do_not(job, db):
    """rating/delta 变化 ⇒ 三列同写（asof 刷新）；没变 ⇒ 连 asof 都不动。"""
    old_asof = date.today() - timedelta(days=10)
    fund = Fund(fund_code='000001', name='测试基金A')
    fund.morningstar_rating = 3
    fund.morningstar_rating_delta = -1
    fund.morningstar_rating_asof = old_asof
    db.add(fund)
    db.commit()

    job.adapter.fetch_fund_rating.return_value = [{'fund_code': '000001', 'rating': 3, 'delta': -1}]
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    db.refresh(fund)
    assert fund.morningstar_rating_asof == old_asof, '值没变，asof 不得被改写'

    # 星级真变了 → asof 必须刷新为抓取日
    job2 = FundRatingSyncJob(job.adapter, db)
    job.adapter.fetch_fund_rating.return_value = [{'fund_code': '000001', 'rating': 4, 'delta': 1}]
    job2.run(full_sync=True, targets=['__full__'])
    db.refresh(fund)
    assert fund.morningstar_rating == 4
    assert fund.morningstar_rating_asof > old_asof


def test_many_changed_rows_are_written_in_a_few_statements(job, db):
    """400 只基金评级全变 ⇒ 必须压成几条语句，而不是 400 条逐行 UPDATE。"""
    codes = [f'{i:06d}' for i in range(400)]
    db.add_all([Fund(fund_code=c, name=f'基金{c}') for c in codes])
    db.commit()

    job.adapter.fetch_fund_rating.return_value = [{'fund_code': c, 'rating': 1, 'delta': 0} for c in codes]
    job.run(full_sync=True, targets=['__full__'])

    job2 = FundRatingSyncJob(job.adapter, db)
    job.adapter.fetch_fund_rating.return_value = [{'fund_code': c, 'rating': 2, 'delta': 1} for c in codes]
    updates, stop = _capture_updates(db)
    try:
        job2.run(full_sync=True, targets=['__full__'])
    finally:
        stop()

    assert len(updates) <= 4, f'400 行应压成 ≤4 条语句（每批 128 行：3 值列 → (900-1)//7），实际 {len(updates)} 条'
    assert all('CASE' in sql for sql in updates), '每条都必须是 CASE 批量形态，不得逐行 WHERE 主键'

    db.expire_all()
    values = {f.fund_code: f.morningstar_rating for f in db.query(Fund).all()}
    assert set(values.values()) == {2}, '新评级必须真的落库'


def test_in_query_is_chunked_beyond_sqlite_variable_limit(job, db):
    """in_ 分批：超过 SQLite 变量上限（999）不报错。"""
    codes = [f'{i:06d}' for i in range(1500)]
    db.add_all([Fund(fund_code=c, name=f'基金{c}') for c in codes])
    db.commit()

    job.adapter.fetch_fund_rating.return_value = [{'fund_code': c, 'rating': 3, 'delta': 0} for c in codes]
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    assert db.query(Fund).filter(Fund.morningstar_rating.isnot(None)).count() == 1500


def _capture_updates(db):
    """收集本 session 引擎上的 UPDATE 语句（#2522 的判据：数语句，不数代码路径）。"""
    from sqlalchemy import event

    updates = []
    engine = db.get_bind()

    def before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        sql = ' '.join(statement.split())
        if sql.upper().startswith('UPDATE'):
            updates.append(sql)

    event.listen(engine, 'before_cursor_execute', before)
    return updates, lambda: event.remove(engine, 'before_cursor_execute', before)
