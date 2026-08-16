# 前端持仓导入与对账设计（#1013）

> 状态：**已确认**（2026-08-16 讨论定稿，待编码）
> 关联：后端 PR #1021（已合入 main-v2）+ 对账/归因设计 `./e-account-reconciliation-design-2026-08-16.md`（v1.0 终版）；视觉规范 `frontend/design.md`（v2.3.4）。

## 1. 背景与目标

E账户（中国结算基金E账户）持仓快照导入。用户上传平台导出的持仓 Excel，系统解析后自动归因到渠道账户（天天基金/支付宝等 Ledger），冲突记录由用户决策，并提供对账中心持续核对系统持仓与 E账户快照的差异。

**核心语义**（与后端设计一致）：Ledger = 销售平台（用户心智）；E账户快照 = 对账/初始化工具，不产生交易流水；归因 = 快照份额归入渠道 Ledger。

## 2. 设计原则

1. **与交易导入完全并行**：持仓流程的状态、方法、组件与交易流程隔离，互不污染（后端已分轨，前端同样分轨）。
2. **遵循 `frontend/design.md`**：令牌（`--bg-card`/`--border-default`/`--radius-*`/`--space-*`）、涨红跌绿（`--color-rise`/`--color-fall`）、表格基线（`src/style/el-table.css`）、文案规范（动词+名词、错误给下一步）、数字格式（金额/份额 2 位、千分位、`tabular-nums`）、日期 `YYYY-MM-DD`（`src/utils/date.ts` 的 `formatDate`）。
3. **复用现有向导骨架**：上传/核对/结果三步的交互范式沿用现有 `UploadStep`/`PreviewStep`/`ResultStep`。
4. **禁止**：`any`/`Record<string, any>` 作 API 类型、硬编码 hex 色值、Emoji、页面内 `:deep(.el-table)` 覆盖视觉基线。

## 3. 入口设计

**位置一（导入）**：`ImportModeCards.vue` 现有三张卡片旁新增第四张「**导入持仓快照**」，点击**跳过选账户步骤**直接进入持仓导入流程（后端自动归因决定账户归属，前端不强制选账户）。

- 标题：`导入持仓快照`
- 描述：`上传平台导出的持仓文件，自动归入对应账户`
- 图标：`ep:document` 或 `ep:files`

**位置二（对账中心）**：持仓页右上角「**对账**」入口（`ep:data-analysis` 图标 + 文案），进入独立对账视图。

## 4. 流程设计

持仓导入为 **3 步**（无选账户步骤）：

```
步骤 1 上传持仓文件 → 步骤 2 核对与冲突处理 → 步骤 3 导入完成
```

### 4.1 步骤 1：上传

- 复用 `UploadArea` 交互（拖拽/点击上传），文件类型限制 `xls/xlsx`。
- 上传后调 `parseHoldingFile(file)`（`POST /api/e-account/parse`），返回解析 rows。
- 错误处理：`error_count > 0` 时提示「解析完成，N 条记录无法识别」，仍可进入下一步（失败行在核对页标注）。

### 4.2 步骤 2：核对与冲突处理（核心）

调 `reconcileHoldings(rows)`（`POST /api/e-account/reconcile`，**直接落库**），返回摘要，按分类展示：

| 分类 | 展示 | 用户操作 |
| :--- | :--- | :--- |
| ✅ 已自动归因（X 条） | 底部折叠明细 | 无需操作 |
| ✅ 已核对一致（X 条） | **折叠**，默认不展开 | 无需操作 |
| ⚠️ 待处理冲突（X 条） | **展开**，用户关注焦点 | 归因覆盖 / 忽略 |
| ❌ 失败行（X 条） | 错误明细（行号 + 原因） | 提示重新上传或忽略 |

**冲突明细行设计**（核心交互）：

| 基金名称 | 当前账本（天天基金） | E账户数据 | 差异 | 操作 |
| :--- | :--- | :--- | :--- | :--- |
| 易方达蓝筹精选 | 500 份 | 1000 份 | +500 份 | [归因覆盖] / [忽略] |

- **归因覆盖**：弹窗确认（含目标账户选择、可选成本输入）。弹窗文案含「E账户数据不包含成本信息，当前成本为净值近似值，可手动输入实际成本」（补丁 2 + P3）；提交调 `attributeHoldings([{record_id, action:'cover', target_ledger_id, avg_price?}])`。
- **忽略**：直接提交 `action:'ignore'`，该记录后续导入不再提示（可在对账中心重置）。
- 提交后局部更新该行状态，冲突清零则自动进入下一步。

### 4.3 步骤 3：结果

- 复用 `ResultStep` 范式：`持仓已同步（N 条记录）`、自动归因数、已核对数、冲突处理数、失败明细。
- 若存在未处理冲突（用户中途退出），提示「X 条冲突未处理，可稍后在『对账』中继续」。

### 4.4 对账中心（独立视图）

持仓页右上角「对账」进入，展示：

- **数据日期提示**（P2）：顶部「E账户数据为最近一次导入 2026-08-15，如需更新请重新导入」。
- **差异列表**：`GET /api/e-account/reconciliation` 返回 items，按状态分组或筛选：

| 基金名称 | E账户份额 | 系统份额 | 差异 | 状态 | 操作 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 易方达蓝筹 | 1000 | 500 | +500 | 未归因 | [归因到…] [忽略] |
| 中欧医疗 | 900 | 900 | 0 | 已核对 ✓ | — |
| 富国天惠 | 800 | 1000 | -200 | 已归因（天天基金） | 仅提示（按钮禁用） |

- **已归因记录**：显示「已归因至 [渠道名]」，差异数字显示但**操作按钮禁用**（只提示不覆盖，补丁 5）。
- **底部操作**：「一键归因全部未冲突记录」（安全操作）、「重置所有忽略」。
- 归因操作复用与步骤 2 相同的弹窗（目标账户 + 可选成本）。

## 5. 状态隔离（关键设计）

**新建独立 composable `useHoldingImport.ts`**，与 `useImportWizard.ts` 平行：

```
frontend/src/views/asset/investment/import/composables/useHoldingImport.ts
```

- 状态：`holdingStep`（0/1/2）、`holdingRows`、`reconcileSummary`（autoAttributed/verified/conflicts/failedRows）、`holdingConflictList`、`holdingParsing`、`holdingReconciling`、`holdingImporting`、`reconciliationItems`、`reconciliationDataDate`。
- 方法：`handleHoldingUpload(file)`、`runReconcile(rows)`、`handleConflictCover(record, targetLedgerId, avgPrice?)`、`handleConflictIgnore(record)`、`loadReconciliation(status?)`、`resetHoldingImport()`。
- 上下文：沿用 provide/inject 模式，`useImportWizardContext.ts` 增加 `provideHoldingWizard`/`useHoldingImportContext`（或独立 InjectionKey），与交易上下文并存。

**理由**：`useImportWizard.ts` 已 1968 行，交易流程状态与持仓语义不同（持仓无 `op_type`/`fee`/`allocation` 等），混入会互相污染；独立 composable 使持仓流程可独立演进、独立测试。

## 6. 组件改动清单

| 文件 | 改动 |
|------|------|
| `src/api/importer.ts` | 新增 `parseHoldingFile(file)`、`reconcileHoldings(rows)`、`attributeHoldings(decisions)`、`fetchReconciliation(status?)`（风格对齐现有 `parseFile`/`confirmImport`） |
| `src/api/types.d.ts` | 新增 `HoldingPreviewRow`、`ReconcileSummary`、`ReconcileConflict`、`ReconcileDecision`、`ReconciliationItem`、`ReconciliationResponse` 类型（**禁止 any**） |
| `components/ImportModeCards.vue` | 新增第四张卡片「导入持仓快照」，点击进入持仓流程 |
| `composables/useHoldingImport.ts` | **新建**：持仓流程状态与方法（见 §5） |
| `composables/useImportWizardContext.ts` | 新增持仓上下文 provide/inject |
| `components/HoldingUploadStep.vue` | **新建**：上传步骤（复用 `UploadArea` 交互） |
| `components/HoldingReconcileStep.vue` | **新建**：核对摘要 + 冲突处理（核心交互，见 §4.2） |
| `components/HoldingResultStep.vue` | **新建**：结果步骤（复用 `ResultStep` 范式） |
| `components/ReconciliationView.vue` | **新建**：对账中心视图（见 §4.4） |
| `index.vue` | 模式切换：持仓模式渲染持仓三步组件；`el-steps` 标题按模式切换（交易 4 步 / 持仓 3 步） |
| 持仓页（`views/asset/...`） | 右上角新增「对账」入口，路由到 `ReconciliationView` |

**不改动**：`useImportWizard.ts`（交易逻辑）、`UploadStep`/`PreviewStep`/`ResultStep`（交易组件）、`LedgerSelectStep`（选账户步骤，持仓跳过）。

## 7. 设计规范遵循清单（design.md 逐条对照）

- [ ] 表格：直接用 `<el-table>` 继承 `src/style/el-table.css` 基线，行高 44px，**禁止页面内 `:deep(.el-table)` 覆盖**；首列「名称+代码」`fixed` 冻结（180-220px）；数值列 `tabular-nums` 纵向对齐
- [ ] 涨跌色：差异值正负走 `--color-rise`/`--color-fall`（系统多/E账户多为视角，统一「正值涨、负值跌」语义）；错误行/冲突用 `--color-danger-system`（危险色只留给错误/破坏性操作）；「已核对 ✓」用 `--color-success`（若设计规范允许，否则用中性色+文字）
- [ ] 文案：标题/按钮动词+名词（`导入持仓快照`、`归因覆盖`、`忽略此记录`），禁用 `确定`/`OK`；错误提示描述问题+下一步；成功直接陈述结果；进行中动词+省略号（`对账中…`）
- [ ] 数字：金额 2 位千分位（`¥12,345.67`）、份额 2 位（`1,234.56 份`）、净值 4 位；差异值带正负号 + 单位
- [ ] 日期：`YYYY-MM-DD`，走 `src/utils/date.ts` 的 `formatDate`，禁止手拼字符串；对账中心数据日期提示用格式化日期
- [ ] 间距：卡片 `--space-standard`（24px）、表格/列表 `--space-compact`（16px）
- [ ] 圆角/阴影：卡片 `--radius-md` + `--shadow-raised`；按钮 `--radius-sm` 40px 高
- [ ] 空状态：对账中心空态文案指向行动（`暂无对账差异，数据一致`），不写干瘪「暂无数据」
- [ ] 禁止：`any`/`Record<string, any>`、硬编码 hex、Emoji、`--brand-*` 直接调用（涨跌必须经 `--color-rise`/`--color-fall`）

## 8. 验证

- `cd frontend && pnpm typecheck`（tsc + vue-tsc）零错误
- `cd frontend && pnpm lint`（eslint + prettier + stylelint）
- `cd frontend && pnpm build` 构建通过
- 手动验证（dev 环境 + 后端 :8000）：上传脱敏样本 `backend/tests/fixtures/e_account_holding_sample.xlsx` → 解析 → 对账（自动归因/冲突分类）→ 处理冲突 → 对账中心可见差异与归因状态；重复导入被跳过（防复活）

## 9. 已确认决策点（2026-08-16 讨论定稿）

| 决策点 | 最终决策 |
| :--- | :--- |
| 1. 入口交互 | **方案 A**：跳过选账户，直接进入持仓流程（后端自动归因决定账户） |
| 2. 步骤数 | 3 步（上传/核对与冲突处理/结果） |
| 3. 溯源字段展示 | P0 不展示（信息密度优先），冲突行展示关键溯源（销售机构/基金管理人）辅助决策 |
| 4. 实现方式 | 独立 `useHoldingImport.ts` composable |
| 5. 对账中心 | 持仓页右上角「对账」入口，独立视图（差异列表 + 归因/忽略操作 + 数据日期提示） |
| 6. 冲突处理 | 核对步骤内联处理（归因覆盖弹窗/忽略），未处理冲突可在对账中心继续 |

## 10. 变更记录

- 2026-08-16：创建 v1（后端 PR #1021 已合入后，4 个决策点待确认）。
- 2026-08-16：v2 按最终方案重写——新增对账/归因流程（Ledger=销售平台语义、融合方案、防复活），决策点全部确认，新增对账中心视图。
