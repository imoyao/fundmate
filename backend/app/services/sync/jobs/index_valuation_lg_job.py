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
from app.services.job_base import SyncJob

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
        saved = 0
        for r in new_data:
            row = (
                self.db.query(IndexValuationBaseline)
                .filter_by(index_code=r['index_code'], trade_date=r['trade_date'])
                .first()
            )
            if row is None:
                row = IndexValuationBaseline(index_code=r['index_code'], trade_date=r['trade_date'])
                self.db.add(row)
            for k, v in r.items():
                if k in ('index_code', 'trade_date'):
                    continue
                if v is not None:
                    setattr(row, k, v)
            saved += 1
        self.db.commit()
        logger.info(f'写入指数估值基线 {saved} 条')
