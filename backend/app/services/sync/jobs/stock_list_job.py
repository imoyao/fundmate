# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:26
# File : stock_list_job.py
# -*- coding: utf-8 -*-
# app/services/sync/jobs/stock_list_job.py

from typing import List

from app.core.db_utils import bulk_insert_if_not_exists
from app.domains.securities.models import Security
from app.services.sync.jobs.base import SyncJob


class StockListSyncJob(SyncJob):
    def get_name(self) -> str:
        return 'stock_list'

    def _fetch_data(self, full_sync: bool) -> List[dict]:
        # 全量同步股票列表
        return self.adapter.fetch_stock_list()

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        # 基本清洗：去除空值，确保必填字段存在
        validated = []
        for item in raw_data:
            if not item.get('symbol') or not item.get('name'):
                continue
            # 补充默认值
            item.setdefault('market', 'CN_A')
            item.setdefault('type', 'stock')
            item.setdefault('currency', 'CNY')
            validated.append(item)
        return validated

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 使用基类通用去重，唯一键为 symbol
        return self._deduplicate_by_unique_key(data, Security, 'symbol')

    def _save_data(self, new_data: List[dict]) -> None:
        try:
            inserted = bulk_insert_if_not_exists(self.db, Security, new_data, 'symbol')
            self.db.commit()
            self.logger.info(f'已保存 {inserted} 条证券记录')
        except Exception:
            self.db.rollback()
            raise
