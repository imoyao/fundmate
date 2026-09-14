# -*- coding: utf-8 -*-
"""基金公司回填 job 测试：消费导入侧观察值 → `funds.company_id`。

背景（#1386 遗留项）：`funds.company_id` 覆盖率长期偏低（实测 ≈11%），聚合页
「基金管理人」大量为空。导入侧样本里的「基金管理人」是中国结算给出的法人全称，
是最权威的补数来源；但导入属 user 域、`funds` 属 market 域，故导入只落观察值，
本 Job 作为 market 域唯一消费者回填——保证 `funds.company_id` 仍然只有一个写者。
"""

import pytest
from loguru import logger

import app.services.sync.company_resolver as company_resolver
from app.domains.funds.models import Fund, FundCompany
from app.domains.positions.models import FundCompanyObservation
from app.services.sync.adapters.null_adapter import NullAdapter
from app.services.sync.jobs.fund_company_backfill_job import FundCompanyBackfillJob

FUND_CODE = '012345'
COMPANY_NAME = '易方达基金管理有限公司'
COMPANY_CODE = '80000222'


@pytest.fixture
def offline_company_list(monkeypatch):
    """脱网：把东财公司名录换成固定样本（否则解析会发起真实网络请求）。"""
    monkeypatch.setattr(
        company_resolver,
        'fetch_fund_company_list',
        lambda: [{'name': '易方达基金', 'code': COMPANY_CODE}],
    )
    monkeypatch.setattr(company_resolver, '_cache', None, raising=False)
    yield company_resolver


def _make_job(db) -> FundCompanyBackfillJob:
    return FundCompanyBackfillJob(NullAdapter(), db)


def _observe(db, fund_code=FUND_CODE, company_name=COMPANY_NAME, family_id=1, source='e_account_holding'):
    db.add(FundCompanyObservation(family_id=family_id, fund_code=fund_code, company_name=company_name, source=source))
    db.commit()


def _fund(db, fund_code=FUND_CODE, company_id=None):
    fund = Fund(fund_code=fund_code, name='易方达蓝筹精选', company_id=company_id)
    db.add(fund)
    db.commit()
    return fund


def test_fills_missing_company_id(db, offline_company_list):
    """观察值命中且基金缺公司归属 → 回填到 fund_companies 的权威行。"""
    _observe(db)
    fund = _fund(db)

    result = _make_job(db).run()

    assert result['status'] == 'success'
    db.refresh(fund)
    assert fund.company_id is not None
    company = db.query(FundCompany).filter_by(id=fund.company_id).one()
    assert company.code == COMPANY_CODE
    assert result['stats']['filled'] == 1
    assert result['stats']['companies_created'] == 1
    logger.info(f'回填结果: {result["stats"]}')


def test_does_not_overwrite_existing_company_id(db, offline_company_list):
    """已有公司归属的基金一律不动（不覆盖同步 job / 人工维护的成果）。"""
    existing = FundCompany(name='易方达基金', code=COMPANY_CODE)
    db.add(existing)
    db.commit()
    _observe(db)
    fund = _fund(db, company_id=existing.id)

    result = _make_job(db).run()

    db.refresh(fund)
    assert fund.company_id == existing.id
    assert result['stats']['filled'] == 0


def test_second_run_is_noop(db, offline_company_list):
    """幂等：回填后重跑不再产生变更（观察值保留、不重复建公司）。"""
    _observe(db)
    fund = _fund(db)

    first = _make_job(db).run()
    second = _make_job(db).run()

    assert first['stats']['filled'] == 1
    assert second['stats']['filled'] == 0
    assert second['stats']['companies_created'] == 0
    assert db.query(FundCompany).count() == 1
    db.refresh(fund)
    assert fund.company_id is not None


def test_no_observations_succeeds(db, offline_company_list):
    """无观察值：成功返回、零变更（不报错、不建任何公司行）。"""
    result = _make_job(db).run()
    assert result['status'] == 'success'
    assert result['stats']['observations'] == 0
    assert db.query(FundCompany).count() == 0


def test_observation_without_fund_is_skipped(db, offline_company_list):
    """观察值有、但 funds 表无该基金 → 计入 skipped，不误建基金行。"""
    _observe(db, fund_code='999999')

    result = _make_job(db).run()

    assert result['status'] == 'success'
    assert result['stats']['filled'] == 0
    assert result['stats']['skipped'] == 1
    assert db.query(Fund).count() == 0
