# 探市 #808 功能点现状盘点（2026-08-19）

> 来源：issue #808（设计文档 + 任务计划，OPEN / Q1-RED）、issue #821（缺陷与缺口跟踪，OPEN）
> 目的：把"已实现 / 未实现"梳理清楚，作为下一步开发依据。
> ⚠️ 重构冲突警示见文末「与进行中重构的重叠」。

## 一、#808 目标回顾

「探市」体验版——免登录沙盒，看实时收益、零门槛添加（≤2 步）、注册引导（迁移本地持仓）。
入口：自选页「探市」Tab（`frontend/src/views/explore/index.vue`，单文件，非路由拆分）。

## 二、已实现（代码层可确认）

| 模块 | 现状 |
|------|------|
| 免登录查看热门资产实时收益（4 张写死卡片） | ✅ 已实现（但数据为假，见 P0-2） |
| 免登录状态下「添加自选」本地写入 localStorage（SIGNED_OUT 分支） | ✅ 已实现 |
| 登录态从 localStorage 迁移持仓到后端（SIGNED_IN 分支，自动） | ✅ 主链路已实现（但静默、无预览，见 P1-5） |
| 探市持仓列出现价/收益（realtimeDataSources 取数） | ✅ 已实现（取数层在重构中，见预警） |
| 热门资产卡片展示 | ✅ 已实现 |

## 三、未实现 / 有缺陷（来自 #821，按优先级）

### P0 — 数据正确性与阻断

- **P0-1 免登录搜不到资产**
  搜索走 `/api/securities/search/`、`/api/funds/search/`，但后端免登录白名单仅含 `/api/health`、`/api/temperature`。
  生产 `AUTH_ENABLED` 时匿名请求 401，错误被前端吞掉 → 搜索下拉静默空白。
  「零门槛添加 ≤2 步」在生产实际不成立，只有 4 张写死热门卡片可用。
  → 修复方向：把证券/基金搜索加入匿名白名单（或新增只读探市搜索端点）。

- **P0-2 热门资产硬编码假成本价**
  `hotAssets` 写死 `costPrice`(4.567/1.234/34.56/0.987)、`quantity:100`，点开即显示编造收益，违反 §6「成本价默认=当前价」。
  → 修复方向：热门卡片成本价的默认语义改为"无成本/按现价"，或标注"示例"。

- **P0-3 登录后本地持仓被清空且不回读**
  迁移后 `localStorage` 被清，但探市页只读本地 → 已登录用户刷新后列表变空。
  → 修复方向：登录态下读后端持仓（含本次合并落地的未归档 `ledger_id=null` 持仓）+ 本地合并。

- **P0-4 迁移丢弃成本价与份额**
  迁移只写代码/名称，`costPrice`/`quantity` 没落库，迁移后盈亏归零。
  → 修复方向：迁移时携带 `costPrice`/`quantity`（需后端 positions 写入支持）。

### P1 — 设计承诺未兑现

- **P1-5 无迁移预览与用户选择**（#807 成功标准 10）
  现在 `SIGNED_IN` 后静默自动迁移，用户看不到合并结果、也无法选「迁移/丢弃」。
  → 修复方向：加迁移预览弹窗 + 用户确认（与组合详情页归档 UI 一致风格）。

- **P1-6 底部转化区缺失**（#808 §3.2）
  全文无「立即注册」CTA、无损失厌恶文案、无迁移提示——引导注册的商业目的未落地。
  → 修复方向：探市页底部加注册转化区（注意与登录重构 `login/index.vue` 解耦）。

### P2 — 体验

- **P2-7 移动端表格未做卡片降级**（§7.2）
  `@media` 只覆盖部分区块，持仓表格窄屏仍是横向表格。
  → 修复方向：持仓表格响应式卡片化（独立组件，避开 watchlist 重构文件）。

- **P2-8 并发批量不一致**
  `realtimeDataSources.ts` 的 `BATCH_SIZE=5`，#808 风险缓解写的是 3，需二选一并同步文档。
  → 修复方向：统一数值 + 更新设计文档。

## 四、验收门槛（#821）

- P0 全修 + P1 兑现
- #807 成功标准 8–11 全部可勾选
- `docs/features/watchlist.md`（及 #808 描述）与代码拉平

## 五、与进行中重构的重叠（⚠️ 重点，别互相覆盖）

以下分支正在进行中，**改动文件与 #808 修复高度重叠，直接改会冲突**：

### A. `feat/watchlist-unified-realtime`（前端自选统一实时行情，领先 main-v2 43 提交，未并入）
动到的重叠文件：
- `frontend/src/constants/index.ts`（**我们 c39cb30 刚加 `TEMP_SOURCE_LABELS`；该分支删 67 行，会冲突**）
- `frontend/src/views/temperature/index.vue`（**我们改了 `displaySource`；该分支改 20 行**）
- `frontend/src/views/asset/portfolio/detail.vue`（**我们加未归档归档；该分支删 130 行**）
- `frontend/src/views/asset/watchlist/index.vue`、`columnDefs.ts`、`columnRenderers.tsx`
- `frontend/src/api/types.d.ts`、`frontend/src/api/watchlist.ts`
- 后端：`positions/views.py`、`positions/schemas.py`、`positions/models.py`（**我们改了 source 校验+归档过滤**）、`watchlist/views.py`（大量删减）、`watchlist_service.py`

### B. `refactor/god-pages-split`（本地，巨型页面拆分）
动到的重叠文件：
- `frontend/src/views/asset/watchlist/index.vue`（大瘦身 205 行）、`columnDefs.ts`、`columnRenderers.tsx`
- `frontend/src/views/temperature/index.vue`（7 行）
- `frontend/src/constants/index.ts`（27 行新增，与 A 方向相反）

### C. 探市页本身（`frontend/src/views/explore/index.vue`）
- **当前未被上述任何重构分支直接改动**（stat 无 explore 行）。
- 但 `realtimeDataSources.ts` 取数层在 `feat/watchlist-unified-realtime` 重构范围内 → 探市取数逻辑若改动需与该分支对齐。

### 操作建议（避免覆盖）
1. **探市页 `explore/index.vue` 本体**：可安全直接改（P0-1/P0-2/P0-3/P1-5/P1-6/P2-7 多落在此文件）。
2. **`constants/index.ts`**：我们刚加的 `TEMP_SOURCE_LABELS` 与两个重构分支都碰它。改前先 `git fetch` + 看 `feat/watchlist-unified-realtime` 是否已并入 main-v2；若未并入，修复 P0 时如需加常量，单独提分支并在合并前 rebase。
3. **`temperature/index.vue`**：仅 `displaySource` 一行是我们改的，其余被重构碰。改温度相关先确认重构状态。
4. **`portfolio/detail.vue` / `positions/*` 后端**：归档功能刚合并，重构分支大改这些文件。归档相关微调需等 `feat/watchlist-unified-realtime` 收敛或协同。
5. **P0-1 后端白名单**：改 `backend/app/core/auth.py` 或新增匿名端点——确认 `feat/watchlist-unified-realtime` 是否也动了 auth（其 diff 显示 `auth.py` 有 3 行删除），先对齐。

## 六、下一步建议顺序

1. 先确认 `feat/watchlist-unified-realtime` 是否会近期并入 main-v2（问持有者 / 看 PR）。
2. 若暂不并入：在 `feature/sso-cross-subdomain` 基础上新开 `fix/explore-p0-*` 分支，只动 `explore/index.vue` 与必要的最小后端白名单，避开重构文件。
3. P0 优先级：P0-1（搜索白名单）→ P0-2（假成本价）→ P0-3/P0-4（登录回读/迁移保真）。

---
*本文件为现状盘点，不含代码改动。临时导出 JSON/MD 在 `C:\Users\imoyao\CodeBuddy\Claw\`（issue808/821 相关），确认无用后可删。*
