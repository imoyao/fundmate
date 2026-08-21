# 自选页（watchlist）拆分进度清单

> 更新日期：2026-08-20（重写，此前版本行号/进度严重过时，以代码实况为准）
> 目标文件：`frontend/src/views/asset/watchlist/index.vue`（当前 **1287 行**，design.md 上限 200~300 行）
> 关联：umbrella #980（上帝页面拆分）、#995（列定义数组化，已完成）、#990/#991/#992/#993（列内增强，OPEN）

## 完成情况（已落地，勿回退）

### A 类 Hook —— 已全部拆完（script 逻辑已收敛到 composable）

| composable | 位置 | 职责 |
|---|---|---|
| `useWatchlistData` | `frontend/src/composables/useWatchlistData.ts`（313 行） | 分页/筛选/fetchData/行操作（置顶/关注/移除）/批量（删除/移动分组）/导出/重置 |
| `useWatchlistToolbar` | `frontend/src/composables/useWatchlistToolbar.ts`（70 行） | 搜索关键词/批量模式/视图 segmented/各弹窗开关 |
| `useWatchlistGroups` | `frontend/src/composables/useWatchlistGroups.ts`（134 行） | 分组 tab 派生 + fetchGroups |
| `useWatchlistTags` | `frontend/src/composables/useWatchlistTags.ts`（67 行） | 标签列表 + 标签筛选面板 |

页面编排：`groups/tags/toolbar/data` 四个实例在 index.vue 组装，`data` 依赖前三个（见 index.vue script 385-388）。

### B 类组件 —— 大部分已拆

| 组件 | 位置 | 说明 |
|---|---|---|
| `WatchlistFilterBar.vue` | `views/asset/watchlist/`（127 行） | 分组 tab + 标签筛选面板 + 视图 segmented |
| `WatchlistSummaryBar.vue` | `views/asset/watchlist/`（142 行） | 实时状态 + 刷新档位 + 估值汇总卡 |
| `WatchlistToolbar.vue` | `views/asset/watchlist/` | 顶部操作栏（搜索 + 批量工具栏 + 正常工具栏） |
| `WatchlistRemoveDialog.vue` | `views/asset/watchlist/` | 移除确认弹窗（含移除范围 radio） |
| `SettingsDrawer` / `TagManagerDialog` / `GroupManagerDialog` / `TagEditorDialog` | `components/Watchlist/` | 设置抽屉 / 标签管理 / 分组管理 / 行内标签编辑 |
| `AddToWatchlistModal` / `OcrImportModal` | `components/QuickEntry/` | 添加自选 / AI 导入 |
| `RealtimeWarningBanner` / `RealtimeStatusIndicator` | `components/` | 实时估值横幅 / 状态指示 |
| `MoneyDisplay` / `RiseFallText` / `MoneyWithRatio` | `components/` | 金额 / 涨跌 / 金额+比率展示 |

### #995 列定义数组化 —— 已完成

- `columnDefs.ts`（242 行）+ `columnRenderers.tsx`（12KB）已落地，`index.vue` 已切到 `v-for="def in dataColumns"` 数据驱动，仅 selection 列因 `type="selection"` 无法 renderer 化而保留模板。
- 新增字段一律改这两文件，**不要再往 index.vue 硬编码堆列**。

## 仍可拆分的模块（剩余，按风险从低到高）

### B 类剩余（小）

- 批量删除按钮（表格上方，batchMode 时显示，约 14 行）——收益小，可留页面或并入 WatchlistToolbar。

### C 类列内增强（#995 之上的增量，issue 仍 OPEN，均在 columnDefs 上增量开发，不碰 index.vue）

| issue | 内容 | 依赖 |
|---|---|---|
| #993 | 表头自定义/显隐/持久化（总装） | #995（已完成）；持久化方案已定：**纯前端 localforage**（2026-08-20 决策） |
| #992 | 列顺序拖拽 | #993 的列配置状态 |
| #991 | 列内指标排序 | #995（columnDefs.sortable 已就绪）+ 后端排序参数透传 |
| #990 | 迷你走势图 Sparkline | 后端批量序列端点 + #995 |

## 落地约束（避免互相覆盖）

1. 改动必须基于已落地的 `columnDefs`/`columnRenderers`，不再向 index.vue 硬编码列。
2. 抽 Hook/组件时，被抽逻辑若依赖 `fetchData`/`fetchTags` 等页面方法，用回调或 composable 返回值注入，不要在子组件里重新请求。
3. 一次只抽一个模块，抽完即 `pnpm typecheck` + 跑通页面，原子提交，不攒大改动。
4. 新分支开发，不要直接在主分支堆改。

## 建议实施顺序

1. ✅ A 类 Hook（已完成）。
2. ✅ B 类组件（FilterBar/SummaryBar/Toolbar/RemoveDialog 已抽，2026-08-20）。
3. ⏳ C 类列增强：按 #993 → #992 → #991 → #990 依赖序推进（#993 持久化用 localforage，纯前端零后端）。

预计 A+B 完成后 index.vue 可降到 ~550 行（仍超 300，但已从「上帝页面」降级为正常页面；彻底到 200 行需进一步合并小 Hook，收益递减，建议止步于 A+B）。
