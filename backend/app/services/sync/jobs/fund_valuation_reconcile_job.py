# app/services/sync/jobs/fund_valuation_reconcile_job.py
"""
预估→正式对照（#2142）

官方净值（市场域 `daily_worth.unit_nav`）到位后，把 `fund_valuation_daily`
里对应的预估行翻成 confirmed，并记录对照三列（official_nav 副本 /
deviation / deviation_pct），供「预估 vs 官方」对照展示与数据源质量观察。

## 时序（T-1 硬护栏，#824）

`fund_nav_job` 丢弃 `date >= today` 的记录：day-D 官方净值**最早 D+1 21:30**
的 fund_nav 增量才落进 daily_worth。故本 job 的 cron 排在其后
（daily_scheduler：`30 8,22 * * *`）：

- 晚 22:30：对照当晚 21:30 刚落库的昨日净值；
- 晨 08:30：兜底（休市日 catch-up、源延迟恢复后补对照）。

官方迟到/缺失时行保持 estimated、三列 NULL——诚实降级，等下一巡自然收敛
（本 job 不限日期扫描全部 estimated 行，晚到 N 天的净值最终都会被对照到）。

## 硬边界

- **不改写 daily_worth**：官方值唯一权威，本 job 只写 fund_valuation_daily
  自己的对照列（official_nav 是副本，读取端不得当权威用）。
- **货基不对照**：货基净值在 `money_fund_daily_worth`（万份收益/7日年化口径），
  与预估行的 nav 不可比；无 daily_worth 匹配的行保持 estimated（含货基与
  QDII 等官方缺行场景）。
- **幂等**：只动 status='estimated' 行；confirmed 行天然跳过，重跑零副作用。
- 零外部请求：纯 DB 读写，target_kind=None 全量路径（targets 忽略），
  不入 SYMBOL_BACKFILL_JOBS。
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

from app.core.time_utils import now_shanghai
from app.domains.funds.models import DailyWorth, FundValuationDaily
from app.services.adapters.null_adapter import NullAdapter
from app.services.job_base import IN_CHUNK_SIZE, SyncJob

# 对照精度：偏差 6 位小数（与净值同精度），偏差率 4 位小数（与 change_pct 同口径）
DEVIATION_QUANTUM = Decimal('0.000001')
PCT_QUANTUM = Decimal('0.0001')


class FundValuationReconcileJob(SyncJob):
    """预估→正式对照：官方净值到位后翻 confirmed 并记录偏差（纯 DB，#2142）。"""

    def __init__(self, db):
        # 纯本地读写（读 daily_worth、写 fund_valuation_daily），NullAdapter 占位
        # ——同 position_price / asset_snapshot 惯例
        super().__init__(NullAdapter(), db)

    def get_name(self) -> str:
        return 'fund_valuation_reconcile'

    @property
    def _allow_empty_data(self) -> bool:
        return True  # 无 estimated 行 / 无官方可对照都是正常状态（非交易日、新库）

    # ── 数据获取（targets=None 全量路径：基类单次调用） ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """全部待对照的 estimated 行（不限日期——净值晚到 N 天最终都会被对照到）。

        targets 参数忽略（target_kind=None，调度层不解析目标池）；
        量级 = 用户池 × 近几日，天然有界。
        """
        rows = (
            self.db.query(
                FundValuationDaily.id,
                FundValuationDaily.fund_code,
                FundValuationDaily.est_date,
                FundValuationDaily.estimated_nav,
            )
            .filter(FundValuationDaily.status == 'estimated')
            .all()
        )
        return [
            {'id': rid, 'fund_code': code, 'est_date': est_date, 'estimated_nav': est_nav}
            for rid, code, est_date, est_nav in rows
        ]

    # ── 数据校验：两步法匹配官方净值，产出确认更新 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """按 (fund_code, est_date) 匹配 daily_worth，命中且 unit_nav 非 None 才产出。

        两步法（同域也保持应用层配对，不做 SQL join）：先收集键，再分批 in_ 取候选。
        未命中 / unit_nav NULL → 不产出（行保持 estimated，诚实降级）。
        """
        if not raw_data:
            return []
        codes = list({r['fund_code'] for r in raw_data})
        dates = list({r['est_date'] for r in raw_data})

        official_map: Dict[Tuple[str, date], Decimal] = {}
        for i in range(0, len(codes), IN_CHUNK_SIZE):
            code_chunk = codes[i : i + IN_CHUNK_SIZE]
            for fund_code, nav_date, unit_nav in (
                self.db.query(DailyWorth.fund_code, DailyWorth.date, DailyWorth.unit_nav)
                .filter(DailyWorth.fund_code.in_(code_chunk), DailyWorth.date.in_(dates))
                .all()
            ):
                if unit_nav is None:
                    continue  # 净值行存在但值缺失：不翻（NULL 官方值对照无意义）
                official_map[(fund_code, nav_date)] = unit_nav

        confirmed: List[dict] = []
        for item in raw_data:
            official = official_map.get((item['fund_code'], item['est_date']))
            if official is None:
                continue
            estimated = item['estimated_nav']
            if estimated is None:
                continue  # 防御：estimated_nav 是非空列，理论上不会出现
            deviation = (estimated - official).quantize(DEVIATION_QUANTUM)
            # 防御：nav 恒为正，0/负值属脏数据 → 偏差率置 NULL（不除零）
            pct = (deviation / official * 100).quantize(PCT_QUANTUM) if official > 0 else None
            confirmed.append(
                {
                    'id': item['id'],
                    'official_nav': official,
                    'deviation': deviation,
                    'deviation_pct': pct,
                    'status': 'confirmed',
                }
            )
        return confirmed

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """不去重：每行独立按 id UPDATE，重复键不可能出现。"""
        return data

    # ── 保存：只 UPDATE，不 INSERT ──

    def _save_data(self, new_data: List[dict]) -> None:
        """按 id 更新对照三列与状态；**绝不插入新行、绝不触碰 daily_worth**。"""
        if not new_data:
            return
        now = now_shanghai()
        for item in new_data:
            self.db.query(FundValuationDaily).filter(FundValuationDaily.id == item['id']).update(
                {
                    'official_nav': item['official_nav'],
                    'deviation': item['deviation'],
                    'deviation_pct': item['deviation_pct'],
                    'status': item['status'],
                    'updated_at': now,
                },
                synchronize_session=False,
            )
        self.db.commit()


__all__ = ['FundValuationReconcileJob']
