# -*- coding: utf-8 -*-
"""测试 FundScaleSyncJob：全市场规模（亿元）覆盖式回填（#1286 数据底座）。

覆盖点：
1. 规模 = 份额 × 单位净值 ÷ 1e8，按 Decimal 精度落库；
2. 只更新本地已存在的基金，**不新建**（L3 不预建全库）；
3. 份额/净值缺一的条目在校验阶段剔除；
4. 第二次运行覆盖旧值（不是「已存在即跳过」）；
5. 稳态重跑**一条 UPDATE 都不发**；多行变更必须压成几条 `CASE` 语句
   （Turso 上「每行一次往返」实测 0.16 s/行，见 #2522）。
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


def test_empty_source_is_failure(job, db):
    """上游一条都没返回 ⇒ **失败**，不是成功。

    口径变更（#1179 同族收口）：全市场列表类 job 抓不到任何记录，
    只可能是上游结构变更 / 接口异常 / 解析失配——不可能是「今天没有数据」。
    旧行为把它当 success，于是市场底座静默停更、日志一片绿。
    """
    job.adapter.fetch_fund_scale.return_value = []
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'failed'
    assert '空数据' in str(result.get('stats', {}).get('error', ''))


def test_in_query_is_chunked_beyond_sqlite_variable_limit(job, db):
    """in_ 分批：超过 SQLite 变量上限（999）不报错。"""
    codes = [f'{i:06d}' for i in range(1500)]
    db.add_all([Fund(fund_code=c, name=f'基金{c}') for c in codes])
    db.commit()

    job.adapter.fetch_fund_scale.return_value = [{'fund_code': c, 'shares': 1.0e8, 'nav': 2.0} for c in codes]
    result = job.run(full_sync=True, targets=['__full__'])
    assert result['status'] == 'success'
    assert db.query(Fund).filter(Fund.scale.isnot(None)).count() == 1500


def _capture_updates(db):
    """收集本 session 引擎上的 UPDATE 语句（'#'2522 的判据：数语句，不数代码路径）。"""
    from sqlalchemy import event

    updates = []
    engine = db.get_bind()

    def before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        sql = ' '.join(statement.split())
        if sql.upper().startswith('UPDATE'):
            updates.append(sql)

    event.listen(engine, 'before_cursor_execute', before)
    return updates, lambda: event.remove(engine, 'before_cursor_execute', before)


def test_rerun_with_same_values_emits_no_update(job, db):
    """同数据重跑：**一条 UPDATE 都不发**（规模没变就不该写库）。"""
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.adapter.fetch_fund_scale.return_value = [{'fund_code': '000001', 'shares': 1.0e9, 'nav': 1.5}]
    job.run(full_sync=True, targets=['__full__'])

    job2 = FundScaleSyncJob(job.adapter, db)
    updates, stop = _capture_updates(db)
    try:
        result = job2.run(full_sync=True, targets=['__full__'])
    finally:
        stop()

    assert result['status'] == 'success'
    assert updates == [], f'规模没变却发了 {len(updates)} 条 UPDATE'


def test_many_changed_rows_are_written_in_a_few_statements(job, db):
    """400 只基金净值全变 ⇒ 必须压成几条语句，而不是 400 条逐行 UPDATE。

    生产实测（run `40044659739`）：7125 只 × 0.16 s = 写库 1139.6 s，
    而其中 1139.6 s 全部花在「每行一次 HTTP 往返」上——本条钉住的就是这个形状。
    """
    codes = [f'{i:06d}' for i in range(400)]
    db.add_all([Fund(fund_code=c, name=f'基金{c}') for c in codes])
    db.commit()

    job.adapter.fetch_fund_scale.return_value = [{'fund_code': c, 'shares': 1.0e9, 'nav': 1.5} for c in codes]
    job.run(full_sync=True, targets=['__full__'])

    job2 = FundScaleSyncJob(job.adapter, db)
    job.adapter.fetch_fund_scale.return_value = [{'fund_code': c, 'shares': 1.0e9, 'nav': 1.6} for c in codes]
    updates, stop = _capture_updates(db)
    try:
        job2.run(full_sync=True, targets=['__full__'])
    finally:
        stop()

    assert len(updates) <= 4, f'400 行应压成 ≤4 条语句（每批 179 行），实际 {len(updates)} 条'
    assert all('CASE' in sql for sql in updates), '每条都必须是 CASE 批量形态，不得逐行 WHERE 主键'
    assert all('fund_code = ?' not in sql for sql in updates)

    db.expire_all()
    values = {f.fund_code: float(f.scale) for f in db.query(Fund).all()}
    assert set(values.values()) == {16.0}, f'新净值必须真的落库，实际 {sorted(set(values.values()))[:5]}'
