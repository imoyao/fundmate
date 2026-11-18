# 技术债务 P0 批次第二批：市场基准统一 + FIFO 盈亏唯一口径（2026-11-10）

> 前置：`#3032`（台账可判定化）、`#3033`（TD-012 真 PG）已合入 `dev`（`7145f134e5`）。
> 本文件是 TD-010 / TD-011 的**裁决落地记录**，状态以 `docs/spec/tech-debt-register.toml` 为准。
> 分支 `fix/tech-debt-p0-basis`，worktree `D:/codes/fm-tech-debt-basis`。

## 0. owner 裁决（来自上一轮 AskUserQuestion）

- **TD-010 两套市值基准** → **B 统一到 T 日最新净值**。
- **TD-011 已实现盈亏口径** → **FIFO 配对自算为唯一出口**（四列标为不可用）。

## 1. TD-010：统一到 T 日库内最新净值

### 实证根因（file:line）
- 唯一分叉点：`summary_service.py:172-174` 的 `_per_ledger_buckets` 循环里
  `market_value_cents(p, rate=rate)` **未传** `effective_nav_yuan`，落到
  `position_valuation.py:102-105` 的 `positions.current_price`（T-1 快照价）。
- 聚合侧 `position_aggregation.py:236,239` 已传 `effective_nav_yuan`（T 日净值）。
- `_per_ledger_buckets` 是 `family_totals` / `get_ledger_distributions` / `write_asset_snapshot`
  的**唯一累加实现**（见该函数 docstring #2179/#2154），故改这一处同时修 summary 读 + 快照写。

### 改动
- `summary_service.py`：`_per_ledger_buckets` 加载 positions 后，取
  `fund_symbols = [p.symbol for p in positions if p.symbol and p.asset_type in ('fund','money_fund')]`，
  批量 `NavService.get_latest_navs(db, fund_symbols, allow_remote=False)`（一次 bulk 查询，非 N+1），
  循环内 `market_value_cents(p, rate=rate, effective_nav_yuan=latest_navs.get(p.symbol))`。
  非基金（股票/ETF）`effective_nav_yuan=None` → 仍回退 `current_price`，与聚合侧一致，无行为变化。
- 无 NAV 时（allow_remote=False 且库内缺失）`get(...)` 返回 None → 回退快照价，安全降级。

### 关于「CALIBER 版本 / 存量不回填」的取舍（重要）
方案 B 原文含「给快照定 CALIBER 版本」。但 `asset_snapshots` 属 summary 域，迁移接线横跨
`database.py` 单库/双库两条路径（#1085 双库），加 DB 列有启动阻断风险，且本改是**一次性**
基准切换。故采用标准做法：**按合并日记 cutover，存量快照不回填**。
- 代码与台账双重标注：本 PR 合并前写入的快照按 T-1 快照价、合并后按 T 日净值；
  趋势图在 cutover 日出现一次台阶属预期，不伪造历史。
- 不引入 `valuation_basis` DB 列。若 owner 后续坚持硬列，再单独 PR（需补 `database.py`
  两条路径的迁移接线，并过 `guard_migrations_pg_aware`）。

## 2. TD-011：FIFO 配对自算为唯一盈亏口径

### 实证澄清（关键）
- `transactions.realized_pnl`（四列读它）实际由**移动加权平均**写入
  （`pnl_service.compute_sell_realized_cents`），**不是 FIFO**。
- 「已落袋表现」前端页面走 **FIFO 配对自算**（`services/analytics/cleared_cycles.py` 的
  `build_cleared_cycles`，经 `summary/views.py:324 cleared_cycles()` 暴露）。
- 两者算法本就不同 ⇒ 「同账户两种盈亏差值=0」**今日不成立**，也不应被强制造假相等。
- 故裁决的真实动作是：**废弃四列、FIFO 为唯一出口**，而非让四列改算 FIFO。

### 改动
- `domains/summary/models.py`：`AssetSnapshot` 四列
  `realized_pnl_cents` / `unrealized_pnl_cents` / `total_pnl_cents` / `money_fund_income_cents`
  加 `DEPRECATED` 标注，指明唯一口径 = `cleared_cycles` FIFO，四列保留仅为存量兼容、不得直接展示。
- `summary_service.py`：`_write_rows` / `_snapshot_payload` 处加注释说明四列已弃用。
- 不动四列写盘逻辑（存量兼容），不动前端（前端 `summary.ts:198-199` 本就声明不消费）。

### 契约回归（防回潮）
- `tests/services/test_snapshot_pnl.py` 新增：
  1. `test_total_assets_uses_t_day_nav`：构造基金持仓，`current_price` 与库内最新净值不同，
     断言 `get_distributions` 总资产按 T 日净值（非快照价）。
  2. `test_canonical_realized_pnl_is_fifo`：构造买入→卖出流水，调 `build_cleared_cycles`，
     断言其 `realized_pnl` 等于独立 FIFO 重算值（守卫 FIFO 为唯一正确出口）。
  3. `test_four_columns_deprecated_not_canonical`：断言快照四列仍被写入（防有人「顺手删列」破坏 schema），
     且其 `realized_pnl` 走移动平均、与 FIFO 值可不同（证明未被静默统一）。

## 3. 验收标准（每条带判据引用）
- 判据：`python scripts/guard_tech_debt_register.py` 全绿；TD-010/TD-011 为 `done` 且判据命中。
- 判据：`python -m unittest tests/services/test_snapshot_pnl.py tests/services/test_analytics_cleared_cycles.py` 全绿。
- 判据：`ruff check` / `ruff format --check`（按 `backend/pyproject.toml`）对改动文件双检通过。
- 走查：`tech-debt-register.toml` TD-010/TD-011 状态=done、verified_at 更新、带 evidence。

## 4. 风险与回滚
- TD-010：总资产由 T-1 快照价跳到 T 日确认净值，单日基金波动通常 <1%；cutover 日一次台阶，已标注。
- TD-011：纯注释 + 契约测试，零行为变更（四列仍按旧逻辑写），回滚只需还原注释与测试。
- 均未触碰 `check_view_thickness.py` / `guard_service_size.py` 基线（净增有限；若超基线把 NAV map
  构建抽成 `position_valuation.build_fund_nav_map()`，移代码不增量）。
