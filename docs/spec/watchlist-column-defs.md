---
title: 自选表格 columnDefs 数据驱动设计（watchlist-column-defs）
---

# 自选表格 columnDefs 数据驱动设计（watchlist-column-defs）

> 对应 issue：#995（前置），并为 #990（Sparkline）、#992（拖拽排序）、#993（表头自定义）提供干净地基。
> 关联 umbrella：#1022。接口源约束见 `realtime-data-sources.md`。

## 0. 现状与问题

`frontend/src/views/asset/watchlist/index.vue` 当前用 **21 个硬编码 `<el-table-column>`**（约 382–673 行），存在：

1. **新增字段 = 改大文件**：每加一列要直接编辑 2000+ 行组件，风险高、易冲突（尤其与 #980 重构并行时）。
2. **实时数据耦合在模板里**：列模板内联 `v-if="realtimeEnabled && getValuationItem(row.symbol)"` 双分支渲染（见"最新价""涨跌幅"两列），无法被 #990/#993 复用。
3. **排序逻辑散落**：`sortName` / `sortNum('current_price')` / `sortAddedReturn` 等内联 `:sort-method`，无集中注册。
4. **无列配置概念**：#993 表头自定义（显隐/排序/宽度）和 #992 拖拽排序缺乏数据载体。

目标：**把"列"抽象为可配置的数据结构（columnDefs），模板改为 `v-for` 渲染**，新增字段只改数据、不碰大组件。

## 1. 设计原则（来自 AGENTS.md 架构原则）

- **最简方案**：只抽象"列定义 + 渲染分发"，不引入表格状态管理库、不重写 valuation 链路。
- **复用既有**：实时数据继续走 `useRealtimeQuotes` → `valuationEngine` → `realtimeDataSources`，columnDefs 只消费 `getValuationItem` 结果，**不得**在 columnDefs 内新开 JSONP 通道。
- **不破坏 #980**：本设计为**独立新增模块**，渐进替换硬编码列，过渡期内新旧可共存，不要求一次到位。
- **长期可维护**：列定义集中在单一文件，新增字段的 PR 只动该文件 + 对应 renderer。

## 2. 数据模型（ColumnDef）

新建 `frontend/src/views/asset/watchlist/columnDefs.ts`：

```ts
export type ColumnRenderer =
  | "product"      // 代码/名称 + 标签（现有 ProductDisplay + tag chips）
  | "date"         // 格式化日期（formatDate）
  | "money"        // MoneyDisplay（精度按 asset_type）
  | "riseFall"     // RiseFallText（涨跌幅，支持实时覆盖）
  | "qty"          // 持有数量 + 单位（份/股）
  | "moneyRatio"   // MoneyWithRatio（金额 + 比率）
  | "sparkline"    // #990：迷你走势（renderer 待定，预留插槽）
  | "actions";     // 操作列（circle 按钮）

export interface ColumnDef {
  key: string;            // 唯一键，如 "current_price"
  label: string;          // 表头文案
  renderer: ColumnRenderer;
  width?: number;
  minWidth?: number;
  align?: "left" | "center" | "right";
  fixed?: "left" | "right";
  sortable?: boolean;
  sortMethod?: (a: WatchlistRow, b: WatchlistRow) => number;
  // 实时覆盖：开启实时估值且存在估值项时，用该字段的实时值替换静态值
  realtimeField?: "currentPrice" | "changePct";
  // #993 预留：用户是否可隐藏
  hideable?: boolean;
  // #992 预留：是否参与拖拽排序（列顺序）
  draggable?: boolean;
  // 渲染器所需额外参数（如 money 的 precision 来源）
  props?: Record<string, unknown>;
}
```

> `WatchlistRow` = 现有表格 `row` 类型（含 `symbol / asset_type / current_price / change_pct / holding_quantity / position_market_value / created_at / tag_ids / is_pinned / favorite` 等）。

## 3. 列定义清单（从现有 21 列映射，首批）

| key | label | renderer | 备注 |
|---|---|---|---|
| `_selection` | （多选） | 内置 selection | `v-if="batchMode"` |
| `_marker` | （置顶/关注图标） | 自定义 marker | 44px，class marker-column |
| `product` | 代码/名称 | product | fixed left，含标签 chips |
| `created_at` | 添加自选日 | date | sortStr；**#2640 起默认隐藏**（腾宽度给当日盈亏） |
| `current_price` | 最新价 | money | **realtimeField: currentPrice**（实时覆盖静态） |
| `change_pct` | 涨跌幅 | ~~riseFall~~ | **已删除（#2641）**：与「当日盈亏」的百分比行是同一个数（`(现价−昨收)/昨收`），并排摆着等于画两遍；排序能力由 `day_pnl` 的 `sortBy: change_pct` 接住 |
| `holding_quantity` | 持有数量 | qty | 单位按 venue |
| `position_market_value` | 持仓市值 | moneyRatio | ratio = marketValueRatio |
| `added_return` | 添加后涨幅 | moneyRatio | sortAddedReturn |
| `holding_pnl` | 持仓收益 | moneyRatio | auto-color |
| `day_pnl` | 当日盈亏 | moneyRatio | **derived: dayPnl**（口径见 `views/asset/watchlist/dayPnl.ts`）；**sortable: custom + sortBy: change_pct**（按涨跌幅排，非金额） |
| `_actions` | 操作 | actions | fixed right，120px |

> 现有"最新价"的 `v-if realtimeEnabled` 双分支，统一收进 `money` renderer 内部，由 `realtimeField` 驱动；**模板不再出现双分支**。（`riseFall` renderer 曾承担同一职责，随 `change_pct` 列在 #2641 删除后一并移除——`RiseFallText` 组件本身仍被 `return_*` 等收益类列使用。）

### 实施偏差（MVP 阶段，已落地）

为降低与 #980 重构的冲突面、避免丢失既有交互，下列列**暂保留原模板**（未纳入 v-for），仅 7 个纯数据列（created_at / current_price / holding_quantity / position_market_value / added_return / holding_pnl / day_pnl）走 columnDefs 驱动：

- `product`：含「添加/编辑标签」按钮（`openTagEditor`），逻辑较特殊，renderer 暂未承载该交互。
- `_marker`：置顶/关注图标列，纯展示 + 行 hover 样式，保留原模板。
- `_selection`：`v-if="batchMode"` 的多选列，el-table 内置 type，不入 renderer。
- `_actions`：含 `v-if="!batchMode"` 显示 `-`、`tooltip`、`status==='HOLDING'` 禁用删除，保留原模板更稳妥。

> 数据列的 `current_price` 实时覆盖双分支已成功内聚进 renderer（核心诉求达成）。
> 待 #980 合入、数据列驱动稳定后，再将 product/actions 切到 renderer，最终删除全部硬编码列。

## 4. 渲染分发（renderer 注册表）

新建 `frontend/src/views/asset/watchlist/columnRenderers.tsx`（或 `.vue` 渲染函数），按 `ColumnRenderer` 枚举集中实现各单元格渲染，签名统一为：

```ts
(row: WatchlistRow, def: ColumnDef, ctx: RenderCtx) => VNode
// ctx 内含：realtimeEnabled, getValuationItem, allTags, 各 open 回调等
```

模板改为：

```vue
<el-table-column
  v-for="def in visibleColumns"
  :key="def.key"
  :label="def.label"
  :width="def.width"
  :min-width="def.minWidth"
  :align="def.align"
  :fixed="def.fixed"
  :sortable="def.sortable"
  :sort-method="def.sortMethod"
>
  <template #default="{ row }">
    <component :is="resolveRenderer(def.renderer)" :row="row" :def="def" :ctx="renderCtx" />
  </template>
</el-table-column>
```

## 5. 与实时数据链路的衔接

- `renderCtx.getValuationItem(symbol)` 仍来自页面现有的 `useRealtimeQuotes` 实例（不新建）。
- renderer 内判断：`if (def.realtimeField && ctx.realtimeEnabled && ctx.getValuationItem(row.symbol))` → 用估值项字段，否则用 `row[def.key]` 静态值。逻辑内聚在 renderer，**不在模板散落**。
- 新增实时字段（如 #990 走势所需的历史点）一律经 `realtimeDataSources.ts` 扩展，renderer 只消费，符合 `realtime-data-sources.md` 约束。

## 6. 为后续 issue 预留的扩展点

- **#993 表头自定义**：基于 `hideable` + 用户列顺序偏好（localStorage），`visibleColumns` 由 `columnDefs` 过滤/重排得到。
- **#992 拖拽排序**：拖拽只改 `visibleColumns` 顺序数组（持久化），不动 `columnDefs` 源定义。
- **#990 Sparkline**：新增 `renderer: "sparkline"`，realtimeField 扩展为含历史序列；renderer 内部决定走哪条数据源。

## 7. 实施步骤（MVP 分层）

1. ✅ 新建 `columnDefs.ts`（§3 清单）+ `columnRenderers`（§4 分发），**不删**原硬编码列。已提交。
2. ✅ 在 `index.vue` 内用 `v-for` 渲染 `dataColumns`（7 个纯数据列）覆盖原硬编码数据列；`product`/`_marker`/`_selection`/`_actions` 保留原模板（见 §3 实施偏差）。实时覆盖双分支已内聚进 renderer，`pnpm run typecheck` 零错误。已提交。
3. ⏳ 删除硬编码数据列，仅保留 `columnDefs` 驱动；并把 `product`/`actions` 也切到 renderer。**待 #980 重构合入、数据列驱动稳定后执行**（避免与 #980 改动区域冲突）。
4. ⏳ 补单元测试：列定义完整性（key 唯一、renderer 均注册）、排序方法正确。
5. ⏳ 之后 #990/#992/#993 各自在 columnDefs 上增量开发。

> 过渡期策略：步骤 2 与步骤 3 之间可停留，确保 #980 重构合入时不冲突（本设计为新增文件，#980 改的是其它区块）。

## 8. 验收标准

- 新增一个展示字段（如某实时指标）只需：在 `columnDefs.ts` 加一条 + 在 renderer 注册表加一个分支；**不修改 `index.vue` 模板主体**。
- 现有全部列行为（排序/实时覆盖/标签/操作/置顶图标）与重构前视觉与功能一致。
- `pnpm run typecheck` 零错误。

## 9. 品类视图列集（#1285，2026-09-10）

引入列「视图作用域」，解决「混合视图把所有品类列并集导致默认超宽」：

- `ColumnDef.scope`：
  - `"mixed"`：混合视图（未按品类筛选）也显示的**通用列**——`product` / `current_price` / `trend` / `holding_quantity` / `position_market_value` / `holding_pnl` / `day_pnl` / `_actions`（**#1421/#1422/#1425 修订**：原集只有 4 列、默认视图信息量过低；#1422 一度扩到 11 列 ≈1338px，#1425 收敛回 8 列；**#2640 起** `created_at` 降为默认隐藏、`day_pnl` 升为默认可见；**2026-10-26 起**预算放宽到 1132px，`trend` 恢复默认可见；**#2641** 删掉 96px 的 `change_pct` 列，其百分比并入 `day_pnl`。见下方「默认列预算」）；
  - `"category"`（默认）：**品类专属列**，仅当「类型筛选命中单一品类」时显示。
  - **通用列判定标准（#1421）**：该列对「**全部品类**」或「**全部可交易品类**（`TRADABLE_TYPES` 7 类）」都成立、不会恒为 `—` → 归 `"mixed"`；只有**真品类专属列**（可转债条款 / 指数估值 / 基金回撤 / 关联 / 投顾指标）留 `"category"`。
- `ColumnDef.appliesTo`：适用 `asset_type` 列表（缺省＝全部品类）。**它是品类视图的判据，与 `scope` 无关**：`scope` 只回答「混合视图要不要出现」。如持仓/市值/收益类列只对 `TRADABLE_TYPES`（不含 `index`/`manager`/`portfolio`）；`current_price` 与 `day_pnl` 用 `QUOTE_TYPES`（含 `index`——指数无持仓、金额 `—`，但涨跌幅成立）。
- `ColumnDef.sortBy`（#2641）：**排序代理字段**。前端派生列（`day_pnl`）在 `row` 上没有同名字段，直接拿 `key` 去查后端白名单会「查不到就静默失效」（#1331 的形态）。指定 `sortBy` 后，点击该列表头会把 `sortBy` 当作 `sort_by` 发给后端；缺省用 `key`。⚠️ `day_pnl.sortBy = "change_pct"` 意味着**按涨跌幅排而非按金额排**（同样涨 1%，一万仓与百万仓的当日盈亏差两个数量级）——要按金额排得后端先落派生字段，属另一张卡。
- `useWatchlistColumnVisibility(activeCategory)`：`activeCategory` = 类型筛选命中单一品类时为其 `asset_type`，否则 `null`（混合视图）。可见列 = 顺序 × 用户显隐偏好 × 视图作用域：
  - 用户显式开启（`shown`）→ **任何视图都显示**（覆盖视图作用域与默认隐藏）；
  - 默认隐藏且未开启 → 隐藏；
  - 其余按 `scope`/`appliesTo` 判定。
- `isHidden(key)` 语义 = 「**当前视图下是否可见**」，设置面板勾选框与表格所见一致（勾上即任何视图都显示）。
- 列宽表达（#1421）：非固定列一律用 `ColumnDef.minWidth`，`ColumnDef.width` 只给固定列（`product` / `_actions` / `_selection`）。原因：EP 只把「无数字 `width`」的列纳入容器余量分配（`flexColumns`），全列固定宽会让表格宽度恒等于 Σ 列宽、容器再宽也不铺满。
- **默认可见列总宽 ≤ 1040px（#1285 立，#1425 重申；2026-10-26 曾临时放宽到 1132，#2641 复位）**：1040 是「1366×768 不横滚」的推导值。2026-10-26 曾为让走势列（92px）留在混合视图而放宽到 1132、接受表格内部横滚；**#2641 删掉 96px 的「今日涨跌幅」列后实测 1036，横滚的代价不必再付，故口径回到 1040**（`trend` 仍在混合视图，两个诉求同时满足）。要加默认列仍须在 PR 里说明宽度来源并同步本口径与 `columnBudget.spec.ts`。横向滚动只发生在**表格内部**（`.el-table` 外框 = 容器宽，页面级横滚禁止），且 `product`（左冻结）与 `_actions`（右冻结）恒定不滚。见 `frontend/design.md`「冻结列与横向滚动规范」§4/§5（已同步）。

#### 默认列预算（2026-10-27，#2641 后实测）

按 `visibleColumns` 的真实判据（`hideable && !defaultHidden && scope==="mixed"`）逐列相加（`columnDefs.ts` 经 esbuild 打包后取 `width ?? minWidth` 求和，不是手算）：

| 列 | product | current_price | trend | holding_quantity | position_market_value | holding_pnl | day_pnl | _actions |
|---|---|---|---|---|---|---|---|---|
| px | 232 | 96 | 92 | 104 | 140 | 128 | 104 | 140 |

合计 **1036px**（上限 1040，余量 4px）。三点必须写清楚，否则下一个人会把账算错：

1. **走势列默认可见是 owner 的明确要求**：`trend` 曾因 1040 预算退到 `scope:"category"`（#2650），导致自选页默认的「持仓」分组看不到走势列；2026-10-26 改回 `"mixed"` 并把预算放宽到 1132。#2641 删掉 `change_pct`（96px）后，`trend` 留在混合视图的同时总宽回到 1040 以内——**不需要再放宽预算**，故上限复位。
2. **#2640 的「进一出一」仍然成立**：`created_at`（104，一次性历史）默认隐藏、`day_pnl`（104，每日主数据）默认可见，两者等宽。
3. **不得再静默加宽**：再加默认列必须同步改 `columnBudget.spec.ts` 的 `BUDGET` 与本表；超限时该用例会打印逐列账目。余量只有 4px，等于没有余量。
- **品类视图的列集由 `appliesTo` 决定，与 `scope` 无关**（`scope` 只决定「混合视图要不要出现」）：新增 `mixed` 列时必须检查它在**经理 / 投顾组合**等无行情、无持仓语义的品类视图里是否也需要 `appliesTo` 收窄（#1425：最新价 → `QUOTE_TYPES`；#2641：当日盈亏 → `QUOTE_TYPES`，删列后指数行的涨跌幅靠它承担）。
