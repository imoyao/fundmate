# app/services/sync/jobs/fund_detail_enrich_job.py
"""
基金详细信息补充任务。
对传入的目标基金列表，补充分类、公司、费率、拼音等静态信息。

注意：pypinyin 是重型依赖（自带 3.2MB 词典），仅在生成拼音简拼时才需要，
因此刻意不放在模块顶层导入，避免应用启动/无关路径（如批量测试、其他 Job）
加载它导致峰值内存暴涨（曾在本机多进程 pytest-xdist 下触发 OOM）。
这是与 tasks.py 中 `-p no:xdist` 正交的额外防护，不要挪回顶层。
"""

import time
import traceback
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy.orm import Session

from app.core.time_utils import now_shanghai
from app.domains.funds.models import FeeRatio, Fund, FundType, PurchaseRule, RedeemRule
from app.services.fund_service import FundService
from app.services.sync.company_resolver import get_or_create_fund_company
from app.services.sync.fund_type_resolution import FundTypeResolver
from app.services.sync.jobs.base import BATCH_SIZE_DETAIL_ENRICH, JobStatus, SyncJob


class FundDetailEnrichJob(SyncJob):
    def __init__(self, akshare_adapter, xalpha_adapter, db: Session):
        super().__init__(akshare_adapter, db)
        self.akshare_adapter = akshare_adapter
        self.xalpha_adapter = xalpha_adapter

    def get_name(self) -> str:
        return 'fund_detail_enrich'

    # 以下四个方法是基类抽象方法的占位实现（本 Job 使用自定义 run 流程）
    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return []

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return []

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    # ── 主流程 ──

    def run(self, full_sync: bool = False, targets: List[str] = None) -> Dict[str, Any]:
        self.snapshot_time = now_shanghai()
        self.status = JobStatus.RUNNING
        self._pre_run()
        self.logger.info('开始补充基金详情')

        self.stats = {'enriched': 0, 'skipped': 0, 'errors': []}

        if not targets:
            self.logger.info('无基金需要补充详情')
            self.status = JobStatus.SUCCESS
            return self._build_result()

        total = len(targets)
        batch_size = getattr(self, 'batch_size', BATCH_SIZE_DETAIL_ENRICH)

        for i in range(0, total, batch_size):
            batch = targets[i : i + batch_size]
            self.logger.info(f'详情进度: {min(i + batch_size, total)}/{total}')

            for code in batch:
                try:
                    fund = self.db.query(Fund).filter_by(fund_code=code).first()
                    if not fund:
                        continue
                    # 今日已处理则跳过
                    if fund.last_nav_check and fund.last_nav_check.date() == date.today():
                        self.stats['skipped'] += 1
                        continue

                    # 获取详情和费率
                    akshare_detail = self.akshare_adapter.fetch_fund_detail(code)
                    xalpha_fee = self.xalpha_adapter.fetch_fund_fee(code)

                    # 更新基本信息
                    self._update_fund_basics(fund, akshare_detail)
                    # 更新费率
                    try:
                        self._update_fund_fees(code, xalpha_fee)
                    except Exception as e:
                        logger.warning(f'更新基金 {code} 费率失败: {e}\n{traceback.format_exc()}')
                    else:  # ✅ 只有没报错，才执行这行统计和标记
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
            f'基金详情补充完成: 新增 {self.stats["enriched"]}, '
            f'跳过 {self.stats["skipped"]}, 错误 {len(self.stats["errors"])}'
        )
        return self._build_result()

    # ── 基本信息更新 ──

    def _update_fund_basics(self, fund: Fund, detail: Dict[str, Any]) -> None:
        """根据 akshare 详情更新 fund 表的静态字段"""
        if not detail:
            return

        # 基金类型映射（文本 -> canonical ID 下沉到 FundTypeResolver，本 Job 只负责落库）
        raw_type = detail.get('fund_type_raw')
        raw_variety = detail.get('fund_variety_raw')
        if raw_type and not fund.fund_type_id:
            type_id, variety_id = FundTypeResolver(self.db).resolve(raw_type, raw_variety)
            fund.fund_type_id = type_id
            if variety_id and not fund.fund_variety_id:
                fund.fund_variety_id = variety_id

        # 若已有小类但缺大类，单独补全（resolver 回填大类并同步 fund_type 关联）
        if fund.fund_type_id and not fund.fund_variety_id and raw_variety:
            _, variety_id = FundTypeResolver(self.db).resolve(raw_type='', raw_variety=raw_variety)
            if variety_id:
                fund.fund_variety_id = variety_id
                fund_type = self.db.query(FundType).filter_by(id=fund.fund_type_id).first()
                if fund_type and fund_type.variety_id is None:
                    fund_type.variety_id = variety_id
                    self.db.flush()

        # 基金公司
        company_name = detail.get('company_name')
        if company_name and not fund.company_id:
            fund.company_id = self._get_or_create_company(company_name)

        # 全称
        if detail.get('fund_full_name') and not fund.full_name:
            fund.full_name = detail['fund_full_name']

        # 成立日期
        if detail.get('create_time') and not fund.create_time:
            fund.create_time = detail['create_time']

        # 业绩比较基准
        if detail.get('benchmark') and not fund.benchmark:
            fund.benchmark = detail['benchmark']

        if detail.get('risk_level') and not fund.risk_level:
            fund.risk_level = detail['risk_level']

        # 拼音简拼
        if fund.name and not fund.pinyin_abbr:
            fund.pinyin_abbr = self._generate_pinyin_abbr(fund.name)

    @staticmethod
    def _generate_pinyin_abbr(name: str) -> str:
        """
        生成拼音首字母简拼（仿天天基金规则：英文/数字原样保留，特殊符号跳过）。
        示例: "华夏成长混合" -> "HXCZHH"

        实现已抽取到 sync/pinyin_utils.generate_pinyin_abbr（amac_institution_job
        同样需要，#1081），此处保留方法作委托，兼容类内既有调用点。
        """
        from app.services.sync.pinyin_utils import generate_pinyin_abbr

        return generate_pinyin_abbr(name)

    # ── 费率更新 ──

    def _update_fund_fees(self, fund_code: str, fee_info: Dict[str, Any]) -> None:
        """根据 xalpha 返回的费率信息创建/关联费率规则"""
        if not fee_info:
            return

        # 费率币种：按基金份额名称特征推导（无结构化币种字段可依赖）
        fund = self.db.query(Fund).filter_by(fund_code=fund_code).first()
        currency = FundService.infer_fund_currency(full_name=fund.full_name, name=fund.name) if fund else 'CNY'

        # 申购费率
        purchase_rate = fee_info.get('purchase_rate')
        if purchase_rate is not None:
            self._save_single_fee(
                fund_code, 'purchase', rate=purchase_rate, start_quota=0, end_quota=None, currency=currency
            )

        # 🔥 关键修复：赎回费率阶梯可能是多个对象的列表，必须循环保存
        redemption_schedule = fee_info.get('redemption_schedule', [])
        if isinstance(redemption_schedule, list):
            for item in redemption_schedule:
                if isinstance(item, dict):  # 确保只处理字典类型的费率数据
                    self._save_single_fee(
                        fund_code,
                        'redeem',
                        rate=item.get('rate'),
                        start_day=item.get('start_day'),
                        end_day=item.get('end_day'),
                        currency=currency,
                    )

    def _save_single_fee(self, fund_code: str, fee_type: str, **kwargs) -> None:
        """保存单条费率记录，自动复用已有规则

        上游数据为百分数（如 1.5），需转为小数（0.015）存入 Decimal 列。
        """
        rate_raw = kwargs.get('rate')
        fee_amount_raw = kwargs.get('fee_amount')

        # ── 安全的 rate 转换 (小数) ──
        safe_rate = None
        if rate_raw is not None:
            try:
                # 先转为 Decimal，再除以 100 得到小数
                safe_rate = Decimal(str(rate_raw)) / Decimal('100')
            except Exception:
                safe_rate = Decimal('0')

        # ── 安全的 fee_amount 转换 ──
        safe_fee_amount = None
        if fee_amount_raw is not None:
            try:
                safe_fee_amount = int(fee_amount_raw)  # Integer 列
            except (ValueError, TypeError):
                safe_fee_amount = None

        # 复用或创建规则
        if fee_type == 'purchase':
            rule = self._get_or_create_purchase_rule(kwargs.get('start_quota', 0), kwargs.get('end_quota'))
            purchase_rule_id = rule.id if rule else None
            redeem_rule_id = None
        else:
            rule = self._get_or_create_redeem_rule(kwargs.get('start_day', 0), kwargs.get('end_day'))
            purchase_rule_id = None
            redeem_rule_id = rule.id if rule else None

        # 查重
        existing = (
            self.db.query(FeeRatio)
            .filter_by(
                fund_code=fund_code,
                fee_type=fee_type,
                purchase_rule_id=purchase_rule_id,
                redeem_rule_id=redeem_rule_id,
            )
            .first()
        )

        if not existing:
            fee_ratio = FeeRatio(
                fund_code=fund_code,
                fee_type=fee_type,
                rate=safe_rate,  # Decimal 小数
                fee_amount=safe_fee_amount,
                currency=kwargs.get('currency', 'CNY'),
                purchase_rule_id=purchase_rule_id,
                redeem_rule_id=redeem_rule_id,
            )
            self.db.add(fee_ratio)

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

    def _get_or_create_company(self, company_name: str) -> int:
        # 唯一写入口（company_resolver）：归一化匹配既有行，杜绝为同一主体建第二行
        if getattr(self, '_fund_company_cache', None) is None:
            self._fund_company_cache: Dict[str, int] = {}
        return get_or_create_fund_company(self.db, company_name, cache=self._fund_company_cache)
