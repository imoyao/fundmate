# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 14:18
# File : test_fund_detail_enrich_job.py
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
        funds = [
            Fund(fund_code='000001', name='华夏成长'),
            Fund(fund_code='002001', name='华夏回报'),
        ]
        db.add_all(funds)
        db.commit()
        return funds

    # ── 基本流程 ──
    def test_enrich_basic_info(self, job, funds):
        """验证基本信息正确写入"""
        # Mock 数据：akshare 详情
        job.akshare_adapter.fetch_fund_detail.side_effect = [
            {
                'fund_type_raw': '混合型',
                'company_name': '华夏基金管理有限公司',
                'create_time': date(2001, 12, 18),
                'benchmark': '沪深300指数收益率×80%',
                'risk_level': 4,
            },
            {},
        ]
        # Mock 费率
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
        job.run()

        # 验证基金 000001
        fund1 = job.db.query(Fund).filter_by(fund_code='000001').first()
        assert fund1.fund_type_id is not None
        assert fund1.fund_variety_id is not None
        assert fund1.company_id is not None
        assert fund1.risk_level == 4
        assert fund1.benchmark == '沪深300指数收益率×80%'

        # 验证基金 002001 没有写入 None
        fund2 = job.db.query(Fund).filter_by(fund_code='002001').first()
        assert fund2.fund_type_id is None

        # 验证费率规则
        purchase_rules = job.db.query(PurchaseRule).all()
        assert len(purchase_rules) == 1  # 两只基金的申购金额区间相同，复用一条规则
        redeem_rules = job.db.query(RedeemRule).all()
        assert len(redeem_rules) == 2  # 第一只有两个阶梯

        fee_ratios = job.db.query(FeeRatio).all()
        assert len(fee_ratios) == 4  # 申购2 + 赎回2

    # ── 规则复用 ──
    def test_rule_reuse(self, job, db):
        """相同的费率阶梯应复用已有规则"""
        # 先手工创建一条规则
        rule = RedeemRule(start_day=0, end_day=7)
        db.add(rule)
        db.commit()

        fund = Fund(fund_code='000001', name='华夏成长')
        db.add(fund)
        db.commit()

        # Mock 返回相同阶梯
        job.akshare_adapter.fetch_fund_detail.return_value = {}
        job.xalpha_adapter.fetch_fund_fee.return_value = {
            'purchase_rate': 0.15,
            'redemption_schedule': [{'start_day': 0, 'end_day': 7, 'rate': 1.5}],
        }

        job.run()

        # 应复用已有规则，赎回规则总数仍为 1
        redeem_rules = db.query(RedeemRule).all()
        assert len(redeem_rules) == 1

    # ── 异常容错 ──
    def test_adapter_failure_does_not_crash(self, job, funds):
        """适配器抛出异常时，Job 不应崩溃"""
        job.akshare_adapter.fetch_fund_detail.side_effect = Exception('网络故障')
        job.xalpha_adapter.fetch_fund_fee.side_effect = Exception('费率获取失败')

        job.run()  # 不应抛出异常

        # stats 中应有 errors
        assert len(job.stats.get('errors', [])) == 2

    # ── 分批提交 ──
    def test_batch_commit(self, job, funds):
        """设置 batch_size=1，验证分批次提交"""
        job.akshare_adapter.fetch_fund_detail.return_value = {
            'fund_type_raw': '股票型',
            'company_name': '华夏基金',
        }
        job.xalpha_adapter.fetch_fund_fee.return_value = {}

        job.batch_size = 1  # 每只基金提交一次
        job.run()

        # 两只基金都应成功更新
        fund1 = job.db.query(Fund).filter_by(fund_code='000001').first()
        fund2 = job.db.query(Fund).filter_by(fund_code='002001').first()
        assert fund1.company_id is not None
        assert fund2.company_id is not None

    # ── 今日已处理跳过 ──
    def test_skip_already_processed_today(self, job, db):
        """last_nav_check 为今天时，应跳过"""
        fund = Fund(fund_code='000001', name='华夏成长', last_nav_check=date.today())
        db.add(fund)
        db.commit()

        job.akshare_adapter.fetch_fund_detail.return_value = {}
        job.xalpha_adapter.fetch_fund_fee.return_value = {}

        job.run()

        # 适配器不应被调用
        assert job.akshare_adapter.fetch_fund_detail.call_count == 0
        assert job.stats['skipped'] == 1
