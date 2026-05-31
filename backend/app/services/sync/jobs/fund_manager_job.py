# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:35
# File : fund_manager_job.py
# -*- coding: utf-8 -*-
# app/services/sync/jobs/fund_manager_job.py

from typing import List

from app.core.db_utils import bulk_insert_if_not_exists
from app.domains.funds.models import Fund, FundManager, Manager
from app.services.sync.jobs.base import SyncJob


class FundManagerSyncJob(SyncJob):
    """
    基金经理信息同步。
    获取每个基金的管理人列表，并保存到 managers 表和 fund_managers 关联表。
    """

    def get_name(self) -> str:
        return 'fund_manager'

    def _get_fund_codes(self) -> List[str]:
        funds = self.db.query(Fund.fund_code).all()
        return [f[0] for f in funds]

    def _fetch_data(self, full_sync: bool) -> List[dict]:
        fund_codes = self._get_fund_codes()
        if not fund_codes:
            return []
        all_managers = []
        for code in fund_codes:
            records = self.adapter.fetch_fund_manager(code)
            for rec in records:
                rec['fund_code'] = code
            all_managers.extend(records)
        return all_managers

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        validated = []
        for item in raw_data:
            if not item.get('fund_code') or not item.get('name') or not item.get('mgr_code'):
                continue
            validated.append(item)
        return validated

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 先过滤掉已存在的经理（按 mgr_code）
        existing_mgr_codes = set(
            row[0]
            for row in self.db.query(Manager.mgr_code).filter(Manager.mgr_code.in_([i['mgr_code'] for i in data])).all()
        )
        new_managers = [item for item in data if item['mgr_code'] not in existing_mgr_codes]
        # 对于关联表，我们后续全量重建或基于基金-经理对去重。简单起见，全部重新插入时做去重。
        return new_managers

    def _save_data(self, new_data: List[dict]) -> None:
        # 1. 插入新的经理
        manager_data = [
            {
                'mgr_code': item['mgr_code'],
                'name': item['name'],
                'appointment_date': item.get('appointment_date'),
                # 其他字段可后续扩展
            }
            for item in new_data
        ]
        inserted_managers = bulk_insert_if_not_exists(self.db, Manager, manager_data, 'mgr_code')
        self.logger.info(f'新增 {inserted_managers} 位经理')

        # 2. 建立基金-经理关联
        # 查询刚插入的经理 id 映射
        mgr_codes = [item['mgr_code'] for item in new_data]
        mgrs = self.db.query(Manager).filter(Manager.mgr_code.in_(mgr_codes)).all()
        mgr_id_map = {m.mgr_code: m.id for m in mgrs}

        # 查询基金 id 映射
        fund_codes = list({item['fund_code'] for item in new_data})
        funds = self.db.query(Fund).filter(Fund.fund_code.in_(fund_codes)).all()
        fund_id_map = {f.fund_code: f.id for f in funds}

        # 准备关联数据
        fund_manager_data = []
        for item in new_data:
            fund_id = fund_id_map.get(item['fund_code'])
            mgr_id = mgr_id_map.get(item['mgr_code'])
            if fund_id and mgr_id:
                fund_manager_data.append(
                    {
                        'fund_id': fund_id,
                        'mgr_id': mgr_id,
                        'start_date': item.get('appointment_date'),
                        'is_classic': item.get('is_classic', False),
                    }
                )

        # 去重插入关联表
        if fund_manager_data:
            existing_rels = set(
                (row.fund_id, row.mgr_id)
                for row in self.db.query(FundManager.fund_id, FundManager.mgr_id)
                .filter(FundManager.fund_id.in_(fund_id_map.values()), FundManager.mgr_id.in_(mgr_id_map.values()))
                .all()
            )
            new_rels = [rel for rel in fund_manager_data if (rel['fund_id'], rel['mgr_id']) not in existing_rels]
            if new_rels:
                self.db.bulk_insert_mappings(FundManager, new_rels)
                self.logger.info(f'新增 {len(new_rels)} 条基金-经理关联')

        self.db.commit()
