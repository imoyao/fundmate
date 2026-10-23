# -*- coding: utf-8 -*-
"""指数估值分位基线回填（乐咕乐股月频，#1407 拍板「组合方案」）。

数据源：akshare ``stock_index_pe_lg``（乐咕乐股，免 cookie，月频约 21 年历史）。
本 Job 只取**近 5 年**（#1407 拍板：更长的市场结构不可比，基线与分位窗口同长），
只落「滚动市盈率」单列进 ``index_valuation_baselines``（与官方日频
``index_valuations`` 分表，理由见模型 docstring）。

覆盖范围以 ``LG_TARGETS`` 显式白名单为准（乐咕实测仅 9 个宽基有源）；无源指数
（中证A500 / 中证2000 等）由 adapter 返回空、本 Job 静默跳过，分位由读路径降级
为 None——**不**静默退化为全库扫描（数据策略硬约束 §3）。
"""

from datetime import date, timedelta
from typing import List

from loguru import logger

from app.domains.indices.models import IndexValuationBaseline
from app.services.index_percentile import PERCENTILE_WINDOW_DAYS
from app.services.job_base import IN_CHUNK_SIZE, SyncJob
from app.services.sync.bulk_ops import bulk_insert_rows, chunked

# 可写列（不含业务键与带默认值的 source）；批量写要求整批键集完全一致
_VALUE_COLUMNS = ('pe_ttm', 'index_name')
_DEFAULT_SOURCE = 'lg'

# 分位基线目标池：乐咕有覆盖的 9 个宽基（与 adapter.LG_INDEX_NAMES 同步维护）。
# 单次调用换整条月频序列，非逐条外部请求，裸 full-sync 即正常模式。
LG_TARGETS = [
    '000016',  # 上证50
    '000010',  # 上证180
    '000009',  # 上证380
    '000015',  # 上证红利
    '000300',  # 沪深300
    '000903',  # 中证100
    '000905',  # 中证500
    '000906',  # 中证800
    '000852',  # 中证1000
]


class IndexValuationLgSyncJob(SyncJob):
    """乐咕月频 PE 基线回填（近 5 年窗口；覆盖式 upsert，幂等可重跑）。"""

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'index_valuation_lg'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        codes = targets if targets else LG_TARGETS
        cutoff = date.today() - timedelta(days=PERCENTILE_WINDOW_DAYS)
        out: List[dict] = []
        for code in codes:
            rows = self.adapter.fetch_index_pe_lg(code)
            if not rows:
                logger.info(f'指数 {code} 乐咕无覆盖，跳过')
                continue
            kept = [r for r in rows if r.get('trade_date') and r['trade_date'] >= cutoff]
            out.extend(kept)
            logger.info(f'指数 {code} 乐咕基线 {len(kept)}/{len(rows)} 条（近 5 年窗口）')
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [r for r in raw_data if r.get('index_code') and r.get('trade_date') and r.get('pe_ttm') is not None]

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
        for r in new_data:
            row = existing.get((r['index_code'], r['trade_date']))
            if row is None:
                item = {'index_code': r['index_code'], 'trade_date': r['trade_date']}
                item.update({k: r.get(k) for k in _VALUE_COLUMNS})
                item['source'] = r.get('source') or _DEFAULT_SOURCE
                inserts.append(item)
                continue
            for k, v in r.items():
                if k in ('index_code', 'trade_date'):
                    continue
                if v is not None:
                    setattr(row, k, v)
        # 批量写：原实现逐行 SELECT + 逐行 `db.add`，Turso 上每行 2 次往返。
        # 本 job 一次回填 9 个指数 × 近 5 年约 60 个采样 = 500+ 行，逐行即分钟级停摆。
        if inserts:
            bulk_insert_rows(self.db, IndexValuationBaseline, inserts, log_scope='指数估值基线')
        self.db.commit()
        logger.info(f'写入指数估值基线 {len(new_data)} 条（新增 {len(inserts)}）')

    def _load_existing(self, new_data: List[dict]) -> dict:
        """一次查回本批已有行，键 = ``(index_code, trade_date)``（按较小一维过滤，理由同 ``index_valuation``）。"""
        codes = sorted({r['index_code'] for r in new_data})
        dates = sorted({r['trade_date'] for r in new_data})
        out: dict = {}
        if len(dates) <= len(codes):
            for part in chunked(dates, IN_CHUNK_SIZE):
                for row in (
                    self.db.query(IndexValuationBaseline).filter(IndexValuationBaseline.trade_date.in_(part)).all()
                ):
                    out[(row.index_code, row.trade_date)] = row
        else:
            for part in chunked(codes, IN_CHUNK_SIZE):
                for row in (
                    self.db.query(IndexValuationBaseline).filter(IndexValuationBaseline.index_code.in_(part)).all()
                ):
                    out[(row.index_code, row.trade_date)] = row
        return out
