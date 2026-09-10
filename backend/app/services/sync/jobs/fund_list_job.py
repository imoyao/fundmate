# app/services/sync/jobs/fund_list_job.py
"""基金列表同步任务（全量）"""

from typing import List

from loguru import logger

from app.domains.funds.models import Fund
from app.services.sync.company_resolver import get_or_create_fund_company
from app.services.sync.jobs.base import SyncJob


class FundListSyncJob(SyncJob):
    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'fund_list'

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """全量获取所有公募基金基本信息（忽略传入的 targets）"""
        return self.adapter.fetch_fund_list()

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """清洗基金列表数据：确保 fund_code 为 6 位数字，name 非空"""
        validated = list()
        for item in raw_data:
            code = item.get('fund_code', '')
            name = item.get('name', '')
            if not code or len(code) != 6 or not code.isdigit():
                continue
            if not name:
                continue
            validated.append(item)
        return validated

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """基于 fund_code 去重"""
        return self._deduplicate_by_unique_key(data, Fund, 'fund_code')

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """
        分两步写入：
        1. 提取新基金公司并插入 fund_companies 表
        2. 插入新的基金记录到 funds 表
        """
        # 1. 处理基金公司
        company_names = {item.get('company_name', '') for item in new_data if item.get('company_name')}
        company_cache = {}

        for name in company_names:
            # 唯一写入口（company_resolver）：精确名 → 归一化名 + 业务族 → 才新建
            company_cache[name] = get_or_create_fund_company(self.db, name, cache=company_cache)

        # 2. 构建基金记录
        fund_records = list()
        for item in new_data:
            fund_records.append(
                {
                    'fund_code': item['fund_code'],
                    'name': item['name'],
                    'company_id': company_cache.get(item.get('company_name')),
                }
            )

        # 3. 去重后批量插入基金记录
        existing_codes = {
            row[0]
            for row in self.db.query(Fund.fund_code)
            .filter(Fund.fund_code.in_([r['fund_code'] for r in fund_records]))
            .all()
        }
        new_records = [r for r in fund_records if r['fund_code'] not in existing_codes]

        if new_records:
            self.db.bulk_insert_mappings(Fund, new_records)
            logger.info(f'新增 {len(new_records)} 只基金')
        self.db.commit()
