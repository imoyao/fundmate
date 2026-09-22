# app/services/sync/jobs/stock_list_job.py
"""证券列表同步任务（全量）"""

from typing import List

from app.domains.securities.models import Security
from app.services.job_base import IN_CHUNK_SIZE, SyncJob


class StockListSyncJob(SyncJob):
    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'stock_list'

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """全量获取场内证券名录：A 股个股 + ETF + 可转债（忽略传入的 targets）。

        #1104：原先只拉个股（`stock_info_a_code_name`），于是 securities 表 5525 条全是
        type='stock'，持仓/自选里的 ETF 与可转债**根本没有证券记录** ——
        而 `PriceHistorySyncJob` 按 symbol 查 securities，查不到即 continue，
        这些品种的日线因此永远为 0 行，自选页最新价只能回落到导入快照。
        """
        return self.adapter.fetch_security_catalog()

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
        """仅去除本次抓取内部的重复 symbol；存量记录的差异交给 `_save_data` 做 upsert。

        不能再用 `_deduplicate_by_unique_key`（它会过滤掉已存在的 symbol）：
        那等于「已登记过的记录永不更新」，ETF / 可转债的 type 修正与名称改名都落不了库（#1104）。
        """
        seen, deduped = set(), []
        for item in data:
            symbol = item.get('symbol')
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            deduped.append(item)
        return deduped

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """新增缺失记录 + 更新存量记录的 name/market/type（upsert，#1104）。

        为什么必须更新存量：ETF / 可转债原先要么没进名录、要么被硬编码的 type='stock' 落库；
        若只插不更新，名录补齐后这些记录仍然是「股票」，按 type 分派的日线取数照样走错接口。
        in_ 分批查询防 SQLite 变量上限（名录 7000+ 条，超 999 变量会 OperationalError）。
        """
        if not new_data:
            return

        symbols = [item['symbol'] for item in new_data]
        existing = {}
        for i in range(0, len(symbols), IN_CHUNK_SIZE):
            chunk = symbols[i : i + IN_CHUNK_SIZE]
            for row in self.db.query(Security).filter(Security.symbol.in_(chunk)).all():
                existing[row.symbol] = row

        inserts, updates = [], []
        for item in new_data:
            row = existing.get(item['symbol'])
            if row is None:
                inserts.append(item)
                continue
            market = item.get('market') or row.market
            if row.type != item['type'] or row.name != item['name'] or row.market != market:
                updates.append({'id': row.id, 'name': item['name'], 'market': market, 'type': item['type']})

        if inserts:
            self.db.bulk_insert_mappings(Security, inserts)
        if updates:
            self.db.bulk_update_mappings(Security, updates)

        self.db.commit()
        self.logger.info(f'证券名录同步完成：新增 {len(inserts)}，更新 {len(updates)}')
