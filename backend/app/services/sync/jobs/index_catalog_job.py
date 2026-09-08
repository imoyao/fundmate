# -*- coding: utf-8 -*-
"""指数名录同步任务（#1286 数据底座；#1365 三源合并）。

与 index_constituent_job 的分工：名录回答「有哪些指数」（搜索/自选引用），
成分回答「某指数里有哪些股票」。

三源合并（2026-09-09，调研见 docs/working-notes/index-catalog-sources-research-2026-09-08.md）：
- 新浪 index_stock_info：交易所挂牌指数（带 SH/SZ 归属）
- 中证官网 index_csindex_all：中证专属码唯一来源（930950/932000/000510）
- 国证官网 index_all_cni：国证专属码唯一来源（399303/399317）
去重优先级 sina > csindex > cni（sina 带交易所归属信息最全）；
万得系（881001 等）无免费权威源，以 399317 国证A指 / 000985 中证全指替代。
"""

from typing import List

from loguru import logger

from app.domains.indices.models import IndexCatalog
from app.services.sync.jobs.base import SyncJob


class IndexCatalogSyncJob(SyncJob):
    @property
    def _allow_empty_data(self) -> bool:
        # 三源全空视为接口异常，静默跳过，避免清空既有名录
        return True

    def get_name(self) -> str:
        return 'index_catalog'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        # 顺序即去重优先级（_deduplicate 保留首次出现）：sina > csindex > cni
        fetchers = [
            ('sina', self.adapter.fetch_index_catalog),
            ('csindex', self.adapter.fetch_index_catalog_csindex),
            ('cni', self.adapter.fetch_index_catalog_cni),
        ]
        out: List[dict] = []
        for name, fetch in fetchers:
            try:
                rows = fetch()
                out.extend(rows)
                logger.info(f'指数名录源 {name} 获取 {len(rows)} 条')
            except Exception as e:
                # 单源失败不阻断其他源（名录覆盖面优先于单源完整性）
                logger.warning(f'指数名录源 {name} 获取失败: {e}')
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [r for r in raw_data if r.get('index_code') and r.get('name')]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 按 index_code 去重，保留首次出现（即高优先级源）；表列 unique 约束兜底
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
