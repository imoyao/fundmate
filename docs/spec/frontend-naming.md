# 前端命名规范（frontend-naming）

> 本文件为 `conventions.md` 第 2.7 节「全局命名规范」的**前端补充细则**，与后端命名规范并列。
> 制定依据：Vue 官方风格指南（Style Guide）、Pure Admin（vue-pure-admin）脚手架实际约定、社区通行实践。
> 关联文档：[`conventions.md`](./conventions.md) 第 2.7 节、[`decisions.md`](./decisions.md)（2026-08-03 条目）。

---

## 1. 制定背景与目标

项目早期前端代码写得较粗糙，文件命名、组件组织、变量/函数命名风格不统一，类型定义散落。
本次整理目标：**先固化规范 + 出具不规范点清单**，后续改造逐条对照清单执行（非一次性大改）。

为什么参照 Pure Admin：
- 本项目前端即基于 `pure-admin-thin` 脚手架（`frontend/package.json` 中 `homepage`/`repository` 指向 pure-admin），技术栈一致（Vue3 + Vite + Element-Plus + TS + Pinia）。
- 其目录约定（api 按模块拆分、components 用 `Re` 前缀标识内置封装、composables 用 `useXxx`、types 集中）是社区成熟范式。

**开源社区对「views 目录组织」的通行解法（关键结论）**：

Vue 官方风格指南（Priority B: Strongly Recommended）对**单文件组件文件名**的立场是：
> "Filenames of Single-File Components should either be always PascalCase or always kebab-case."

即：官方只要求**项目内大小写风格一致**，并不强制 PascalCase 或 kebab-case 二选一；官方也**未强制**「目录组件（文件夹含 `index.vue`）」与「平铺 `PascalCase.vue`」二选一。
「目录组件」模式（每个组件/页面一个文件夹，入口为 `index.vue`）是 Nuxt、Pure Admin 等框架/脚手架的**可选约定**，目的是便于组件内聚子组件、样式、类型文件，并非 Vue 官方红线。

**因此本项目决策（见 decisions.md）：对于 views 下混用 `index.vue` 包裹与 `PascalCase` 大组件的情况，保持现状不强制统一。** 规范只约束"大小写风格必须一致、文件名须语义自解释"，不强制目录形态。

---

## 2. 文件与目录命名

| 对象 | 规范 | 示例（✅） | 反例（❌） |
|------|------|-----------|-----------|
| Vue 单文件组件（.vue） | PascalCase，项目内统一 | `AccountOverview.vue`、`MoneyDisplay.vue` | `accountOverview.vue`、`account-overview.vue`（混用） |
| 工具/API 模块（.ts） | camelCase | `temperature.ts`、`usePageRefresh.ts` | `Temperature.ts`、`temperature-api.ts` |
| 组合式函数文件 | `use` + PascalCase | `useRealtimeQuotes.ts` | `realtimeQuotes.ts`、`use_realtime_quotes.ts` |
| 类型声明文件 | `*.d.ts` 或 `types.ts`；全局类型入 `types/` | `favorites.d.ts`、`types/router.d.ts` | 在业务 `.vue` 里随意 `interface` |
| 目录（组件/页面） | PascalCase 或 kebab-case，**全项目统一选一**；组件目录入口用 `index.vue` | `components/MoneyDisplay/`、`views/asset/Overview/` | 混用 `MarketFooter/` 与 `page-footer/` |
| 内置封装组件前缀 | 沿用 Pure Admin `Re` 前缀（ReCol/ReDialog/ReIcon…），业务组件**禁止**用 `Re` 前缀 | `ReDialog`、`MoneyDisplay` | `ReMoneyDisplay`（业务误用前缀） |
| 常量/配置目录 | `constants/`（纯常量）、`config/`（运行时配置）、`utils/`（函数）；三者职责不混 | `constants/index.ts`、`config/index.ts` | 把常量塞进 `utils/ledger.ts` |

**禁止**：
- 文件名用单字母、拼音缩写、无语义英文（如 `tmp.vue`、`a.vue`、`test2.vue`）。
- 同一目录内 PascalCase 与 kebab-case 混用。

---

## 3. 变量、函数与导出命名

| 对象 | 规范 | 示例（✅） | 反例（❌） |
|------|------|-----------|-----------|
| 局部变量 / 函数参数 | camelCase，语义自解释 | `ledgerId`、`holdingDays` | `a`、`data1`、`tmp` |
| 函数名 | 动词开头 camelCase，语义清晰 | `getLedgers`、`createWatchlistItem` | `ledgerApi`、`doThing` |
| API 请求函数 | 统一 `get/create/update/delete/fetch/sync` 动词前缀 | `getWatchlistItems`、`syncFundFees` | `refreshTokenApi`（Api 后缀冗余）、`getLogin`（login 是名词非动作） |
| 常量 | UPPER_SNAKE_CASE | `CURRENT_USER_ID`、`DEFAULT_PAGE_SIZE` | `currentUserId` |
| 布尔变量 | `is/has/can/should` 前缀 | `isLoading`、`hasError` | `loadingFlag`、`errorState` |
| 类型/接口 | PascalCase，后缀区分用途 | `WatchlistItem`（实体）、`WatchlistItemCreate`（入参）、`ApiResponse<T>`（泛型） | `watchlist_item`、`IWatchlistItem`（禁 I 前缀匈牙利命名） |
| 枚举 | PascalCase 单数或复数集合 | `LedgerType`、`AssetCategory` | `ledger_type_enum` |

**类型安全红线**（对齐 conventions 2.7 + 2.11）：
- **禁止 `any` / `Record<string, any>` 作为 API 入参或响应类型**。后端已输出强类型契约（见 `api/types.d.ts`、`types/`），前端须对齐。确需宽松处用 `unknown` + 收窄，或显式定义接口。
- 禁止 `data?: object` 空泛类型；应定义具体入参接口或 `Record<string, unknown>`。
- 接口字段名与后端 JSON 字段严格一致（camelCase 已约定），禁止自行臆造字段。

---

## 4. 组件内部约定

- `defineOptions({ name })` 必须与**路由 name** 完全一致（conventions 4.8 已强制，避免 keep-alive 失效）。
- 模板内组件引用 PascalCase（SFC/字符串模板），与 `import` 名一致。
- Props / Emits：Props 用 camelCase（`modelValue`），模板传参用 kebab-case（`v-model:model-value`）；Emits 事件名 camelCase，模板监听 kebab-case。
- 单文件组件顶级元素顺序统一：`<script setup>` → `<template>` → `<style>`（或 template 在前，但 `<style>` 永远最后）。

---

## 5. 类型组织约定

- **实体/契约类型集中管理**：跨模块复用的类型放 `src/types/` 或 `src/api/types.d.ts`；单文件内联 `interface` 仅限本文件私有类型。
- 当前问题：`api/watchlist.ts`、`api/ledger.ts` 等文件内既定义 `WatchlistItem` 等实体接口又放请求函数，改造时逐步将**跨模块复用类型**抽到 `api/types.d.ts` 或 `types/`，请求函数文件只保留调用。
- API 模块职责单一：一个业务域一个文件（`funds.ts`/`ledger.ts`/`watchlist.ts`），不在 `utils.ts` 塞业务请求。

---

## 6. 待改造清单（执行层）

见 [`frontend-naming-audit.md`](./frontend-naming-audit.md)。本文件为规范基线，audit 为逐条待办。
改造原则遵循 conventions 第 16 章（AI 编码约束）：不坏不修改、精准修改、逐条闭环。

---

## 7. 参考来源

- Vue.js Style Guide（官方）：<https://vuejs.org/style-guide/> —— Priority B: `single-file-component-filename`、component name casing。
- Pure Admin（vue-pure-admin）脚手架：`frontend/` 目录结构与 `Re` 前缀组件约定。
- 社区共识：目录组件（folder + index.vue）为可选组织模式，非官方强制；项目内一致性优先。
