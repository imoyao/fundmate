# -*- coding: utf-8 -*-
"""测试 FundPositionSyncJob：持仓明细/行业配置落库（#870）+ 目标池红线（#1286 / #1403）。

两条主线：

1. **目标池不得退化为全库**（`data-strategy.md` §4.3.2 / §4.3.3）——原 `fund_meta_job`
   正是在这里出错：`db.query(Fund).all()` + 逐只抓取 = 全库 26,938 次外部请求（≈13.5 小时），
   见 #1403。
2. **明细是源、标量是派生**——`equity_position` 取「行业配置合计」而非「前十大之和」，
   且**无源数据时不覆盖原值**（不用 0 掩盖缺失）。
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import Fund, FundHolding, FundIndustryAlloc
from app.services.job_base import JobStatus
from app.services.sync.jobs.fund_position_job import FundPositionSyncJob

# 12 条明细：前 10 条合计 10.0%，若仍按「前十大求和」会得到 10.0 而不是行业合计 35.5，
# 因此下面的断言能直接区分新旧口径。
HOLDINGS_PAYLOAD = {
    'fund_code': '000001',
    'report_period': '2026Q2',
    'report_date': date(2026, 6, 30),
    'holding_basis': 'full',
    'holdings': [
        {
            'stock_code': f'{i:06d}',
            'stock_name': f'股{i}',
            'ratio': 1.0,
            'shares': 10.0,
            'market_value': 100.0,
            'rank': i,
        }
        for i in range(1, 13)
    ],
}

# 双体系并存：证监会门类（csrc）+ GICS 板块（gics），合计 35.5
INDUSTRY_PAYLOAD = {
    'fund_code': '000001',
    'report_period': '2026Q2',
    'report_date': date(2026, 6, 30),
    'items': [
        {'industry_code': 'C', 'industry_name': '制造业', 'scheme': 'csrc', 'ratio': 30.0},
        {'industry_code': '25', 'industry_name': '非必需消费品', 'scheme': 'gics', 'ratio': 5.5},
    ],
}
INDUSTRY_TOTAL = 35.5


def _rerun(job, targets):
    """重跑同一个 job 实例。

    基类 `SyncJob.run()` 是 ``while self.status in (PENDING, FAILED, RETRYING)`` —— 一旦跑到
    SUCCESS，再次调用 run() 会**直接什么都不做**（实例不可复用）。测试里要模拟「同一 job
    跑第二轮」，必须先把状态复位，否则会得到假通过。
    """
    job.status = JobStatus.PENDING
    return job.run(full_sync=True, targets=targets)


@pytest.fixture
def job(db):
    adapter = MagicMock()
    adapter.fetch_fund_top_holdings.return_value = HOLDINGS_PAYLOAD
    adapter.fetch_fund_industry_allocation.return_value = INDUSTRY_PAYLOAD
    return FundPositionSyncJob(adapter, db)


# ── 目标池红线 ──


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

    result = job.run(full_sync=True, targets=['000001', '110022'])
    assert result['status'] == 'success'

    called = [c.args[0] for c in job.adapter.fetch_fund_top_holdings.call_args_list]
    assert called == ['000001', '110022']

    assert float(db.query(Fund).filter_by(fund_code='000001').first().equity_position) == INDUSTRY_TOTAL
    assert float(db.query(Fund).filter_by(fund_code='110022').first().equity_position) == INDUSTRY_TOTAL
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


@pytest.mark.parametrize('targets', [[], None, ['__full__']], ids=['empty', 'none', 'full'])
def test_skip_path_always_sets_snapshot_time(job, db, targets):
    """回归（2026-10-01 生产实测）：早退路径必须自己打 `snapshot_time`。

    本 job 覆写了 `run()`，因此**不进**基类开头那句 ``self.snapshot_time = now_shanghai()``。
    漏赋值时，`orchestrator.run_job` 的 ``now_shanghai() - job.snapshot_time`` 会抛
    ``TypeError: unsupported operand type(s) for -: 'datetime.datetime' and 'NoneType'``，
    把一次干净的「显式跳过」变成 `pdm run sync --job fund_position` 非零退出。
    """
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.run(full_sync=True, targets=targets)

    assert job.snapshot_time is not None
    job.adapter.fetch_fund_top_holdings.assert_not_called()


def test_pool_is_deduped_and_capped(job, monkeypatch):
    monkeypatch.setattr('app.services.sync.jobs.fund_position_job.MAX_TARGETS', 3)
    pool = job.resolve_pool(['a', 'b', 'a', '__full__', '', 'c', 'd'])
    assert pool == ['a', 'b', 'c']


# ── 货基守卫（#1982）────────────────────────────────────────────────────────


def test_pool_drops_only_catalog_confirmed_money_funds(job, monkeypatch):
    """只剔名录**明确**说是货基的（True）：False 与 None 都必须留下。

    `None` 的语义是「名录没说话」（无此码 / 类型未知 / market 域不可达），
    按 #1661 的「宁漏不误」不能当成「不是货基」，更不能当成「是货基」——
    误剔除会让真实基金的持仓数据再也同步不进来。
    """
    monkeypatch.setattr(
        'app.services.fund_utils.resolve_money_fund_flags_strict',
        lambda codes: {'110022': True, '110033': False, '110044': None},
    )

    pool = job.resolve_pool(['110022', '110033', '110044'])

    assert pool == ['110033', '110044']
    assert job.stats['money_fund_excluded'] == 1


def test_pool_records_zero_excluded_when_nothing_dropped(job, monkeypatch):
    """剔除数为 0 也要记：它证明判定**跑过**，而不是没查（排查时用得上）。"""
    monkeypatch.setattr('app.services.fund_utils.resolve_money_fund_flags_strict', lambda codes: {})

    assert job.resolve_pool(['005827']) == ['005827']
    assert job.stats['money_fund_excluded'] == 0


def test_pool_survives_catalog_failure_without_guessing(job, monkeypatch):
    """名录读取抛错 → 整池保留、不猜。宁可少省一次请求，也不能误剔真实基金。"""

    def _boom(codes):
        raise RuntimeError('market 域不可达')

    monkeypatch.setattr('app.services.fund_utils.resolve_money_fund_flags_strict', _boom)

    assert job.resolve_pool(['110022', '110033']) == ['110022', '110033']


def test_partial_failure_does_not_abort_batch(job, db):
    """单只失败只跳过该只，其余继续。"""
    db.add_all([Fund(fund_code='000001', name='A'), Fund(fund_code='110022', name='B')])
    db.commit()

    def side_effect(code):
        if code == '000001':
            raise RuntimeError('模拟数据源异常')
        return HOLDINGS_PAYLOAD

    job.adapter.fetch_fund_top_holdings.side_effect = side_effect
    result = job.run(full_sync=True, targets=['000001', '110022'])
    assert result['status'] == 'success'
    # 000001 持仓失败但行业配置成功 → 仓位仍可派生（两条链路互为补充）
    assert float(db.query(Fund).filter_by(fund_code='000001').first().equity_position) == INDUSTRY_TOTAL
    assert float(db.query(Fund).filter_by(fund_code='110022').first().equity_position) == INDUSTRY_TOTAL


# ── 明细落库 ──


def test_holdings_are_persisted_with_basis_and_rank(job, db):
    """持仓明细落 fund_holdings，带报告期与披露口径。"""
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.run(full_sync=True, targets=['000001'])

    rows = db.query(FundHolding).filter_by(fund_code='000001').all()
    assert len(rows) == 12
    assert {r.report_period for r in rows} == {'2026Q2'}
    assert {r.holding_basis for r in rows} == {'full'}
    assert {r.source for r in rows} == {'eastmoney'}
    assert sorted(r.rank for r in rows) == list(range(1, 13))
    assert float(rows[0].shares) == 10.0
    assert float(rows[0].market_value) == 100.0


def test_quarterly_top10_and_semiannual_full_coexist(job, db):
    """回归：前十大（季报）与全量（半年报）**并存**，不得互相覆盖。

    若把两者合成单一口径，季报期数据会"凭空缩水"，被误读为大幅减仓。
    """
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    # 第一次：半年报全量（2026Q2）
    job.run(full_sync=True, targets=['000001'])

    # 第二次：季报前十大（2026Q3）——不得覆盖掉上一期的全量
    top10_payload = {
        **HOLDINGS_PAYLOAD,
        'report_period': '2026Q3',
        'holding_basis': 'top10',
        'holdings': HOLDINGS_PAYLOAD['holdings'][:10],
    }
    job.adapter.fetch_fund_top_holdings.return_value = top10_payload
    _rerun(job, ['000001'])

    full_rows = db.query(FundHolding).filter_by(fund_code='000001', holding_basis='full').all()
    top10_rows = db.query(FundHolding).filter_by(fund_code='000001', holding_basis='top10').all()
    assert len(full_rows) == 12
    assert len(top10_rows) == 10
    assert {r.report_period for r in full_rows} == {'2026Q2'}
    assert {r.report_period for r in top10_rows} == {'2026Q3'}


def test_industry_allocs_persisted_with_scheme(job, db):
    """行业配置落 fund_industry_allocs，并按 csrc / gics 标记体系（禁止跨体系相加）。"""
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.run(full_sync=True, targets=['000001'])

    rows = db.query(FundIndustryAlloc).filter_by(fund_code='000001').all()
    assert len(rows) == 2
    by_scheme = {r.scheme: r for r in rows}
    assert by_scheme['csrc'].industry_code == 'C'
    assert float(by_scheme['csrc'].ratio) == 30.0
    assert by_scheme['gics'].industry_code == '25'
    assert float(by_scheme['gics'].ratio) == 5.5


# ── 派生标量口径 ──


def test_equity_position_comes_from_industry_total_not_top10(job, db):
    """口径：#870 起 `equity_position` = 行业配置合计，**不是**前十大重仓之和。

    本用例故意让两者不等（前十大 10.0 vs 行业合计 35.5），以区分新旧口径。
    """
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.run(full_sync=True, targets=['000001'])

    fund = db.query(Fund).filter_by(fund_code='000001').first()
    assert float(fund.equity_position) == INDUSTRY_TOTAL
    assert fund.equity_position_period == '2026Q2'


def test_no_source_data_leaves_equity_position_untouched(job, db):
    """无源数据（如部分 QDII 无行业配置、且持仓也取不到）→ 保持原值，不用 0 掩盖缺失。"""
    fund = Fund(fund_code='000001', name='测试基金A', equity_position=42.5, equity_position_period='2026Q1')
    db.add(fund)
    db.commit()

    job.adapter.fetch_fund_top_holdings.return_value = {}
    job.adapter.fetch_fund_industry_allocation.return_value = {}
    result = job.run(full_sync=True, targets=['000001'])

    assert result['status'] == 'success'
    db.expire_all()
    fund = db.query(Fund).filter_by(fund_code='000001').first()
    assert float(fund.equity_position) == 42.5
    assert fund.equity_position_period == '2026Q1'


def test_same_report_period_is_upserted_not_duplicated(job, db):
    """同一报告期重复跑（幂等）：覆盖更新，不产生重复行。"""
    db.add(Fund(fund_code='000001', name='测试基金A'))
    db.commit()

    job.run(full_sync=True, targets=['000001'])
    _rerun(job, ['000001'])

    assert db.query(FundHolding).filter_by(fund_code='000001').count() == 12
    assert db.query(FundIndustryAlloc).filter_by(fund_code='000001').count() == 2


def test_holdings_only_does_not_reset_position(job, db):
    """只有持仓、没有行业配置时：明细照落，但派生标量不动（无源即不派生）。"""
    fund = Fund(fund_code='000001', name='测试基金A', equity_position=42.5, equity_position_period='2026Q1')
    db.add(fund)
    db.commit()

    job.adapter.fetch_fund_industry_allocation.return_value = {}
    job.run(full_sync=True, targets=['000001'])

    db.expire_all()
    fund = db.query(Fund).filter_by(fund_code='000001').first()
    assert float(fund.equity_position) == 42.5
    assert fund.equity_position_period == '2026Q1'
    assert db.query(FundHolding).filter_by(fund_code='000001').count() == 12
