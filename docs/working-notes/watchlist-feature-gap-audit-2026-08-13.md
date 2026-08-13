# 自选功能 Issue 实现缺口核验（2026-08-13）

逐条核对 #661 / #807 / #826 / #860 四个自选相关 issue，对照当前 `backend/app/domains/watchlist` 与 `frontend/src/views/asset/watchlist` 及文档，确认哪些功能真正未落地。结论：**真正未做的是「备注可编辑 UI + 分享」「品种差异化描述维度」「双层估值开关平台级」「探市沙盒子系统的 8/10/11 承诺」**；同时 #860 待办清单存在文档漂移（把已做的分组/标签也标成未做）。

## 核验结论总表

| 功能点 | 来源 issue | 后端状态 | 前端状态 | 证据 |
|---|---|---|---|---|
| 分组（系统+自定义） | #661 #860 | ✅ `WatchlistGroup.is_system` | ✅ 分组 tabs + `fetchGroups` | `models.py` / `index.vue` |
| 自定义标签（labels 式） | #661 #860 | ✅ `WatchlistTagDef`+`WatchlistItemTag` | ✅ 增删改/打标 UI | `models.py` / `index.vue` |
| 按产品区分（基础 `asset_type`） | #661 #860 | ⚠️ 仅 STOCK/ETF/FUND/CB/INDEX | ✅ 统一类型标签 | `models.py` |
| 自选备注 `notes` 可编辑 UI | #661 #860 | 字段已建 | ❌ 无编辑器（仅 `add_reason`） | `AddToWatchlistModal.vue:442` |
| 备注分享能力 | #661 #860 | ❌ 无 | ❌ 无 | 前端无 share |
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
- 自定义备注（支持分享）：❌ 未实现。后端 `WatchlistItem.notes` 字段存在，但前端 watchlist 无 `notes` 编辑入口（`AddToWatchlistModal` 只收 `add_reason`，line 442，全前端搜不到 notes 编辑器）；分享能力完全缺失。
- 品种不同描述维度不同：❌ 未实现。所有类型共用统一字段。
- 该 issue 关闭时已在 `docs/spec/tech-debt.md` 第 97 行诚实标注 2 项 `[ ]`（备注分享、品种维度），属"带已知缺口关闭"，非偷偷关。

### #807（CLOSED）· 实时估值设计文档
- 实时估值核心（1–7）：✅ 已交付。
- 免登录沙盒（8–11）：被 `docs/features/watchlist.md` 第 10 行重定义为已上线的探市页 `/explore`，缺口转 #821（OPEN）。但 #821 实证探市页仍是半成品：免登录搜索 401、热门卡片硬编码假成本价、登录后本地持仓清空不回读、迁移丢弃成本价/份额。故"沙盒已实现"措辞高估——壳子挂到 /explore，核心承诺 8/10/11 未兑现。

### #826（OPEN）· 付费/免费分层
- 估值前端直连约束：✅ 已实现（15/30/60/90 档）。
- 双层估值开关：⚠️ 只做一半。用户级 localStorage 开关 ✅；平台级 env `REALTIME_QUOTES_ENABLED` + 配置接口后端 0 命中，平台无法强制关闭估值。
- 每日收益日历免费确认、付费候选清单登记：产品决策项，仍 OPEN。

### #860（OPEN）· 收口 #661 剩余项
- 待办 4 项里有 2 项文档漂移：把"系统分组+自定义分组""自定义标签"标成 `[ ]`，但这两者在 #661 已落地、代码也确实存在。#860 自身总结又承认"#661 已实现核心"，内部自相矛盾。
- 真正未做 2 项与 #661 缺口一致：品种维度描述、可分享备注。
- 已据此将 #860 两个错标勾选框改为 `[x]`（见 issue 正文修订）。

## 文档漂移纠正
- #860 待办：`- [ ] 系统分组 + 自定义分组` → `- [x]`，`- [ ] 自定义标签（labels 式）` → `- [x]`（2026-08-13 执行）。

## 建议排期（未实现项）
- P0：自选 `notes` 编辑 UI（在 watchlist 详情/弹窗补 notes 输入）；探市页 P0 缺陷（#821）。
- P1：品种差异化描述维度与经理/组合实体；双层估值平台级 env+配置接口（#826）。
- P2：备注分享能力（需先做分享基础设施）。

## 关联
- 源 issue：#661 #807 #826 #860 #821
- 设计基线：`docs/features/watchlist.md`
- 技术债登记：`docs/spec/tech-debt.md` 第 97 行（#661 缺口）
