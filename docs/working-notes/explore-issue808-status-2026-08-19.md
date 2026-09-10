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
  → **2026-09-10 已落地**：`ExploreWatchlistTable.vue` 增加 ≤768px 卡片降级
  （matchMedia 切换，信息与桌面列一一对应，样式全部走设计 token）。

- **P2-8 并发批量不一致**
  `realtimeDataSources.ts` 的 `BATCH_SIZE=5`，#808 风险缓解写的是 3，需二选一并同步文档。
  → **2026-09-10 已裁决**：以实运行为准收敛为 **5**（实测无风控拦截），
  代码注释与本文档已同步；#808 原设计稿的「3」作废。

## 四、验收门槛（#821）

- P0 全修 + P1 兑现
- #807 成功标准 8–11 全部可勾选
- `docs/features/watchlist.md`（及 #808 描述）与代码拉平

## 五、与进行中重构的重叠（⚠️ 重点，别互相覆盖）

以下分支正在进行中，**改动文件与 #808 修复高度重叠，直接改会冲突**：

### A. `feat/watchlist-unified-realtime`（前端自选统一实时行情）—— 已合入，无未并入 diff
- HEAD `161380c`，**是 `main-v2` 的祖先**（已用 `git merge-base --is-ancestor` 双向验证），其全部工作已包含在 main-v2 历史中，**没有未合并的改动，无"剩余工作量"**。
- 最新提交为「阶段 A 取数层批量数据源改造（#990）」，即它"在干嘛"= 实时行情取数层批量数据源改造，已落地。
- ⚠️ 之前此处误写为"领先 main-v2 43 提交、未并入、删 67/130 行"——那是把 `git diff main-v2..该分支`（旧祖先视角，把 main-v2 后来新增的内容显示成"删除"）当成了分支的改动。**实际这些文件（`constants/index.ts` 的 `TEMP_SOURCE_LABELS`、`temperature/index.vue` 的 `displaySource`、`portfolio/detail.vue` 的归档 UI）都是我们在 `c39cb30` 之后才加的，分支时代根本不存在，不存在冲突风险。**
- 结论：做 #808 修复时**无需**避让 unified-realtime，它不会覆盖我们的代码。

### B. `refactor/god-pages-split` —— 已合入 main-v2（2026-08-20），不再构成分叉冲突
- 已合并（7 提交，+1774/-959）：watchlist/index.vue 拆分后现约 1287 行，columnDefs/columnRenderers 已落地，login 重构已含 OAuth 修复。
- 做 #808 修复时直接以 main-v2 当前代码为基，无需避让。

### C. 探市页本身（`frontend/src/views/explore/index.vue`）
- **当前未被 `refactor/god-pages-split` 直接改动**（stat 无 explore 行）。
- `realtimeDataSources.ts` 取数层是 `feat/watchlist-unified-realtime`（#990）已合入的成果；若 `refactor/god-pages-split` 后续也触及取数层，探市取数逻辑改动需与该分叉分支对齐。

### 操作建议（避免覆盖）
1. **探市页 `explore/index.vue` 本体**：可安全直接改（P0-1/P0-2/P0-3/P1-5/P1-6/P2-7 多落在此文件）。
2. **`constants/index.ts`**：`TEMP_SOURCE_LABELS` 已随 god-pages-split 合入 main-v2，改动以 main-v2 当前内容为准。
3. **`temperature/index.vue`**：god-pages-split 的 7 行改动已合入，以 main-v2 当前内容为准。
4. **`portfolio/detail.vue` / `positions/*` 后端**：归档功能已在 main-v2，无分叉冲突。
5. **P0-1 后端白名单**：改 `backend/app/core/auth.py` 或新增匿名端点——直接以 main-v2 为基。

## 六、下一步建议顺序

1. ✅ 两条重构线均已并入 main-v2：`feat/watchlist-unified-realtime`（此前已合入）、`refactor/god-pages-split`（2026-08-20 合入）——无等待项。
2. 从 main-v2 切 `fix/explore-p0-*` 分支，只动 `explore/index.vue` 与必要的最小后端白名单。watchlist 新结构（index.vue 约 1287 行 + columnDefs + 子组件）已就位，探市页引用相关 API 时以新结构为准。
3. P0 优先级：P0-1（搜索白名单）→ P0-2（假成本价）→ P0-3/P0-4（登录回读/迁移保真）。

---
*本文件为现状盘点，不含代码改动。临时导出 JSON/MD 在 `C:\Users\imoyao\CodeBuddy\Claw\`（issue808/821 相关），确认无用后可删。*
