# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/12
# File : security_industry_map_job.py
# app/services/sync/jobs/security_industry_map_job.py
"""证券 → 行业映射同步任务（#1981，2026-10-30 接万得补 csrc 缺口）。

读侧在 :mod:`app.services.penetration`（纯读），本任务负责把外部数据源刷进
``security_industry_maps``。**没有它，表永远是空的，功能等于没上线。**

## 刷什么、怎么刷

- ``sw1`` 申万一级：**每次全量刷**，31 个一级行业 × 1 个请求。覆盖广、成本低，不做增量判断。
- ``csrc`` 证监会门类（**主口径**，基金侧 ``fund_industry_allocs`` 只有 csrc）：
  只在给了 ``--targets`` 时刷。两条通道，**优先万得**：

  | 通道 | 覆盖 | 成本 | 何时用 |
  |---|---|---|---|
  | 万得 ``get_stock_basicinfo`` | 股票 + 可转债（自动解析正股） | 10 只/请求 | 配了 ``WIND_MCP_TOKEN``/``WIND_MCP_URL`` 时 |
  | 巨潮 ``stock_profile_cninfo`` | 仅 A 股 | 1 只/请求 | 万得不可用，或万得漏了某只 |

  典型用法是买入新股后按需补::

      pdm run sync --job security_industry_maps --targets 600519,110059

  没给 targets 时**只**更新 sw1 —— 这是刻意的：本任务跑在 market 域会话上，而持仓
  （``positions``）在 user 域，为了「自动找出该补哪几只」而跨域查询会把本卡变成一处
  新的跨域依赖（而本仓有跨域守卫）。宁可让缺口显式暴露在 ``industry_map_missing``
  里，也不要埋一个隐式的跨域读取。

## 失败处理

单只失败只记 warning 跳过；万得整批失败时**剩余代码回退巨潮**（不因为一条通道挂了就
放弃当轮）。**只有全表都空才算本次失败** —— 否则一次网络抖动就会把整张表清空（#1431
那类「停更 40 天零行」的教训）。
"""

from typing import Any, Dict, List

from loguru import logger

from app.services.adapters import wind_stock
from app.services.fund_utils import normalize_fund_code
from app.services.job_base import SyncJob
from app.services.security_industry_map_service import (
    SCHEME_CSRC,
    SCHEME_SW1,
    SOURCE_CNINFO,
    SOURCE_SWSRESEARCH,
    SOURCE_WIND,
    IndustryMapRow,
    csrc_code_of,
    fetch_csrc_industry_of,
    fetch_sw1_industry_map,
    upsert_industry_map,
)


class SecurityIndustryMapSyncJob(SyncJob):
    """个股 / 可转债 → 行业映射（#1981 / #2749）。"""

    @property
    def _allow_empty_data(self) -> bool:
        # 首次上线时表本来就是空的；空数据不该被当成同步失败
        return True

    def get_name(self) -> str:
        return 'security_industry_maps'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        out: List[dict] = []

        # ── 申万一级：全量（31 个请求）────────────────────────────────
        sw_rows = fetch_sw1_industry_map()
        for row in sw_rows:
            out.append({**row.as_dict(), 'scheme': SCHEME_SW1, 'source': SOURCE_SWSRESEARCH})

        # 申万「一级行业名 → 行业代码」映射：万得只给中文名，不给 801xxx 代码。
        # 不复用这份全量结果就得再问一次上游，而 sw1 行的 industry_code 必须是代码
        # （与既有行同构），故顺手建表；名字对不上就**不写 sw1**，不猜代码。
        sw_code_by_name = {row.industry_name: row.industry_code for row in sw_rows if row.industry_name}

        out.extend(self._fetch_target_rows(targets or [], sw_code_by_name))

        logger.info(f'[#1981] 取数合计 {len(out)} 条（sw1 全量 {len(sw_rows)} 条 + targets {len(targets or [])} 只）')
        return out

    # ── targets：万得优先，巨潮兜底 ────────────────────────────────────

    def _fetch_target_rows(self, targets: List[str], sw_code_by_name: Dict[str, str]) -> List[dict]:
        """按 targets 刷 csrc（主口径）与 sw1（能对上行业名时）。

        万得一条通道同时给两套口径且能解析可转债正股；巨潮只给 A 股 csrc。
        故顺序是「先用万得覆盖尽可能多，再把剩下的交给巨潮」，而不是二选一。
        """
        codes = [normalize_fund_code(t) for t in targets]
        codes = [c for c in dict.fromkeys(codes) if c]
        if not codes:
            return []

        rows: List[dict] = []
        covered: set[str] = set()

        if wind_stock.is_available():
            rows, covered = self._fetch_from_wind(codes, sw_code_by_name)

        leftovers = [c for c in codes if c not in covered]
        if leftovers:
            logger.info(f'[#2749] 万得未覆盖 {len(leftovers)} 只，回退巨潮（仅 csrc）: {leftovers}')
        for code in leftovers:
            row = fetch_csrc_industry_of(code)
            if row is None:
                continue
            rows.append({**row.as_dict(), 'scheme': SCHEME_CSRC, 'source': SOURCE_CNINFO})
            covered.add(code)
        return rows

    def _fetch_from_wind(self, codes: List[str], sw_code_by_name: Dict[str, str]) -> tuple[List[dict], set[str]]:
        """万得通道：股票批量、可转债逐只（实测混批与批量转债都会丢行，见 wind_stock 文档）。"""
        rows: List[dict] = []
        covered: set[str] = set()

        stocks = [c for c in codes if not wind_stock.is_bond_code(c)]
        bonds = [c for c in codes if wind_stock.is_bond_code(c)]

        try:
            stock_items = wind_stock.fetch_stock_industries(stocks) if stocks else {}
        except Exception as e:  # noqa: BLE001 - 通道级失败 ⇒ 交给巨潮兜底，不中断当轮
            logger.warning(f'[#2749] 万得股票行业通道失败，本批回退巨潮: {e}')
            stock_items = {}

        for symbol, item in stock_items.items():
            rows.extend(self._wind_rows(symbol, item, sw_code_by_name))
            covered.add(symbol)

        for bond in bonds:
            try:
                item = wind_stock.fetch_bond_industry(bond)
            except Exception as e:  # noqa: BLE001 - 单只失败只影响这一只
                logger.warning(f'[#2749] 万得转债行业通道失败 {bond}: {e}')
                continue
            if not item:
                continue
            rows.extend(self._wind_rows(bond, item, sw_code_by_name))
            covered.add(bond)
        return rows, covered

    @staticmethod
    def _wind_rows(symbol: str, item: Dict[str, Any], sw_code_by_name: Dict[str, str]) -> List[dict]:
        """一条万得结果 → 最多两行（csrc 主口径 + sw1）。

        csrc 走 ``csrc_code_of``（中文门类名 → 单字母；认不出返回 None 即不写），
        与巨潮通道同一套字典——两路写进同一张表必须是同一套编码，否则读侧会看到
        同一只股票两个 csrc 值。
        """
        out: List[dict] = []
        csrc_name = item.get('csrc')
        csrc_code = csrc_code_of(csrc_name)
        if csrc_code:
            out.append(
                {
                    'symbol': symbol,
                    'scheme': SCHEME_CSRC,
                    'source': SOURCE_WIND,
                    'industry_code': csrc_code,
                    'industry_name': csrc_name,
                    'source_ref': item.get('wind_code') or item.get('underlying'),
                    'effective_date': None,
                }
            )
        elif csrc_name:
            logger.warning(f'[#2749] 证监会门类名未收录 {symbol}: {csrc_name!r}（不猜，留缺口）')

        sw1_name = item.get('sw1')
        sw1_code = sw_code_by_name.get(sw1_name) if sw1_name else None
        if sw1_code:
            out.append(
                {
                    'symbol': symbol,
                    'scheme': SCHEME_SW1,
                    'source': SOURCE_WIND,
                    'industry_code': sw1_code,
                    'industry_name': sw1_name,
                    'source_ref': item.get('wind_code') or item.get('underlying'),
                    'effective_date': None,
                }
            )
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
        万得行排在巨潮行之前（``_fetch_target_rows`` 的构造顺序），故两路都拿到时
        以万得为准——它给的是主口径 csrc 原文，不需要二次猜。
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
        # 按 (scheme, source) 分组：同一 scheme 可能来自不同通道（万得 / 巨潮 / 申万官网），
        # source 是回溯「这条数据谁给的」的唯一线索，不能被 scheme 吞掉。
        grouped: Dict[tuple, List[IndustryMapRow]] = {}
        for r in data:
            grouped.setdefault((r['scheme'], r['source']), []).append(
                IndustryMapRow(
                    symbol=r['symbol'],
                    industry_code=r['industry_code'],
                    industry_name=r.get('industry_name'),
                    source_ref=r.get('source_ref'),
                    effective_date=r.get('effective_date'),
                )
            )

        for (scheme, source), rows in grouped.items():
            stats = upsert_industry_map(self.db, rows, scheme, source)
            logger.info(f'[#1981] {scheme}/{source} 落库：{stats}')
            # 两个层级都记：scheme 级给「这次补了多少」的粗看，scheme_source 级给
            # 「这条数据是万得还是巨潮给的」的追溯（统计页按前缀取用）。
            for prefix in (scheme, f'{scheme}_{source}'):
                self.stats[f'{prefix}_inserted'] = self.stats.get(f'{prefix}_inserted', 0) + stats['inserted']
                self.stats[f'{prefix}_updated'] = self.stats.get(f'{prefix}_updated', 0) + stats['updated']
