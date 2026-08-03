# 前端命名不规范点清单（frontend-naming-audit）

> 本清单为 [`frontend-naming.md`](./frontend-naming.md) 的执行层待办。**仅定位问题，不立即修改**（用户决策：先出规范 + 清单，后续逐条确认再改）。
> 扫描范围：`frontend/src` 全量。扫描日期：2026-08-03。
> 严重程度：`P0`=类型安全/契约风险，`P1`=风格一致性，`P2`=可读性优化。

---

## 一、API 层 `any` / 空泛类型滥用（P0 · 类型安全红线）

规范依据：frontend-naming §3「类型安全红线」、conventions 2.7/2.11。

| 文件 | 行 | 现状 | 建议 |
|------|----|------|------|
| `src/api/watchlist.ts` | 51/80/108/127 | `updateWatchlistItem(... data: Record<string, any>)`、`getWatchlistItems(params?: Record<string, any>)`、`getWatchlistTags(params?: Record<string, any>)` | 定义具体入参接口（如 `WatchlistItemUpdate`、`WatchlistItemQuery`） |
| `src/api/ledger.ts` | 23/71/83 | `createLedger(data: {...})` 内联宽松对象、`updateLedgerPosition(... data: Record<string, any>)`、`updateLedgerTransaction(... data: Record<string, any>)` | 抽取 `LedgerCreate`/`LedgerPositionUpdate` 接口（部分后端已有，前端对齐） |
| `src/api/importer.ts` | 4/21 | `parseFile(file: File, template: string, ledgerId: number \| null)`、`confirmImport(rows: any[])` | `confirmImport(rows: StandardTransactionRecord[])` 或 `ImportRow[]` |
| `src/api/user.ts` | 38/43/48 | `getLogin = (data?: object)`、`refreshTokenApi = (data?: object)`、`logoutApi = (supabaseToken?: string \| null)` | `data?: LoginParams`（具体入参接口） |

> 注：`Record<string, any>` 直接对应此前 typecheck 的 B 类债务（接口契约需核对）。改造前须先与后端 `api/types.d.ts` 对齐字段，禁止盲改掩盖契约问题。

---

## 二、API 函数命名不一致（P1）

规范依据：frontend-naming §3「API 请求函数」。

| 文件 | 现状 | 问题 | 建议 |
|------|------|------|------|
| `src/api/user.ts` | `getLogin`、`refreshTokenApi`、`logoutApi` | `Api` 后缀冗余、`getLogin` 动词/名词混用 | `login`、`refreshToken`、`logout`（统一动词式，去掉 `Api` 后缀） |
| `src/api/ledger.ts` | `deleteLedgerWithOptions`、`migrateLedgerPositions` | 命名尚可，但 `updateLedgerPosition` 与 `updateLedgerTransaction` 参数风格不一 | 参数统一用具体接口，函数名保持 `updateXxx` 动词式 |
| 全局 | `getLedgers`(camel) vs `refreshTokenApi`(带 Api) vs `calcFundNav`(calc 前缀) | 三种风格并存 | 统一 `get/create/update/delete/fetch/sync/calc` 动词前缀，禁 `Api` 后缀 |

---

## 三、类型与实现混放（P1）

规范依据：frontend-naming §5「类型组织约定」。

| 文件 | 现状 | 建议 |
|------|------|------|
| `src/api/watchlist.ts` | 内联定义 `WatchlistItem`/`WatchlistGroup`/`WatchlistTag`/`HomeSummaryItem` 等实体接口 + 请求函数 | 跨模块复用实体（`WatchlistItem` 等）抽至 `api/types.d.ts` 或 `types/`，本文件只留请求 |
| `src/api/ledger.ts` | 内联 `LedgerItem` + 请求函数 | 同上，`LedgerItem` 抽至 `api/types.d.ts` |
| `src/api/types.d.ts` | 已集中 `Position`/`SummaryData` 等 | 作为唯一契约源，逐步并入 watchlist/ledger 实体 |

---

## 四、components 目录层级混用（P1）

规范依据：frontend-naming §2「目录命名」「内置封装前缀」。

| 现状 | 问题 | 建议 |
|------|------|------|
| `components/` 下既有 `ReXxx/` 目录（ReDialog 等，Pure Admin 内置），也有 `MetricCard/`、`MoneyDisplay/`、`MarketFooter/` 等文件夹组件，还有平铺 `WatchlistWidget.vue` | 同一 `components/` 下"目录组件"与"平铺单文件"混用，层级不统一 | 业务组件统一改为**目录组件**（文件夹 + `index.vue`），与 `ReXxx` 平级；平铺的 `WatchlistWidget.vue` 迁入 `WatchlistWidget/index.vue` |
| `WatchlistWidget.vue` 平铺 | 与同目录 `MetricCard/`（目录）不一致 | 改为 `WatchlistWidget/index.vue` |
| 业务组件误用 `Re` 前缀风险 | `Re` 为 Pure Admin 内置标识，业务组件不可用 | 核查确认无业务组件以 `Re` 开头（当前未见，列为守卫项） |

---

## 五、utils / constants / config 职责边界模糊（P2）

规范依据：frontend-naming §2「常量/配置目录」。

| 文件 | 现状 | 建议 |
|------|------|------|
| `src/utils/ledger.ts`、`src/utils/trading.ts` | 偏领域常量/规则，非纯函数工具 | 评估是否归 `constants/` 或独立 `domain/`；若含纯函数则保留 utils，常量迁出 |
| `src/constants/index.ts`、`src/config/index.ts` | 两类各一文件，边界需明确 | 在文件头补注释说明：constants=编译期常量，config=运行时可配项，避免后续混入 |

---

## 六、views 目录形态（不强制 · 记录现状）

规范依据：frontend-naming §1「开源社区通行解法」、decisions 2026-08-03。

| 模块 | 现状 | 决策 |
|------|------|------|
| `views/account/` | 平铺 `PascalCase.vue`（`AccountOverview.vue` 等 9 个）+ `components/` 子目录 | 保持现状 |
| `views/asset/`、`views/login/`、`views/temperature/` | 多为 `index.vue` 包裹（文件夹 + index.vue） | 保持现状 |
| 全局 | 两种形态并存 | **不强制统一**，仅保证各自大小写风格一致（已满足 PascalCase） |

---

## 七、执行顺序建议

1. **P0 先行**：清 `any`/空泛类型，但必须**先与后端契约对齐**（B 类债务同源），单独排期，不盲改。
2. **P1 次之**：API 函数命名统一（去 `Api` 后缀、动词式）、类型集中、components 改目录组件。
3. **P2 收尾**：utils/constants/config 边界梳理。

每条改造遵循 conventions 第 16 章：精准修改、不坏不修改、逐条闭环验证（typecheck 通过）。
