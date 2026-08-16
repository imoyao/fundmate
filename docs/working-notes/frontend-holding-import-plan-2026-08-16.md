# 前端持仓导入设计（#1013）

> 状态：**待确认**（本文档为设计稿，用户确认后实现）
> 关联：后端已合入 main-v2（PR #1021）；设计依据 `docs/working-notes/e-account-import-data-decentralization-plan-2026-08-16.md` §8；视觉规范 `frontend/design.md`（v2.3.4）。

## 1. 背景与目标

E账户（基金销售平台，如天天基金/蚂蚁）持仓快照导入。用户上传券商导出的持仓 Excel，预览确认后落库为持仓快照（`positions`），**不产生交易流水**。

后端已就绪（勿改）：

| 端点 | 说明 |
|------|------|
| `POST /api/importers/holdings/parse` | multipart `file` + query `source`（默认 `e_account_holding`）/ `ledger_id`（可选）。响应 `{data: rows[], total, error_count, duplicate_count, ledger_id, ledger_name, message}`。`ledger_id` 不传时后端自动创建/复用「基金E账户」聚合账户 |
| `POST /api/importers/holdings/confirm` | JSON `{rows: 预览行[]}`。响应 `{data: {imported, skipped, errors}, message}` |

预览行字段：`symbol, name, type, quantity, price, amount, snapshot_date, currency, account_name, ledger_id, source_broker, fund_manager, share_class, fund_account, trade_account, dividend_preference, error, import_hash, is_duplicate, source`。

## 2. 设计原则

1. **与交易导入完全并行**：持仓流程的状态、方法、组件与交易流程隔离，互不污染（后端已分轨，前端同样分轨）。
2. **遵循 `frontend/design.md`**：令牌（`--bg-card`/`--border-default`/`--radius-*`/`--space-*`）、涨红跌绿（`--color-rise`/`--color-fall`）、表格基线（`src/style/el-table.css`）、文案规范（动词+名词、错误给下一步）、数字格式（金额/份额 2 位、千分位、`tabular-nums`）、日期 `YYYY-MM-DD`（`src/utils/date.ts` 的 `formatDate`）。
3. **复用现有向导骨架**：上传/预览/结果三步的交互范式沿用现有 `UploadStep`/`PreviewStep`/`ResultStep`，不另起炉灶。
4. **禁止**：`any`/`Record<string, any>` 作 API 类型、硬编码 hex 色值、Emoji、页面内 `:deep(.el-table)` 覆盖视觉基线。

## 3. 入口设计

**位置**：`ImportModeCards.vue` 现有三张卡片（手动批量录入 / AI 截图识别 / 录入负债应收款）旁新增第四张「**导入持仓快照**」。

**交互决策（待确认）**：

- **方案 A（推荐）**：卡片点击后**跳过选账户步骤**，直接进入持仓导入流程（上传 → 预览 → 结果）。理由：持仓导入的账户由后端自动创建/复用「基金E账户」聚合账户，前端强制选账户与后端语义冲突；且现有卡片区在「选账户」步骤内，持仓卡片点击后需跳出该步骤。
- 方案 B：保留选账户步骤，账户可选（不选则后端自动创建）。交互更重，与后端「自动聚合」语义重叠，不推荐。

**卡片文案**（遵循 design.md 文案规范，动词+名词、克制）：

- 标题：`导入持仓快照`
- 描述：`上传基金平台导出的持仓文件，一键同步当前持仓`
- 图标：`ep:document` 或 `ep:files`（与现有卡片图标风格一致，`IconifyIconOffline`）

## 4. 流程设计

持仓导入为 **3 步**（无选账户步骤）：

```
步骤 1 上传持仓文件 → 步骤 2 预览与核对 → 步骤 3 导入完成
```

### 4.1 步骤 1：上传

- 复用 `UploadArea` 交互（拖拽/点击上传），文件类型限制 `xls/xlsx`（后端仅支持 Excel）。
- 上传后调 `parseHoldingFile(file)`。
- 解析成功后展示后端返回的聚合账户信息（`ledger_name`，如「基金E账户」），提示「持仓将归入该账户」。
- 错误处理：`error_count > 0` 时提示「解析完成，N 条记录无法识别」，仍可进入预览查看错误行。

### 4.2 步骤 2：预览与核对

- 表格列（与交易预览不同，独立列配置）：

| 列 | 字段 | 说明 |
|----|------|------|
| 基金名称 | `name` | 首列，`fixed` 冻结（design.md 表格规范） |
| 基金代码 | `symbol` | 等宽数字 |
| 持有份额 | `quantity` | 2 位小数，`tabular-nums` |
| 最新净值 | `price` | 4 位小数（净值精度） |
| 持仓市值 | `amount` | 金额 2 位，千分位 |
| 快照日期 | `snapshot_date` | `formatDate` 格式化 |
| 币种 | `currency` | — |
| 状态 | `error` / `is_duplicate` | 错误行标红（`--color-danger-system`）、重复行标记「已存在」 |

- 错误行/重复行默认不勾选（沿用现有 `selectedKeys` 选择机制），用户可手动勾选。
- 溯源字段（`fund_manager`/`share_class`/`fund_account`/`trade_account`/`dividend_preference`/`source_broker`）**不在表格展示**（信息密度优先），可在行 hover 或详情提示中展示（可选，P0 不做）。

### 4.3 步骤 3：结果

- 复用 `ResultStep` 范式：`导入完成（N 条记录）`、跳过数、错误明细（`errors` 列表展示 symbol/name/error）。
- 成功提示遵循 design.md：`持仓已同步（12 条记录）`。

## 5. 状态隔离（关键设计）

**新建独立 composable `useHoldingImport.ts`**，与 `useImportWizard.ts` 平行，不修改交易流程任何状态：

```
frontend/src/views/asset/investment/import/composables/useHoldingImport.ts
```

- 状态：`holdingStep`（0/1/2）、`holdingPreviewRows`、`holdingSelectedKeys`、`holdingDuplicateCount`、`holdingErrorCount`、`holdingImportedCount`、`holdingSkippedCount`、`holdingErrors`、`holdingLedgerName`、`holdingParsing`、`holdingImporting`。
- 方法：`handleHoldingUpload(file)`、`confirmHoldingImport()`、`resetHoldingImport()`。
- 上下文：沿用 provide/inject 模式，`useImportWizardContext.ts` 增加 `provideHoldingWizard`/`useHoldingImportContext`（或独立 InjectionKey），与交易上下文并存。

**理由**：`useImportWizard.ts` 已 1968 行，交易流程状态（`previewData`/`selectedKeys`/`currentStep` 等）与持仓语义不同（持仓无 `op_type`/`fee`/`allocation` 等），混入会互相污染；独立 composable 使持仓流程可独立演进、独立测试。

## 6. 组件改动清单

| 文件 | 改动 |
|------|------|
| `src/api/importer.ts` | 新增 `parseHoldingFile(file, source?)`、`confirmHoldings(rows)`（风格对齐现有 `parseFile`/`confirmImport`） |
| `src/api/types.d.ts` | 新增 `HoldingPreviewRow`、`HoldingImportResult` 类型（**禁止 any**） |
| `components/ImportModeCards.vue` | 新增第四张卡片「导入持仓快照」，点击进入持仓流程 |
| `composables/useHoldingImport.ts` | **新建**：持仓流程状态与方法（见 §5） |
| `composables/useImportWizardContext.ts` | 新增持仓上下文 provide/inject |
| `components/HoldingUploadStep.vue` | **新建**：上传步骤（复用 `UploadArea` 交互） |
| `components/HoldingPreviewStep.vue` | **新建**：预览表格（独立列配置） |
| `components/HoldingResultStep.vue` | **新建**：结果步骤（复用 `ResultStep` 范式） |
| `index.vue` | 模式切换：持仓模式渲染持仓三步组件；`el-steps` 标题按模式切换（交易 4 步 / 持仓 3 步） |

**不改动**：`useImportWizard.ts`（交易逻辑）、`UploadStep`/`PreviewStep`/`ResultStep`（交易组件）、`LedgerSelectStep`（选账户步骤，持仓跳过）。

## 7. 设计规范遵循清单（design.md 逐条对照）

- [ ] 表格：直接用 `<el-table>` 继承 `src/style/el-table.css` 基线，行高 44px，**禁止页面内 `:deep(.el-table)` 覆盖**；首列「名称+代码」`fixed` 冻结（180-220px）；数值列 `tabular-nums` 纵向对齐
- [ ] 涨跌色：持仓市值/盈亏走 `--color-rise`/`--color-fall`；错误行用 `--color-danger-system`（危险色只留给错误/破坏性操作）
- [ ] 文案：标题/按钮动词+名词（`导入持仓快照`、`同步持仓`），禁用 `确定`/`OK`；错误提示描述问题+下一步；成功直接陈述结果；进行中动词+省略号（`导入中…`）
- [ ] 数字：金额 2 位千分位（`¥12,345.67`）、份额 2 位（`1,234.56 份`）、净值 4 位；`font-variant-numeric: tabular-nums`
- [ ] 日期：`YYYY-MM-DD`，走 `src/utils/date.ts` 的 `formatDate`，禁止手拼字符串
- [ ] 间距：卡片 `--space-standard`（24px）、表格/列表 `--space-compact`（16px）
- [ ] 圆角/阴影：卡片 `--radius-md` + `--shadow-raised`；按钮 `--radius-sm` 40px 高
- [ ] 空状态：上传区空态文案指向行动（`上传基金平台导出的持仓文件`），不写干瘪「暂无数据」
- [ ] 禁止：`any`/`Record<string, any>`、硬编码 hex、Emoji、`--brand-*` 直接调用（涨跌必须经 `--color-rise`/`--color-fall`）

## 8. 验证

- `cd frontend && pnpm typecheck`（tsc + vue-tsc）零错误
- `cd frontend && pnpm lint`（eslint + prettier + stylelint）
- `cd frontend && pnpm build` 构建通过
- 手动验证（dev 环境 + 后端 :8000）：上传脱敏样本 `backend/tests/fixtures/e_account_holding_sample.xlsx` → 预览 → 确认 → 持仓页可见；重复导入被标记跳过

## 9. 待确认决策点

1. **入口交互**：方案 A（跳过选账户，推荐）vs 方案 B（保留选账户可选）
2. **步骤数**：3 步（上传/预览/结果，推荐）vs 复用 4 步向导
3. **预览表格**：溯源字段（基金管理人/份额类别/分红方式等）P0 不展示，仅错误/重复标记——是否可接受
4. **实现方式**：独立 `useHoldingImport.ts` composable（推荐）vs 并入 `useImportWizard.ts`

## 10. 变更记录

- 2026-08-16：创建设计文档（后端 PR #1021 已合入后）。
