# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 14:13
# File : fund_detail_enrich_job.py
# app/services/sync/jobs/fund_detail_enrich_job.py

import time
from datetime import date
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy.orm import Session

from app.core.time_utils import now_shanghai
from app.domains.funds.models import FeeRatio, Fund, FundCompany, FundType, FundVariety, PurchaseRule, RedeemRule
from app.services.sync.jobs.base import BATCH_SIZE_DETAIL_ENRICH, FeeType, JobStatus, SyncJob


class FundDetailEnrichJob(SyncJob):
    """补充基金详细信息（分类、公司、费率等）"""

    def __init__(self, akshare_adapter, xalpha_adapter, db: Session):
        super().__init__(akshare_adapter, db)  # 基类需要
        self.akshare_adapter = akshare_adapter
        self.xalpha_adapter = xalpha_adapter

    def get_name(self) -> str:
        return 'fund_detail_enrich'

    # 本 Job 不使用基类标准流程，以下方法仅作为抽象方法占位
    def _fetch_data(self, full_sync: bool) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return []

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return []

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    # ---------- 目标代码 ----------
    def _get_target_codes(self) -> List[str]:
        """复用 target_file_codes 或从数据库获取核心池代码"""
        if hasattr(self, 'target_file_codes') and self.target_file_codes:
            return [c for c in self.target_file_codes if c.isdigit() and len(c) == 6]
        # 默认：所有活跃基金
        funds = self.db.query(Fund).filter(Fund.is_active).all()
        codes = [fund.fund_code for fund in funds]
        return codes

    # ---------- 主流程 ----------
    def run(self, full_sync: bool = False) -> Dict[str, Any]:
        self.snapshot_time = now_shanghai()
        self.status = JobStatus.RUNNING
        self._pre_run()
        self.logger.info('开始补充基金详情')

        # 初始化统计字典
        self.stats = {'enriched': 0, 'skipped': 0, 'errors': []}

        codes = self._get_target_codes()
        if not codes:
            self.logger.info('无基金需要补充详情')
            self.status = JobStatus.SUCCESS
            return self._build_result()

        total = len(codes)
        batch_size = BATCH_SIZE_DETAIL_ENRICH

        for i in range(0, total, batch_size):
            batch = codes[i : i + batch_size]
            self.logger.info(f'详情进度: {min(i + batch_size, total)}/{total}')

            for code in batch:
                try:
                    # 获取已有记录，跳过今日已处理的
                    fund = self.db.query(Fund).filter_by(fund_code=code).first()
                    if not fund:
                        continue
                    if fund.last_nav_check and fund.last_nav_check.date() == date.today():
                        self.stats['skipped'] += 1
                        continue

                    # 获取详情
                    akshare_detail = self.adapter.fetch_fund_detail(code)
                    xalpha_fee = self.xalpha_adapter.fetch_fund_fee(code)

                    # 更新基本信息
                    self._update_fund_basics(fund, akshare_detail)
                    # 更新费率
                    self._update_fund_fees(code, xalpha_fee)
                    # 更新时间戳
                    fund.last_nav_check = now_shanghai()
                    self.stats['enriched'] += 1

                except Exception as e:
                    logger.warning(f'补充基金 {code} 详情失败: {e}')
                    self.stats['errors'].append({'fund_code': code, 'error': str(e)})

            # 批次提交
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f'批次提交失败: {e}')
                time.sleep(1)  # 避免请求过快

        self._post_run()
        self.status = JobStatus.SUCCESS
        self.logger.info(
            f"基金详情补充完成: 新增 {self.stats['enriched']}, 跳过 {self.stats['skipped']}, 错误 {len(self.stats['errors'])}"
        )
        return self._build_result()

    # ---------- 内部辅助方法 ----------
    def _update_fund_basics(self, fund: Fund, detail: Dict[str, Any]):
        """更新基金静态信息字段"""
        if not detail:
            return

        # 基金类型映射
        raw_type = detail.get('fund_type_raw')
        if raw_type:
            fund_type_id = self._get_or_create_fund_type(raw_type)
            if fund_type_id:
                fund.fund_type_id = fund_type_id
                # 尝试推断大类 (简化: 取类型字符串分割的第一部分)
                variety_name = raw_type.split('-')[0] if '-' in raw_type else raw_type
                variety_id = self._get_or_create_fund_variety(variety_name)
                if variety_id:
                    fund.fund_variety_id = variety_id

        # 基金公司
        company_name = detail.get('company_name')
        if company_name:
            company_id = self._get_or_create_company(company_name)
            if company_id:
                fund.company_id = company_id

        # 其他字段
        if detail.get('create_time'):
            fund.create_time = detail['create_time']
        if detail.get('benchmark'):
            fund.benchmark = detail['benchmark']
        if detail.get('risk_level'):
            fund.risk_level = detail['risk_level']

    def _update_fund_fees(self, fund_code: str, fee_info: Dict[str, Any]):
        """根据 xalpha 费率数据创建/关联规则"""
        if not fee_info:
            return

        # 申购费率
        purchase_rate = fee_info.get('purchase_rate')
        if purchase_rate is not None:
            self._save_single_fee(fund_code, FeeType.PURCHASE, rate=purchase_rate, start_quota=0, end_quota=None)

        # 赎回费率阶梯
        redemption_schedule = fee_info.get('redemption_schedule')
        if redemption_schedule:
            for item in redemption_schedule:
                self._save_single_fee(
                    fund_code, FeeType.REDEEM, rate=item['rate'], start_day=item['start_day'], end_day=item['end_day']
                )

    def _save_single_fee(self, fund_code: str, fee_type: str, **kwargs):
        """保存单条费率记录，自动复用规则"""
        if fee_type in (FeeType.PURCHASE,):
            rule = self._get_or_create_purchase_rule(kwargs.get('start_quota', 0), kwargs.get('end_quota'))
            purchase_rule_id = rule.id if rule else None
            redeem_rule_id = None
        else:
            rule = self._get_or_create_redeem_rule(kwargs.get('start_day', 0), kwargs.get('end_day'))
            purchase_rule_id = None
            redeem_rule_id = rule.id if rule else None

        # 检查是否已存在相同关联
        existing = (
            self.db.query(FeeRatio)
            .filter_by(
                fund_code=fund_code, fee_type=fee_type, purchase_rule_id=purchase_rule_id, redeem_rule_id=redeem_rule_id
            )
            .first()
        )
        if not existing:
            fee_ratio = FeeRatio(
                fund_code=fund_code,
                fee_type=fee_type,
                rate=kwargs.get('rate'),
                fee_amount=kwargs.get('fee_amount'),
                purchase_rule_id=purchase_rule_id,
                redeem_rule_id=redeem_rule_id,
            )
            self.db.add(fee_ratio)

    # ---------- 规则复用方法 ----------
    def _get_or_create_purchase_rule(self, start_quota: float, end_quota: float = None):
        rule = self.db.query(PurchaseRule).filter_by(start_quota=start_quota, end_quota=end_quota).first()
        if not rule:
            rule = PurchaseRule(start_quota=start_quota, end_quota=end_quota)
            self.db.add(rule)
            self.db.flush()
        return rule

    def _get_or_create_redeem_rule(self, start_day: int, end_day: int = None):
        rule = self.db.query(RedeemRule).filter_by(start_day=start_day, end_day=end_day).first()
        if not rule:
            rule = RedeemRule(start_day=start_day, end_day=end_day)
            self.db.add(rule)
            self.db.flush()
        return rule

    def _get_or_create_fund_type(self, type_name: str) -> int:
        inst = self.db.query(FundType).filter_by(name=type_name).first()
        if not inst:
            inst = FundType(name=type_name)
            self.db.add(inst)
            self.db.flush()
        return inst.id

    def _get_or_create_fund_variety(self, variety_name: str) -> int:
        inst = self.db.query(FundVariety).filter_by(name=variety_name).first()
        if not inst:
            inst = FundVariety(name=variety_name)
            self.db.add(inst)
            self.db.flush()
        return inst.id

    def _get_or_create_company(self, company_name: str) -> int:
        inst = self.db.query(FundCompany).filter_by(name=company_name).first()
        if not inst:
            inst = FundCompany(name=company_name, code=company_name)
            self.db.add(inst)
            self.db.flush()
        return inst.id
