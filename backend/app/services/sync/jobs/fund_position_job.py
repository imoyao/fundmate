# -*- coding: utf-8 -*-
"""近似股票仓位回填任务（#1286 数据底座 · 逐只抓取，核心池限定）。

链路：`akshare_adapter.fetch_fund_top_holdings(code)` → `ak.fund_portfolio_hold_em`，
**单基金一次 HTTP**（实测 ≈1.8s/只）。近似股票仓位 = 前十大重仓占净值比合计（%），
仅近似口径（非全口径资产配置），字段注释已注明。

目标池红线（`data-strategy.md` §4.3.2 / §4.3.3）：

- 逐只抓取类 job **一律按目标池限量**，并设硬上限 `MAX_TARGETS`；
- `__full__` 与空 targets 都表示「**无受限目标池**」→ 显式跳过，**禁止退化为全库**。

  为什么这条不能松：全库 `funds` 有 26,938 只，逐只抓 ≈ **13.5 小时**，且必撞
  东财限流（这正是 #1403「未引爆的限流炸弹」的原始形态）。核心池实测仅 117 只
  （占全库 0.43%），耗时 ≈3.5 分钟。
"""

from typing import List, Optional

from app.services.sync.jobs.base import JobStatus, SyncJob

# 逐只抓取的硬上限：超过即截断并告警，防止一次同步变成数小时的外部请求风暴
MAX_TARGETS = 500
# 全量占位符：对逐只抓取类 job 不构成有效目标池
FULL_PLACEHOLDER = '__full__'


class FundPositionSyncJob(SyncJob):
    """近似股票仓位（前十大重仓合计）回填 —— 仅核心池。"""

    @property
    def _allow_empty_data(self) -> bool:
        return True

    def get_name(self) -> str:
        return 'fund_position'

    def resolve_pool(self, targets: Optional[List[str]]) -> List[str]:
        """解析受限目标池：剔除占位符/空值、去重保序、超限截断。

        `__full__` 与空列表语义相同 —— 「无受限目标池」，返回空列表由调用方跳过。
        """
        seen = set()
        pool: List[str] = []
        for t in targets or []:
            if not t or t == FULL_PLACEHOLDER or t in seen:
                continue
            seen.add(t)
            pool.append(t)
        if len(pool) > MAX_TARGETS:
            self.logger.warning(
                f'目标池 {len(pool)} 只超过上限 {MAX_TARGETS}，已截断'
                f'（逐只 ≈1.8s/只；全库 26,938 只 ≈13.5 小时，见 #1403）'
            )
            pool = pool[:MAX_TARGETS]
        return pool

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None):
        pool = self.resolve_pool(targets)
        if not pool:
            # 显式跳过：空 targets 的正确语义是「无需处理」，不是「处理全部记录」
            self.logger.warning(
                f'目标池为空或仅含 {FULL_PLACEHOLDER}：按 data-strategy.md §4.3.3 显式跳过，禁止退化为全库逐只抓取'
            )
            self.status = JobStatus.SUCCESS
            return self._build_result()
        return super().run(full_sync=full_sync, targets=pool)

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        out = []
        for code in targets:
            try:
                holdings = self.adapter.fetch_fund_top_holdings(code)
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f'基金 {code} 重仓抓取失败: {e}')
                continue
            if not holdings:
                continue
            ratio = sum(h.get('ratio') or 0 for h in holdings[:10])
            if ratio:
                out.append({'fund_code': code, 'equity_position': round(ratio, 2)})
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [i for i in (raw_data or []) if i.get('fund_code')]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 仓位随季报变化，须覆盖更新而非按唯一键跳过
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        from app.domains.funds.models import Fund

        codes = [i['fund_code'] for i in new_data]
        existing = {f.fund_code: f for f in self.db.query(Fund).filter(Fund.fund_code.in_(codes)).all()}
        updated = 0
        for item in new_data:
            fund = existing.get(item['fund_code'])
            if fund is None:
                continue
            fund.equity_position = item['equity_position']
            updated += 1
        self.db.commit()
        self.logger.info(f'近似股票仓位回填 {updated} 只（本批命中 {len(new_data)} 条）')
