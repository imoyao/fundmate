# app/services/sync/jobs/stock_list_job.py
"""证券列表同步任务（全量）"""

from typing import List

from loguru import logger

from app.domains.securities.models import Security
from app.services.sync.jobs.base import SyncJob


class StockListSyncJob(SyncJob):
    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'stock_list'

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """全量获取所有 A 股股票基本信息（忽略传入的 targets）"""
        return self.adapter.fetch_stock_list()

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """清洗股票列表数据：确保 symbol 和 name 非空，补充默认值"""
        validated = list()
        for item in raw_data:
            if not item.get('symbol') or not item.get('name'):
                continue
            item.setdefault('market', 'CN_A')
            item.setdefault('type', 'stock')
            item.setdefault('currency', 'CNY')
            validated.append(item)
        return validated

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """基于 symbol 去重"""
        return self._deduplicate_by_unique_key(data, Security, 'symbol')

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """批量插入新的证券记录"""
        if not new_data:
            return

        # 批量插入（数据库会自动跳过已存在的 symbol 因为 unique 约束）
        existing_symbols = {
            row[0]
            for row in self.db.query(Security.symbol)
            .filter(Security.symbol.in_([item['symbol'] for item in new_data]))
            .all()
        }
        new_records = [item for item in new_data if item['symbol'] not in existing_symbols]

        if new_records:
            self.db.bulk_insert_mappings(Security, new_records)
            logger.info(f'新增 {len(new_records)} 只证券')

        self.db.commit()
