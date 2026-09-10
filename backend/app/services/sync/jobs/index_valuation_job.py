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
from app.services.sync.jobs.base import SyncJob

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
        saved = 0
        for r in new_data:
            row = (
                self.db.query(IndexValuation).filter_by(index_code=r['index_code'], trade_date=r['trade_date']).first()
            )
            if row is None:
                row = IndexValuation(index_code=r['index_code'], trade_date=r['trade_date'])
                self.db.add(row)
            for k, v in r.items():
                if k in ('index_code', 'trade_date'):
                    continue
                # 仅在拿到新值时覆盖（避免用 None 抹掉上一轮已落库的口径值）
                if v is not None:
                    setattr(row, k, v)
            saved += 1
        self.db.commit()
        logger.info(f'写入指数估值 {saved} 条')
