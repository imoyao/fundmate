# -*- coding: utf-8 -*-
"""指数日线点位同步任务（#275 基准对比 / #861 绩效分析底座）。

数据源：韭圈儿公开接口（JiucaishuoAdapter，免登录 best-effort，万得全A 点位
为反推派生值——口径与风险见 jiucaishuo_adapter.py 模块注释）。

写入语义：按 (index_code, trade_date) **upsert**（覆盖同日），非名录那种整体
重建——日线序列应只增不改（反推锚点平移会导致全序列微小漂移，重跑全量
以最新锚点为准，属预期行为）。

增量策略：全量（--full-sync / grab.all）拉近 120 月（接口上限 10 年）；
常规增量拉近 12 月（2 个 HTTP 请求，自愈缺口）。
"""

from typing import List

from loguru import logger

from app.domains.indices.models import IndexDaily
from app.services.sync.jobs.base import SyncJob

# 默认目标：万得全A（Wind 专有代码，韭圈儿 gu_code 原生形态）
DEFAULT_TARGETS = ['881001.WI']


class IndexDailySyncJob(SyncJob):
    batch_size = 5  # 每目标 2 个 HTTP 请求，batch 无需大

    @property
    def _allow_empty_data(self) -> bool:
        # 数据源失败/非交易日返回空时静默跳过，不阻断整体同步
        return True

    def get_name(self) -> str:
        return 'index_daily'

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        # '__full__' 是编排器的全量占位符，不是真实 gu_code
        gu_codes = [t for t in targets if t != '__full__'] or DEFAULT_TARGETS
        months = 120 if full_sync else 12
        out = []
        for gu in gu_codes:
            gu = gu.strip()
            if not gu:
                continue
            try:
                out.append({'gu_code': gu, **self.adapter.fetch_index_daily(gu, months)})
            except Exception as e:
                # 单目标失败不阻断其他目标（best-effort 数据源，fallback 见 #275）
                self.logger.warning(f'指数日线 {gu} 获取失败: {e}')
        return out

    # ── 校验 / 去重 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        for item in raw_data:
            rows = item.get('rows') or []
            if not rows:
                self.logger.warning(f'指数日线 {item.get("gu_code")} 序列为空，跳过')
                continue
            out.append(item)
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 行内按 trade_date 去重（保留首现）；跨次运行靠 _save_data 的 upsert 覆盖
        for item in data:
            seen = set()
            rows = []
            for r in item['rows']:
                if r['trade_date'] in seen:
                    continue
                seen.add(r['trade_date'])
                rows.append(r)
            item['rows'] = rows
        return data

    # ── 落库（upsert）──

    def _save_data(self, new_data: List[dict]) -> None:
        for item in new_data:
            index_code = item['gu_code']
            rows = item['rows']
            existing = {
                r.trade_date: r
                for r in self.db.query(IndexDaily)
                .filter(
                    IndexDaily.index_code == index_code,
                    IndexDaily.trade_date.in_([r['trade_date'] for r in rows]),
                )
                .all()
            }
            inserted = updated = 0
            for r in rows:
                row = existing.get(r['trade_date'])
                if row is None:
                    self.db.add(
                        IndexDaily(
                            index_code=index_code,
                            trade_date=r['trade_date'],
                            close=r['close'],
                            ret_pct=r.get('ret_pct'),
                            source='jiucaishuo',
                        )
                    )
                    inserted += 1
                else:
                    row.close = r['close']
                    row.ret_pct = r.get('ret_pct')
                    updated += 1
            self.db.commit()
            logger.info(f'指数日线 {index_code}: 新增 {inserted} / 更新 {updated}（共 {len(rows)} 条）')
