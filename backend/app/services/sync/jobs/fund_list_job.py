# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:34
# File : fund_list_job.py
# -*- coding: utf-8 -*-
# app/services/sync/jobs/fund_list_job.py

from typing import List

from app.core.symbol_utils import get_normalizer
from app.domains.funds.models import Fund, FundCompany
from app.services.sync.jobs.base import SyncJob


class FundListSyncJob(SyncJob):
    """
    全市场基金列表同步。
    注意：xalpha 本身不提供全量列表，此处使用 akshare 数据源（在适配器中实现）。
    """

    def get_name(self) -> str:
        return 'fund_list'

    def _fetch_data(self, full_sync: bool) -> List[dict]:
        # 调用 adapter.fetch_fund_list()，该 adapter 应为 akshare（或 xalpha 包装）
        # 如果当前 adapter 是 XalphaAdapter 且不支持，会自动 fallback?
        # 为简化，我们直接预期 adapter 已实现 fetch_fund_list（在 AkshareAdapter 中实现）
        return self.adapter.fetch_fund_list()

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        validated = []
        normalizer = get_normalizer()
        for item in raw_data:
            fund_code = item.get('fund_code')
            name = item.get('name')
            if not fund_code or not name:
                continue
            # 标准化基金代码（6位数字）
            if len(fund_code) != 6 or not fund_code.isdigit():
                continue
            # 处理基金公司
            company_name = item.get('company_name')
            item['company_name'] = company_name
            # 可选字段
            item.setdefault('full_name', '')
            item.setdefault('fund_type', '')
            item.setdefault('risk_level', None)
            item.setdefault('create_time', None)
            validated.append(item)
        return validated

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 先过滤掉已存在的基金代码
        return self._deduplicate_by_unique_key(data, Fund, 'fund_code')

    def _save_data(self, new_data: List[dict]) -> None:
        # 1. 处理基金公司：先查重，再插入
        company_cache = {}
        for item in new_data:
            company_name = item.get('company_name', '')
            if not company_name:
                continue
            if company_name not in company_cache:
                existing = self.db.query(FundCompany).filter_by(name=company_name).first()
                if existing:
                    company_cache[company_name] = existing.id
                else:
                    # FundCompany 还有 code、full_name 字段
                    # 首次同步时公司编码未知，用 name 的拼音或留空
                    new_company = FundCompany(
                        name=company_name,
                        code='',  # 后续补充
                        full_name='',  # 后续补充
                    )
                    self.db.add(new_company)
                    self.db.flush()
                    company_cache[company_name] = new_company.id

        # 2. 构建 Fund 记录，映射 company_id
        fund_records = []
        for item in new_data:
            fund_records.append(
                {
                    'fund_code': item['fund_code'],
                    'name': item['name'],
                    'full_name': item.get('full_name', ''),
                    'company_id': company_cache.get(item.get('company_name')),
                    # 以下字段首次同步不填充
                    # "fund_type_id": None,
                    # "fund_variety_id": None,
                    # "symbol_prefix": item["fund_code"][:2],
                }
            )

        try:
            # 去重插入
            existing_codes = set(
                row[0]
                for row in self.db.query(Fund.fund_code)
                .filter(Fund.fund_code.in_([r['fund_code'] for r in fund_records]))
                .all()
            )
            new_records = [r for r in fund_records if r['fund_code'] not in existing_codes]
            if new_records:
                self.db.bulk_insert_mappings(Fund, new_records)
                self.logger.info(f'新增 {len(new_records)} 只基金')
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
