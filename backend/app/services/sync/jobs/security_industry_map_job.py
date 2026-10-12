# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/12
# File : security_industry_map_job.py
# app/services/sync/jobs/security_industry_map_job.py
"""证券 → 行业映射同步任务（#1981）。

读侧在 :mod:`app.services.penetration`（纯读），本任务负责把外部数据源刷进
``security_industry_maps``。**没有它，表永远是空的，功能等于没上线。**

## 刷什么、怎么刷

- ``sw1`` 申万一级：**每次全量刷**，31 个一级行业 × 1 个请求（实测 3/3 通过）。
  覆盖广、成本低，所以不做增量判断。
- ``csrc`` 证监会门类：**只在给了 ``--targets`` 时刷**（巨潮逐只，5000+ 请求刷不起）。
  典型用法是买入新股后按需补::

      pdm run sync --job security_industry_maps --targets 600519,000001

  没给 targets 时**只**更新 sw1 —— 这是刻意的：本任务跑在 market 域会话上，而持仓
  （``positions``）在 user 域，为了「自动找出该补哪几只」而跨域查询会把本卡变成一处
  新的跨域依赖（而本仓有跨域守卫）。宁可让缺口显式暴露在 ``industry_map_missing``
  里，也不要埋一个隐式的跨域读取。

## 失败处理

单只 ``csrc`` 取数失败只记 warning 跳过；``sw1`` 单个行业失败也只跳过该行业
（见 :func:`fetch_sw1_industry_map`）。**只有全表都空才算本次失败** —— 否则一次网络
抖动就会把整张表清空（#1431 那类「停更 40 天零行」的教训）。
"""

from typing import List

from loguru import logger

from app.services.job_base import SyncJob
from app.services.security_industry_map_service import (
    SCHEME_CSRC,
    SCHEME_SW1,
    SOURCE_CNINFO,
    SOURCE_SWSRESEARCH,
    IndustryMapRow,
    fetch_csrc_industry_of,
    fetch_sw1_industry_map,
    upsert_industry_map,
)


class SecurityIndustryMapSyncJob(SyncJob):
    """个股 / 可转债 → 行业映射（#1981）。"""

    @property
    def _allow_empty_data(self) -> bool:
        # 首次上线时表本来就是空的；空数据不该被当成同步失败
        return True

    def get_name(self) -> str:
        return 'security_industry_maps'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        out: List[dict] = []

        # ── 申万一级：全量（31 个请求）────────────────────────────────
        for row in fetch_sw1_industry_map():
            out.append({**row.as_dict(), 'scheme': SCHEME_SW1, 'source': SOURCE_SWSRESEARCH})

        # ── 证监会门类：仅按 targets 逐只（巨潮）──────────────────────
        for code in targets or []:
            row = fetch_csrc_industry_of(code)
            if row is None:
                continue
            out.append({**row.as_dict(), 'scheme': SCHEME_CSRC, 'source': SOURCE_CNINFO})

        logger.info(f'[#1981] 取数合计 {len(out)} 条（sw1 全量 + csrc {len(targets or [])} 只）')
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [
            r
            for r in raw_data
            if r.get('symbol') and r.get('industry_code') and r.get('scheme') in (SCHEME_CSRC, SCHEME_SW1)
        ]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """按 ``(symbol, scheme)`` 去重，保留首条。

        同一只股票理论上只属于申万一个一级行业；但接口偶发重复行时，保留首条比
        「留最后一条」更安全 —— 后者会让下游无提示地取到另一条记录。
        """
        seen = set()
        out = []
        for r in data:
            key = (r['symbol'], r['scheme'])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def _save_data(self, data: List[dict]) -> None:
        by_scheme: dict[str, List[IndustryMapRow]] = {}
        sources = {SCHEME_SW1: SOURCE_SWSRESEARCH, SCHEME_CSRC: SOURCE_CNINFO}
        for r in data:
            by_scheme.setdefault(r['scheme'], []).append(
                IndustryMapRow(
                    symbol=r['symbol'],
                    industry_code=r['industry_code'],
                    industry_name=r.get('industry_name'),
                    source_ref=r.get('source_ref'),
                    effective_date=r.get('effective_date'),
                )
            )

        for scheme, rows in by_scheme.items():
            stats = upsert_industry_map(self.db, rows, scheme, sources[scheme])
            logger.info(f'[#1981] {scheme} 落库：{stats}')
            self.stats[f'{scheme}_inserted'] = stats['inserted']
            self.stats[f'{scheme}_updated'] = stats['updated']
