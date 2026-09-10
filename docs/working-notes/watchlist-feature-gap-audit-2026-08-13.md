# 自选功能 Issue 实现缺口核验（2026-08-13）

逐条核对 #661 / #807 / #826 / #860 四个自选相关 issue，对照当前 `backend/app/domains/watchlist` 与 `frontend/src/views/asset/watchlist` 及文档，确认哪些功能真正未落地。结论：**真正未做的是「备注分享（已砍，不实现）」「品种差异化描述维度」「双层估值开关平台级」「探市沙盒子系统的 8/10/11 承诺」**；备注可编辑 UI 已在 #1285 落地（2026-09-10），同时 #860 待办清单存在文档漂移（把已做的分组/标签也标成未做）。

## 核验结论总表

| 功能点 | 来源 issue | 后端状态 | 前端状态 | 证据 |
|---|---|---|---|---|
| 分组（系统+自定义） | #661 #860 | ✅ `WatchlistGroup.is_system` | ✅ 分组 tabs + `fetchGroups` | `models.py` / `index.vue` |
| 自定义标签（labels 式） | #661 #860 | ✅ `WatchlistTagDef`+`WatchlistItemTag` | ✅ 增删改/打标 UI | `models.py` / `index.vue` |
| 按产品区分（基础 `asset_type`） | #661 #860 | ⚠️ 仅 STOCK/ETF/FUND/CB/INDEX | ✅ 统一类型标签 | `models.py` |
| 自选备注 `notes` 可编辑 UI | #661 #860 #1285 | 字段已建 | ✅ 已实现（自选页「备注」列 + 添加弹窗均支持，与 Favorite 复盘页共享 `watchlist.notes`） | `NotesEditorDialog.vue` / `AddToWatchlistModal.vue` |
| 备注分享能力 | #661 #860 | — | — | 已砍：本期不做分享，备注仅本地编辑 |
| 品种不同描述维度不同 | #661 #860 | ❌ 统一 schema | ❌ 统一表格 | `models.py` 单表 |
| 基金经理/组合(投顾)可观察实体 | #661 #860 | ❌ 仅枚举无实体（`entity_type=MANAGER` 悬空） | ❌ 无 | `models.py` |
| 实时估值核心（成功标准 1–7） | #807 | ✅ | ✅ | `useRealtimeQuotes` + 估值表 |
| 免登录沙盒（8–11） | #807→#821 | — | ⚠️ 重定义到 /explore 但 P0 缺陷未修 | `#821 OPEN` |
| 估值前端直连约束(30s/1m/90s) | #826 | — | ✅ `REFRESH_INTERVAL_OPTIONS=[15,30,60,90]` | `useRealtimeQuotes.ts:14` |
| 双层估值开关·平台级 env+配置接口 | #826 | ❌ 后端 0 命中 `REALTIME_QUOTES_ENABLED` | ⚠️ 仅 localStorage 用户级 | `useRealtimeQuotes.ts:10` |
| 每日收益日历免费确认 / 付费候选清单 | #826 | 产品决策 | OPEN 勾选项 | — |

## 各 Issue 逐条判定

### #661（CLOSED）· 自选核心
- 分组（系统+自定义）：✅ 已实现。
- 自定义标签（labels 式）：✅ 已实现。
- 按产品区分：基础 `asset_type` 区分有；但无基金经理、组合（投顾）两类可观察实体。
- 自定义备注：✅ 已实现（#1285，2026-09-10）。后端 `WatchlistItem.notes` + 前端自选页「备注」列（整格点击编辑）/ 添加弹窗均支持编辑，与 Favorite（未竟之蹊）复盘页共享同一 `watchlist.notes` 字段。分享能力已砍，本期不做。
- 品种不同描述维度不同：❌ 未实现。所有类型共用统一字段。
- 该 issue 关闭时已在 `docs/spec/tech-debt.md` 第 97 行诚实标注 2 项 `[ ]`（备注分享、品种维度）；其中备注编辑已在 #1285 落地、分享已砍，仅品种维度仍待 #1286 数据底座 / #1285 消费侧。

### #807（CLOSED）· 实时估值设计文档
- 实时估值核心（1–7）：✅ 已交付。
- 免登录沙盒（8–11）：被 `docs/features/watchlist.md` 第 10 行重定义为已上线的探市页 `/explore`，缺口转 #821（OPEN）。但 #821 实证探市页仍是半成品：免登录搜索 401、热门卡片硬编码假成本价、登录后本地持仓清空不回读、迁移丢弃成本价/份额。故"沙盒已实现"措辞高估——壳子挂到 /explore，核心承诺 8/10/11 未兑现。

### #826（OPEN）· 付费/免费分层
- 估值前端直连约束：✅ 已实现（15/30/60/90 档）。
- 双层估值开关：⚠️ 只做一半。用户级 localStorage 开关 ✅；平台级 env `REALTIME_QUOTES_ENABLED` + 配置接口后端 0 命中，平台无法强制关闭估值。
- 每日收益日历免费确认、付费候选清单登记：产品决策项，仍 OPEN。

### #860（OPEN）· 收口 #661 剩余项
- 待办 4 项里有 2 项文档漂移：把"系统分组+自定义分组""自定义标签"标成 `[ ]`，但这两者在 #661 已落地、代码也确实存在。#860 自身总结又承认"#661 已实现核心"，内部自相矛盾。
- 真正未做 1 项与 #661 缺口一致：品种维度描述（#1285 消费侧 / #1286 数据底座）；可分享备注已砍，备注编辑已在 #1285 落地。
- 已据此将 #860 两个错标勾选框改为 `[x]`（见 issue 正文修订）。

## 文档漂移纠正
- #860 待办：`- [ ] 系统分组 + 自定义分组` → `- [x]`，`- [ ] 自定义标签（labels 式）` → `- [x]`（2026-08-13 执行）。

## 建议排期（未实现项）
- P0：自选 `notes` 编辑 UI（已在 #1285 落地，2026-09-10）；探市页 P0 缺陷（#821）。
- P1：品种差异化描述维度与经理/组合实体；双层估值平台级 env+配置接口（#826）。
- ~~P2：备注分享能力~~（已砍：不实现分享，备注仅本地编辑，见 #1285 决议）。

## 关联
- 源 issue：#661 #807 #826 #860 #821
- 设计基线：`docs/features/watchlist.md`
- 技术债登记：`docs/spec/tech-debt.md` 第 97 行（#661 缺口）

## 2026-08-14 落地更新（issue #826 关闭）

- **双层估值开关·平台级**：✅ 已落地。后端新增 `GET /api/utils/config/`（读 env `REALTIME_QUOTES_ENABLED`，默认 true），加入 `PUBLIC_PREFIXES` 白名单（探市免登录访客可读总闸）；前端 `useRealtimeQuotes.ts` 初始化拉取平台级开关，关闭时强制停轮询、`toggle` 无效。实现见 `backend/app/domains/utils/views.py`、`backend/app/core/auth.py`、`frontend/src/composables/useRealtimeQuotes.ts`。
- **每日收益日历免费确认 / 付费候选清单**：✅ 已登记。分层规范入 `docs/spec/pricing-tier.md`（判定准则 + 功能归属表 + 双层开关 + 前端直连硬约束）；OCR→#823、行业拥挤度→#892/#891、一键自动源→#930 各有 issue 跟踪。
- **估值前端直连约束**：✅ 已作为硬约束写入 `docs/spec/pricing-tier.md` §4。
- 本表第 19-20 行「❌/⚠️」状态即日起全部闭环；#826 验收通过后关闭。
