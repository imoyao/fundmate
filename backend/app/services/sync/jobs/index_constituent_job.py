# -*- coding: utf-8 -*-
"""指数成分同步任务（#1286 数据底座）。

复用 akshare 现成接口，不自行造轮子：
- 中证系指数（000300/000905/000016/000852 等）：index_stock_cons_csindex
- 其他（上证/深证等）：index_stock_cons（sina）回退

成分会随指数调样变化，按指数整体覆盖式更新（先删后插）。
"""

from typing import List

from loguru import logger

from app.domains.indices.models import IndexConstituent
from app.services.sync.jobs.base import SyncJob

# 目标宽基 / 主流指数（plain code，不含交易所后缀）。
# csindex 系列优先走 index_stock_cons_csindex，其余回退 sina。
INDEX_TARGETS = [
    '000300',  # 沪深300
    '000905',  # 中证500
    '000016',  # 上证50
    '000852',  # 中证1000
    '399001',  # 深证成指
    '399006',  # 创业板指
    '000001',  # 上证指数
    '399106',  # 深证综指
]


class IndexConstituentSyncJob(SyncJob):
    """指数成分股回填。"""

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'index_constituents'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        codes = targets if targets else INDEX_TARGETS
        out = []
        for code in codes:
            rows = self.adapter.fetch_index_constituents_csindex(code)
            if not rows:
                rows = self.adapter.fetch_index_constituents_sina(code)
            index_name = rows[0].get('index_name') if rows else None
            for r in rows:
                symbol = r.get('symbol')
                if not symbol:
                    continue
                out.append(
                    {
                        'index_code': code,
                        'index_name': r.get('index_name') or index_name,
                        'symbol': symbol,
                        'stock_name': r.get('stock_name'),
                        'in_date': r.get('in_date'),
                    }
                )
            logger.info(f'指数 {code} 成分 {len(rows)} 条')
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [i for i in raw_data if i.get('index_code') and i.get('symbol')]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 按 (index_code, symbol) 去重，保留首次出现
        seen = set()
        out = []
        for i in data:
            key = (i['index_code'], i['symbol'])
            if key in seen:
                continue
            seen.add(key)
            out.append(i)
        return out

    def _save_data(self, new_data: List[dict]) -> None:
        # 按指数整体替换成分（指数调样后旧成分应被清除）
        by_index = {}
        for i in new_data:
            by_index.setdefault(i['index_code'], []).append(i)
        for index_code, rows in by_index.items():
            self.db.query(IndexConstituent).filter(IndexConstituent.index_code == index_code).delete(
                synchronize_session=False
            )
            for r in rows:
                self.db.add(
                    IndexConstituent(
                        index_code=r['index_code'],
                        index_name=r.get('index_name'),
                        symbol=r['symbol'],
                        stock_name=r.get('stock_name'),
                        in_date=r.get('in_date'),
                    )
                )
            logger.info(f'写入指数 {index_code} 成分 {len(rows)} 条')
        self.db.commit()
