# app/services/sync/jobs/fund_manager_job.py
"""基金经理同步任务（全量，当前接口不稳定，暂时跳过）"""

from typing import List

from loguru import logger

from app.core.db_utils import bulk_insert_if_not_exists
from app.domains.funds.models import Fund, FundManager, Manager
from app.services.sync.jobs.base import SyncJob


class FundManagerSyncJob(SyncJob):
    def get_name(self) -> str:
        return 'fund_manager'

    # ── 目标代码获取 ──

    def _get_all_fund_codes(self) -> List[str]:
        """获取所有已存在的基金代码"""
        funds = self.db.query(Fund.fund_code).all()
        return [fund.fund_code for fund in funds]

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """遍历所有基金代码，获取关联的基金经理"""
        codes = targets if targets else self._get_all_fund_codes()
        if not codes:
            return []

        all_managers = list()
        for code in codes:
            try:
                managers = self.adapter.fetch_fund_manager(code)
                for mgr in managers:
                    mgr['fund_code'] = code
                all_managers.extend(managers)
            except Exception as e:
                logger.warning(f'获取基金 {code} 经理信息失败: {e}')
        return all_managers

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """确保必填字段存在，生成唯一 mgr_code"""
        validated = list()
        for item in raw_data:
            if not item.get('fund_code') or not item.get('name'):
                continue
            # 生成唯一经理标识（如果适配器未提供）
            if not item.get('mgr_code'):
                import hashlib

                raw = f'{item.get("name", "")}_{item.get("company", "")}'
                item['mgr_code'] = hashlib.sha256(raw.encode()).hexdigest()[:12]
            validated.append(item)
        return validated

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """基于 mgr_code 去重"""
        return self._deduplicate_by_unique_key(data, Manager, 'mgr_code')

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """插入新经理并建立基金-经理关联"""
        # 1. 插入新经理
        mgr_records = [{'mgr_code': item['mgr_code'], 'name': item['name']} for item in new_data]
        inserted = bulk_insert_if_not_exists(self.db, Manager, mgr_records, 'mgr_code')
        logger.info(f'新增 {inserted} 位经理')

        # 2. 建立基金-经理关联
        mgr_codes = [item['mgr_code'] for item in new_data]
        mgr_map = {m.mgr_code: m.id for m in self.db.query(Manager).filter(Manager.mgr_code.in_(mgr_codes)).all()}
        fund_codes = list({item['fund_code'] for item in new_data})
        fund_map = {f.fund_code: f.id for f in self.db.query(Fund).filter(Fund.fund_code.in_(fund_codes)).all()}

        rel_records = list()
        for item in new_data:
            fid = fund_map.get(item['fund_code'])
            mid = mgr_map.get(item['mgr_code'])
            if fid and mid:
                rel_records.append({'fund_id': fid, 'mgr_id': mid})

        existing_rels = set(
            (row.fund_id, row.mgr_id)
            for row in self.db.query(FundManager.fund_id, FundManager.mgr_id)
            .filter(
                FundManager.fund_id.in_(fund_map.values()),
                FundManager.mgr_id.in_(mgr_map.values()),
            )
            .all()
        )
        new_rels = [r for r in rel_records if (r['fund_id'], r['mgr_id']) not in existing_rels]
        if new_rels:
            self.db.bulk_insert_mappings(FundManager, new_rels)
            logger.info(f'新增 {len(new_rels)} 条基金-经理关联')

        self.db.commit()
