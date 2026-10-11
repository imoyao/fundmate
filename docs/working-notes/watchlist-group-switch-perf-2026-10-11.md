# 自选切分组性能重设计（2026-10-11）

> 问题：自选页切分组 / 切「全部」/ 切「持仓」实测卡数秒（用户报「卡好几秒」）。
> 目标：端到端 < 300ms，**业务与预期零修改**（字段、口径、契约逐字不变）。
> 分支：`fix/watchlist-group-switch-perf`（worktree `D:\codes\fm-perf-watchlist`，基于 `origin/dev`）。

## 一、根因（profiling 定位，非猜测）

三层叠加，缺一不会「卡好几秒」：

1. **前端串行两请求**：`useWatchlistData.fetchData` 先请求基础列表、再请求分组数据，两次 RTT + 两次后端全量执行串起来。
2. **后端 enrich 逐行 N+1**：`list_items` 对每行做 8+ 次单行查询（持仓聚合、最新行情、添加日价格、分组/标签、展示名反查、可转债条款、指数估值、基金回撤……），158 行 × 8+ ≈ 千余次查询。
3. **`daily_worth` 大表窗口查询**：最新行情兜底用窗口函数在 **754 万行**上全量物化（单条 708ms，cProfile 实测）；基金回撤再按行扫 3 年序列（20 行 = 737ms）。
4. **展示字段在分页前算**：`fill_page_display_fields` 语义本应只对页内 ≤20 行补算，但批量路径丢失 ctx 后退化为逐行查库；且 `build_all_items` 建了 ctx 却没传给 `list_holding_items`，预取整体跑了 2 遍。

## 二、接口设计（决策依据见 `docs/spec/decisions.md` D24）

**不新增任何端点**（用户确认；`/summary/` 之类残缺副本属临时接口，后期必然反复改动）：

- `GET /api/watchlist/items/` 的既有 **`fields` 参数升级为稳定投影选择器**：`full` = 基础 + 展示专用字段（默认，逐字保持原口径），`lite` = 仅基础字段（分组切换即时刷新用）。
- 批量预取提速 + 前端两请求 `Promise.all` 并行。契约冻结：路由、分页结构、错误信封零变化（`scripts/check_api_conventions.py` 通过，api.md 无需重生成）。

### 后端：`BatchContext` 批量预取

把「158 行 × 8+ 查询」压缩为「~8 条 IN 查询」，与行数无关：

| 段 | 内容 | 关键点 |
|---|---|---|
| 1-7 基础段 | 持仓聚合 / 均价 / 最新行情 / 添加日价格 / 分组标签链接 / 展示名反查链 | 行情用窗口函数（`price_history` 仅 1.3 万行，28ms 可接受）；添加日价格 CTE；`daily_worth` 兜底改 **CTE + 每基金 `idx_daily_worth_code_date_unique` 索引倒序 `LIMIT 2` 点查 + UNION ALL**（708ms → ~100ms 内），SQLite 不支持带括号的复合 SELECT 分量故必须用 CTE |
| 8 展示段 `_prefetch_display_fields` | 可转债条款 / 指数估值 / 基金回撤 / 跨渠道关联 | **独立成段**（与基础段无数据依赖），供页级 ctx 单独执行 |

**两段式作用域**（性能的关键结构）：

- 列表路径：base ctx（`need_display_fields=False`，全量 symbol 只跑 1-7 段）→ 排序分页 → `fill_page_display_fields` 用**页级 ctx**（`need_base_fields=True+need_display_fields=True` 中只跑第 8 段）只对页内 ≤20 行补展示字段——回撤 3 年序列只算 20 支，不算 158 行。
- 导出路径：`need_display_fields = not lite and not defer_display`，全量行 enrich 仍一次性拿齐（导出可容忍慢）。
- `ctx=None` 回退分支全部保留（测试 spy 依赖 + 语义基线）。

### 前端

`useWatchlistData.fetchData` 两请求改 `Promise.all` 并行；`useWatchlistValuation.ts` 是 `allItems` 唯一消费方，已核对无其他调用点受影响。

## 三、语义保真（两处踩坑，均已修）

A/B 逐字段对比（8000 = 主仓原版，8001 = 本分支，同一真实 DB）：**12 个场景 0 diff**（all/hold/watch × full/lite + group/tag/search/venue/favorite/asset_types 八个筛选分支）。过程中抓到两处批量路径语义漂移：

1. **基金回撤识别不能按前缀猜**：真实基金 symbol 是 6 位裸码（`001414`），与股票同形；早期预取按 `'OF.'/'fund_'` 前缀过滤在真实数据上**恒为空** → 基金行全部误报 `insufficient`（显示 `—` 而非真实回撤）。修正为从 watchlist + positions 反查 `asset_type=='fund'`（两条 IN 点查取并集，多算无害、少算必错）。
2. **持仓虚拟行 `price_at_added` 恒 None**：该字段是「自选条目」概念（添加日收盘价），dev 口径下 `_build_holding_row` 硬编码 None、`_enrich_holding_with_watchlist` 不覆盖；批量版曾从 ctx 回填真实值 ⇒ 9 行多出数据。已改回恒 None 并注释口径。

## 四、验收数据（2026-10-11，min-of-5，8000 vs 8001 同机交叉测）

| 场景 | 原版 | 本分支 | 提速 |
|---|---:|---:|---:|
| all-full | 4325ms | **288ms** | ×15.0 |
| all-lite | 2866ms | **142ms** | ×20.2 |
| hold-full | 2278ms | **215ms** | ×10.6 |
| hold-lite | 1575ms | **97ms** | ×16.3 |
| watch-full | 1178ms | **248ms** | ×4.8 |
| watch-lite | 660ms | **109ms** | ×6.0 |
| group1-full | 410ms | **133ms** | ×3.1 |

**六个场景全部 < 300ms**（切分组端到端达标）。测试：`tests/domains/test_watchlist.py` 92 项 + `test_watchlist_unified_code` / `test_migrations_watchlist_name_snapshot` 23 项全绿；ruff / api 约定检查 / 前端 typecheck 通过。

## 五、遗留（不在本卡范围）

- `list_holding_items` 的 `search` 非空分支仍逐行调 `resolve_display_name`（默认切分组不带 search，不构成热点；如后续做搜索场景优化另立卡）。
- 导出路径全量展示预取（106 支基金 × 3 年序列）约 1.2s，导出属低频容忍操作，未优化。
- 原版数字噪声大（同场景两轮 1636 vs 4325ms），故一律 min-of-5 交叉测量；勿用单次读数下结论。
