# -*- coding: utf-8 -*-
"""指数名录同步任务（#1286 数据底座）。

与 index_constituent_job 的分工：名录回答「有哪些指数」（搜索/自选引用），
成分回答「某指数里有哪些股票」。akshare index_stock_info_sina 一次拉全量
名录（sh/sz 前缀指数），整体覆盖式更新（名录条目变化极少，全量重建成本可忽略）。
"""

from typing import List

from loguru import logger

from app.domains.indices.models import IndexCatalog
from app.services.sync.jobs.base import SyncJob


class IndexCatalogSyncJob(SyncJob):
    @property
    def _allow_empty_data(self) -> bool:
        # 接口偶发为空时静默跳过，避免清空既有名录
        return True

    def get_name(self) -> str:
        return 'index_catalog'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return self.adapter.fetch_index_catalog()

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [r for r in raw_data if r.get('index_code') and r.get('name')]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 按 index_code 去重（表列 unique 约束兜底）
        seen = set()
        out = []
        for r in data:
            if r['index_code'] in seen:
                continue
            seen.add(r['index_code'])
            out.append(r)
        return out

    def _save_data(self, new_data: List[dict]) -> None:
        # 名录整体覆盖式重建（条目量 ~千级，成本可忽略）
        self.db.query(IndexCatalog).delete(synchronize_session=False)
        for r in new_data:
            self.db.add(
                IndexCatalog(
                    index_code=r['index_code'],
                    name=r['name'],
                    exchange=r.get('exchange'),
                    source=r.get('source', 'sina'),
                )
            )
        self.db.commit()
        logger.info(f'指数名录重建完成，共 {len(new_data)} 条')
