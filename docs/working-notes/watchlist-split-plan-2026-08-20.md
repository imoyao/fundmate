# 自选页（watchlist）拆分为止项清单

> 生成日期：2026-08-20
> 目标文件：`frontend/src/views/asset/watchlist/index.vue`（当前 **1758 行 / 57KB**，design.md 上限 200~300 行）
> 关联：umbrella #980（上帝页面拆分）、#995（列定义数组化，已完成）

## 完成情况（已落地，勿回退）

- **#995 列定义数组化**：`columnDefs.ts`（8KB）+ `columnRenderers.tsx`（12KB）已落地，`index.vue` 已切到 `v-for="def in dataColumns"` 数据驱动，仅 selection 列保留模板。新增字段一律改这两文件，**不要再往 index.vue 硬编码堆列**。
- **已抽 Hook**：`useWatchlistGroups`、`useWatchlistTags`、`useRealtimeQuotes`（位于 `frontend/src/composables/`）。
- **已抽组件**（位于 `frontend/src/components/`）：`RealtimeWarningBanner`、`RealtimeStatusIndicator`、`AddToWatchlistModal`、`OcrImportModal`、`TagManagerDialog`、`GroupManagerDialog`、`TagEditorDialog`、`SettingsDrawer`、`MoneyDisplay`。

## 仍可拆分的模块（按风险从低到高）

### A. 抽 Hook —— 最大减重项（script 约 600 行可外移）

| 模块 | 当前位置 | 目标文件 | 说明 |
|------|---------|---------|------|
| 分页/筛选 state | 787-840（currentPage/pageSize/totalItems/searchKeyword/fetchParams 等） | `useWatchlistQuery.ts` | 分页与查询参数聚合，纯数据 |
| 批量操作 | 870-929（batchMode/selectedItems/handleBatchDelete/handleBatchMoveToGroup） | `useWatchlistBatch.ts` | 依赖 fetchData 回调，需注入 |
| 搜索防抖 | 930-940（debounceSearch/searchTimer） | 并入 `useWatchlistQuery.ts` | 与筛选 state 同域 |
| 视图切换/筛选重置 | 965-1009（handleViewChange/resetFilters/toggleDraftTag） | `useWatchlistFilters.ts` | 与 useWatchlistTags 协同 |
| 行操作编排 | 990-1058（handleTogglePin/handleToggleFavorite/confirmRemove/executeRemove/openTagEditor 等） | `useWatchlistRowActions.ts` | 纯副作用编排，调 API |
| 抽屉/弹窗开关 | 795-808、1060-1086（各 show* ref + onItemAdded/onOcrImported/onTagEditorSaved） | 留在页面或 `useWatchlistDialogs.ts` | 轻量，可留页面 |

> 抽 Hook 后 index.vue `<script>` 预计从 ~1100 行降到 ~400 行。

### B. 抽 UI 子组件 —— template 减负（template 约 450 行可外移）

| 区块 | 行号 | 目标组件 | 说明 |
|------|------|---------|------|
| 工具栏按钮组（新增/刷新/导出/OCR/设置/批量） | 99-126 | `WatchlistToolbar.vue` | 纯展示 + emit 事件 |
| 分组切换 tabs | 145-180 | `WatchlistGroupTabs.vue` | 依赖 `allGroups`/`activeGroup`（已在 useWatchlistGroups） |
| 标签筛选面板 | 200-260 | `WatchlistTagFilter.vue` | 依赖 useWatchlistTags |
| 汇总条（市值/成本/盈亏） | 280-356 | `WatchlistSummaryBar.vue` | 读 `summary` computed |
| 删除确认弹窗 | 470-486 | 并入 `useWatchlistRowActions` + 现有删除 dialog，或 `WatchlistRemoveDialog.vue` | 逻辑已在 A 类 Hook |

> 抽组件后 index.vue `<template>` 预计从 ~540 行降到 ~150 行。

### C. 列内增强（#995 之上的增量，issue 仍 OPEN）

- #990 列内排序持久化
- #991 列宽/显隐拖拽
- #993 列配置本地持久化

这些在 `columnDefs.ts` 上增量开发，**不碰 index.vue**。

## 落地约束（避免互相覆盖）

1. 改动必须基于已落地的 `columnDefs`/`columnRenderers`，不再向 index.vue 硬编码列。
2. 抽 Hook 时，被抽逻辑若依赖 `fetchData`/`fetchTags` 等页面方法，用回调或 composable 返回值注入，不要在子组件里重新请求。
3. 一次只抽一个模块，抽完即 `pnpm typecheck` + 跑通页面，原子提交，不攒大改动。
4. 新分支开发，不要直接在主分支堆改。

## 建议实施顺序

1. 先抽 **A 类 Hook**（减重最大、风险低、与 UI 解耦）。
2. 再抽 **B 类组件**（纯展示，依赖 A 已就绪的 state）。
3. 最后做 **C 类列增强**（独立 issue）。

预计 A+B 完成后 index.vue 可降到 ~550 行（仍超 300，但已从「上帝页面」降级为正常页面；彻底到 200 行需进一步合并小 Hook，收益递减，建议止步于 A+B）。
