# -*- coding: utf-8 -*-
"""测试 FundDetailEnrichJob 的费率规则复用、容错和分批提交"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import FeeRatio, Fund, PurchaseRule, RedeemRule
from app.services.sync.jobs.fund_detail_enrich_job import FundDetailEnrichJob


class TestFundDetailEnrichJob:
    @pytest.fixture
    def job(self, db):
        akshare_mock = MagicMock()
        xalpha_mock = MagicMock()
        return FundDetailEnrichJob(akshare_mock, xalpha_mock, db)

    @pytest.fixture
    def funds(self, db):
        """准备两只待补充的基金"""
        fund_a = Fund(fund_code='000001', name='华夏成长')
        fund_b = Fund(fund_code='002001', name='华夏回报')
        db.add_all([fund_a, fund_b])
        db.commit()
        return [fund_a, fund_b]

    def test_enrich_basic_info(self, job, funds):
        """验证基本信息正确写入"""
        job.akshare_adapter.fetch_fund_detail.side_effect = [
            {
                'fund_type_raw': '混合型',
                'company_name': '华夏基金管理有限公司',
                'create_time': date(2001, 12, 18),
                'benchmark': '沪深300指数收益率×80%',
                'risk_level': 4,
                'fund_full_name': '华夏成长证券投资基金',
            },
            {},
        ]
        job.xalpha_adapter.fetch_fund_fee.side_effect = [
            {
                'purchase_rate': 0.15,
                'redemption_schedule': [
                    {'start_day': 0, 'end_day': 7, 'rate': 1.5},
                    {'start_day': 7, 'end_day': None, 'rate': 0.5},
                ],
            },
            {'purchase_rate': 0.12, 'redemption_schedule': []},
        ]

        job.batch_size = 2
        job.run(targets=['000001', '002001'])

        fund1 = job.db.query(Fund).filter_by(fund_code='000001').first()
        assert fund1.fund_type_id is not None
        assert fund1.company_id is not None
        assert fund1.risk_level == 4
        assert fund1.benchmark == '沪深300指数收益率×80%'
        assert fund1.full_name == '华夏成长证券投资基金'
        assert fund1.pinyin_abbr == 'HXCZ'

        fund2 = job.db.query(Fund).filter_by(fund_code='002001').first()
        assert fund2.fund_type_id is None

        purchase_rules = job.db.query(PurchaseRule).all()
        assert len(purchase_rules) == 1
        redeem_rules = job.db.query(RedeemRule).all()
        assert len(redeem_rules) == 2
        fee_ratios = job.db.query(FeeRatio).all()
        assert len(fee_ratios) == 4

    def test_rule_reuse(self, job, db):
        """相同的费率阶梯应复用已有规则"""
        db.add(RedeemRule(start_day=0, end_day=7))
        db.commit()

        fund = Fund(fund_code='000001', name='华夏成长')
        db.add(fund)
        db.commit()

        job.akshare_adapter.fetch_fund_detail.return_value = {}
        job.xalpha_adapter.fetch_fund_fee.return_value = {
            'purchase_rate': 0.15,
            'redemption_schedule': [{'start_day': 0, 'end_day': 7, 'rate': 1.5}],
        }

        job.run(targets=['000001'])

        redeem_rules = db.query(RedeemRule).all()
        assert len(redeem_rules) == 1

    def test_adapter_failure_does_not_crash(self, job, funds):
        """适配器抛出异常时，Job 不应崩溃"""
        job.akshare_adapter.fetch_fund_detail.side_effect = Exception('网络故障')
        job.xalpha_adapter.fetch_fund_fee.side_effect = Exception('费率获取失败')

        job.run(targets=['000001', '002001'])

        assert len(job.stats.get('errors', [])) == 2

    def test_batch_commit(self, job, funds):
        """设置 batch_size=1，验证分批次提交"""
        job.akshare_adapter.fetch_fund_detail.return_value = {
            'fund_type_raw': '股票型',
            'company_name': '华夏基金',
        }
        job.xalpha_adapter.fetch_fund_fee.return_value = {}

        job.batch_size = 1
        job.run(targets=['000001', '002001'])

        fund1 = job.db.query(Fund).filter_by(fund_code='000001').first()
        fund2 = job.db.query(Fund).filter_by(fund_code='002001').first()
        assert fund1.company_id is not None
        assert fund2.company_id is not None

    def test_skip_already_processed_today(self, job, db):
        """last_nav_check 为今天时，应跳过"""
        fund = Fund(fund_code='000001', name='华夏成长', last_nav_check=date.today())
        db.add(fund)
        db.commit()

        job.akshare_adapter.fetch_fund_detail.return_value = {}
        job.xalpha_adapter.fetch_fund_fee.return_value = {}

        job.run(targets=['000001'])

        assert job.akshare_adapter.fetch_fund_detail.call_count == 0
        assert job.stats['skipped'] == 1
