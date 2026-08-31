# 统一对账工作台设计（Reconciliation Workbench）

> 状态：**已定稿**（2026-08-31，小组讨论收敛，可作为开发任务书）
> 关联 issue：#1232（总括设计与决策清单）、#1233（决策 10「记一笔写流水」改造 · 前置依赖）、#1133（域 B 源头）
> 沿用设计：E账户对账 `e-account-reconciliation-design-2026-08-16.md`、账本渠道分类 `ledger-channel-category-redesign-2026-08-28.md`、`docs/design/components.md`
> 设计哲学：**从「自动修正」到「透明对账 + 手动裁决」；从「分散入口」到「统一工作台」；从「导入即落库」到「草稿承接头寸、不中断操作」**

---

## 0. 摘要

手动导入是投资记账的核心场景，数据源头在用户手里，系统永远无法 100% 自动正确。现有三套流程各自独立、形态不一：同花顺交割单导入「导入即落库、无对账」、E账户导入「只能 cover/ignore、不能就地补录」、"记一笔"手动记账「只建持仓不建流水、跳离上下文是中断操作」；而「草稿承接头寸」所需的 Local Storage 草稿层完全空白。

本设计把现有 E账户对账抽象为通用「对账域」，提出**统一对账工作台（Workbench）**：草稿层承接头寸、统一入口收敛三套流程、就地补充替代跳"记一笔"。**不推翻 E账户现有实现，而是纳入框架复用其范式与字段。**

---

## 1. 问题域与现状梳理

### 1.1 三域（对账场景）

| 域 | 基准源（expected） | 目标源（actual） | 现状 |
| :-- | :-- | :-- | :-- |
| **A · E账户对账** | E账户官方持仓快照 | 渠道持仓（流水推导） | ✅ 已上线（专用） |
| **B · 持仓快照一致性** | 期初快照 + 期后流水推演的理论持仓 | 当前实际持仓 | ❌ 空白（#1133 P2，本框架定为 P1） |
| **C · 对账单/交割单导入** | 导入的券商/基金对账单 | 系统现有持仓 | ❌ 无对账（导入即落库） |

### 1.2 三套孤立流程现状（2026-08-31 代码调研）

- **同花顺交割单导入**：`parsers/ths_stock.py` + 前端 `useImportWizard.ts` 四步向导（选账户→上传→预览修正→导入完成）。管线 `parse→enrich→commit`。**缺口**：止于「导入完成」，解析失败/对不上的行直接跳过，无对账补录环节。
- **E账户导入**：唯一成型对账链路（`/investment/reconcile` + `/api/e-account/{reconcile,attribution,reconciliation}` + 四态归因）。**缺口**：只能 cover/ignore，不能就地补录。
- **"记一笔"手动记账**：`/investment/manual` → `usePositionSubmit.submitPosition` → `createPosition` → `POST /api/positions/`，**只建 Position 不建 Transaction**（详见 #1233）。只支持 buy/sell/dividend/dividend_reinvest/split。**缺口**：无对账补充能力，跳离上下文即中断。
- **Local Storage 草稿**：**完全空白**。导入态纯内存（`useImportWizard.ts` 约 1968 行，`ref`/`reactive`），刷新即丢；全仓搜 `pendingImport/tempImport/importDraft` **0 命中**。

### 1.3 核心痛点

入口分散、形态不一；对账补充被迫跳"记一笔"（中断）；导入中途无法承接头寸（刷新丢失）；后期 AI 识图/Excel/PDF（#823/#921/#929/#934/#935）接入会放大这些断裂。

---

## 2. 设计哲学

1. **透明对账优于自动修正**：系统职责是"呈现差异 + 提供裁决工具 + 保留审计线索"。
2. **用户是唯一真相裁决者**。
3. **不中断操作**：对账补充绝不强跳"记一笔"，在工作台内就地完成。
4. **草稿承接头寸**：导入/对账中间态持久化本地，可恢复、可跨页承接。
5. **渐进式落地**：先底座（草稿层 + 统一入口），再逐域接入，避免一次性大改留 bug。

---

## 3. 专业 Reconciliation 理念映射

| 专业理念 | 本框架落地 |
| :-- | :-- |
| 流水不可变 | 调整通过新增「调整凭证」实现，不篡改既有流水 |
| Cleared / Uncleared | 对账状态标签（pending / cleared / ignored） |
| 对账差异中心 | 统一工作台 Dashboard，跨域聚合 |
| 期初持仓锚点 | 域 B 以快照为「期初余额」，叠加期后流水 |
| 差异分类 | 数量 / 成本 / 资金 / 孤儿 |
| 一键调整 | 补录 / 期初调整 / 直接修正（对冲）/ 忽略 |
| 柔性提示 | 中性信息色 Banner，严禁弹窗打断 |
| 审计线索 | `adjustment_logs`，全量留痕可追溯 |
| 对账状态标签 | 固定卡片标题行右侧，信息色非红 |

---

## 4. 现有基础盘点（复用，不推翻）

### 4.1 ★ 三个可直接复用的既有资产（本轮调研新发现，显著削减实现量）

| 资产 | 位置 | 用途 |
| :-- | :-- | :-- |
| **`recompute_position_from_transactions`** | `position_service.py:779` | **从流水重算持仓**——正是域 B「流水推演理论持仓」需要的能力，现成可用 |
| **交易处理汇点族** | `position_service.py` | `process_buy_or_deposit`(447) / `process_sell_or_withdraw`(670) / `process_dividend`(863) / `process_dividend_reinvest`(907) / `process_orphan_*`(934-1061)。均为「**写 Transaction + 更新 Position**」原子操作 |
| **`entry_status='orphan'` 既有语义** | `summary_service.py:64` 等 | "孤儿/孤立流水"在系统里已是既有概念（`position_id=None` + `entry_status='orphan'`），域 B 孤儿检测应**对齐既有语义**而非另起炉灶 |

### 4.2 其他既有资产

- **域 A 范式**：`ownership_status`(active/shadow) + `position_import_meta.is_attributed/is_ignored/source_broker/fund_manager` + 三 API + 防复活 + 幂等。**直接复用，不动。**
- **`PositionSource` 枚举**：`app/core/constants.py:144`，已含 12 个值 + `POSITION_SOURCE_LABELS` 中文标签（详见 §8.2）。**决策 11 应扩展它，而非新建枚举。**
- **`localforage` 封装**：`frontend/src/utils/localforage/index.ts`，IndexedDB 优先 + localStorage 降级 + 分钟级 TTL + `keys()` 可枚举。**直接用作草稿底座。**
- **聚合层**：`position_aggregation.py` 已 join `position_import_meta` 补齐字段、已返回 `snapshot_date`/`snapshot_date_latest`/`nav_date`，**无对账逻辑**（待扩展）。

---

## 5. 通用对账框架

### 5.1 对账域（Reconciliation Domain）
每个域 = 一组「基准源 vs 目标源」对比，各自实现 `run_reconciliation()` 返回差异项。

### 5.2 对账运行（Reconciliation Run）
快照式，每次 run 记录 `data_date`/源标识/输入范围/输出摘要，写入 `reconciliation_runs`；幂等、可重跑。

### 5.3 差异项模型（Discrepancy）
`type`（数量/成本/资金/孤儿）、`severity`（info/warning，**禁刺眼红**）、`status`（pending/cleared/ignored）、`scope`（ledger_id + symbol）、`expected`/`actual`/`diff`。

### 5.4 调整机制（按语义分派到既有汇点，**不新建调整表**）

| 补充类型 | 分派汇点 | 落库结果 |
| :-- | :-- | :-- |
| 增量型（补一笔缺失买卖） | `process_buy_or_deposit` / `process_sell_or_withdraw` 等 | **Transaction（source=reconciliation_adjustment）+ Position 增量更新**，聚合层天然可见 |
| 设定型（期初建仓、改数量/成本） | `upsert_from_holding` | SET Position，**不建流水**（硬约束） |

> 注：`position_aggregation.py` **只查 `positions`，不读 `transactions`**。因此任何补充若要被聚合层看到，**必须落到 Position**（增量型经汇点自动同步；设定型经 SET 直接落 Position）。

### 5.5 审计线索
所有**用户主动操作**写 `adjustment_logs`（action: `ignore_temporary`/`ignore_permanent`/`supplement`/`adjust`/`cover`）。**系统自动行为不写**（如新 run 重置 pending、差异消失置 cleared），避免淹没审计线索。

### 5.6 对账状态标签
`cleared`/`uncleared`/`discrepancy`/`ignored`，固定卡片标题行右侧（复用 `AssetTypeBadge`/`TemperatureLevelBadge` 规约）。
> ⚠️ 与 `watchlist/models.py` 的 `cleared_positions`（探市观测持仓）语义不同，本期不混用。

### 5.7 草稿层（Draft Layer）
- **底座**：`localforage`（IndexedDB 优先 + TTL）。
- **key**：`recon-draft:<familyId>`（**全局单槽**，真正"只存一份"）。
- **payload**：`{ domain, ledgerId, savedAt, rows/previewData, ... }`——**必须带 `domain` 标记**（见 §5.8）。
- **不存文件二进制**：只存解析结果（恢复后无法重新解析，故行内编辑是刚需；`selectedKeys` 是 `Set`，序列化时转数组）。
- **TTL 7 天** + 「丢弃草稿」入口。

### 5.8 草稿恢复的域路由（关键交互）
| 场景 | 交互 |
| :-- | :-- |
| **同域**草稿 | Banner：「发现 6月1日的未完成草稿，恢复 / 丢弃」（无跳转） |
| **跨域**草稿 | **弹窗**（不直接跳转）：「你有一份【E账户导入】的草稿（6月1日 14:30，共 23 行）。E账户草稿需要在 E账户导入页继续。」→ 主按钮「前往继续」（确认后跳转）/ 次按钮「放弃这份草稿」 |

> 直接跳转会让用户被"传送"走且丢失当前页状态，违背柔性原则，故跨域必须弹窗确认。

---

## 6. 三域落地区

### 6.1 域 B · 持仓快照一致性对账（P1）

**算法口径（已修正 #1133 原文的矛盾）**：

```
理论持仓 = 期初余额（快照份额）+ 期后流水净变化（confirm_date > snapshot_date）
差异     = 实际持仓（positions.quantity）- 理论持仓
```

> **⚠️ #1133 原文写的是 `confirm_date <= snapshot_date`，存在内在矛盾**：它描述的典型场景是「6 月导入快照 → 8 月又导入新买入流水」，但按原文算法 8 月流水被排除在窗口外，而它已增量进 `positions.quantity` → **必然误报**。必须改为 `> snapshot_date`。

**边界（硬约束推论）**：
- **无流水则 skip**：`upsert_from_holding` 是 SET 语义（覆盖而非累加，**不会"数量翻倍"**）且**绝不调 `TransactionService.create`**。纯快照/E账户模式无流水可推 → **跳过对账，禁止误报**。
- **孤儿检测限定**：仅当该 `(ledger_id, symbol)` **在 transactions 表存在至少 1 条记录**时才检测；无流水 → skip。
- **匹配键用 `ledger_id + symbol`**：`Transaction.position_id` 可能为 `None`（孤立流水，`summary_service.py:64`），不能用 position_id 匹配。
- **孤儿两方向**：① 持仓无流水（仅当该 symbol 完全无 transaction 才报，快照导入走 skip）；② 流水无持仓（理论持仓 > 0 但系统无持仓）——后者才是真孤儿，对齐既有 `entry_status='orphan'` 语义。

**成本处理**：**P1 只做数量差异**。理由不是"算法复杂"，而是**口径不可比**——`upsert_from_holding` SET 覆盖 `avg_price`，而 `process_buy_or_deposit` 是加权摊薄，E账户归因成本更是净值近似（设计文档 P3）。对比必然假阳性。
- 差异详情**只展示当前成本**（`positions.avg_price`）+ 标注「来自最近一次导入/快照（SET 覆盖），非流水推导，本期不参与对账」。
- **技术债**：未来成本可比需在 `position_import_meta` 增加 `cost_source` 标记。

### 6.2 域 C · 对账单/交割单导入对账（P1）
导入（`orchestrator.commit`/`commit_holdings`）commit 成功后**单独调用**对账，与导入事务解耦（对账失败不影响已导入数据）。

**异步方式**：项目**无后台任务队列基础设施**（`backend/app` 下无 celery/RQ/APScheduler）。但対账是纯 DB 聚合，比现有 `aggregate_positions`（同步、`allow_remote=False`）还轻，200 条毫秒级。
→ **采用前端交互层异步**：fire-and-forget 调对账接口，结果回来更新全局 Banner 差异计数。零基础设施，达成"不阻塞"体验。

### 6.3 统一对账工作台（Workbench Shell）
单一路由，三域 Tab + 顶部状态栏（数据日期 / 待裁决计数）+ 柔性 Warning Banner。取代分散的 E账户对账中心页 + 交易导入无对账 + 手动记账孤岛。

### 6.4 就地补充（In-context Supplement）
工作台内直接编辑补充，生成调整凭证（分派见 §5.4），**绝不强跳"记一笔"**。

### 6.5 忽略语义（跨域分治，UI 统一）

| 域 | 后台实现 | 语义 |
| :-- | :-- | :-- |
| **A（E账户）** | `position_import_meta.is_ignored = True`（现状，不动） | **永久忽略**（对实体记录的裁决） |
| **B/C** | `discrepancies.status='ignored'` + `is_permanent` | 默认**本期忽略**（新 run 重置 pending）；可选**永久忽略** |

**按钮交互（分组 + 节奏，Gmail「归档 vs 删除」模式）**：
- **本次忽略**：行内按钮（临时操作，快捷）
- **永久忽略**：进详情弹窗 / 批量操作栏 + **二次确认弹窗**（说清后果，**不强制输入文字**，因有可撤销兜底）

**安全阀 · 已忽略清单**：跨域聚合展示（域 A 的 `is_ignored` + 域 B/C 的 `is_permanent`），**可撤销**。这是"永久忽略"的解药——不是限制忽略范围，而是**可发现 + 可撤销**。
- **API**：后端提供统一接口 `GET /api/reconciliation/ignored/`（合并两源，返回标准化结构 `{domain, ledger_id, ledger_name, symbol, name, reason, ignored_at, is_permanent, undo_action}`）+ `DELETE /api/reconciliation/ignored/{domain}/{id}`（按 domain 分派撤销）。**不做前端分别拉取再合并**（结构不同，分页/排序难做）。

**新 run 时的状态流转**：
| 重算结果 | `is_permanent` | 行为 |
| :-- | :-- | :-- |
| 差异仍存在 | FALSE | 重置为 **pending**（版本化，强迫重新审视） |
| 差异仍存在 | TRUE | 保持 **ignored**（永久静默） |
| 差异已消失 | — | 置为 **cleared** |

---

## 7. 前端交互规范（对齐 `docs/design/components.md`）

- 强制复用 `SectionHeader` / `MetricCard` / `MetricGrid` / `CardBlock` / `MoneyDisplay` / `AssetTypeBadge` / `ProductDisplay`；状态标签固定标题行右侧；栅格 12 列。
- **柔性 Warning Banner**：中性信息色，可点进工作台；**严禁弹窗打断**（草稿跨域恢复的场景除外，该场景需确认跳转）。
- **对账中心 Dashboard**：左右分栏对比（理论 vs 实际），高亮差异，按严重度着色。
- **分步引导**：数据导入 → 自动对账 → 手动处理差异。
- **审计可视化**：「已忽略清单」内展示每次调整的"谁、何时、改了什么、原因"。

---

## 8. 数据模型增量

### 8.1 新增三表（均为 user 域，含 `family_id`）

```sql
-- 活跃差异（按业务键 upsert，非按 run 重建）
CREATE TABLE discrepancies (
  id                INTEGER PRIMARY KEY,
  family_id         INTEGER NOT NULL,
  domain            VARCHAR(2)  NOT NULL,          -- 'A' | 'B' | 'C'
  ledger_id         INTEGER,
  symbol            VARCHAR(30) NOT NULL,
  discrepancy_type  VARCHAR(20) NOT NULL,          -- quantity|cost|cash|orphan
  expected_value    NUMERIC,
  actual_value      NUMERIC,
  diff              NUMERIC,
  status            VARCHAR(20) DEFAULT 'pending', -- pending|cleared|ignored
  is_permanent      BOOLEAN DEFAULT FALSE,         -- 永久忽略逃生舱
  ignored_reason    TEXT,
  ignored_at        TIMESTAMP,
  ignored_by        INTEGER,
  last_run_id       INTEGER,
  first_detected_at TIMESTAMP,
  updated_at        TIMESTAMP,
  UNIQUE(family_id, domain, ledger_id, symbol, discrepancy_type)
);

-- 对账运行记录（历史与摘要）
CREATE TABLE reconciliation_runs (
  id          INTEGER PRIMARY KEY,
  family_id   INTEGER NOT NULL,
  domain      VARCHAR(2) NOT NULL,
  data_date   DATE,
  started_at  TIMESTAMP,
  finished_at TIMESTAMP,
  triggered_by VARCHAR(20),                        -- manual|import|schedule
  summary_json TEXT                                -- pending/cleared/ignored 计数
);

-- 审计日志（仅用户主动操作）
CREATE TABLE adjustment_logs (
  id             INTEGER PRIMARY KEY,
  family_id      INTEGER NOT NULL,
  run_id         INTEGER,
  discrepancy_id INTEGER,
  action         VARCHAR(30) NOT NULL,  -- ignore_temporary|ignore_permanent|supplement|adjust|cover
  before_json    TEXT,
  after_json     TEXT,
  reason         TEXT,
  operator       INTEGER,
  created_at     TIMESTAMP
);
```

> **为何 `discrepancies` 按业务键 upsert 而非按 run 重建**：对账差异在业务语义上是**持续状态**（没解决就一直存在）。若按 run 重建，则 `is_permanent` 无法挂行（下期是新记录，不继承），必须另建独立忽略规则表——徒增复杂度。历史追溯由 `reconciliation_runs` + `adjustment_logs` + `discrepancies.updated_at` 承担。

### 8.2 来源标记（决策 11）——**扩展既有 `PositionSource`，不新建枚举**

`app/core/constants.py:144` **已存在** `PositionSource` 枚举（12 值）+ `POSITION_SOURCE_LABELS` 中文标签：

```
manual / e_account_holding / tiantian_fund / ths_stock / standard_fund /
standard_stock / alipay_fund / alipay_pdf / standard_template /
ai_txn / ai_holding / explore
```

**落地方式**：
- `positions`：**已有 `source` 列，直接复用**。如需表达"对账补录"，在 `PositionSource` **追加** `RECONCILIATION_ADJUSTMENT = 'reconciliation_adjustment'`（同步加 `POSITION_SOURCE_LABELS` 中文标签）。
- `transactions`：**新增独立 `source` 列**（不存 `extra` JSON），枚举**复用同一套 `PositionSource`**（命名保持一致，避免两套体系）。
- **⚠️ 去重哈希耦合**：`compute_position_hash(source, ledger_id, symbol, snapshot_date)`（`records.py:41-53`）**以 source 为第一维**。因此：
  - **存量记录的 `source` 一律不改**（不回填、不改写），否则 `import_hash` 漂移导致去重/幂等失效；
  - 新枚举值只用于新记录。

### 8.3 迁移硬约束（AGENTS.md）
1. 新表必须登记 `app/core/db_factory.DATA_DOMAIN_REGISTRY`，三表均含 `family_id` → **user 域**，未登记启动即被拦截。
2. 模型字段变更须同步 Create/Update/Out Schema（`conventions.md` §4.3）。
3. 需写迁移脚本，范式见 `scripts/migrate_ledgers_aggregation_fields.py`。

---

## 9. 与现有代码/文档关系

| 现有资产 | 处理 |
| :-- | :-- |
| E账户 `reconcile`/`attribution`/`reconciliation` API 与范式 | **复用**为域 A，不动 |
| `positions.ownership_status`、`position_import_meta` 字段 | **复用** |
| `recompute_position_from_transactions` / `process_*` 汇点族 / `entry_status='orphan'` | **复用**（域 B 与补充动作的核心基础设施） |
| `PositionSource` 枚举 | **扩展**（追加 reconciliation_adjustment） |
| `localforage` 封装 | **复用**为草稿底座 |
| `AggregationHero` / `useAggregation` / `AssetTypeBadge` | **复用**为展示基座 |
| `position_aggregation.py` | **扩展**对账标记计算 |

---

## 10. 实施路线（P0–P3）

| 优先级 | 内容 | 说明 | 风险 |
| :-- | :-- | :-- | :-- |
| **P0** | 草稿层（localforage 全局单槽 + 域标记 + 域路由）+ 统一入口脚手架 | 底座；改善"刷新即丢/中断"，零迁移 | 低 |
| **P0 前置** | **#1233**「记一笔写流水」改造（复用 `process_*` 汇点） | 数据完整性 + 域 B 前置依赖；**独立 issue，不混入本卡开发** | 中 |
| **P1** | 三表落地 + 域 B 计算 + 柔性提醒 | 纯计算层 + 组件演进 | 低 |
| **P1** | 域 C 导入后接对账（前端交互层异步） | 导入完成页引导进工作台 | 中 |
| **P2** | E账户对账迁入工作台 + 就地补充替代跳"记一笔" | 统一入口，复用 API | 中 |
| **P3** | 识别层（#823/#921/#929/#934/#935）接草稿与对账 | AI 识图/Excel/PDF 落草稿 → 工作台 | 高 |

> 原则：**P0 先打底座**，后续域接入都建立在草稿层 + 统一入口之上，避免各自为政留下 bug。

---

## 11. 已拍板决策清单（2026-08-31 小组讨论收敛）

| # | 决策项 | 结论 |
| :-- | :-- | :-- |
| 1 | 域 B 对账范围 | 只做**数量**差异 + 孤儿检测（限定「该 symbol 有流水」才检测） |
| 2 | 算法口径 | **理论持仓 = 期初快照 + 期后流水净变化（`confirm_date > snapshot_date`）**（修正 #1133 原文矛盾） |
| 3 | 成本呈现 | 只展示当前成本 + 标注来源（快照 SET，非流水推导，**不参与对账**） |
| 4 | 补充动作落库 | **按语义分派既有汇点**，不新建调整表：增量型→`process_*`（Transaction+Position）；设定型→`upsert_from_holding`（SET，不建流水） |
| 5 | 「记一笔」改造 | 改走 `process_*` 汇点使其同时写流水；**存量不回填**；**货基/逆回购保持建持仓**；独立 issue **#1233** |
| 6 | 来源标记 | **扩展既有 `PositionSource`**（不新建枚举命名）；`transactions` 新增独立 `source` 列；存量 `source` **不改** |
| 7 | 忽略语义 | UI 统一叫「忽略」：行内=本次忽略（下期重置），详情/批量栏+二次确认=永久忽略；域 A 保持现状 |
| 8 | 已忽略清单 | 跨域聚合、**可撤销**；后端统一 API（非前端合并） |
| 9 | 审计日志 | 用户主动操作**全写**；系统自动行为**不写** |
| 10 | 永久忽略二次确认 | 确认弹窗即可，**不强制输入文字**（有可撤销兜底） |
| 11 | 草稿层 | **全局单槽**（`recon-draft:<familyId>`）+ 域标记 + 域路由恢复 + 7 天 TTL + 可丢弃 |
| 12 | 草稿跨域恢复 | **弹窗确认**（不直接跳转）；同域则 Banner 直接恢复/丢弃 |
| 13 | 表结构 | `discrepancies` 按业务键 upsert + `is_permanent`；`reconciliation_runs`；`adjustment_logs` |
| 14 | 异步方式 | **前端交互层异步**（项目无队列基础设施），对账与导入事务解耦 |
| 15 | 去重底线 | 由后端 `import_hash` UNIQUE 约束兜底；P0 不做前端预校验，但须如实展示后端返回的重复统计 |

---

## 12. 存量数据盘点（2026-08-31 实测，只读）

**库文件**：`backend/invest.db`（注意：`invest.user.dev.db` 为空库；开发期 positions/transactions 均在 `invest.db`）

| 项 | 结果 |
| :-- | :-- |
| `positions` 总行数 | **150** |
| `positions.source` 分布 | `e_account_holding` = 102，**`manual` = 48** |
| `transactions` 总行数 | **2051** |
| `transactions.type` 分布 | buy 991 / sell 703 / dividend_tax 132 / dividend 69 / dividend_cash 66 / deposit 50 / tax 40 |
| `transactions` 是否有 `source` 列 | **否**（需新增） |
| `positions` 是否有 `op_type` 列 | **否**（记一笔的 op_type 未落库，仅作提交参数） |

**关键推论**：
1. **`manual` 已是既有 `source` 取值** → 决策 10 改造后记一笔的 source 仍为 `manual`，**哈希不漂移，无去重风险**。
2. `process_buy_or_deposit` 的 source **默认为 `PositionSource.MANUAL`**（`position_service.py:569`），因此**交易导入若不显式传 source，其建出的持仓会被标成 `manual`** → 存量 48 条 `manual` 中可能混杂"真手动记账"与"交易导入默认 manual"，**无法回溯区分**。这正是决策 11 必须正确传递 source 的原因，也是**存量不改写 source** 的依据。
3. **`positions` 无 `op_type` 列** → 记一笔连"这笔持仓由何种操作产生"都未持久化，数据完整性问题比预估更严重（#1233 价值被进一步印证）。

---

## 13. 域 B 边界用例（验收基准）

| # | 场景 | 预期 |
| :-- | :-- | :-- |
| 1 | 快照后无交易 | 理论 = 快照份额；与实际一致 → **无差异** |
| 2 | 快照后有买入（合法增量） | 理论 = 快照 + 买入；实际同步增量 → **无差异**（不误报） |
| 3 | 导入旧快照回退持仓 | 理论 = 快照 + 期后流水；实际被 SET 回退 → **报差异**（真实问题） |
| 4 | 纯快照/E账户（无流水） | **skip，不检测、不告警** |
| 5 | 有流水但持仓缺失 | 理论持仓 > 0 而系统无持仓 → **报孤儿**（对齐 `entry_status='orphan'`） |
| 6 | 持仓存在但完全无流水 | 若为快照导入 → **skip**；否则报孤儿 |

---

## 14. 关联 Issues

- **#1232** 统一对账工作台总括设计与决策清单（本文件的载体）
- **#1233** 「记一笔」只写 positions 不写 transactions（**P0 前置依赖**）
- #1133 聚合视图视觉优化（域 B 的 P2 快照对账源头）
- #1132 场内证券聚合卡片 / #1101 场外基金聚合
- #1012 基金E账户持仓解析器（域 A 基础）
- #1018 AI 持仓识别误走交易管线（holding_recognizer）
- #929 持仓导入功能（含截图/OCR 复用）/ #921 AI 识别导入分层架构（BaseRecognizer）
- #823 OCR 截图导入 + 用量表 / #934 资产简记托盘截图导入入口 / #935 MinerU 支付宝截图识别
- #786 ShowBuy 导入系统决策文档（历史基线）

---

## 15. 变更记录

- 2026-08-31：创建（#1133 讨论 + 专业 Reconciliation 理念 + 三套流程现状调研）。
- 2026-08-31：小组讨论收敛后**定稿**——替换「开放决策点」为 §11 已拍板清单；修正域 B 算法口径；确定按语义分派既有汇点（不新建调整表）；确定扩展既有 `PositionSource`（不新建枚举）；补充 §12 存量盘点、§13 边界用例、§8 三表 DDL；关联 #1232 / #1233。
