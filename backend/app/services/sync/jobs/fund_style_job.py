# -*- coding: utf-8 -*-
"""基金投资风格箱（晨星式 8 分类）同步任务（#2478 · 逐只抓取，目标池限量）。

链路（每只基金 **1 次 HTTP**）：

  `adapter.fetch_fund_style_history(code)` → 8 风格 × 月度日期轴（成立起全历史）
  → 落 `fund_style_exposures`（long，append-only），并派生 `funds.dominant_style`。

**为什么值得单独一个 job**（评估文档 `fund_style_tag_feasibility.md`）：
风格箱是 fundmate 缺失的基础数据维度，对**主动基金**尤其高价值——
  1. 风格定位：用户按风格偏好筛选基金（探市/自选）；
  2. 风格漂移：基金经理宣称风格 vs 箱体实际漂移，纪律性监控；
  3. 组合透视：持仓加权风格暴露（服务层另提供，见 fund_style_service）。

**与 FundPositionSyncJob 的差异（勿照搬）**：
  - **不剔货基**：货基/债基的风格箱（固收风格 ~100）是有效数据，剔了反而丢维度；
    fund_position 剔货基是因为「货基被摊出股票行业」是伪数据，此处不成立。
  - **历史全量回补**：上游每次返回成立起全历史（实测 000001：283 点，2003-04 起），
    本 job 按 `(fund_code, style_name, stat_date)` 去重后**只插缺失时点**——
    首次跑即完成全历史回补，之后月度增量只有 1 个新时点/只。

**断档即永久缺口**：上游不提供历史回补，某天漏抓的时点无法事后补
（韭圈儿只保留当前截面 + 本库已落部分）。故 job 失败记 errors（#1833 同款），
由 freshness 观察暴露；本表**无清理策略**（与 composite/multi 的 1 年保留不同）。

目标池红线（`data-strategy.md` §4.3.2 / §4.3.3）：同 fund_position——
逐只抓取类 job 一律按目标池限量，`__full__` 与空 targets 都表示「无受限目标池」
→ 显式跳过，**禁止退化为全库**（全库 26,938 只 ≈ 1 请求/只，无必要也无消费场景）。

调度：**月度**（上游按月更新：月末点 + 当月最新点），由 daily_scheduler 的
cron 触发（见 DEFAULT_FUND_STYLE_CRON）；不进每日执行计划。
"""

from datetime import date
from typing import Any, Dict, List, Optional

from app.core.time_utils import now_shanghai
from app.services.job_base import JobStatus, SyncJob

# 逐只抓取的硬上限：超过即截断并告警（同 fund_position 的量级考量）
MAX_TARGETS = 500
# 全量占位符：对逐只抓取类 job 不构成有效目标池
FULL_PLACEHOLDER = '__full__'

# 数据来源标记（写入 fund_style_exposures.source 与 sync_logs 审计）
STYLE_SOURCE = 'jiucaishuo_style'


class FundStyleSyncJob(SyncJob):
    """基金风格箱同步 —— 目标池限量（持仓 + 自选），月度增量。"""

    def __init__(self, adapter, db):
        """批量调小到 25（同 fund_position：每只 1 次外部请求，批量小一点让进度可观测）。

        ⚠️ 必须在**实例**上设：基类 `SyncJob.__init__` 里有
        ``self.batch_size = BATCH_SIZE_DEFAULT``，会把子类的类属性静默覆盖掉。
        """
        super().__init__(adapter, db)
        self.batch_size = 25

    @property
    def _allow_empty_data(self) -> bool:
        # 上游对无风格数据的基金返回空——允许空（该只跳过），不阻断整批
        return True

    def get_name(self) -> str:
        return 'fund_style'

    def resolve_pool(self, targets: Optional[List[str]]) -> List[str]:
        """解析受限目标池：归一化带前缀 symbol、剔除占位符/空值、去重保序、超限截断。

        #2478：与 fund_position 的 resolve_pool 同构（含 #1983 的 ETF 裸码归一化），
        但**不剔货基**——风格箱对货基/债基同样有有效值（固收风格），见模块 docstring。
        带前缀的股票 symbol（非 ETF）不归本 job（韭圈儿风格箱只覆盖基金）。
        """
        from app.core.symbol_utils import derive_security_type, split_symbol
        from app.services.fund_utils import normalize_fund_code

        seen = set()
        pool: List[str] = []
        for t in targets or []:
            if not t or t == FULL_PLACEHOLDER:
                continue
            if not (t.isdigit() and len(t) == 6):
                # 带前缀 symbol：剥出裸码后按证券细类判定是否归本 job
                bare = normalize_fund_code(t)
                if not bare:
                    self.logger.warning(f'目标 {t} 无法归一化为 6 位代码，已丢弃')
                    continue
                market, _ = split_symbol(t)
                if derive_security_type(bare, market) != 'etf':
                    # 股票 / 可转债等非基金标的：韭圈儿风格箱不覆盖，跳过
                    self.logger.debug(f'目标 {t} 非 ETF/基金类，已跳过')
                    continue
                t = bare
            if t in seen:
                continue
            seen.add(t)
            pool.append(t)
        if len(pool) > MAX_TARGETS:
            self.logger.warning(
                f'目标池 {len(pool)} 只超过上限 {MAX_TARGETS}，已截断'
                f'（逐只 1 次请求 ≈3s/只；全库 26,938 只无消费场景，见 data-strategy.md §4.3.3）'
            )
            pool = pool[:MAX_TARGETS]
        return pool

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        """覆写 `run()` 时**必须自己打 `snapshot_time`**（同 fund_position 的教训：

        基类 `SyncJob.run()` 开头赋值，而本方法可能早退（目标池为空）根本不进基类，
        漏赋值会让 `orchestrator.run_job` 的耗时计算抛 TypeError。2026-10-01 生产实测。
        """
        self._full_sync_flag = full_sync
        self.snapshot_time = now_shanghai()

        pool = self.resolve_pool(targets)
        if not pool:
            # 显式跳过：空 targets 的正确语义是「无需处理」，不是「处理全部记录」
            self.logger.warning(
                f'目标池为空或仅含 {FULL_PLACEHOLDER}：按 data-strategy.md §4.3.3 显式跳过，禁止退化为全库逐只抓取'
            )
            self.status = JobStatus.SUCCESS
            return self._build_result()
        return super().run(full_sync=full_sync, targets=pool)

    # ── 抓取 / 校验 / 去重 / 写入 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """逐只抓风格箱全历史，拉平为 long 行（每只 8 风格 × N 时点）。

        每只 1 次 HTTP；失败记 errors 并跳过该只（不产出记录 → 不覆盖已有派生值）。
        日期轴与每条 style.values **等长**（adapter 侧已校验），按位置对齐取值。
        """
        out: List[dict] = []
        for code in targets:
            try:
                parsed = self.adapter.fetch_fund_style_history(code)
            except Exception as e:  # noqa: BLE001 - 单只失败不阻断整批
                self.logger.warning(f'基金 {code} 风格箱抓取失败: {e}')
                # #1833 同款：记 errors，否则「抓失败」与「上游无数据」同为 0 记录，
                # 页面继续展示旧数据而无人知道它已停更。
                self.stats.setdefault('errors', []).append({'fund_code': code, 'stage': 'fetch_style', 'error': str(e)})
                continue

            dates = parsed.get('dates') or []
            styles = parsed.get('styles') or []
            rows: List[dict] = []
            for i, stat_date in enumerate(dates):
                try:
                    d = date.fromisoformat(stat_date)
                except (TypeError, ValueError):
                    # 契约变更（日期格式变了）→ 整只跳过，不让错位数据落库
                    self.logger.warning(f'基金 {code} 风格箱日期无法解析: {stat_date!r}，整只跳过')
                    rows = []
                    break
                for s in styles:
                    rows.append(
                        {
                            'fund_code': code,
                            'stat_date': d,
                            'style_name': s['name'],
                            'value': s['values'][i],
                        }
                    )
            if not rows:
                continue
            out.append({'fund_code': code, 'rows': rows})
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """每只至少要有行、且 value 可转 float。"""
        valid: List[dict] = []
        for item in raw_data or []:
            rows = [
                r
                for r in (item.get('rows') or [])
                if r.get('style_name') and r.get('stat_date') and r.get('value') is not None
            ]
            if not rows:
                continue
            for r in rows:
                try:
                    r['value'] = float(r['value'])
                except (TypeError, ValueError):
                    self.logger.warning(f'基金 {item["fund_code"]} 风格值无法解析: {r.get("value")!r}，丢弃该行')
                    r['_drop'] = True
            rows = [r for r in rows if not r.get('_drop')]
            if rows:
                valid.append({'fund_code': item['fund_code'], 'rows': rows})
        return valid

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """按 `(fund_code, style_name, stat_date)` 复合键过滤已落库行。

        这就是「断点续传 / 月度增量」的机制：上游每次返回全历史，去重后只剩
        缺失时点（首次跑 = 全量回补；之后每月 = 1 个新时点/只）。

        复合键无法用基类的 `_deduplicate_by_unique_key`（单键），故自定义；
        查询按 fund_code 分批（`IN_CHUNK_SIZE`），防 SQLite 变量上限（#1286 教训）。
        """
        from app.domains.funds.models import FundStyleExposure
        from app.services.job_base import IN_CHUNK_SIZE

        if not data:
            return []
        codes = sorted({item['fund_code'] for item in data})
        existing: set = set()
        for i in range(0, len(codes), IN_CHUNK_SIZE):
            chunk = codes[i : i + IN_CHUNK_SIZE]
            for fund_code, style_name, stat_date in (
                self.db.query(FundStyleExposure.fund_code, FundStyleExposure.style_name, FundStyleExposure.stat_date)
                .filter(FundStyleExposure.fund_code.in_(chunk))
                .all()
            ):
                existing.add((fund_code, style_name, stat_date))
        for item in data:
            item['rows'] = [r for r in item['rows'] if (r['fund_code'], r['style_name'], r['stat_date']) not in existing]
        return [item for item in data if item['rows']]

    def _save_data(self, new_data: List[dict]) -> None:
        """批量插入新行 + 派生 `funds.dominant_style` / `style_period`。

        派生口径：本批**最新 stat_date** 时点暴露值最大的风格（并列取上游序列首位，
        上游 info_lists 顺序固定，故确定性）。该时点全 0（理论不可能，合计=100 约束）
        或本批无行 → 不派生（同 equity_position 的「无源即不派生」）。
        """
        from app.domains.funds.models import Fund, FundStyleExposure

        rows: List[dict] = []
        derivatives: List[dict] = []
        for item in new_data:
            code = item['fund_code']
            item_rows = item['rows']
            rows.extend(item_rows)

            latest_date = max(r['stat_date'] for r in item_rows)
            latest_rows = [r for r in item_rows if r['stat_date'] == latest_date]
            # max 并列时取序列首位（上游顺序确定）；全 0 不派生
            best = max(latest_rows, key=lambda r: r['value'])
            if best['value'] and best['value'] > 0:
                derivatives.append(
                    {
                        'fund_code': code,
                        'dominant_style': best['style_name'],
                        'style_period': latest_date.isoformat(),
                    }
                )

        self.db.bulk_insert_mappings(FundStyleExposure, rows)
        updated = self._apply_dominant_style(Fund, derivatives)
        self.db.commit()

        self.logger.info(
            f'风格箱落库 {len(rows)} 行 / 派生主导风格 {updated} 只（本批命中 {len(new_data)} 只基金）'
        )

    def _apply_dominant_style(self, fund_model, derivatives: List[dict]) -> int:
        """把派生主导风格写回 `funds`。

        **只在有源数据时写**：抓不到风格箱的基金保持原值不动（NULL 或上期值），
        不用 '未知' 或旧值冒充新值（同 `_apply_equity_position` 的取舍）。
        """
        if not derivatives:
            return 0
        codes = [d['fund_code'] for d in derivatives]
        existing = {f.fund_code: f for f in self.db.query(fund_model).filter(fund_model.fund_code.in_(codes)).all()}
        updated = 0
        for item in derivatives:
            fund = existing.get(item['fund_code'])
            if fund is None:
                # 目标池可能含库中暂无的基金码（自选先于 fund_list 落库）——跳过即可
                self.logger.debug(f'基金 {item["fund_code"]} 不在 funds 表，跳过派生标量')
                continue
            fund.dominant_style = item['dominant_style']
            fund.style_period = item['style_period']
            updated += 1
        return updated
