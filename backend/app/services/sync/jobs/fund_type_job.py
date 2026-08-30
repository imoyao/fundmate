# -*- coding: utf-8 -*-
"""基金类型回填任务（#1155 根治项）。

现状：本地库 fund_type_id 约 88.7% 缺失（#1155），搜索/筛选/风险等级展示都依赖它。
数据源：akshare fund_name_em（即 fetch_fund_list）含每只基金的「基金类型」文本。
本 Job 扫描待回填的基金（默认缺 fund_type_id / fund_variety_id 的行），
经 FundTypeResolver 映射后批量写回，幂等（只补 NULL，已填不覆盖）。

职责划分（低耦合）：
- 抓取、批量落库在本 Job；
- 原始类型文本 -> 内部 canonical ID 的下沉到 FundTypeResolver（enrich job 也复用）。
"""

from typing import List

from loguru import logger

from app.domains.funds.models import Fund
from app.services.sync.fund_type_resolution import FundTypeResolver
from app.services.sync.jobs.base import SyncJob


class FundTypeSyncJob(SyncJob):
    def get_name(self) -> str:
        return 'fund_type'

    @property
    def _allow_empty_data(self) -> bool:
        # 无基金可回填时静默跳过，不报错阻断整体同步
        return True

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """获取 (fund_code, raw_type) 列表。

        akshare fund_name_em 一次返回全市场，按实例缓存避免重复请求（分批时也只抓一次）。
        targets 为空（全量回填）时返回全部；否则仅筛选目标代码。
        """
        if not hasattr(self, '_list_cache'):
            self._list_cache = self.adapter.fetch_fund_list()
        if not targets:
            return [{'fund_code': r['fund_code'], 'raw_type': r.get('fund_type', '')} for r in self._list_cache]
        wanted = set(targets)
        return [
            {'fund_code': r['fund_code'], 'raw_type': r.get('fund_type', '')}
            for r in self._list_cache
            if r['fund_code'] in wanted
        ]

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        validated = []
        for item in raw_data:
            code = item.get('fund_code', '')
            if not code or len(code) != 6 or not code.isdigit():
                continue
            if not item.get('raw_type'):
                continue
            validated.append(item)
        return validated

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """按输入去重（保证 fund_code 唯一），不做「已存在则跳过」——本 Job 是更新语义。"""
        seen = set()
        out = []
        for item in data:
            code = item['fund_code']
            if code in seen:
                continue
            seen.add(code)
            out.append(item)
        return out

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """把待回填基金的 fund_type_id / fund_variety_id 批量写回。

        只处理数据库中确实缺失类型的行，避免无谓写与覆盖既有标注。
        """
        codes = [item['fund_code'] for item in new_data]
        funds = (
            self.db.query(Fund)
            .filter(Fund.fund_code.in_(codes))
            .filter((Fund.fund_type_id.is_(None)) | (Fund.fund_variety_id.is_(None)))
            .all()
        )
        if not funds:
            return

        resolver = FundTypeResolver(self.db)
        by_code = {f.fund_code: f for f in funds}
        updated = 0
        for item in new_data:
            fund = by_code.get(item['fund_code'])
            if fund is None:
                continue
            type_id, variety_id = resolver.resolve(item['raw_type'])
            if type_id is None and variety_id is None:
                continue
            if fund.fund_type_id is None and type_id is not None:
                fund.fund_type_id = type_id
            if fund.fund_variety_id is None and variety_id is not None:
                fund.fund_variety_id = variety_id
            updated += 1

        if updated:
            self.db.commit()
            logger.info(f'回填 {updated} 只基金类型')
