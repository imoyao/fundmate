# -*- coding: utf-8 -*-
"""指数估值同步任务（#1285 消费侧「指数」品类 / #1394）。

数据源：中证指数**官方**估值文件（akshare `stock_zh_index_value_csindex`，免 cookie）。
按 (index_code, trade_date) 覆盖式 upsert；无官方估值文件的指数**静默跳过**
（中证只为其自有/合作指数提供 indicator 文件，非全量指数都有）。

口径与限制：
- 官方列名「市盈率1 / 市盈率2 / 股息率1 / 股息率2」原样落库，不做主观口径命名；
- 官方文件仅下发近约 20 个交易日 → 本任务**不计算历史分位**（缺口单开 issue）。
"""

from typing import List

from loguru import logger

from app.domains.indices.models import IndexValuation
from app.services.job_base import IN_CHUNK_SIZE, SyncJob
from app.services.sync.bulk_ops import bulk_insert_rows, chunked, set_if_changed

# 可写列（不含 `index_code`/`trade_date` 业务键，也不含带 Python 默认值的 `source`）。
# 批量写要求整批**键集完全一致**，所以缺的列显式填 None，不能只塞 row 里有的键。
_VALUE_COLUMNS = ('index_name', 'pe_1', 'pe_2', 'dividend_yield_1', 'dividend_yield_2')
_DEFAULT_SOURCE = 'csindex'

# 默认目标：中证系主流宽基 / 红利（这些指数官方提供估值文件）
INDEX_VALUATION_TARGETS = [
    '000300',  # 沪深300
    '000905',  # 中证500
    '000852',  # 中证1000
    '000016',  # 上证50
    '000903',  # 中证100
    '000906',  # 中证800
    '000009',  # 上证380
    '000010',  # 上证180
    '000015',  # 上证红利
    '930950',  # 中证偏股基金
    '932000',  # 中证2000
    '000510',  # 中证A500
]


class IndexValuationSyncJob(SyncJob):
    """指数估值回填（全量，无需 targets）。"""

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'index_valuation'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        codes = targets if targets else INDEX_VALUATION_TARGETS
        out: List[dict] = []
        for code in codes:
            rows = self.adapter.fetch_index_valuation_csindex(code)
            if not rows:
                logger.info(f'指数 {code} 无官方估值文件，跳过')
                continue
            out.extend(rows)
            logger.info(f'指数 {code} 估值 {len(rows)} 条')
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [r for r in raw_data if r.get('index_code') and r.get('trade_date')]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        seen = set()
        out = []
        for r in data:
            key = (r['index_code'], r['trade_date'])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def _save_data(self, new_data: List[dict]) -> None:
        if not new_data:
            return
        existing = self._load_existing(new_data)
        inserts: List[dict] = []
        updated = unchanged = 0
        for r in new_data:
            row = existing.get((r['index_code'], r['trade_date']))
            if row is None:
                item = {'index_code': r['index_code'], 'trade_date': r['trade_date']}
                item.update({k: r.get(k) for k in _VALUE_COLUMNS})
                # source 显式给默认值：批量 INSERT 里不能塞 None，否则把模型默认抹成 NULL
                item['source'] = r.get('source') or _DEFAULT_SOURCE
                inserts.append(item)
                continue
            changed = False
            for k, v in r.items():
                if k in ('index_code', 'trade_date'):
                    continue
                # 仅在拿到新值时覆盖（避免用 None 抹掉上一轮已落库的口径值）
                if v is not None:
                    # 值真变了才赋值：Numeric 列读回来是 Decimal、源给的是 float，
                    # 裸 setattr 会让每行判脏 ⇒ 每行一条 UPDATE（Turso 0.2s/行）。
                    changed |= set_if_changed(row, k, v)
            if changed:
                updated += 1
            else:
                unchanged += 1
        # 批量写：原实现逐行 `filter_by().first()` + 逐行 `db.add`，Turso（Hrana/HTTP）
        # 上每行 2 次往返（~0.4s/行）。#2522 同族——每日调度被写库吃光预算
        # （run 39943903338 实测 index_daily 58.8 分钟）。
        if inserts:
            bulk_insert_rows(self.db, IndexValuation, inserts, log_scope='指数估值')
        self.db.commit()
        logger.info(f'写入指数估值 {len(new_data)} 条（新增 {len(inserts)} / 更新 {updated} / 未变 {unchanged}）')

    def _load_existing(self, new_data: List[dict]) -> dict:
        """一次查回本批已有行，键 = ``(index_code, trade_date)``。

        只按**较小的一维**过滤再按主键并入字典：用 ``codes × dates`` 的笛卡尔条件
        会撞 SQL 参数上限（``IN_CHUNK_SIZE`` = 900），且日频场景下 dates 通常只有 1~20 个。
        """
        codes = sorted({r['index_code'] for r in new_data})
        dates = sorted({r['trade_date'] for r in new_data})
        out: dict = {}
        if len(dates) <= len(codes):
            for part in chunked(dates, IN_CHUNK_SIZE):
                for row in self.db.query(IndexValuation).filter(IndexValuation.trade_date.in_(part)).all():
                    out[(row.index_code, row.trade_date)] = row
        else:
            for part in chunked(codes, IN_CHUNK_SIZE):
                for row in self.db.query(IndexValuation).filter(IndexValuation.index_code.in_(part)).all():
                    out[(row.index_code, row.trade_date)] = row
        return out
