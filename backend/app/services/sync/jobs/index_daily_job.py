# -*- coding: utf-8 -*-
"""指数日线点位同步任务（#275 基准对比 / #861 绩效分析底座）。

数据源：韭圈儿公开接口（JiucaishuoAdapter，免登录 best-effort）。点位口径双模式：
- anchored：有真实收盘锚（股票/宽基指数如 881001 万得全A），反推派生、锚随最新收盘平移；
- normalized：基金指数（885 系）无估值锚，起点归一化 1000，逐日确定不漂移。
口径与风险细节见 jiucaishuo_adapter.py 模块注释。

写入语义：按 (index_code, trade_date) **upsert**（覆盖同日），非名录那种整体
重建——日线序列应只增不改（反推锚点平移会导致全序列微小漂移，重跑全量
以最新锚点为准，属预期行为）。

目标与增量策略（#275 定稿的万得系全家桶，见 WIND_INDEX_TARGETS）：
全量（--full-sync / grab.all）取成立来（date='all'，万得全A 6464 条）；
常规增量（每日调度）拉近 12 月（2 个 HTTP 请求/目标，自愈缺口）。
"""

from typing import List

from loguru import logger

from app.domains.indices.models import IndexDaily
from app.services.sync.jobs.base import SyncJob

# 万得系指数目标清单（#275 定稿）：韭圈儿 gu_code 原生形态（.WI 后缀）。
# 来源：#275 2022 年评论梳理的「适用性广泛」万得基金系列指数 + 万得全A；
# 新增品种在此追加一行即可（接口通用，无每指数特判）。
# 可用性（2026-09-09 实测）：✅=韭圈儿已收录可取；⏳=暂未收录（detail 无序列），
# 保留在清单中——收录后自动生效（每日增量 warning 即跟进信号）。
WIND_INDEX_TARGETS: List[tuple] = [
    ('881001.WI', '万得全A'),  # ✅ anchored 6464 条
    ('885000.WI', '万得普通股票型基金指数'),  # ✅ normalized 5503 条
    ('885001.WI', '万得偏股混合型基金指数'),  # ✅ normalized 5508 条
    ('885002.WI', '万得平衡混合型基金指数'),  # ⏳ 未收录
    ('885003.WI', '万得偏债混合型基金指数'),  # ✅ normalized 5502 条
    ('885005.WI', '万得债券型基金指数'),  # ⏳ 未收录
    ('885006.WI', '万得混合债券型一级基金指数'),  # ⏳ 未收录
    ('885007.WI', '万得混合债券型二级基金指数'),  # ✅ normalized 5503 条
    ('885008.WI', '万得中长期纯债型基金指数'),  # ⏳ 未收录
    ('885072.WI', '万得混合型FOF指数'),  # ⏳ 未收录
    ('885073.WI', '万得偏股混合型FOF指数'),  # ⏳ 未收录
    ('885074.WI', '万得平衡混合型FOF指数'),  # ⏳ 未收录
    ('885075.WI', '万得偏债混合型FOF指数'),  # ⏳ 未收录
]
DEFAULT_TARGETS = [gu for gu, _name in WIND_INDEX_TARGETS]


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
        # 全量取成立来（接口 date='all'）；增量拉近 12 月（自愈缺口，2 请求/目标）
        months = 'all' if full_sync else 12
        names = dict(WIND_INDEX_TARGETS)
        out = []
        for gu in gu_codes:
            gu = gu.strip()
            if not gu:
                continue
            try:
                out.append({'gu_code': gu, 'gu_name': names.get(gu, gu), **self.adapter.fetch_index_daily(gu, months)})
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
            price_mode = item.get('price_mode', 'anchored')
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
                            price_mode=price_mode,
                        )
                    )
                    inserted += 1
                else:
                    row.close = r['close']
                    row.ret_pct = r.get('ret_pct')
                    row.price_mode = price_mode
                    updated += 1
            self.db.commit()
            logger.info(f'指数日线 {index_code}({price_mode}): 新增 {inserted} / 更新 {updated}（共 {len(rows)} 条）')
