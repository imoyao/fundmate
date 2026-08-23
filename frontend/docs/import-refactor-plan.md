# Import 域拆分方案梳理（#984 第三役 · 前置调研）

> 状态：调研文档，未改动任何代码。
> 范围：仅梳理 `frontend/src/views/asset/investment/import`、`eaccount-import` 与
> `components/QuickEntry/OcrImportModal.vue` 三个 import 入口的组件树、耦合点与候选拆分方向。
> 前置条件：#1018（AI 持仓识别误建交易流水）**已合入**（后端 `dd92936` + 前端 `f11c775`），
> `holding_import` 场景与持仓汇点确认接口已落地，本文基于此现状撰写。

---

## 1. 现状组件树（三大 import 域）

### 1.1 交易导入向导（`investment/import/`）— 最厚重

```
investment/import/index.vue
├─ ImportModeCards.vue              // 入口卡片（上传/AI/手动/模板）
├─ components/LedgerSelectStep.vue  // 第1步 选账户（含 ledgerId 状态）
├─ components/UploadStep.vue        // 第2步 文件上传解析
├─ components/PreviewStep.vue       // 第3步 交易预览+编辑+冲突
├─ components/ResultStep.vue        // 第4步 结果
├─ components/AiImportModal.vue     // 【AI·交易】txn_import，确认→/api/importers/confirm
└─ composables/
   ├─ useImportWizard.ts            // ★ ~1980 行，所有交易状态+AI txn 行集中于此
   └─ useImportWizardContext.ts     // provide/inject 跨步骤共享
```

### 1.2 持仓导入（`investment/eaccount-import/index.vue`）— #1018 已加 AI 入口

```
eaccount-import/index.vue
├─ 上传文件（param+净额双模式） → parseHoldings → reconcileEaccount（reconcile_holdings，无流水）
├─ ★ AI 识别持仓（本期新增）：holding_import → previewRows → 同一条 reconcile 流程
└─ 预览表格 + 手动编辑 + 冲突对账 + 一键归因
```

### 1.3 自选导入（`components/QuickEntry/OcrImportModal.vue`）— 轻量

```
OcrImportModal.vue
├─ watchlist_import（默认） → 候选勾选 → createWatchlistItem
└─ 文本/图片两种识别，独立 usage 三态展示
```

---

## 2. 三个 AI 入口的现状对比（#1018 后的关键耦合点）

| 维度 | 自选 OcrImportModal | 交易 AiImportModal | 持仓 eaccount-import（AI） |
|---|---|---|---|
| 场景 key | `watchlist_import` | `txn_import` | `holding_import` |
| 识别 API | `recognizeImage/parseImportText` | 同左 | 同左 |
| 返回结构 | `items[]`（候选列表） | `rows[]`（OcrTxnRow） | `rows[]`（OcrHoldingRow） |
| 确认接口 | `createWatchlistItem` | `/api/importers/confirm` | `/api/e-account/reconcile/`（reconcile_holdings） |
| usage feature | `watchlist_import` | `txn_import` | `holding_import` |
| UI 骨架 | 文本/图片 tab + 候选勾选 | 文本/图片 tab + 行预览 | 文本/图片 tab + 行预览 |

**重复实现点（拆分价值所在）**：
- 文本/图片双 tab + `FileReader→base64` 转换 + usage 三态横幅：**三处各写一份**，结构高度雷同。
- `canRecognize` / `fileToBase64` / usage 状态机：**逻辑重复**。
- 行预览表格（`OcrTxnRow` / `OcrHoldingRow`）：字段近义但类型不统一，无法共用组件。

---

## 3. 主要耦合/设计债

1. **`useImportWizard.ts` 单一巨型 composable（~1980 行）**：持有全部交易状态 +
   所有步骤动作 + AI txn 行回填（`onAiRowsFound`）。步骤组件经 `useImportWizardContext`
   注入同一切片，**任一步骤改动都牵动整文件**，是 #984 第三役最可能的首要拆分对象。
2. **三个 AI 导入 UI 三份拷贝**：同一套「图片/文本识别 + 额度显示」被复制三次，
   新增场景（如未来基金分红识别）需再复制一遍。
3. **行类型未归一**：`OcrTxnRow` / `OcrHoldingRow` / `HoldingParseRow` 三套近义结构，
   预览表格无法复用，且 `holding_import` 后端 `source=ai_holding` 与文件通道
   `source=eaccount` 在确认口径上需前端显式区分（当前持仓走 reconcile，交易走 confirm）。
4. **确认落库路径分歧是刻意保留的**（#1018 根因）：持仓/自选 **绝不** 经过交易管线，
   因此"统一弹窗"必须按 scenario 分派确认动作，不能盲目合并。

---

## 4. 候选拆分方向（A / B / C，待 #1018 合入后拍板）

### A. 统一 AI 导入弹窗（收敛三份拷贝）
- 抽出 `OcrImportModal` 通用骨架（图片/文本 tab + base64 + usage 横幅 + 识别调用），
  由 `scenario` prop 驱动：`watchlist_import` / `txn_import` / `holding_import`。
- 确认动作按 scenario 分派：
  - watchlist → `createWatchlistItem`
  - txn → `POST /api/importers/confirm`
  - holding → 复用 `eaccount-import` 的 `reconcileEaccount`（或抽出 `commitHoldings` 前端封装）
- 收益：消除三份 UI 拷贝，新增场景零成本。
- 风险：持仓确认走 `reconcile` 而非 `confirm`，需保证场景分派不串；交易向导的
  `onAiRowsFound` 回填逻辑要保留（props 回调而非内部消化）。

### B. 继续拆交易向导（治理 `useImportWizard` 巨型文件）
- 把 `useImportWizard` 按职责拆子 composable：`useLedgerSelect` / `useUploadParse` /
  `usePreviewEdit` / `useAiTxnRows`，`index.vue` 组合后 `provide` 聚合 ctx。
- 收益：单一文件从 ~1980 行降到可读单元，步骤改动局部化。
- 风险：涉及 provide/inject 契约调整，需配回归测试。

### C. 抽公共 WizardShell（路由层级）
- 抽出 `investment` 下交易/持仓两条导入路由共享的向导壳（步骤条 + 布局 + 账户选择），
  各自只填"解析源"与"确认动作"插槽。
- 收益：交易/持仓结构对称、视觉一致。
- 风险：两条域确认语义差异大（reconcile vs confirm），插槽契约设计成本高。

---

## 5. 建议落地顺序（供拍板参考）
1. 先做 **A**（ROI 最高、直接复用 #1018 的 `holding_import`，且消除当前三份拷贝）。
2. A 稳定后做 **B**（治理巨型 composable，降低后续维护风险）。
3. **C** 视 A/B 结果决定是否必要（若 A 已统一 AI 入口、B 已瘦身向导，C 收益递减）。

> 本文档仅调研，不改动代码。具体选 A/B/C 待评审确认后再进入实现。
