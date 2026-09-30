# -*- coding: utf-8 -*-
"""基金持仓明细 + 行业配置回填任务（#870 / #1286 数据底座 · 逐只抓取，核心池限定）。

链路（每只基金 **2 次 HTTP**，实测各 ≈1–2.6s）：

  `adapter.fetch_fund_top_holdings(code)`        → 持仓明细（季报前十大 / 半年报年报全量）
  `adapter.fetch_fund_industry_allocation(code)` → 行业配置（csrc / gics 双体系）
  → 落 `fund_holdings` / `fund_industry_allocs`，并派生 `funds.equity_position`。

**明细是源、标量是派生**：`equity_position` 取「**行业配置合计**」，不再取「前十大之和」。
后者对分散型基金系统性低估（实测 005827 前十大 38.95% vs 全量 76.43%，偏差 −37.5pp），
且季报期只有前十大、与半年报口径不可比；而证监会要求季报**也**披露行业分类比例，故
行业配置合计在任何报告期都是全量口径，并与持仓全量合计交叉吻合到小数点后两位。
**无源数据时不覆盖原值**——不用 0 掩盖缺失（QDII 实测无行业配置，若写 0 就是假数据）。

目标池红线（`data-strategy.md` §4.3.2 / §4.3.3）：

- 逐只抓取类 job **一律按目标池限量**，并设硬上限 `MAX_TARGETS`；
- `__full__` 与空 targets 都表示「**无受限目标池**」→ 显式跳过，**禁止退化为全库**。

  为什么这条不能松：全库 `funds` 有 26,938 只，逐只抓 ≈ **13.5 小时**，且必撞
  东财限流（这正是 #1403「未引爆的限流炸弹」的原始形态）。核心池实测 133 只
  （占全库 0.5%），2 次 HTTP/只 ≈ **5–8 分钟**。

调度：**不要放进每日调度**。持仓是季报数据，日变更量为 0，每日跑纯属浪费外部请求
并叠加限流风险；按 `daily_scheduler` 的周任务触发。
"""

from typing import List, Optional

from app.services.job_base import JobStatus, SyncJob

# 逐只抓取的硬上限：超过即截断并告警，防止一次同步变成数小时的外部请求风暴
MAX_TARGETS = 500
# 全量占位符：对逐只抓取类 job 不构成有效目标池
FULL_PLACEHOLDER = '__full__'

# 数据来源标记（写入两张表的 source 列，便于日后区分多源/回溯）
HOLDING_SOURCE = 'eastmoney'
INDUSTRY_SOURCE = 'eastmoney'


class FundPositionSyncJob(SyncJob):
    """基金持仓明细 + 行业配置回填 —— 仅核心池（#870）。"""

    def __init__(self, adapter, db):
        """批量调小到 25。

        ⚠️ 必须在**实例**上设：基类 `SyncJob.__init__` 里有
        ``self.batch_size = BATCH_SIZE_DEFAULT``，会把子类的类属性静默覆盖掉
        （写 `batch_size = 25` 当类属性不生效，实测日志仍打「进度: 50/117」）。
        每只 = 2 次外部请求，批量小一点让进度可观测、单批失败面更小。
        """
        super().__init__(adapter, db)
        self.batch_size = 25

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
                f'（逐只 2 次请求 ≈3s/只；全库 26,938 只 ≈22 小时，见 #1403）'
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
        """逐只抓取持仓明细与行业配置；两者皆空则跳过该只（不产出记录）。"""
        out: List[dict] = []
        for code in targets:
            holdings, industry = {}, {}
            try:
                holdings = self.adapter.fetch_fund_top_holdings(code) or {}
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f'基金 {code} 持仓抓取失败: {e}')
            try:
                industry = self.adapter.fetch_fund_industry_allocation(code) or {}
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f'基金 {code} 行业配置抓取失败: {e}')
            if not holdings and not industry:
                # 无源数据：不产出记录，从而不覆盖该基金已有的标量值
                continue
            out.append({'fund_code': code, 'holdings': holdings, 'industry': industry})
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [i for i in (raw_data or []) if i.get('fund_code') and (i.get('holdings') or i.get('industry'))]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 报告期数据随新披露推进，须覆盖更新而非按唯一键跳过
        return data

    # ── 写入 ──

    def _save_data(self, new_data: List[dict]) -> None:
        from app.domains.funds.models import Fund, FundHolding, FundIndustryAlloc

        holding_rows: List[dict] = []
        industry_rows: List[dict] = []
        derivatives: List[dict] = []

        for item in new_data:
            code = item['fund_code']
            holdings = item.get('holdings') or {}
            industry = item.get('industry') or {}

            for row in holdings.get('holdings') or []:
                holding_rows.append(
                    {
                        'fund_code': code,
                        'report_period': holdings['report_period'],
                        'report_date': holdings.get('report_date'),
                        'holding_basis': holdings.get('holding_basis'),
                        'stock_code': row['stock_code'],
                        'stock_name': row.get('stock_name'),
                        'ratio': row.get('ratio'),
                        'shares': row.get('shares'),
                        'market_value': row.get('market_value'),
                        'rank': row.get('rank'),
                        'source': HOLDING_SOURCE,
                    }
                )

            items = industry.get('items') or []
            for row in items:
                industry_rows.append(
                    {
                        'fund_code': code,
                        'report_period': industry['report_period'],
                        'report_date': industry.get('report_date'),
                        'industry_code': row['industry_code'],
                        'industry_name': row.get('industry_name'),
                        'scheme': row.get('scheme'),
                        'ratio': row.get('ratio'),
                        'source': INDUSTRY_SOURCE,
                    }
                )

            if items:
                # 派生标量：行业配置合计（全量口径，任何报告期都不失真）
                derivatives.append(
                    {
                        'fund_code': code,
                        'equity_position': round(sum(r.get('ratio') or 0 for r in items), 2),
                        'report_period': industry['report_period'],
                    }
                )

        saved_holdings = self._upsert(
            FundHolding,
            ('fund_code', 'report_period', 'holding_basis', 'stock_code'),
            holding_rows,
            ('ratio', 'shares', 'market_value', 'rank', 'stock_name', 'report_date', 'source'),
        )
        saved_industry = self._upsert(
            FundIndustryAlloc,
            ('fund_code', 'report_period', 'industry_code'),
            industry_rows,
            ('ratio', 'industry_name', 'scheme', 'report_date', 'source'),
        )
        updated_funds = self._apply_equity_position(Fund, derivatives)
        self.db.commit()

        self.logger.info(
            f'持仓明细 {saved_holdings} 条 / 行业配置 {saved_industry} 条 / 派生仓位 {updated_funds} 只'
            f'（本批命中 {len(new_data)} 只基金）'
        )

    def _upsert(self, model, key_fields: tuple, rows: List[dict], update_fields: tuple) -> int:
        """按业务唯一键批量 upsert（存在则更新指定字段，否则插入）。

        每批只涉及 ≤`batch_size` 只基金、≤2 个报告期，故 `fund_code` / `report_period`
        的 ``in_`` 取值范围很小，不会撞 SQLite 变量上限（对比 `IN_CHUNK_SIZE` 的教训）。
        """
        if not rows:
            return 0

        codes = {r['fund_code'] for r in rows}
        periods = {r['report_period'] for r in rows}
        model_cols = {f: getattr(model, f) for f in key_fields}
        existing = (
            self.db.query(model)
            .filter(model_cols['fund_code'].in_(codes), model_cols['report_period'].in_(periods))
            .all()
        )
        index = {tuple(getattr(obj, f) for f in key_fields): obj for obj in existing}

        for row in rows:
            key = tuple(row[f] for f in key_fields)
            obj = index.get(key)
            if obj is None:
                obj = model(**{f: row[f] for f in key_fields})
                self.db.add(obj)
                index[key] = obj
            for field in update_fields:
                setattr(obj, field, row.get(field))
        return len(rows)

    def _apply_equity_position(self, fund_model, derivatives: List[dict]) -> int:
        """把派生仓位写回 `funds`（口径 = 行业配置合计）。

        **只在有源数据时写**：无行业配置的基金（如部分 QDII）保持原值不动，
        不用 0 或旧值冒充新值。
        """
        if not derivatives:
            return 0
        codes = [d['fund_code'] for d in derivatives]
        existing = {f.fund_code: f for f in self.db.query(fund_model).filter(fund_model.fund_code.in_(codes)).all()}
        updated = 0
        for item in derivatives:
            fund = existing.get(item['fund_code'])
            if fund is None:
                continue
            fund.equity_position = item['equity_position']
            fund.equity_position_period = item['report_period']
            updated += 1
        return updated
